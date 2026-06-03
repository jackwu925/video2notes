import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from video2notes.paths import display_path, user_path


DEFAULT_MODEL = "small"
DEFAULT_LANGUAGE = "Chinese"
DEFAULT_OUTPUT_FORMAT = "txt"
DEFAULT_DEVICE = "auto"
DEFAULT_TRANSCRIPTION_TIMEOUT = 0
LANGUAGE_PRESETS = ("Chinese", "English")
LANGUAGE_ALIASES = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "cn": "Chinese",
    "chinese": "Chinese",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "english": "English",
}


def find_whisper_binary() -> str:
    venv_whisper = Path(sys.executable).with_name("whisper")
    if venv_whisper.exists():
        return str(venv_whisper)

    whisper = shutil.which("whisper")
    if whisper:
        return whisper

    raise FileNotFoundError("Cannot find whisper executable. Install openai-whisper in the active Python environment.")


def resolve_device(device: str | None) -> str | None:
    if not device or device != "auto":
        return device

    try:
        import torch
    except ImportError:
        return "cpu"

    return "cuda" if torch.cuda.is_available() else "cpu"


def normalize_language(language: str | None) -> str | None:
    if not language:
        return None

    normalized = language.strip()
    if not normalized or normalized.lower() in {"auto", "detect", "none"}:
        return None

    return LANGUAGE_ALIASES.get(normalized.lower(), normalized)


def transcribe_audio(
    audio_path: Path,
    output_dir: Path,
    model: str = DEFAULT_MODEL,
    language: str | None = DEFAULT_LANGUAGE,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    device: str | None = DEFAULT_DEVICE,
    timeout: int = DEFAULT_TRANSCRIPTION_TIMEOUT,
) -> Path:
    audio_path = user_path(audio_path)
    output_dir = user_path(output_dir)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {display_path(audio_path)}")

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        find_whisper_binary(),
        str(audio_path),
        "--model",
        model,
        "--output_dir",
        str(output_dir),
        "--output_format",
        output_format,
    ]

    normalized_language = normalize_language(language)
    if normalized_language:
        cmd.extend(["--language", normalized_language])

    resolved_device = resolve_device(device)
    if resolved_device:
        cmd.extend(["--device", resolved_device])

    try:
        subprocess.run(cmd, check=True, timeout=timeout if timeout > 0 else None)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Whisper transcription timed out after {timeout} seconds.") from exc

    if output_format == "all":
        return output_dir

    return output_dir / f"{audio_path.stem}.{output_format}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe an audio file with Whisper.")
    parser.add_argument("--audio", required=True, type=Path, help="Path to the input audio file.")
    parser.add_argument(
        "--output-dir",
        default=Path("data/subtitles"),
        type=Path,
        help="Directory where subtitle files will be written.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Whisper model name.")
    parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help=(
            "Speech recognition language hint for the original audio, for example Chinese, English, en, or zh. "
            "Use auto or an empty string to let Whisper detect it. This does not translate audio."
        ),
    )
    parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        choices=("txt", "vtt", "srt", "tsv", "json", "all"),
        help="Whisper output format.",
    )
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help="Torch device: auto, cpu, or cuda. auto uses CUDA when PyTorch can see a GPU.",
    )
    parser.add_argument(
        "--timeout",
        default=DEFAULT_TRANSCRIPTION_TIMEOUT,
        type=int,
        help="Maximum transcription time in seconds. Use 0 to disable the limit.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    language = args.language or None
    output_path = transcribe_audio(
        audio_path=args.audio,
        output_dir=args.output_dir,
        model=args.model,
        language=language,
        output_format=args.output_format,
        device=args.device,
        timeout=args.timeout,
    )
    print(f"Subtitles saved: {display_path(output_path)}")
