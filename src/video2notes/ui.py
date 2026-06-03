import base64
import hashlib
import html
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from video2notes.downloader import video_key
from video2notes.paths import display_path, project_root, sanitize_project_paths
from video2notes.pipeline import (
    DEFAULT_AUDIO_DIR,
    DEFAULT_METADATA_DIR,
    DEFAULT_SUBTITLES_DIR,
    DEFAULT_SUMMARIES_DIR,
)
from video2notes.llm import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    LLM_PROVIDER_PRESETS,
    LLMConfig,
    get_provider_preset,
)

DEFAULT_UI_HOST = os.getenv("VIDEO2NOTES_UI_HOST", "127.0.0.1")
DEFAULT_UI_PORT = int(os.getenv("VIDEO2NOTES_UI_PORT", "8501"))
MAX_UI_PORT = int(os.getenv("VIDEO2NOTES_UI_MAX_PORT", "8599"))
PREVIEW_CHARS = 12000
TRANSCRIPT_PREVIEW_CHARS = 300000
TRANSCRIPT_ROW_LIMIT = 2000
TIMESTAMP_LINE_PATTERN = re.compile(
    r"^\s*\[?(?P<start>\d{1,2}:\d{2}(?::\d{2})?(?:[\.,]\d+)?)\s*-->\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?(?:[\.,]\d+)?)\]?\s*(?P<text>.*)$"
)
API_PROFILES_PATH = Path("data/config/api_profiles.json")
ACTIVE_RUN_PATH = Path("data/config/active_run.json")
DEFAULT_LOGS_DIR = Path("data/logs")
MAIN_PANEL_HEIGHT = 780
ASSETS_DIR = Path("assets")
UI_LOGO_PATH = ASSETS_DIR / "video2notes_logo.svg"

UI_TEXT = {
    "zh": {
        "api_header": "API 配置",
        "api_key": "API Key",
        "api_key_required": "请输入 API Key，或选择 Ollama / LM Studio 这类本地供应商。",
        "api_not_configured": "请先在右上角 API 配置中确认 API，或启用“只生成字幕”。",
        "api_ready": "API 已确认：{profile}",
        "api_saved": "API 配置已确认并保存。",
        "api_storage_note": "API 配置会保存在本机 data/config/api_profiles.json。",
        "ai_panel": "AI 分析与笔记",
        "analysis_fullscreen": "分析结果",
        "batch_urls": "视频链接",
        "base_url": "API Base URL",
        "confirm_api": "确认并保存 API",
        "cpu": "CPU",
        "device": "设备",
        "download_markdown": "下载 MD",
        "chinese_notes": "中文总结",
        "english_notes": "英文总结",
        "expand_playlist": "展开播放列表",
        "expand_analysis": "放大分析结果",
        "gpu": "GPU",
        "llm_task": "分析要求",
        "llm_task_help": "留空时使用默认的视频分析报告结构。",
        "llm_task_placeholder": "可选：写下希望重点分析的内容，例如关键论点、行动项或争议点。",
        "local_media_path": "本地媒体",
        "local_media_path_help": "可选：填写本地音频或视频文件路径后，会跳过网页下载，直接转写该文件。",
        "model": "模型名称",
        "notes_language": "总结语言",
        "pipeline_completed": "流程已完成。",
        "pipeline_failed": "流程失败，退出码：{code}。",
        "pipeline_started": "流程已在后台启动。",
        "pipeline_stopped": "流程已停止。",
        "profile": "配置",
        "profile_name": "配置名称",
        "provider": "供应商",
        "reuse_existing": "复用缓存",
        "run_pipeline": "运行",
        "saved_api_profile": "历史 API 配置",
        "select_summary": "总结报告",
        "settings": "API 配置",
        "skip_llm": "只生成字幕（跳过总结）",
        "source_language": "音频语言",
        "source_language_auto": "自动识别音频语言",
        "source_language_chinese": "中文音频",
        "source_language_english": "英文音频",
        "source_panel": "视频来源",
        "source_required": "请输入视频链接，或填写本地音频/视频路径。",
        "subtitle_panel": "字幕 / 转写",
        "timeout": "超时时间（秒）",
        "whisper_model": "转写模型",
        "stop_pipeline": "停止",
        "yt_dlp_cookies": "cookies.txt",
        "yt_dlp_cookies_help": "可选：Bilibili、YouTube 等站点需要登录态时，填写浏览器导出的 cookies.txt 路径。",
        "video_not_selected": "未选择视频",
        "video_pending": "待处理",
    },
    "en": {
        "api_header": "API Configuration",
        "api_key": "API key",
        "api_key_required": "Enter an API key, or select a local provider such as Ollama or LM Studio.",
        "api_not_configured": "Confirm an API configuration in API Config, or enable Subtitles Only.",
        "api_ready": "API confirmed: {profile}",
        "api_saved": "API configuration confirmed and saved.",
        "api_storage_note": "API profiles are stored locally in data/config/api_profiles.json.",
        "ai_panel": "AI Analysis & Notes",
        "analysis_fullscreen": "Analysis Result",
        "batch_urls": "Video Links",
        "base_url": "API Base URL",
        "confirm_api": "Confirm and Save API",
        "cpu": "CPU",
        "device": "Device",
        "download_markdown": "Download MD",
        "chinese_notes": "Chinese notes",
        "english_notes": "English notes",
        "expand_playlist": "Expand Playlist",
        "expand_analysis": "Expand analysis result",
        "gpu": "GPU",
        "llm_task": "Analysis Instructions",
        "llm_task_help": "Leave blank to use the default video analysis report structure.",
        "llm_task_placeholder": (
            "Optional: describe what the model should focus on, such as key arguments, "
            "action items, or disputed points."
        ),
        "local_media_path": "Local media",
        "local_media_path_help": (
            "Optional: enter a local audio or video path to skip webpage download and transcribe it directly."
        ),
        "model": "Model Name",
        "notes_language": "Summary Language",
        "pipeline_completed": "Pipeline completed.",
        "pipeline_failed": "Pipeline failed with exit code {code}.",
        "pipeline_started": "Pipeline started in the background.",
        "pipeline_stopped": "Pipeline stopped.",
        "profile": "Profile",
        "profile_name": "Profile name",
        "provider": "Provider",
        "reuse_existing": "Reuse Cache",
        "run_pipeline": "Run",
        "saved_api_profile": "Saved API profile",
        "select_summary": "Summary report",
        "settings": "API Config",
        "skip_llm": "Subtitles Only (Skip Summary)",
        "source_language": "Audio Language",
        "source_language_auto": "Auto-detect audio language",
        "source_language_chinese": "Chinese audio",
        "source_language_english": "English audio",
        "source_panel": "Video Source",
        "source_required": "Enter a video link, or provide a local audio/video path.",
        "subtitle_panel": "Subtitles / Transcript",
        "timeout": "Timeout seconds",
        "whisper_model": "Transcription Model",
        "stop_pipeline": "Stop",
        "yt_dlp_cookies": "cookies.txt",
        "yt_dlp_cookies_help": (
            "Optional: enter a browser-exported cookies.txt path for sites that require login cookies."
        ),
        "video_not_selected": "No video selected",
        "video_pending": "Pending",
    },
}

def streamlit_script_target() -> tuple[str, Path]:
    root = project_root()
    source_script = root / "src" / "video2notes" / "ui.py"
    if source_script.exists():
        return display_path(source_script), root

    package_script = Path(__file__).expanduser()
    return package_script.name, package_script.parent


def asset_data_uri(path: Path) -> str:
    resolved = project_root() / path
    if not resolved.exists():
        return ""

    if path.suffix.lower() == ".svg":
        mime_type = "image/svg+xml"
    elif path.suffix.lower() == ".png":
        mime_type = "image/png"
    else:
        mime_type = "application/octet-stream"
    encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def launch() -> None:
    port = find_available_port(DEFAULT_UI_HOST, DEFAULT_UI_PORT, MAX_UI_PORT)
    script_target, cwd = streamlit_script_target()
    env = os.environ.copy()
    env["VIDEO2NOTES_PROJECT_ROOT"] = project_root().as_posix()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            script_target,
            "--server.address",
            DEFAULT_UI_HOST,
            "--server.port",
            str(port),
        ],
        check=True,
        cwd=cwd,
        env=env,
    )


def find_available_port(host: str = DEFAULT_UI_HOST, start: int = DEFAULT_UI_PORT, end: int = MAX_UI_PORT) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port

    raise RuntimeError(f"No available UI port in range {start}-{end}.")


def read_text_preview(path: Path, max_chars: int = PREVIEW_CHARS) -> str:
    resolved = path.expanduser()
    if not resolved.exists():
        return ""

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars]}\n\n... preview truncated ..."


def sanitize_log_file(path: Path) -> None:
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8", errors="replace")
    sanitized = sanitize_project_paths(text)
    if sanitized != text:
        path.write_text(sanitized, encoding="utf-8")


def read_text_tail(path: Path, max_chars: int = 6000) -> str:
    resolved = path.expanduser()
    if not resolved.exists():
        return ""

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text

    return text[-max_chars:]


def read_pipeline_log(log_path_value: str | None, max_chars: int = 20000) -> str:
    if not log_path_value:
        return ""

    return sanitize_project_paths(read_text_tail(Path(log_path_value), max_chars=max_chars))


def summarize_pipeline_error(log_path_value: str | None, fallback: str) -> str:
    log_text = read_pipeline_log(log_path_value, max_chars=PREVIEW_CHARS)
    if not log_text:
        return fallback

    keywords = (
        "error",
        "failed",
        "traceback",
        "not found",
        "no such file",
        "does not exist",
        "timed out",
        "permission denied",
        "runtimeerror",
        "filenotfounderror",
        "valueerror",
    )
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    for line in reversed(lines):
        if any(keyword in line.lower() for keyword in keywords):
            detail = line[-520:]
            return f"{fallback} {detail}"
    return fallback


def first_video_link(url_text: str) -> str:
    for line in url_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def compact_transcript_timestamp(value: str) -> str:
    cleaned = value.strip().strip("[]").replace(",", ".")
    without_fraction = cleaned.split(".", 1)[0]
    parts = without_fraction.split(":")
    if len(parts) >= 2:
        return ":".join(parts[-2:])
    return without_fraction or "--:--"


def transcript_rows_from_text(
    text: str,
    limit: int = TRANSCRIPT_ROW_LIMIT,
    include_plain_text: bool = True,
) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines()]
    rows: list[tuple[str, str]] = []
    index = 0
    while index < len(lines) and len(rows) < limit:
        line = lines[index]
        timestamp_match = TIMESTAMP_LINE_PATTERN.match(line)
        if timestamp_match:
            timestamp = compact_transcript_timestamp(timestamp_match.group("start"))
            inline_text = timestamp_match.group("text").strip()
            if inline_text:
                rows.append((timestamp, inline_text))
                index += 1
                continue
            text_parts = []
            index += 1
            while index < len(lines) and lines[index] and "-->" not in lines[index]:
                if not lines[index].isdigit() and lines[index] != "WEBVTT":
                    text_parts.append(lines[index])
                index += 1
            if text_parts:
                rows.append((timestamp, " ".join(text_parts)))
            continue
        if include_plain_text and line and not line.isdigit() and line != "WEBVTT":
            rows.append(("--:--", line))
        index += 1
    return rows


def sample_transcript_rows(language: str) -> list[tuple[str, str]]:
    if language == "zh":
        return [
            ("00:00", "欢迎来到今天的视频，我们会把长视频转成可复用的结构化笔记。"),
            ("00:18", "系统会先下载音频，然后使用 Whisper 生成带时间戳的字幕。"),
            ("00:42", "接下来，大模型会基于字幕生成摘要、关键观点和时间线。"),
            ("01:15", "如果已经处理过同一个视频，可以复用缓存，避免重复下载和转写。"),
            ("01:48", "最终输出会保存为 Markdown、字幕文件和结构化 JSON。"),
        ]
    return [
        ("00:00", "Welcome to Video2Notes. This workspace turns long videos into structured notes."),
        ("00:18", "The pipeline downloads audio, transcribes subtitles, and keeps timestamps."),
        ("00:42", "An OpenAI-compatible LLM then creates summaries, key points, and timelines."),
        ("01:15", "Cached artifacts can be reused to avoid repeated downloads and transcription."),
        ("01:48", "The final output is saved as Markdown, subtitle files, and structured JSON."),
    ]


def sample_summary(language: str) -> str:
    if language == "zh":
        return """### 摘要
运行分析后，这里会展示视频分析报告。

### 关键观点
- 自动下载视频音频并转写字幕。
- 使用大模型生成结构化总结。
- 支持缓存复用和本地文件导出。

### 行动项
1. 输入一个或多个视频链接。
2. 确认 API 配置。
3. 点击运行生成总结。"""
    return """### Summary
Generated video notes will appear here after a run.

### Key Points
- Download video audio and transcribe timestamped subtitles.
- Generate structured notes with an OpenAI-compatible LLM.
- Reuse cache and export local files.

### Action Items
1. Paste one or more video links.
2. Confirm the API configuration.
3. Run the pipeline to generate notes."""


def preview_key(label: str, path: Path) -> str:
    digest = hashlib.sha1(f"{label}:{display_path(path)}".encode()).hexdigest()[:12]
    return f"preview_{digest}"


def current_run_stem(url_text: str) -> str:
    stems = current_run_stems(url_text)
    return stems[0] if stems else ""


def current_run_stems(url_text: str) -> list[str]:
    video_link = first_video_link(url_text)
    metadata = latest_video_metadata(video_link)
    stems: list[str] = []
    if metadata:
        if metadata.get("extractor") == "local":
            media_path = str(metadata.get("media_path") or metadata.get("webpage_url") or "")
            if media_path:
                stems.append(Path(media_path).stem)
        stems.append(video_key(metadata))

    video_id = video_id_from_url(video_link)
    if video_id:
        stems.append(video_id)
    elif video_link and not urlparse(video_link).netloc:
        stems.append(Path(video_link).stem)

    return list(dict.fromkeys(stem for stem in stems if stem))


def current_run_file(
    url_text: str,
    directory: Path,
    suffixes: tuple[str, ...],
) -> Path | None:
    stems = current_run_stems(url_text)
    for stem in stems:
        match = related_file(directory, stem, suffixes)
        if match:
            return match
    if stems:
        return None

    recent_files = list_recent_files(directory, suffixes=suffixes)
    return recent_files[0] if recent_files else None


def keyword_seen(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def pipeline_progress_state(
    url_text: str,
    log_text: str,
    running: bool,
    skip_llm: bool,
    completed: bool,
) -> dict[str, object]:
    if not running and not completed and not log_text:
        return {
            "progress": 0.0,
            "current_stage": "audio",
            "stages": {
                "audio": "waiting",
                "subtitles": "waiting",
                "summary": "skipped" if skip_llm else "waiting",
            },
        }

    audio_path = current_run_file(url_text, DEFAULT_AUDIO_DIR, (".wav", ".mp3", ".m4a", ".webm", ".opus"))
    subtitle_path = current_run_file(url_text, DEFAULT_SUBTITLES_DIR, (".srt", ".txt", ".vtt", ".tsv", ".json"))
    summary_path = current_run_file(url_text, DEFAULT_SUMMARIES_DIR, (".md",))

    audio_started = keyword_seen(log_text, ("Reading video metadata", "Downloading and extracting audio"))
    audio_done = bool(audio_path) or keyword_seen(log_text, ("Audio ready:", "Reusing existing audio:"))
    subtitle_started = keyword_seen(log_text, ("Transcribing subtitles",))
    subtitle_done = bool(subtitle_path) or keyword_seen(log_text, ("Subtitles saved:", "Reusing existing subtitles:"))
    summary_started = keyword_seen(log_text, ("Analyzing subtitles with the LLM",))
    summary_skipped = skip_llm or keyword_seen(log_text, ("LLM analysis skipped", "LLM_API_KEY is not configured"))
    summary_done = bool(summary_path) or keyword_seen(
        log_text,
        ("LLM analysis saved:", "Reusing existing LLM analysis:"),
    )

    stages = {
        "audio": "done" if audio_done else "running" if running and audio_started else "waiting",
        "subtitles": "done" if subtitle_done else "running" if running and subtitle_started else "waiting",
        "summary": (
            "skipped"
            if summary_skipped
            else "done"
            if summary_done
            else "running"
            if running and summary_started
            else "waiting"
        ),
    }

    if completed:
        stages["audio"] = "done"
        stages["subtitles"] = "done"
        stages["summary"] = "skipped" if summary_skipped else "done"

    if stages["summary"] in {"done", "skipped"} and stages["subtitles"] == "done":
        progress = 1.0
        current_stage = "summary"
    elif stages["summary"] == "running":
        progress = 0.86
        current_stage = "summary"
    elif stages["subtitles"] == "done":
        progress = 0.72
        current_stage = "subtitles"
    elif stages["subtitles"] == "running":
        progress = 0.58
        current_stage = "subtitles"
    elif stages["audio"] == "done":
        progress = 0.42
        current_stage = "audio"
    elif stages["audio"] == "running":
        progress = 0.22
        current_stage = "audio"
    else:
        progress = 0.04 if running else 0.0
        current_stage = "audio"

    return {
        "progress": progress,
        "current_stage": current_stage,
        "stages": stages,
    }


def pipeline_log_indicates_success(log_text: str, skip_llm: bool) -> bool:
    subtitle_done = keyword_seen(log_text, ("Subtitles saved:", "Reusing existing subtitles:"))
    summary_done = skip_llm or keyword_seen(
        log_text,
        ("LLM analysis saved:", "Reusing existing LLM analysis:", "LLM analysis skipped"),
    )
    return subtitle_done and summary_done


def summary_path_from_pipeline_log(log_text: str) -> Path | None:
    prefixes = ("LLM analysis saved:", "Reusing existing LLM analysis:")
    for line in reversed([line.strip() for line in log_text.splitlines() if line.strip()]):
        for prefix in prefixes:
            if line.startswith(prefix):
                summary_path = Path(line.removeprefix(prefix).strip())
                if summary_path.exists():
                    return summary_path
    return None


def local_api_key(provider: str, api_key: str) -> str:
    preset = get_provider_preset(provider)
    if preset.get("requires_api_key", True):
        return api_key.strip()
    return api_key.strip() or "local"


def tr(language: str, key: str, **values: object) -> str:
    return UI_TEXT[language][key].format(**values)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_api_store() -> dict[str, object]:
    payload = read_json(API_PROFILES_PATH, {"active": "", "profiles": []})
    if not isinstance(payload, dict):
        return {"active": "", "profiles": []}
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        payload["profiles"] = []
    payload.setdefault("active", "")
    return payload


def save_api_profile(profile: dict[str, object]) -> None:
    store = load_api_store()
    profiles = [item for item in store["profiles"] if item.get("name") != profile.get("name")]
    profiles.insert(0, profile)
    store["profiles"] = profiles[:20]
    store["active"] = profile.get("name", "")
    write_json(API_PROFILES_PATH, store)


def read_active_run_state() -> dict[str, object]:
    payload = read_json(ACTIVE_RUN_PATH, {})
    return payload if isinstance(payload, dict) else {}


def write_active_run_state(pid: int, log_path: Path, url_text: str, skip_llm: bool) -> None:
    write_json(
        ACTIVE_RUN_PATH,
        {
            "pid": pid,
            "log_path": display_path(log_path),
            "url_text": url_text,
            "skip_llm": skip_llm,
            "started_at": now_iso(),
        },
    )


def clear_active_run_state() -> None:
    try:
        ACTIVE_RUN_PATH.unlink()
    except FileNotFoundError:
        return


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def hydrate_active_run_state(st, state: dict[str, object]) -> None:
    if state.get("log_path"):
        st.session_state["pipeline_log_path"] = str(state["log_path"])
    if state.get("url_text"):
        st.session_state["pipeline_url_text"] = str(state["url_text"])
    st.session_state["pipeline_skip_llm"] = bool(state.get("skip_llm"))
    st.session_state["pipeline_completed"] = False


def get_active_api_profile(store: dict[str, object]) -> dict[str, object] | None:
    profiles = [profile for profile in store.get("profiles", []) if isinstance(profile, dict)]
    active_name = store.get("active")
    for profile in profiles:
        if profile.get("name") == active_name:
            return profile
    return profiles[0] if profiles else None


def api_profile_label(profile: dict[str, object]) -> str:
    name = str(profile.get("name") or "Untitled")
    provider = str(profile.get("provider") or "Custom")
    model = str(profile.get("model") or DEFAULT_MODEL)
    return f"{name} ({provider} / {model})"


def profile_widget_key(profile: dict[str, object] | None, label: str) -> str:
    raw = label if profile is None else json.dumps(profile, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def confirmed_llm_config(st) -> LLMConfig:
    profile = st.session_state.get("confirmed_api_profile") or {}
    provider = str(profile.get("provider") or "Custom")
    return LLMConfig(
        api_key=local_api_key(provider, str(profile.get("api_key") or "")),
        base_url=str(profile.get("base_url") or DEFAULT_BASE_URL),
        model=str(profile.get("model") or DEFAULT_MODEL),
        timeout_seconds=int(profile.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
    )


def set_transient_notice(st, level: str, message: str) -> None:
    duration = 12.0 if level == "error" else 7.0
    st.session_state["transient_notice"] = {
        "level": level,
        "message": message,
        "created_at": time.time(),
        "duration": duration,
        "notice_id": time.time_ns(),
    }


def render_transient_notice(st) -> None:
    notice = st.session_state.get("transient_notice")
    if not isinstance(notice, dict):
        return

    created_at = float(notice.get("created_at") or 0)
    duration = float(notice.get("duration") or 8.0)
    if time.time() - created_at > duration:
        st.session_state.pop("transient_notice", None)
        return

    level = html.escape(str(notice.get("level") or "info"))
    message = html.escape(str(notice.get("message") or ""))
    notice_id = html.escape(str(notice.get("notice_id") or created_at))
    if not message:
        return
    st.markdown(
        f'<div class="v2n-center-notice v2n-center-notice-{level}" data-notice-id="{notice_id}">{message}</div>',
        unsafe_allow_html=True,
    )


def render_api_settings(
    st,
    language: str,
    api_store: dict[str, object],
    active_profile: dict[str, object] | None,
) -> None:
    with st.popover(tr(language, "settings"), icon=":material/settings:", use_container_width=True):
        st.markdown(f"### {tr(language, 'api_header')}")
        profiles = [profile for profile in api_store.get("profiles", []) if isinstance(profile, dict)]
        if profiles:
            profile_labels = [api_profile_label(profile) for profile in profiles]
            active_label = api_profile_label(active_profile) if active_profile else profile_labels[0]
            active_index = profile_labels.index(active_label) if active_label in profile_labels else 0
            selected_label = st.selectbox(
                tr(language, "saved_api_profile"),
                profile_labels,
                index=active_index,
                key="api_profile_select",
            )
            selected_profile = profiles[profile_labels.index(selected_label)]
        else:
            selected_label = "SiliconFlow"
            selected_profile = None
        widget_key = profile_widget_key(selected_profile, selected_label)

        providers = list(LLM_PROVIDER_PRESETS)
        default_provider = str((selected_profile or {}).get("provider") or "SiliconFlow")
        provider_preset = get_provider_preset(default_provider)
        profile_provider = str((selected_profile or {}).get("provider") or default_provider)
        default_name = str((selected_profile or {}).get("name") or default_provider)
        default_api_key = str((selected_profile or {}).get("api_key") or "")
        default_base_url = (
            str(selected_profile.get("base_url"))
            if selected_profile and profile_provider == default_provider
            else str(provider_preset["base_url"])
        )
        default_model = (
            str(selected_profile.get("model"))
            if selected_profile and profile_provider == default_provider
            else str(provider_preset["model"])
        )
        provider = st.selectbox(
            tr(language, "provider"),
            providers,
            index=providers.index(default_provider) if default_provider in providers else providers.index("Custom"),
            key=f"api_provider_{widget_key}",
        )
        provider_preset = get_provider_preset(provider)
        if selected_profile and profile_provider == provider:
            base_url_value = default_base_url
            model_value = default_model
        else:
            base_url_value = str(provider_preset["base_url"])
            model_value = str(provider_preset["model"])
        profile_name = st.text_input(
            tr(language, "profile_name"),
            value=default_name,
            key=f"api_name_{widget_key}",
        )
        api_key = st.text_input(
            tr(language, "api_key"),
            value=default_api_key,
            type="password",
            placeholder="sk-...",
            key=f"api_key_{widget_key}",
        )
        base_url = st.text_input(
            tr(language, "base_url"),
            value=base_url_value,
            key=f"api_base_url_{widget_key}_{provider}",
        )
        model = st.text_input(
            tr(language, "model"),
            value=model_value,
            key=f"api_model_{widget_key}_{provider}",
        )
        timeout_seconds = st.number_input(
            tr(language, "timeout"),
            min_value=5,
            max_value=600,
            value=int((selected_profile or {}).get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
            step=5,
            key=f"api_timeout_{widget_key}",
        )

        if st.button(tr(language, "confirm_api"), key="confirm_api_settings", use_container_width=True):
            candidate = LLMConfig(
                api_key=local_api_key(provider, api_key),
                base_url=base_url.strip() or DEFAULT_BASE_URL,
                model=model.strip() or DEFAULT_MODEL,
                timeout_seconds=int(timeout_seconds),
            )
            if not candidate.is_configured:
                st.error(tr(language, "api_key_required"))
            else:
                profile = {
                    "name": profile_name.strip() or f"{provider} {model.strip() or DEFAULT_MODEL}",
                    "provider": provider,
                    "api_key": api_key.strip(),
                    "base_url": candidate.base_url,
                    "model": candidate.model,
                    "timeout_seconds": candidate.timeout_seconds,
                    "updated_at": now_iso(),
                }
                save_api_profile(profile)
                st.session_state["confirmed_api_profile"] = profile
                st.session_state.pop("transient_notice", None)
                st.session_state["pipeline_last_status"] = ("success", tr(language, "api_saved"))
                st.success(tr(language, "api_saved"))

        llm_config = confirmed_llm_config(st)
        confirmed_profile = st.session_state.get("confirmed_api_profile")
        if llm_config.is_configured and confirmed_profile:
            st.success(tr(language, "api_ready", profile=api_profile_label(confirmed_profile)))
        else:
            st.info(tr(language, "api_not_configured"))
        st.caption(tr(language, "api_storage_note"))


def build_pipeline_command(
    url: str,
    url_text: str,
    url_file: str,
    media_file: str,
    cookies_path: str,
    playlist: bool,
    whisper_model: str,
    source_language: str,
    subtitle_format: str,
    device: str,
    reuse_existing: bool,
    skip_llm: bool,
    llm_task: str,
    analysis_language: str,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "video2notes.cli",
        "run",
        "--audio-dir",
        str(DEFAULT_AUDIO_DIR),
        "--metadata-dir",
        str(DEFAULT_METADATA_DIR),
        "--subtitles-dir",
        str(DEFAULT_SUBTITLES_DIR),
        "--summaries-dir",
        str(DEFAULT_SUMMARIES_DIR),
        "--whisper-model",
        whisper_model,
        "--language",
        source_language,
        "--subtitle-format",
        subtitle_format,
        "--device",
        device,
        "--analysis-language",
        analysis_language,
    ]
    if url.strip():
        cmd.append(url.strip())
    if url_text.strip():
        cmd.extend(["--url-text", url_text.strip()])
    if url_file.strip():
        cmd.extend(["--url-file", url_file.strip()])
    if media_file.strip():
        cmd.extend(["--media-file", media_file.strip()])
    if cookies_path.strip():
        cmd.extend(["--cookies", cookies_path.strip()])
    if playlist:
        cmd.append("--playlist")
    if reuse_existing:
        cmd.append("--reuse-existing")
    if skip_llm:
        cmd.append("--skip-llm")
    if llm_task.strip():
        cmd.extend(["--llm-task", llm_task.strip()])
    return cmd


def pipeline_env(llm_config: LLMConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["LLM_API_KEY"] = llm_config.api_key
    env["LLM_BASE_URL"] = llm_config.base_url
    env["LLM_MODEL"] = llm_config.model
    env["LLM_TIMEOUT_SECONDS"] = str(llm_config.timeout_seconds)
    return env


def active_process(st) -> subprocess.Popen | int | None:
    process = st.session_state.get("pipeline_process")
    if process and process.poll() is None:
        return process

    state = read_active_run_state()
    try:
        pid = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid_is_running(pid):
        hydrate_active_run_state(st, state)
        return pid
    return None


def process_pid(process: subprocess.Popen | int) -> int:
    return process if isinstance(process, int) else process.pid


def latest_pipeline_log_path() -> Path:
    DEFAULT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_LOGS_DIR / f"ui-pipeline-{timestamp}.log"


def start_pipeline_process(cmd: list[str], llm_config: LLMConfig) -> tuple[subprocess.Popen, Path]:
    log_path = latest_pipeline_log_path()
    log_handle = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            cmd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=pipeline_env(llm_config),
            cwd=project_root(),
            start_new_session=(os.name == "posix"),
        )
    finally:
        log_handle.close()
    return process, log_path


def stop_pipeline_process(process: subprocess.Popen | int) -> None:
    if isinstance(process, subprocess.Popen) and process.poll() is not None:
        return
    pid = process_pid(process)
    try:
        if os.name == "posix":
            os.killpg(pid, signal.SIGTERM)
        else:
            if isinstance(process, subprocess.Popen):
                process.terminate()
            else:
                os.kill(pid, signal.SIGTERM)
        if isinstance(process, subprocess.Popen):
            process.wait(timeout=3)
        else:
            for _ in range(30):
                if not pid_is_running(pid):
                    break
                time.sleep(0.1)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        if os.name == "posix":
            os.killpg(pid, signal.SIGKILL)
        else:
            if isinstance(process, subprocess.Popen):
                process.kill()
            else:
                os.kill(pid, signal.SIGKILL)
        if isinstance(process, subprocess.Popen):
            process.wait(timeout=3)


def list_files(directory: Path, suffixes: tuple[str, ...] | None = None) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.glob("*") if path.is_file()]
    if suffixes:
        files = [path for path in files if path.suffix.lower() in suffixes]
    return sorted(files)


def list_recent_files(directory: Path, suffixes: tuple[str, ...] | None = None) -> list[Path]:
    files = list_files(directory, suffixes=suffixes)
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def source_label_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "youtube" in host or "youtu.be" in host:
        return "YouTube"
    if "bilibili" in host:
        return "Bilibili"
    if host:
        return host.removeprefix("www.")
    return "URL"


def video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if "youtube" in host:
        query_video_id = parse_qs(parsed.query).get("v", [""])[0]
        return query_video_id or (path_parts[-1] if path_parts else "")
    if "youtu.be" in host:
        return path_parts[0] if path_parts else ""
    if "bilibili" in host:
        for part in path_parts:
            if part.startswith("BV") or part.startswith("av"):
                return part
    return ""


def video_embed_url(url: str) -> str:
    video_id = video_id_from_url(url)
    if not video_id:
        return ""

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtube" in host or "youtu.be" in host:
        return f"https://www.youtube.com/embed/{video_id}"
    if "bilibili" in host:
        query = {"autoplay": "0"}
        if video_id.startswith("BV"):
            query["bvid"] = video_id
        elif video_id.startswith("av") and video_id[2:].isdigit():
            query["aid"] = video_id[2:]
        else:
            return ""
        page = parse_qs(parsed.query).get("p", [""])[0]
        if page:
            query["page"] = page
        return f"https://player.bilibili.com/player.html?{urlencode(query)}"
    return ""


def media_kind_from_source(source: str) -> str:
    parsed = urlparse(source)
    path_text = parsed.path if parsed.scheme or parsed.netloc else source
    suffix = Path(path_text).suffix.lower()
    if suffix in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac"}:
        return "audio"
    if suffix in {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}:
        return "video"
    return ""


def fallback_video_title(url: str, language: str) -> str:
    if not url:
        return tr(language, "video_not_selected")
    source = source_label_from_url(url)
    video_id = video_id_from_url(url)
    if video_id:
        return f"{source} video {video_id}"
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.removeprefix("www.")
    return Path(url).name or url


def latest_video_metadata(video_link: str = "") -> dict[str, object]:
    explicit_link = bool(video_link)
    for metadata_path in list_recent_files(DEFAULT_METADATA_DIR, suffixes=(".json",)):
        metadata = read_json(metadata_path, {})
        if isinstance(metadata, dict):
            if not explicit_link:
                return metadata
            candidate_urls = [
                str(metadata.get("media_path") or ""),
                str(metadata.get("webpage_url") or ""),
                str(metadata.get("original_url") or ""),
                str(metadata.get("url") or ""),
            ]
            if any(
                candidate_url and (video_link in candidate_url or candidate_url in video_link)
                for candidate_url in candidate_urls
            ):
                return metadata
            continue
    return {}


def video_preview_details(url_text: str, language: str) -> dict[str, str]:
    fallback = tr(language, "video_pending")
    video_link = first_video_link(url_text)
    metadata = latest_video_metadata(video_link)
    title = str(metadata.get("title") or fallback_video_title(video_link, language))
    source_url = str(metadata.get("webpage_url") or metadata.get("original_url") or video_link)
    source = str(metadata.get("source") or "")
    if not source and source_url:
        parsed = urlparse(source_url)
        source = source_label_from_url(source_url) if parsed.scheme or parsed.netloc else "Local file"
    if not source:
        source = fallback
    return {
        "title": title,
        "source": source,
    }


def static_video_placeholder_html(video_details: dict[str, str]) -> str:
    return f"""
    <div class="v2n-video-thumb">
      <div class="v2n-thumb-title">{html.escape(video_details["title"])}</div>
      <div class="v2n-play">▶</div>
    </div>
    """


def video_link_fallback_html(source: str, video_details: dict[str, str]) -> str:
    return f"""
    <div class="v2n-video-link-fallback">
      <div class="v2n-video-link-title">{html.escape(video_details["title"])}</div>
      <a href="{html.escape(source, quote=True)}" target="_blank" rel="noreferrer">
        {html.escape(source)}
      </a>
    </div>
    """


def render_video_source_player(st, source_text: str, video_details: dict[str, str]) -> None:
    source = first_video_link(source_text)
    embed_url = video_embed_url(source)
    if embed_url:
        st.iframe(embed_url, height=315)
        return

    media_kind = media_kind_from_source(source)
    if media_kind:
        parsed = urlparse(source)
        media_source: str | Path = source
        if not parsed.scheme and not parsed.netloc:
            media_path = Path(source).expanduser()
            if not media_path.exists():
                st.markdown(static_video_placeholder_html(video_details), unsafe_allow_html=True)
                return
            media_source = media_path
        if media_kind == "audio":
            st.audio(media_source)
        else:
            st.video(media_source)
        return

    if source and urlparse(source).scheme:
        st.markdown(video_link_fallback_html(source, video_details), unsafe_allow_html=True)
        return

    st.markdown(static_video_placeholder_html(video_details), unsafe_allow_html=True)


def selectbox_index(options: list[str], selected: str | None) -> int:
    if selected and selected in options:
        return options.index(selected)
    return 0


def related_file(directory: Path, stem: str, suffixes: tuple[str, ...]) -> Path | None:
    for suffix in suffixes:
        path = directory / f"{stem}{suffix}"
        if path.exists():
            return path
    return None


def svg_icon(name: str) -> str:
    icons = {
        "analysis": (
            '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2">'
            '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="9" cy="18" r="3"/>'
            '<path d="M8.7 7.2l5.6 1.6M7.5 8.7l1.2 8M16.2 9.5l-6.6 6.7"/></svg>'
        ),
        "source": (
            '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2">'
            '<path d="M10 13a4 4 0 0 1 0-6l2-2a4 4 0 0 1 6 6l-1 1"/>'
            '<path d="M14 11a4 4 0 0 1 0 6l-2 2a4 4 0 0 1-6-6l1-1"/></svg>'
        ),
        "transcript": (
            '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2">'
            '<path d="M3 12h3l2-7 4 14 3-10 2 5h4"/></svg>'
        ),
    }
    return f'<span class="v2n-inline-icon v2n-icon-{html.escape(name)}">{icons.get(name, "")}</span>'


def panel_header_html(step: int, title: str, color_class: str, chip: str = "", icon: str = "") -> str:
    icon_html = svg_icon(icon) if icon else ""
    chip_html = ""
    if chip:
        chip_class = color_class.replace("step", "chip")
        chip_html = f'<span class="v2n-chip {chip_class}">{html.escape(chip)}</span>'
    return (
        '<div class="v2n-panel-title">'
        '<div class="v2n-title-left">'
        f'<span class="v2n-step {color_class}">{step}</span>'
        f"<span>{html.escape(title)}</span>"
        f"{icon_html}"
        f"{chip_html}"
        "</div>"
        "</div>"
    )


def render_analysis_fullscreen_dialog(st, language: str, summary_text: str) -> None:
    @st.dialog(tr(language, "analysis_fullscreen"), width="large", icon=":material/open_in_full:")
    def dialog() -> None:
        st.markdown('<div class="v2n-fullscreen-summary">', unsafe_allow_html=True)
        st.markdown(summary_text)
        st.markdown("</div>", unsafe_allow_html=True)

    dialog()


def transcript_rows_html(rows: list[tuple[str, str]]) -> str:
    row_html = "".join(
        '<div class="v2n-row">'
        f'<div class="v2n-time">{html.escape(timestamp)}</div>'
        f"<div>{html.escape(text)}</div>"
        "</div>"
        for timestamp, text in rows
    )
    return f'<div class="v2n-transcript-list">{row_html}</div>'


def render_pipeline_progress(st, progress_state: dict[str, object]) -> None:
    progress = float(progress_state["progress"])
    st.progress(progress, text="Progress")


def hide_streamlit_toolbar(st) -> None:
    st.markdown(
        """
        <style>
        :root {
          --v2n-bg: #f5f7fb;
          --v2n-card: #ffffff;
          --v2n-border: #d9e1ec;
          --v2n-muted: #667085;
          --v2n-text: #172033;
          --v2n-blue: #2563eb;
          --v2n-green: #18a058;
          --v2n-purple: #6d4aff;
          --v2n-red: #ef4444;
          --v2n-panel-height: 780px;
        }
        .stApp {
          background: var(--v2n-bg);
          color: var(--v2n-text);
          font-size: 16px;
        }
        html, body, [data-testid="stAppViewContainer"] {
          background: var(--v2n-bg);
        }
        header[data-testid="stHeader"],
        header[data-testid="stAppHeader"],
        [data-testid="stHeader"],
        [data-testid="stAppHeader"],
        .stApp > header {
          display: none !important;
          height: 0 !important;
          min-height: 0 !important;
        }
        [data-testid="stAppViewContainer"] > .main {
          padding-top: 0 !important;
        }
        .block-container,
        [data-testid="stMainBlockContainer"] {
          max-width: 1920px;
          width: 100%;
          padding: clamp(1.45rem, 3.3vh, 2.6rem) 1.1rem 0.25rem;
        }
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stWidgetLabel"],
        label,
        input,
        textarea {
          font-size: .98rem;
        }
        div[data-testid="stMarkdownContainer"] h1 {
          font-size: 1.28rem;
          line-height: 1.25;
          margin: .35rem 0 .45rem;
        }
        div[data-testid="stMarkdownContainer"] h2 {
          font-size: 1.08rem;
          line-height: 1.3;
          margin: .55rem 0 .35rem;
        }
        div[data-testid="stMarkdownContainer"] h3 {
          font-size: 1rem;
          line-height: 1.35;
          margin: .5rem 0 .28rem;
        }
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        [data-testid="stSidebar"] {
          border-right: 1px solid var(--v2n-border);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          border: 1px solid var(--v2n-border);
          border-radius: 14px;
          box-shadow: 0 10px 30px rgba(16, 24, 40, 0.05);
          background: var(--v2n-card);
          height: var(--v2n-panel-height) !important;
          min-height: var(--v2n-panel-height) !important;
          max-height: var(--v2n-panel-height) !important;
          overflow-x: hidden !important;
          overflow-y: hidden !important;
          box-sizing: border-box;
        }
        @keyframes v2nNoticeFade {
          0% {
            opacity: 0;
            transform: translate(-50%, -46%) scale(.98);
          }
          8% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
          }
          88% {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
          }
          100% {
            opacity: 0;
            transform: translate(-50%, -54%) scale(.98);
          }
        }
        .v2n-center-notice {
          position: fixed;
          left: 50%;
          top: 50%;
          z-index: 999999;
          max-width: min(560px, calc(100vw - 48px));
          min-width: min(420px, calc(100vw - 48px));
          padding: 18px 22px;
          border-radius: 16px;
          border: 1px solid #fecaca;
          background: #fff;
          box-shadow: 0 24px 70px rgba(16, 24, 40, .22);
          color: #172033;
          font-size: .98rem;
          line-height: 1.5;
          font-weight: 750;
          text-align: center;
          pointer-events: none;
          animation: v2nNoticeFade 11.5s ease-in-out forwards;
        }
        .v2n-center-notice-error {
          border-color: #fecaca;
          background: #fff5f5;
          color: #b42318;
        }
        .v2n-center-notice-warning {
          border-color: #fed7aa;
          background: #fff7ed;
          color: #9a3412;
        }
        .v2n-center-notice-success {
          border-color: #bbf7d0;
          background: #f0fdf4;
          color: #166534;
        }
        .v2n-header {
          display: flex;
          align-items: center;
          min-height: 60px;
          padding: 0 0 8px;
        }
        .v2n-brand {
          display: flex;
          align-items: center;
          gap: 12px;
          color: var(--v2n-text);
          font-weight: 800;
          font-size: 2.05rem;
        }
        .v2n-logo {
          width: 54px;
          height: 54px;
          display: block;
          flex: 0 0 54px;
        }
        .v2n-logo-fallback {
          width: 54px;
          height: 54px;
          border-radius: 9px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: #ffffff;
          background: #2563eb;
          font-size: 1.52rem;
        }
        div[data-testid="stSegmentedControl"] {
          display: flex;
          justify-content: flex-end;
          padding-top: 2px;
        }
        div[data-testid="stSegmentedControl"] [role="radiogroup"] {
          border: 1px solid #d7deea;
          border-radius: 10px;
          background: #ffffff;
          padding: 2px;
          box-shadow: 0 6px 18px rgba(16, 24, 40, 0.04);
        }
        div[data-testid="stSegmentedControl"] label {
          min-height: 30px !important;
          border-radius: 8px !important;
          font-weight: 800;
          font-size: .9rem;
        }
        div[data-testid="stPopover"] > button {
          min-height: 34px;
          width: 100%;
          border: 1px solid #d7deea;
          border-radius: 10px;
          background: #ffffff;
          color: #172033;
          font-weight: 800;
          box-shadow: 0 6px 18px rgba(16, 24, 40, 0.04);
        }
        div[data-testid="stPopover"] > button:hover {
          border-color: #b9c5d8;
          background: #fbfcfe;
        }
        div[data-testid="stPopoverBody"] {
          min-width: min(430px, calc(100vw - 32px));
        }
        .v2n-panel-title {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 12px;
        }
        .v2n-title-left {
          display: flex;
          align-items: center;
          gap: 10px;
          color: var(--v2n-text);
          font-weight: 800;
          font-size: 1.08rem;
        }
        .v2n-step {
          width: 24px;
          height: 24px;
          border-radius: 999px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-size: 0.8rem;
          font-weight: 800;
        }
        .v2n-step-red { background: var(--v2n-red); }
        .v2n-step-green { background: var(--v2n-green); }
        .v2n-step-purple { background: var(--v2n-purple); }
        .v2n-chip-row {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          gap: 10px;
          margin: 10px 0 12px;
        }
        .v2n-chip {
          border: 1px solid #e4e9f2;
          background: #f8fafc;
          border-radius: 10px;
          padding: 8px 12px;
          font-size: .93rem;
          font-weight: 700;
          color: #344054;
        }
        .v2n-chip-site {
          display: inline-flex;
          align-items: center;
          gap: 8px;
        }
        .v2n-chip-green {
          border-color: #cbf0d8;
          background: #ecfdf3;
          color: #14833b;
        }
        .v2n-chip-purple {
          border-color: #ded7ff;
          background: #f2efff;
          color: #5b39dc;
        }
        .v2n-inline-icon {
          width: 20px;
          height: 20px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: #667085;
          flex: 0 0 auto;
        }
        .v2n-inline-icon svg {
          width: 100%;
          height: 100%;
        }
        .v2n-inline-icon svg:not([fill="none"]) {
          fill: currentColor;
        }
        .v2n-title-left .v2n-inline-icon {
          color: #667085;
          margin-left: 2px;
        }
        .v2n-chip .v2n-inline-icon {
          width: 18px;
          height: 18px;
        }
        .v2n-icon-source {
          color: #64748b;
        }
        .v2n-icon-transcript,
        .v2n-title-left .v2n-icon-transcript {
          color: #18a058;
        }
        .v2n-icon-analysis,
        .v2n-title-left .v2n-icon-analysis {
          color: #6d4aff;
        }
        .v2n-video-thumb {
          aspect-ratio: 16 / 9;
          min-height: 0;
          border-radius: 12px;
          background:
            radial-gradient(circle at 74% 34%, rgba(56, 189, 248, .48), transparent 28%),
            linear-gradient(135deg, #0c1b3a 0%, #102451 48%, #111827 100%);
          position: relative;
          overflow: hidden;
          color: white;
          padding: 22px;
          margin-top: 10px;
          border: 1px solid #12244a;
        }
        div[data-testid="stVideo"],
        div[data-testid="stVideo"] video {
          aspect-ratio: 16 / 9;
          width: 100%;
        }
        div[data-testid="stVideo"] {
          margin-bottom: 0;
        }
        .v2n-video-thumb:before {
          content: "";
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(255,255,255,.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.06) 1px, transparent 1px);
          background-size: 34px 34px;
          opacity: .38;
        }
        .v2n-thumb-title {
          position: relative;
          z-index: 1;
          max-width: 280px;
          font-size: 1.55rem;
          line-height: 1.16;
          font-weight: 850;
          letter-spacing: 0;
        }
        .v2n-play {
          position: absolute;
          left: 50%;
          top: 50%;
          transform: translate(-50%, -50%);
          width: 74px;
          height: 52px;
          border-radius: 14px;
          background: #ef4444;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.6rem;
          z-index: 1;
          box-shadow: 0 16px 30px rgba(239, 68, 68, .32);
        }
        .v2n-video-title {
          margin-top: 5px;
          color: #172033;
          font-size: 1.08rem;
          line-height: 1.28;
          font-weight: 850;
        }
        .v2n-video-link-fallback {
          aspect-ratio: 16 / 9;
          min-height: 0;
          border: 1px solid #d9e1ec;
          border-radius: 12px;
          background: #fbfcfe;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 10px;
          padding: 18px;
          margin-top: 10px;
          box-sizing: border-box;
          overflow-wrap: anywhere;
        }
        .v2n-video-link-title {
          color: #172033;
          font-size: 1.02rem;
          line-height: 1.35;
          font-weight: 850;
        }
        .v2n-video-link-fallback a {
          color: #2563eb;
          font-size: .95rem;
          font-weight: 750;
          text-decoration: none;
        }
        .v2n-video-subtitle {
          margin-top: 2px;
          color: #667085;
          font-size: .94rem;
          line-height: 1.35;
        }
        .v2n-transcript-list {
          border-top: 1px solid #edf1f7;
          margin-top: 8px;
          max-height: clamp(300px, calc(100vh - 470px), 460px);
          overflow-y: auto;
          padding-right: 4px;
        }
        .v2n-row {
          display: grid;
          grid-template-columns: 78px 1fr;
          gap: 16px;
          padding: 11px 2px;
          border-bottom: 1px solid #edf1f7;
          color: #1f2937;
          font-size: .98rem;
          line-height: 1.38;
        }
        .v2n-time {
          color: var(--v2n-green);
          font-weight: 800;
          text-align: right;
          font-variant-numeric: tabular-nums;
        }
        .v2n-fullscreen-summary {
          color: #1f2937;
          font-size: 1.04rem;
          line-height: 1.62;
          max-height: calc(100vh - 180px);
          overflow-y: auto;
          padding-right: 8px;
        }
        .v2n-progress-spacer {
          min-height: 38px;
        }
        .stButton > button {
          border-radius: 10px;
          min-height: 42px;
          font-weight: 800;
          font-size: .92rem;
          gap: 3px;
        }
        .stButton > button[kind="primary"] {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: #2563eb;
          border-color: #2563eb;
          color: #ffffff;
        }
        .stButton > button [data-testid="stIconMaterial"] {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 1.22rem;
          min-width: 1.22rem;
          height: 1.22rem;
          margin: 0 !important;
          line-height: 1;
        }
        .stButton > button[kind="primary"] [data-testid="stIconMaterial"] {
          color: #ffffff;
          font-size: 1.48rem;
        }
        .stButton > button[kind="primary"]:hover {
          background: #1d4ed8;
          border-color: #1d4ed8;
          color: #ffffff;
        }
        .stButton > button[kind="tertiary"] {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: #ffffff;
          border: 1px solid #d7deea;
          border-radius: 10px;
          color: #111827;
        }
        .stButton > button[kind="tertiary"] [data-testid="stIconMaterial"] {
          color: #6b7280;
          font-size: 1.1rem;
        }
        .stButton > button[kind="tertiary"]:hover {
          background: #fbfcfe;
          border-color: #b9c5d8;
          color: #111827;
        }
        div[data-testid="stDownloadButton"] > button {
          border-radius: 10px;
          min-height: 38px;
          font-weight: 800;
          font-size: .84rem;
        }
        .stTextArea textarea, .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
          border-radius: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def app() -> None:
    import streamlit as st

    logo_uri = asset_data_uri(UI_LOGO_PATH)
    logo_html = (
        f'<img class="v2n-logo" src="{html.escape(logo_uri)}" alt="Video2Notes logo">'
        if logo_uri
        else '<span class="v2n-logo-fallback">▶</span>'
    )

    st.set_page_config(
        page_title="Video2Notes",
        page_icon=logo_uri or "▶",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    hide_streamlit_toolbar(st)

    header_col, actions_col = st.columns([7.2, 1.8], vertical_alignment="center")
    with header_col:
        st.markdown(
            f"""
            <div class="v2n-header">
              <div class="v2n-brand">{logo_html}<span>Video2Notes</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with actions_col:
        language_col, settings_col = st.columns([0.9, 1.1], gap="small", vertical_alignment="center")
        with language_col:
            language_label = st.segmented_control(
                "Language",
                ["EN", "中文"],
                default="EN",
                key="ui_language_segment",
                label_visibility="collapsed",
                width="stretch",
            )
    language = "zh" if language_label == "中文" else "en"

    api_store = load_api_store()
    active_profile = get_active_api_profile(api_store)
    if "confirmed_api_profile" not in st.session_state and active_profile:
        st.session_state["confirmed_api_profile"] = active_profile
    with settings_col:
        render_api_settings(st, language, api_store, active_profile)
    llm_config = confirmed_llm_config(st)
    running_process = active_process(st)

    source_col, transcript_col, notes_col = st.columns([1, 1, 1], gap="medium")
    summary_files = list_recent_files(DEFAULT_SUMMARIES_DIR, suffixes=(".md",))
    selected_summary_path = None
    selected_summary_text = sample_summary(language)
    selected_summary_full_text = selected_summary_text

    with source_col:
        with st.container(border=True, height=MAIN_PANEL_HEIGHT):
            st.markdown(
                panel_header_html(1, tr(language, "source_panel"), "v2n-step-red", icon="source"),
                unsafe_allow_html=True,
            )
            url_text = st.text_area(
                tr(language, "batch_urls"),
                value="",
                placeholder="https://www.youtube.com/watch?v=...\nhttps://www.bilibili.com/video/BV...",
                height=86,
                key="run_batch_urls",
                label_visibility="collapsed",
            )
            import_col, cookies_col = st.columns(2, gap="small")
            with import_col:
                local_media_path = st.text_input(
                    tr(language, "local_media_path"),
                    value="",
                    placeholder="data/imports/demo.mp4",
                    help=tr(language, "local_media_path_help"),
                    key="run_local_media_path",
                )
            with cookies_col:
                cookies_path = st.text_input(
                    tr(language, "yt_dlp_cookies"),
                    value="",
                    placeholder="cookies.txt",
                    help=tr(language, "yt_dlp_cookies_help"),
                    key="run_cookies_path",
                )
            current_source_text = local_media_path.strip() or url_text
            preview_url_text = (
                str(st.session_state.get("pipeline_url_text") or "") if running_process else current_source_text
            )
            video_details = video_preview_details(preview_url_text, language)
            render_video_source_player(st, preview_url_text, video_details)
            st.markdown(
                f"""
                <div class="v2n-video-title">{html.escape(video_details["title"])}</div>
                <div class="v2n-video-subtitle">{html.escape(video_details["source"])} · Video2Notes</div>
                """,
                unsafe_allow_html=True,
            )
            opt_a, opt_b, opt_c = st.columns([1.1, 1.7, 1.1])
            with opt_a:
                playlist = st.checkbox(tr(language, "expand_playlist"), value=False)
            with opt_b:
                skip_llm = st.checkbox(tr(language, "skip_llm"), value=False)
            with opt_c:
                reuse_existing = st.checkbox(tr(language, "reuse_existing"), value=True)

    with transcript_col:
        with st.container(border=True, height=MAIN_PANEL_HEIGHT):
            st.markdown(
                panel_header_html(2, tr(language, "subtitle_panel"), "v2n-step-green", "Whisper", "transcript"),
                unsafe_allow_html=True,
            )
            control_a, control_b = st.columns(2)
            with control_a:
                whisper_model = st.selectbox(
                    tr(language, "whisper_model"),
                    ["tiny", "base", "small", "medium", "large", "turbo"],
                    index=2,
                )
            with control_b:
                device_options = {
                    tr(language, "gpu"): "cuda",
                    tr(language, "cpu"): "cpu",
                }
                device_label = st.selectbox(tr(language, "device"), list(device_options), index=0)
                device = device_options[device_label]
            language_options = {
                tr(language, "source_language_auto"): "auto",
                tr(language, "source_language_chinese"): "Chinese",
                tr(language, "source_language_english"): "English",
            }
            language_label = st.selectbox(
                tr(language, "source_language"),
                list(language_options),
                index=0,
            )
            source_language = language_options[language_label]
            preview_url_text = (
                str(st.session_state.get("pipeline_url_text") or "") if running_process else current_source_text
            )
            active_subtitle_path = current_run_file(
                preview_url_text,
                DEFAULT_SUBTITLES_DIR,
                (".srt", ".txt", ".vtt", ".tsv", ".json"),
            )
            log_transcript_rows = transcript_rows_from_text(
                read_pipeline_log(st.session_state.get("pipeline_log_path"), max_chars=TRANSCRIPT_PREVIEW_CHARS),
                include_plain_text=False,
            )
            if active_subtitle_path:
                subtitle_text = read_text_preview(active_subtitle_path, max_chars=TRANSCRIPT_PREVIEW_CHARS)
                file_transcript_rows = transcript_rows_from_text(subtitle_text)
                if running_process and len(log_transcript_rows) > len(file_transcript_rows):
                    transcript_rows = log_transcript_rows
                else:
                    transcript_rows = file_transcript_rows or log_transcript_rows or sample_transcript_rows(language)
            else:
                transcript_rows = log_transcript_rows or sample_transcript_rows(language)
            st.markdown(transcript_rows_html(transcript_rows), unsafe_allow_html=True)

    with notes_col:
        with st.container(border=True, height=MAIN_PANEL_HEIGHT):
            notes_header_col, notes_action_col = st.columns([1, 0.16], vertical_alignment="center")
            with notes_header_col:
                st.markdown(
                    panel_header_html(3, tr(language, "ai_panel"), "v2n-step-purple", "LLM", "analysis"),
                    unsafe_allow_html=True,
                )
            with notes_action_col:
                expand_analysis_clicked = st.button(
                    " ",
                    icon=":material/open_in_full:",
                    help=tr(language, "expand_analysis"),
                    key="expand_analysis_button",
                    use_container_width=True,
                )
            analysis_language_options = {
                tr(language, "chinese_notes"): "Chinese",
                tr(language, "english_notes"): "English",
            }
            analysis_language_label = st.selectbox(
                tr(language, "notes_language"),
                list(analysis_language_options),
                index=1 if language == "en" else 0,
                key=f"run_analysis_language_{language}",
            )
            analysis_language = analysis_language_options[analysis_language_label]
            llm_task = st.text_area(
                tr(language, "llm_task"),
                value="",
                placeholder=tr(language, "llm_task_placeholder"),
                help=tr(language, "llm_task_help"),
                height=126,
                key="run_llm_task",
            )
            if summary_files:
                summary_options = [display_path(path) for path in summary_files]
                selected_summary = st.selectbox(
                    tr(language, "select_summary"),
                    summary_options,
                    index=selectbox_index(summary_options, st.session_state.get("active_summary_path")),
                    key="summary_select",
                )
                st.session_state["active_summary_path"] = selected_summary
                selected_summary_path = Path(selected_summary)
                selected_summary_full_text = selected_summary_path.read_text(encoding="utf-8", errors="replace")
                selected_summary_text = selected_summary_full_text
            with st.container(height=300, border=False):
                st.markdown(selected_summary_text)
            if expand_analysis_clicked:
                render_analysis_fullscreen_dialog(st, language, selected_summary_text)
            if selected_summary_path:
                st.download_button(
                    tr(language, "download_markdown"),
                    data=selected_summary_full_text,
                    file_name=selected_summary_path.name,
                    mime="text/markdown",
                    key=f"download_summary_{selected_summary_path.stem}",
                    use_container_width=True,
                )

    subtitle_format = "srt"
    stored_process = st.session_state.get("pipeline_process")
    active_run_state = read_active_run_state()
    running_process = active_process(st)
    if running_process and not active_run_state and st.session_state.get("pipeline_log_path"):
        write_active_run_state(
            process_pid(running_process),
            Path(str(st.session_state["pipeline_log_path"])),
            str(st.session_state.get("pipeline_url_text") or current_source_text).strip(),
            bool(st.session_state.get("pipeline_skip_llm", skip_llm)),
        )
        active_run_state = read_active_run_state()
    active_run_ended = bool(active_run_state) and running_process is None and stored_process is None
    if (stored_process and running_process is None) or active_run_ended:
        if isinstance(stored_process, subprocess.Popen):
            returncode = stored_process.poll()
        else:
            active_log = read_pipeline_log(active_run_state.get("log_path"))
            active_skip_llm = bool(active_run_state.get("skip_llm"))
            returncode = 0 if pipeline_log_indicates_success(active_log, active_skip_llm) else 1
        log_path_value = st.session_state.get("pipeline_log_path") or active_run_state.get("log_path")
        if log_path_value:
            sanitize_log_file(Path(log_path_value))
        if returncode == 0:
            completed_source_text = str(
                st.session_state.get("pipeline_url_text")
                or active_run_state.get("url_text")
                or current_source_text
            ).strip()
            completed_log_text = read_pipeline_log(log_path_value)
            completed_summary_path = summary_path_from_pipeline_log(completed_log_text) or current_run_file(
                completed_source_text,
                DEFAULT_SUMMARIES_DIR,
                (".md",),
            )
            if completed_summary_path:
                st.session_state["active_summary_path"] = display_path(completed_summary_path)
            st.session_state["pipeline_last_status"] = ("success", tr(language, "pipeline_completed"))
            st.session_state["pipeline_completed"] = True
        elif returncode is not None:
            message_key = "pipeline_stopped" if returncode < 0 else "pipeline_failed"
            message = tr(language, message_key, code=returncode) if message_key == "pipeline_failed" else tr(
                language, message_key
            )
            if message_key == "pipeline_failed":
                message = summarize_pipeline_error(log_path_value, message)
                set_transient_notice(st, "error", message)
                st.session_state["pipeline_last_status"] = ("error", message)
            else:
                st.session_state["pipeline_last_status"] = ("warning", message)
            st.session_state["pipeline_completed"] = False
        st.session_state.pop("pipeline_process", None)
        clear_active_run_state()
        running_process = None
        st.rerun()

    render_transient_notice(st)
    progress_url_text = str(st.session_state.get("pipeline_url_text") or current_source_text)
    progress_state = pipeline_progress_state(
        progress_url_text,
        read_pipeline_log(st.session_state.get("pipeline_log_path")),
        running=running_process is not None,
        skip_llm=bool(st.session_state.get("pipeline_skip_llm", skip_llm)),
        completed=bool(st.session_state.get("pipeline_completed")),
    )

    bottom_progress, bottom_actions = st.columns([4.2, 0.82], gap="medium", vertical_alignment="bottom")
    with bottom_progress:
        progress_visible = running_process is not None or float(progress_state["progress"]) > 0
        if progress_visible:
            render_pipeline_progress(st, progress_state)
        else:
            st.markdown('<div class="v2n-progress-spacer"></div>', unsafe_allow_html=True)
    with bottom_actions:
        run_col, stop_col = st.columns(2, gap="small")
        with run_col:
            run_clicked = st.button(
                tr(language, "run_pipeline"),
                type="primary",
                icon=":material/play_arrow:",
                disabled=running_process is not None,
                key="run_pipeline_button",
                use_container_width=True,
            )
        with stop_col:
            stop_clicked = st.button(
                tr(language, "stop_pipeline"),
                type="tertiary",
                icon=":material/check_box_outline_blank:",
                disabled=running_process is None,
                key="stop_pipeline_button",
                use_container_width=True,
            )

    if stop_clicked and running_process:
        stop_pipeline_process(running_process)
        st.session_state["pipeline_last_status"] = ("warning", tr(language, "pipeline_stopped"))
        st.session_state["pipeline_completed"] = False
        st.session_state.pop("pipeline_process", None)
        clear_active_run_state()
        st.rerun()

    if run_clicked:
        local_media_path_clean = local_media_path.strip()
        active_source_text = local_media_path_clean or url_text.strip()
        if not local_media_path_clean and not first_video_link(url_text):
            error_message = tr(language, "source_required")
            set_transient_notice(st, "error", error_message)
            st.session_state["pipeline_last_status"] = ("error", error_message)
            st.rerun()
        elif not skip_llm and not llm_config.is_configured:
            error_message = tr(language, "api_not_configured")
            set_transient_notice(st, "error", error_message)
            st.session_state["pipeline_last_status"] = ("error", error_message)
            st.rerun()
        else:
            command = build_pipeline_command(
                url="",
                url_text="" if local_media_path_clean else url_text,
                url_file="",
                media_file=local_media_path_clean,
                cookies_path=cookies_path,
                playlist=False if local_media_path_clean else playlist,
                whisper_model=whisper_model,
                source_language=source_language,
                subtitle_format=subtitle_format,
                device=device,
                reuse_existing=reuse_existing,
                skip_llm=skip_llm,
                llm_task=llm_task,
                analysis_language=analysis_language,
            )
            try:
                process, log_path = start_pipeline_process(command, llm_config)
            except Exception as exc:
                error_message = sanitize_project_paths(str(exc))
                set_transient_notice(st, "error", error_message)
                st.session_state["pipeline_last_status"] = ("error", error_message)
                st.rerun()
            else:
                st.session_state["pipeline_process"] = process
                st.session_state["pipeline_log_path"] = display_path(log_path)
                st.session_state["pipeline_url_text"] = active_source_text
                st.session_state["pipeline_skip_llm"] = skip_llm
                st.session_state["pipeline_completed"] = False
                write_active_run_state(process.pid, log_path, active_source_text, skip_llm)
                st.session_state["pipeline_last_status"] = ("info", tr(language, "pipeline_started"))
                st.rerun()

    if running_process:
        time.sleep(1)
        st.rerun()



if __name__ == "__main__":
    app()
