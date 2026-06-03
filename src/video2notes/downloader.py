import json
import shutil
import subprocess
import sys
from pathlib import Path

from video2notes.paths import display_path, user_path

DEFAULT_YT_DLP_SOCKET_TIMEOUT = 30
DEFAULT_YT_DLP_RETRIES = 2
DEFAULT_METADATA_TIMEOUT = 120
DEFAULT_DOWNLOAD_TIMEOUT = 1800
MAX_VIDEO_KEY_LENGTH = 120


def find_yt_dlp_binary() -> str:
    venv_yt_dlp = Path(sys.executable).with_name("yt-dlp")
    if venv_yt_dlp.exists():
        return str(venv_yt_dlp)

    yt_dlp = shutil.which("yt-dlp")
    if yt_dlp:
        return yt_dlp

    raise FileNotFoundError("Cannot find yt-dlp executable. Install yt-dlp in the active Python environment.")


def run_yt_dlp(cmd: list[str], timeout: int | None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"yt-dlp timed out after {timeout} seconds.") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"yt-dlp failed: {details}") from exc


def add_yt_dlp_network_options(
    cmd: list[str],
    cookies: Path | None = None,
    socket_timeout: int = DEFAULT_YT_DLP_SOCKET_TIMEOUT,
    retries: int = DEFAULT_YT_DLP_RETRIES,
) -> list[str]:
    if socket_timeout > 0:
        cmd.extend(["--socket-timeout", str(socket_timeout)])
    if retries >= 0:
        cmd.extend(["--retries", str(retries)])
        cmd.extend(["--fragment-retries", str(retries)])
    if cookies:
        cmd.extend(["--cookies", str(user_path(cookies))])
    return cmd


def load_video_metadata(
    url: str,
    cookies: Path | None = None,
    socket_timeout: int = DEFAULT_YT_DLP_SOCKET_TIMEOUT,
    retries: int = DEFAULT_YT_DLP_RETRIES,
    timeout: int = DEFAULT_METADATA_TIMEOUT,
) -> dict:
    cmd = [find_yt_dlp_binary(), "--no-playlist", "--dump-single-json", url]
    add_yt_dlp_network_options(cmd, cookies=cookies, socket_timeout=socket_timeout, retries=retries)

    result = run_yt_dlp(cmd, timeout=timeout)
    return json.loads(result.stdout)


def expand_playlist_urls(
    url: str,
    cookies: Path | None = None,
    socket_timeout: int = DEFAULT_YT_DLP_SOCKET_TIMEOUT,
    retries: int = DEFAULT_YT_DLP_RETRIES,
    timeout: int = DEFAULT_METADATA_TIMEOUT,
) -> list[str]:
    cmd = [find_yt_dlp_binary(), "--flat-playlist", "--dump-single-json", url]
    add_yt_dlp_network_options(cmd, cookies=cookies, socket_timeout=socket_timeout, retries=retries)

    result = run_yt_dlp(cmd, timeout=timeout)
    payload = json.loads(result.stdout)
    entries = payload.get("entries") or []
    urls = []
    for entry in entries:
        entry_url = entry.get("webpage_url") or entry.get("url")
        if entry_url:
            urls.append(entry_url)

    return urls or [url]


def video_key(metadata: dict) -> str:
    raw_key = (
        metadata.get("title")
        or metadata.get("fulltitle")
        or metadata.get("id")
        or metadata.get("display_id")
        or "video"
    )
    key_chars = []
    previous_separator = False
    for char in str(raw_key).strip():
        if char.isalnum() or char in ("-", "_"):
            key_chars.append(char)
            previous_separator = False
        elif not previous_separator:
            key_chars.append("_")
            previous_separator = True

    key = "".join(key_chars).strip("_")
    return key[:MAX_VIDEO_KEY_LENGTH].rstrip("_") or "video"


def save_metadata(metadata: dict, output_dir: Path) -> Path:
    output_dir = user_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / f"{video_key(metadata)}.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata_path


def expected_audio_path(metadata: dict, output_dir: Path, extension: str = "wav") -> Path:
    return user_path(output_dir) / f"{video_key(metadata)}.{extension}"


def download_audio(
    url: str,
    metadata: dict,
    output_dir: Path,
    cookies: Path | None = None,
    socket_timeout: int = DEFAULT_YT_DLP_SOCKET_TIMEOUT,
    retries: int = DEFAULT_YT_DLP_RETRIES,
    timeout: int = DEFAULT_DOWNLOAD_TIMEOUT,
) -> Path:
    output_dir = user_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = expected_audio_path(metadata, output_dir, "%(ext)s")

    cmd = [
        find_yt_dlp_binary(),
        "--no-playlist",
        "--no-simulate",
        "--print",
        "after_move:filepath",
        "-x",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "-o",
        str(output_template),
        url,
    ]
    add_yt_dlp_network_options(cmd, cookies=cookies, socket_timeout=socket_timeout, retries=retries)

    result = run_yt_dlp(cmd, timeout=timeout)
    printed_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not printed_paths:
        raise RuntimeError("yt-dlp did not report a downloaded audio file path.")

    audio_path = user_path(printed_paths[-1])
    if not audio_path.exists():
        raise FileNotFoundError(f"Downloaded audio file was not found: {display_path(audio_path)}")

    return audio_path
