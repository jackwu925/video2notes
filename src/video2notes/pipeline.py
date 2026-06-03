import argparse
import copy
from dataclasses import dataclass
from pathlib import Path

from video2notes import downloader as downloader_module
from video2notes.downloader import (
    download_audio,
    expected_audio_path,
    expand_playlist_urls,
    load_video_metadata,
    save_metadata,
    video_key,
)
from video2notes.exports import export_summary_artifacts
from video2notes.paths import display_path, user_path
from video2notes.llm import (
    DEFAULT_ANALYSIS_LANGUAGE,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL as DEFAULT_LLM_MODEL,
    DEFAULT_TASK,
    DEFAULT_TIMEOUT_SECONDS,
    LLMConfig,
    analyze_subtitles,
)
from video2notes.transcriber import (
    DEFAULT_DEVICE,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_TRANSCRIPTION_TIMEOUT,
    transcribe_audio,
)


DEFAULT_AUDIO_DIR = Path("data/audio")
DEFAULT_METADATA_DIR = Path("data/metadata")
DEFAULT_SUBTITLES_DIR = Path("data/subtitles")
DEFAULT_SUMMARIES_DIR = Path("data/summaries")
DEFAULT_SUBTITLE_FORMAT = "srt"
DEFAULT_YT_DLP_SOCKET_TIMEOUT = int(getattr(downloader_module, "DEFAULT_YT_DLP_SOCKET_TIMEOUT", 30))
DEFAULT_YT_DLP_RETRIES = int(getattr(downloader_module, "DEFAULT_YT_DLP_RETRIES", 2))
DEFAULT_METADATA_TIMEOUT = int(getattr(downloader_module, "DEFAULT_METADATA_TIMEOUT", 120))
DEFAULT_DOWNLOAD_TIMEOUT = int(getattr(downloader_module, "DEFAULT_DOWNLOAD_TIMEOUT", 1800))


@dataclass(frozen=True)
class PipelineResult:
    metadata_path: Path
    audio_path: Path
    subtitle_path: Path
    summary_path: Path | None
    artifact_paths: dict[str, Path]


def save_summary(summary: str, output_dir: Path, key: str) -> Path:
    output_dir = user_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{key}.md"
    summary_path.write_text(summary, encoding="utf-8")
    return summary_path


def expected_subtitle_path(audio_path: Path, output_dir: Path, subtitle_format: str) -> Path:
    return user_path(output_dir) / f"{audio_path.stem}.{subtitle_format}"


def expected_metadata_subtitle_path(metadata: dict[str, object], output_dir: Path, subtitle_format: str) -> Path:
    return user_path(output_dir) / f"{video_key(metadata)}.{subtitle_format}"


def normalize_generated_subtitle_path(generated_path: Path, target_path: Path) -> Path:
    generated_path = user_path(generated_path)
    target_path = user_path(target_path)
    if generated_path == target_path or not generated_path.exists():
        return generated_path

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.unlink()
    generated_path.replace(target_path)
    return target_path


def local_media_metadata(media_path: Path) -> dict[str, object]:
    path = user_path(media_path)
    if not path.exists():
        raise FileNotFoundError(f"Local media file does not exist: {display_path(path)}")
    if not path.is_file():
        raise ValueError(f"Local media path is not a file: {display_path(path)}")

    return {
        "id": video_key({"id": path.stem}),
        "title": path.stem,
        "media_path": display_path(path),
        "webpage_url": display_path(path),
        "original_url": display_path(path),
        "source": "Local file",
        "extractor": "local",
    }


def emit_progress(args: argparse.Namespace, stage: str, message: str) -> None:
    callback = getattr(args, "progress_callback", None)
    if callback:
        callback(stage, message)


def resolve_llm_config(args: argparse.Namespace) -> LLMConfig:
    runtime_config = getattr(args, "llm_config", None)
    if runtime_config is not None:
        return runtime_config

    api_key = getattr(args, "llm_api_key", None)
    if api_key is not None:
        return LLMConfig(
            api_key=api_key,
            base_url=getattr(args, "llm_base_url", None) or DEFAULT_BASE_URL,
            model=getattr(args, "llm_model", None) or DEFAULT_LLM_MODEL,
            timeout_seconds=int(getattr(args, "llm_timeout_seconds", None) or DEFAULT_TIMEOUT_SECONDS),
        )

    return LLMConfig.from_env()


def run_many(args: argparse.Namespace) -> list[PipelineResult]:
    if getattr(args, "media_file", None):
        print(f"\n[1/1] Processing local media: {display_path(args.media_file)}")
        emit_progress(args, "item_start", f"[1/1] Processing local media {display_path(args.media_file)}")
        result = run_pipeline(args)
        emit_progress(args, "item_done", f"[1/1] Completed local media {display_path(args.media_file)}")
        return [result]

    urls = collect_urls(args)
    if not urls:
        raise ValueError("No URL provided. Pass a URL argument or use --url-file.")

    results = []
    for index, url in enumerate(urls, start=1):
        print(f"\n[{index}/{len(urls)}] Processing video: {url}")
        emit_progress(args, "item_start", f"[{index}/{len(urls)}] Processing {url}")
        item_args = copy.copy(args)
        item_args.url = url
        result = run_pipeline(item_args)
        results.append(result)
        emit_progress(args, "item_done", f"[{index}/{len(urls)}] Completed {url}")
    return results


def collect_urls(args: argparse.Namespace) -> list[str]:
    raw_cookies = getattr(args, "cookies", None)
    cookies = user_path(raw_cookies) if raw_cookies else None
    yt_dlp_socket_timeout = int(getattr(args, "yt_dlp_socket_timeout", DEFAULT_YT_DLP_SOCKET_TIMEOUT))
    yt_dlp_retries = int(getattr(args, "yt_dlp_retries", DEFAULT_YT_DLP_RETRIES))
    metadata_timeout = int(getattr(args, "metadata_timeout", DEFAULT_METADATA_TIMEOUT))
    urls = []

    if args.url:
        urls.append(args.url)

    url_text = getattr(args, "url_text", None)
    if url_text:
        text_urls = [
            line.strip()
            for line in url_text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        urls.extend(text_urls)

    if args.url_file:
        file_urls = [
            line.strip()
            for line in user_path(args.url_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        urls.extend(file_urls)

    if args.playlist:
        expanded_urls = []
        for url in urls:
            expanded_urls.extend(
                expand_playlist_urls(
                    url,
                    cookies=cookies,
                    socket_timeout=yt_dlp_socket_timeout,
                    retries=yt_dlp_retries,
                    timeout=metadata_timeout,
                )
            )
        urls = expanded_urls

    return list(dict.fromkeys(urls))


def run_pipeline(args: argparse.Namespace) -> PipelineResult:
    raw_cookies = getattr(args, "cookies", None)
    cookies = user_path(raw_cookies) if raw_cookies else None
    yt_dlp_socket_timeout = int(getattr(args, "yt_dlp_socket_timeout", DEFAULT_YT_DLP_SOCKET_TIMEOUT))
    yt_dlp_retries = int(getattr(args, "yt_dlp_retries", DEFAULT_YT_DLP_RETRIES))
    metadata_timeout = int(getattr(args, "metadata_timeout", DEFAULT_METADATA_TIMEOUT))
    download_timeout = int(getattr(args, "download_timeout", DEFAULT_DOWNLOAD_TIMEOUT))
    transcription_timeout = int(getattr(args, "transcription_timeout", DEFAULT_TRANSCRIPTION_TIMEOUT))
    reuse_audio = args.reuse_existing or args.reuse_audio
    reuse_subtitle = args.reuse_existing or args.reuse_subtitle
    reuse_summary = args.reuse_existing or args.reuse_summary
    if args.force:
        reuse_audio = False
        reuse_subtitle = False
        reuse_summary = False

    media_file = getattr(args, "media_file", None)
    if media_file:
        print("Using local media file...")
        emit_progress(args, "media_start", "Using local media file...")
        audio_path = user_path(media_file)
        metadata = local_media_metadata(audio_path)
        metadata_path = save_metadata(metadata, args.metadata_dir)
        print(f"Metadata saved: {display_path(metadata_path)}")
        emit_progress(args, "metadata_done", f"Metadata saved: {display_path(metadata_path)}")
        print(f"Audio ready: {display_path(audio_path)}")
        emit_progress(args, "audio_done", f"Local media ready: {display_path(audio_path)}")
    else:
        print("Reading video metadata...")
        emit_progress(args, "metadata_start", "Reading video metadata...")
        metadata = load_video_metadata(
            args.url,
            cookies=cookies,
            socket_timeout=yt_dlp_socket_timeout,
            retries=yt_dlp_retries,
            timeout=metadata_timeout,
        )
        metadata_path = save_metadata(metadata, args.metadata_dir)
        print(f"Metadata saved: {display_path(metadata_path)}")
        emit_progress(args, "metadata_done", f"Metadata saved: {display_path(metadata_path)}")

        print("Downloading and extracting audio...")
        emit_progress(args, "audio_start", "Downloading and extracting audio...")
        cached_audio_path = expected_audio_path(metadata, args.audio_dir)
        if reuse_audio and cached_audio_path.exists():
            audio_path = cached_audio_path
            print(f"Reusing existing audio: {display_path(audio_path)}")
            emit_progress(args, "audio_cached", f"Reusing audio: {display_path(audio_path)}")
        else:
            audio_path = download_audio(
                args.url,
                metadata,
                args.audio_dir,
                cookies=cookies,
                socket_timeout=yt_dlp_socket_timeout,
                retries=yt_dlp_retries,
                timeout=download_timeout,
            )
        print(f"Audio ready: {display_path(audio_path)}")
        emit_progress(args, "audio_done", f"Audio ready: {display_path(audio_path)}")

    print("Transcribing subtitles...")
    emit_progress(args, "subtitle_start", "Transcribing subtitles with Whisper...")
    cached_subtitle_path = expected_metadata_subtitle_path(metadata, args.subtitles_dir, args.subtitle_format)
    if reuse_subtitle and cached_subtitle_path.exists():
        subtitle_path = cached_subtitle_path
        print(f"Reusing existing subtitles: {display_path(subtitle_path)}")
        emit_progress(args, "subtitle_cached", f"Reusing subtitles: {display_path(subtitle_path)}")
    else:
        generated_subtitle_path = transcribe_audio(
            audio_path=audio_path,
            output_dir=args.subtitles_dir,
            model=args.whisper_model,
            language=args.language or None,
            output_format=args.subtitle_format,
            device=args.device,
            timeout=transcription_timeout,
        )
        subtitle_path = normalize_generated_subtitle_path(generated_subtitle_path, cached_subtitle_path)
    print(f"Subtitles saved: {display_path(subtitle_path)}")
    emit_progress(args, "subtitle_done", f"Subtitles ready: {display_path(subtitle_path)}")

    summary_path = None
    artifact_paths: dict[str, Path] = {}
    if args.skip_llm:
        print("LLM analysis skipped by request.")
        emit_progress(args, "llm_skipped", "Skipped LLM analysis.")
    else:
        llm_config = resolve_llm_config(args)
        if not llm_config.is_configured:
            message = "LLM_API_KEY is not configured; skipping LLM analysis. Configure the UI or create a .env file."
            if args.require_llm:
                raise RuntimeError(message)
            print(message)
            emit_progress(args, "llm_skipped", message)
        else:
            summary_path = user_path(args.summaries_dir) / f"{video_key(metadata)}.md"
            if reuse_summary and summary_path.exists():
                summary = summary_path.read_text(encoding="utf-8")
                print(f"Reusing existing LLM analysis: {display_path(summary_path)}")
                emit_progress(args, "llm_cached", f"Reusing summary: {display_path(summary_path)}")
            else:
                print("Analyzing subtitles with the LLM...")
                emit_progress(args, "llm_start", "Analyzing subtitles with the LLM...")
                transcript = subtitle_path.read_text(encoding="utf-8")
                summary = analyze_subtitles(llm_config, transcript, args.llm_task, args.analysis_language)
                summary_path = save_summary(summary, args.summaries_dir, video_key(metadata))
            print(f"LLM analysis saved: {display_path(summary_path)}")
            emit_progress(args, "llm_done", f"Summary saved: {display_path(summary_path)}")
            if args.export_artifacts:
                artifact_paths = export_summary_artifacts(summary, args.summaries_dir, video_key(metadata))
                for artifact_name, artifact_path in artifact_paths.items():
                    print(f"Exported {artifact_name}: {display_path(artifact_path)}")
                if artifact_paths:
                    emit_progress(args, "artifacts_done", "Study artifacts exported.")

    return PipelineResult(
        metadata_path=metadata_path,
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        summary_path=summary_path,
        artifact_paths=artifact_paths,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a video, transcribe it, and save local artifacts.")
    parser.add_argument("url", nargs="?", help="Video URL.")
    parser.add_argument("--url-file", type=Path, help="Text file containing one video URL per line.")
    parser.add_argument("--url-text", default="", help="Newline-separated video URLs. Useful for UI integrations.")
    parser.add_argument("--media-file", default=None, type=Path, help="Local audio or video file to transcribe.")
    parser.add_argument("--playlist", action="store_true", help="Expand playlist entries before processing.")
    parser.add_argument("--audio-dir", default=DEFAULT_AUDIO_DIR, type=Path)
    parser.add_argument("--metadata-dir", default=DEFAULT_METADATA_DIR, type=Path)
    parser.add_argument("--subtitles-dir", default=DEFAULT_SUBTITLES_DIR, type=Path)
    parser.add_argument("--summaries-dir", default=DEFAULT_SUMMARIES_DIR, type=Path)
    parser.add_argument("--cookies", default=None, type=Path, help="Optional cookies.txt path for yt-dlp.")
    parser.add_argument(
        "--yt-dlp-socket-timeout",
        default=DEFAULT_YT_DLP_SOCKET_TIMEOUT,
        type=int,
        help="yt-dlp network socket timeout in seconds.",
    )
    parser.add_argument(
        "--yt-dlp-retries",
        default=DEFAULT_YT_DLP_RETRIES,
        type=int,
        help="yt-dlp retry count for network and fragment failures.",
    )
    parser.add_argument(
        "--metadata-timeout",
        default=DEFAULT_METADATA_TIMEOUT,
        type=int,
        help="Maximum time in seconds for reading video metadata.",
    )
    parser.add_argument(
        "--download-timeout",
        default=DEFAULT_DOWNLOAD_TIMEOUT,
        type=int,
        help="Maximum time in seconds for downloading and extracting audio.",
    )
    parser.add_argument("--whisper-model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help=(
            "Speech recognition language hint for the original audio, for example Chinese, English, en, or zh. "
            "Use auto to let Whisper detect it. This does not translate audio."
        ),
    )
    parser.add_argument(
        "--subtitle-format",
        default=DEFAULT_SUBTITLE_FORMAT,
        choices=("txt", "vtt", "srt", "tsv", "json"),
        help="Subtitle format generated by Whisper. srt keeps timestamps for better LLM analysis.",
    )
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help="Torch device for Whisper: auto, cpu, or cuda. auto uses CUDA when PyTorch can see a GPU.",
    )
    parser.add_argument(
        "--transcription-timeout",
        default=DEFAULT_TRANSCRIPTION_TIMEOUT,
        type=int,
        help="Maximum Whisper transcription time in seconds. Use 0 to disable the limit.",
    )
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse cached audio, subtitles, and summaries.")
    parser.add_argument("--reuse-audio", action="store_true", help="Reuse existing audio if present.")
    parser.add_argument("--reuse-subtitle", action="store_true", help="Reuse existing subtitle if present.")
    parser.add_argument("--reuse-summary", action="store_true", help="Reuse existing LLM summary if present.")
    parser.add_argument("--force", action="store_true", help="Ignore cached artifacts and regenerate everything.")
    parser.add_argument("--skip-llm", action="store_true", help="Skip subtitle analysis with the LLM API.")
    parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Fail if LLM_API_KEY is not configured instead of skipping analysis.",
    )
    parser.add_argument("--llm-task", default=DEFAULT_TASK, help="Instruction for subtitle analysis.")
    parser.add_argument(
        "--analysis-language",
        default=DEFAULT_ANALYSIS_LANGUAGE,
        help="Notes output language for LLM analysis: Chinese, English, or auto. auto follows the transcript.",
    )
    parser.add_argument(
        "--export-artifacts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Export chapters, key points, concepts, takeaways, and timeline artifacts from the LLM summary.",
    )
    return parser


def main() -> None:
    run_many(build_parser().parse_args())
