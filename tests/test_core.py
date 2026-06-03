import os
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


sys.path.insert(0, "src")

from video2notes.downloader import expected_audio_path, video_key
from video2notes.exports import export_summary_artifacts, extract_timeline, split_markdown_sections
from video2notes.llm import (
    DEFAULT_TASK,
    LLMConfig,
    analysis_language_instruction,
    chunk_text,
    final_analysis_prompt,
    get_provider_preset,
    load_env_file,
)
from video2notes.pipeline import collect_urls, expected_subtitle_path, local_media_metadata, resolve_llm_config
from video2notes.transcriber import normalize_language, resolve_device
from video2notes.ui import (
    build_pipeline_command,
    fallback_video_title,
    find_available_port,
    pipeline_progress_state,
    preview_key,
    read_pipeline_log,
    sanitize_log_file,
    read_text_preview,
    media_kind_from_source,
    source_label_from_url,
    stop_pipeline_process,
    streamlit_script_target,
    summary_path_from_pipeline_log,
    transcript_rows_from_text,
    video_embed_url,
    video_preview_details,
    video_id_from_url,
)


def test_video_key_prefers_sanitized_title() -> None:
    assert video_key({"id": "BV1Pa4y1v7Uk", "title": "Some Title"}) == "Some_Title"


def test_video_key_sanitizes_title() -> None:
    assert video_key({"title": "hello/world:video？ 第 1 集"}) == "hello_world_video_第_1_集"


def test_video_key_fallback() -> None:
    assert video_key({}) == "video"


def test_chunk_text_splits_by_max_chars() -> None:
    assert list(chunk_text("abcdef", max_chars=2)) == ["ab", "cd", "ef"]


def test_load_env_file_does_not_override_existing_env(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=from_file\nLLM_API_KEY='abc'\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "from_env")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    load_env_file(env_file)

    assert os.environ["LLM_MODEL"] == "from_env"
    assert os.environ["LLM_API_KEY"] == "abc"


def test_resolve_llm_config_prefers_runtime_config() -> None:
    runtime_config = LLMConfig(
        api_key="manual-key",
        base_url="https://example.com/v1",
        model="manual-model",
        timeout_seconds=30,
    )
    args = argparse.Namespace(llm_config=runtime_config)
    assert resolve_llm_config(args) is runtime_config


def test_resolve_llm_config_accepts_runtime_fields() -> None:
    args = argparse.Namespace(
        llm_api_key="manual-key",
        llm_base_url="https://example.com/v1",
        llm_model="manual-model",
        llm_timeout_seconds=30,
    )
    config = resolve_llm_config(args)

    assert config.api_key == "manual-key"
    assert config.base_url == "https://example.com/v1"
    assert config.model == "manual-model"
    assert config.timeout_seconds == 30


def test_provider_preset_supports_local_provider_without_api_key() -> None:
    preset = get_provider_preset("Ollama")
    assert preset["base_url"] == "http://127.0.0.1:11434/v1"
    assert preset["requires_api_key"] is False


def test_resolve_device_pass_through() -> None:
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("cuda") == "cuda"
    assert resolve_device(None) is None


def test_find_available_port_returns_first_free_port(monkeypatch) -> None:
    attempts = []

    class FakeSocket:
        def __enter__(self) -> "FakeSocket":
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def bind(self, address: tuple[str, int]) -> None:
            attempts.append(address[1])
            if address[1] == 8501:
                raise OSError("port busy")

    monkeypatch.setattr("video2notes.ui.socket.socket", lambda *args, **kwargs: FakeSocket())

    assert find_available_port(start=8501, end=8502) == 8502
    assert attempts == [8501, 8502]


def test_read_text_preview_truncates(tmp_path) -> None:
    path = tmp_path / "sample.srt"
    path.write_text("abcdef", encoding="utf-8")
    assert read_text_preview(path, max_chars=3) == "abc\n\n... preview truncated ..."


def test_read_pipeline_log_hides_project_root(tmp_path) -> None:
    path = tmp_path / "log.txt"
    path.write_text(f"File {Path.cwd().as_posix()}/src/video2notes/ui.py failed", encoding="utf-8")
    assert Path.cwd().as_posix() not in read_pipeline_log(path.as_posix())
    assert "src/video2notes/ui.py" in read_pipeline_log(path.as_posix())


def test_summary_path_from_pipeline_log_prefers_saved_summary(tmp_path) -> None:
    summary_path = tmp_path / "Demo_Video.md"
    summary_path.write_text("# Demo", encoding="utf-8")

    assert summary_path_from_pipeline_log(f"LLM analysis saved: {summary_path.as_posix()}") == summary_path


def test_pipeline_progress_state_tracks_running_stage() -> None:
    state = pipeline_progress_state(
        "https://www.youtube.com/watch?v=progress-test-missing",
        "Downloading and extracting audio...\nAudio ready:\nTranscribing subtitles with Whisper...",
        running=True,
        skip_llm=False,
        completed=False,
    )

    assert state["stages"]["audio"] == "done"
    assert state["stages"]["subtitles"] == "running"
    assert state["stages"]["summary"] == "waiting"
    assert state["current_stage"] == "subtitles"


def test_sanitize_log_file_rewrites_project_root(tmp_path) -> None:
    path = tmp_path / "log.txt"
    path.write_text(f"File {Path.cwd().as_posix()}/src/video2notes/ui.py failed", encoding="utf-8")
    sanitize_log_file(path)
    text = path.read_text(encoding="utf-8")
    assert Path.cwd().as_posix() not in text
    assert "src/video2notes/ui.py" in text


def test_streamlit_script_target_is_relative() -> None:
    script_target, cwd = streamlit_script_target()
    assert script_target == "src/video2notes/ui.py"
    assert not script_target.startswith("/")
    assert cwd.name == "video2notes"


def test_preview_key_is_stable_and_distinguishes_context(tmp_path) -> None:
    path = tmp_path / "sample.srt"
    assert preview_key("Subtitle preview", path) == preview_key("Subtitle preview", path)
    assert preview_key("Subtitle preview", path) != preview_key("files", path)


def test_video_preview_derives_youtube_identity_from_url() -> None:
    url = "https://www.youtube.com/watch?v=gmz7eOB-tCg"

    assert source_label_from_url(url) == "YouTube"
    assert video_id_from_url(url) == "gmz7eOB-tCg"
    assert video_embed_url(url) == "https://www.youtube.com/embed/gmz7eOB-tCg"
    assert fallback_video_title(url, "en") == "YouTube video gmz7eOB-tCg"


def test_video_preview_derives_bilibili_identity_from_url() -> None:
    url = "https://www.bilibili.com/video/BV1Pa4y1v7Uk/?share_source=copy_web"

    assert source_label_from_url(url) == "Bilibili"
    assert video_id_from_url(url) == "BV1Pa4y1v7Uk"
    assert video_embed_url(url) == (
        "https://player.bilibili.com/player.html?autoplay=0&bvid=BV1Pa4y1v7Uk"
    )
    assert fallback_video_title(url, "en") == "Bilibili video BV1Pa4y1v7Uk"


def test_video_preview_accepts_local_media_path() -> None:
    details = video_preview_details("data/imports/demo.mp4", "en")

    assert details["title"] == "demo.mp4"
    assert details["source"] == "Local file"


def test_media_kind_from_source_detects_direct_media() -> None:
    assert media_kind_from_source("data/imports/demo.mp4") == "video"
    assert media_kind_from_source("https://example.com/audio.mp3?token=abc") == "audio"
    assert media_kind_from_source("https://example.com/watch?v=abc") == ""


def test_transcript_rows_from_text_accepts_whisper_log_segments() -> None:
    rows = transcript_rows_from_text(
        "Transcribing subtitles...\n"
        "[00:00.000 --> 00:02.500] hello world\n"
        "[00:02.500 --> 00:04.000] next line",
        include_plain_text=False,
    )

    assert rows == [("00:00", "hello world"), ("00:02", "next line")]


def test_normalize_language_supports_english_aliases() -> None:
    assert normalize_language("English") == "English"
    assert normalize_language("en") == "English"
    assert normalize_language("auto") is None


def test_analysis_language_instruction_supports_english() -> None:
    assert "English" in analysis_language_instruction("English")
    assert "same language" in analysis_language_instruction("auto")


def test_final_analysis_prompt_uses_english_sections() -> None:
    prompt = final_analysis_prompt("00:00 hello", "Analyze this.", "English")
    assert "Video Analysis Report" in prompt
    assert "One-Sentence Summary" in prompt
    assert "Chapters / Timeline" in prompt
    assert "Important Concepts" in prompt
    assert "Review Q&A" not in prompt
    assert "Transcript:" in prompt


def test_final_analysis_prompt_uses_chinese_report_title() -> None:
    prompt = final_analysis_prompt("00:00 你好", DEFAULT_TASK, "Chinese")
    assert "视频分析报告" in prompt
    assert "一句话总结" in prompt
    assert "结论与启发" in prompt


def test_final_analysis_prompt_translates_default_task_for_english() -> None:
    prompt = final_analysis_prompt("00:00 hello", DEFAULT_TASK, "English")
    assert "Analyze these video subtitles" in prompt
    assert "structured notes" in prompt


def test_expected_audio_path_stays_relative() -> None:
    assert expected_audio_path({"id": "BV123", "title": "Demo Video"}, Path("audio")) == Path(
        "audio/Demo_Video.wav"
    )


def test_expected_subtitle_path_stays_relative() -> None:
    assert expected_subtitle_path(Path("work/audio.wav"), Path("subs"), "srt") == Path("subs/audio.srt")


def test_local_media_metadata_uses_relative_display_path() -> None:
    Path("data").mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir="data", prefix="test-local-", suffix=" demo clip.mp4", delete=False) as media:
        media.write(b"demo")
        media_path = Path(media.name)

    try:
        metadata = local_media_metadata(media_path)
    finally:
        media_path.unlink(missing_ok=True)

    assert metadata["id"] == video_key({"id": media_path.stem})
    assert metadata["title"] == media_path.stem
    assert metadata["media_path"] == (Path("data") / media_path.name).as_posix()
    assert not str(metadata["media_path"]).startswith("/")
    assert metadata["source"] == "Local file"


def test_collect_urls_deduplicates_url_file(tmp_path) -> None:
    url_file = tmp_path / "urls.txt"
    url_file.write_text(
        "https://example.com/a\n# comment\nhttps://example.com/a\nhttps://example.com/b\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        url="https://example.com/a",
        url_text="",
        url_file=url_file,
        playlist=False,
        cookies=None,
    )
    assert collect_urls(args) == ["https://example.com/a", "https://example.com/b"]


def test_collect_urls_accepts_newline_text() -> None:
    args = argparse.Namespace(
        url=None,
        url_text="https://example.com/a\n# comment\nhttps://example.com/b\nhttps://example.com/a",
        url_file=None,
        playlist=False,
        cookies=None,
    )
    assert collect_urls(args) == ["https://example.com/a", "https://example.com/b"]


def test_build_pipeline_command_uses_cli_subprocess_shape() -> None:
    command = build_pipeline_command(
        url="https://example.com/video",
        url_text="",
        url_file="",
        media_file="",
        cookies_path="cookies.txt",
        playlist=False,
        whisper_model="small",
        source_language="English",
        subtitle_format="srt",
        device="cuda",
        reuse_existing=True,
        skip_llm=False,
        llm_task="",
        analysis_language="English",
    )

    assert command[:4] == [sys.executable, "-m", "video2notes.cli", "run"]
    assert "https://example.com/video" in command
    assert "--reuse-existing" in command
    assert "--device" in command
    assert "cuda" in command
    assert "--cookies" in command
    assert "cookies.txt" in command
    assert "--download-timeout" not in command


def test_build_pipeline_command_supports_local_media() -> None:
    command = build_pipeline_command(
        url="",
        url_text="",
        url_file="",
        media_file="data/imports/demo.mp4",
        cookies_path="",
        playlist=False,
        whisper_model="small",
        source_language="auto",
        subtitle_format="srt",
        device="cpu",
        reuse_existing=True,
        skip_llm=True,
        llm_task="",
        analysis_language="Chinese",
    )

    assert "--media-file" in command
    assert "data/imports/demo.mp4" in command
    assert "--url-text" not in command


def test_stop_pipeline_process_terminates_process() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    try:
        stop_pipeline_process(process)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()


def test_split_markdown_sections() -> None:
    sections = split_markdown_sections("# 一句话总结\nhello\n## 重要概念\nconcepts")
    assert sections["一句话总结"] == "hello"
    assert sections["重要概念"] == "concepts"


def test_extract_timeline() -> None:
    timeline = extract_timeline("- 00:00:00 - 00:01:00 intro")
    assert timeline == [{"start": "00:00:00", "end": "00:01:00", "title": "intro"}]


def test_export_summary_artifacts(tmp_path) -> None:
    summary = """# 一句话总结
hello

# 章节/时间线
- 00:00:00 - 00:01:00 intro

# 关键观点
- 测试验证行为。

# 重要概念
- 测试：验证系统行为是否符合预期。

# 结论与启发
- 应优先验证关键路径。
"""
    artifacts = export_summary_artifacts(summary, tmp_path, "demo")
    assert artifacts["chapters"].exists()
    assert artifacts["key_points"].exists()
    assert artifacts["concepts"].exists()
    assert artifacts["takeaways"].exists()
    assert artifacts["timeline"].exists()
    assert "qa" not in artifacts
    assert "flashcards" not in artifacts
