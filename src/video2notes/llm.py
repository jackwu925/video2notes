import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import requests


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_CHUNK_CHARS = 30000
DEFAULT_TASK = "请分析这段视频字幕，帮助我理解视频讲了什么，并提炼出结构化知识点、关键概念和结论启发。"
DEFAULT_ENGLISH_TASK = (
    "Analyze these video subtitles, explain what the video is about, and extract structured notes, key concepts, "
    "and implications."
)
DEFAULT_ANALYSIS_LANGUAGE = "Chinese"
LLM_PROVIDER_PRESETS = {
    "OpenAI": {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "requires_api_key": True,
    },
    "SiliconFlow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V4-Pro",
        "requires_api_key": True,
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "requires_api_key": True,
    },
    "Qwen Global": {
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "requires_api_key": True,
    },
    "Qwen China": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "requires_api_key": True,
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
        "requires_api_key": True,
    },
    "Ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "llama3.1",
        "requires_api_key": False,
    },
    "LM Studio": {
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "local-model",
        "requires_api_key": False,
    },
    "Custom": {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "requires_api_key": True,
    },
}
ANALYSIS_LANGUAGE_CHOICES = ("auto", "Chinese", "English")
ANALYSIS_LANGUAGE_ALIASES = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "cn": "Chinese",
    "chinese": "Chinese",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "english": "English",
}


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_env_file(Path(".env"))
        return cls(
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
            model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
            timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> Iterable[str]:
    cleaned = text.strip()
    for start in range(0, len(cleaned), max_chars):
        yield cleaned[start : start + max_chars]


def chat_completion(config: LLMConfig, messages: list[dict[str, str]], temperature: float = 0.2) -> str:
    if not config.is_configured:
        raise RuntimeError("LLM_API_KEY is not configured.")

    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.model,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=config.timeout_seconds,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"LLM request failed with HTTP {response.status_code}: {response.text}")

    payload = response.json()
    return payload["choices"][0]["message"]["content"].strip()


def get_provider_preset(provider: str) -> dict[str, object]:
    return LLM_PROVIDER_PRESETS.get(provider, LLM_PROVIDER_PRESETS["Custom"]).copy()


def normalize_analysis_language(language: str | None) -> str:
    if not language:
        return DEFAULT_ANALYSIS_LANGUAGE

    normalized = language.strip()
    if not normalized:
        return DEFAULT_ANALYSIS_LANGUAGE

    if normalized.lower() in {"auto", "same", "same-as-transcript"}:
        return "auto"

    return ANALYSIS_LANGUAGE_ALIASES.get(normalized.lower(), normalized)


def analysis_language_instruction(language: str | None) -> str:
    normalized = normalize_analysis_language(language)
    if normalized == "English":
        return (
            "Write the final Markdown analysis in English. Keep exact timestamps from the transcript when available."
        )
    if normalized == "auto":
        return (
            "Use the same language as the transcript for the final Markdown analysis. "
            "Keep exact timestamps from the transcript when available."
        )
    return "请使用中文输出最终 Markdown 分析。如果字幕中有时间戳，必须保留真实时间戳。"


def output_sections_instruction(language: str | None) -> str:
    normalized = normalize_analysis_language(language)
    if normalized == "English":
        return (
            "Use Markdown with exactly these headings: # Video Analysis Report, ## One-Sentence Summary, "
            "## Core Content, ## Chapters / Timeline, ## Key Points, ## Important Concepts, "
            "## Conclusions and Implications."
        )
    if normalized == "auto":
        return (
            "Use clear Markdown sections for the report title, one-sentence summary, core content, "
            "chapters/timeline, key points, important concepts, and conclusions/implications."
        )
    return (
        "请使用 Markdown 输出，并严格使用这些标题：# 视频分析报告、## 一句话总结、## 核心内容、"
        "## 章节/时间线、## 关键观点、## 重要概念、## 结论与启发。"
    )


def timestamp_instruction(language: str | None) -> str:
    normalized = normalize_analysis_language(language)
    if normalized == "English":
        return (
            "If the transcript contains SRT/VTT/TSV/JSON timestamps, the Chapters / Timeline section must quote "
            "real timestamps from the transcript."
        )
    if normalized == "auto":
        return (
            "If the transcript contains SRT/VTT/TSV/JSON timestamps, the timeline section must quote real "
            "timestamps from the transcript."
        )
    return "如果字幕包含 SRT/VTT/TSV/JSON 时间戳，章节/时间线必须引用真实时间戳，不要声称没有时间戳。"


def system_prompt(language: str | None) -> str:
    normalized = normalize_analysis_language(language)
    if normalized in {"English", "auto"}:
        return (
            "You are a rigorous video subtitle analysis assistant. Analyze only the provided transcript and do not "
            "invent information that is not present."
        )
    return "你是严谨的视频内容分析助手。只基于字幕分析，不要编造字幕中没有的信息。"


def chunk_prompt(transcript_chunk: str, index: int, total: int, analysis_language: str | None) -> str:
    normalized = normalize_analysis_language(analysis_language)
    if normalized in {"English", "auto"}:
        return (
            f"This is part {index}/{total} of a long video transcript. "
            "Extract the covered time range, main content, key points, terms, and possible action items. "
            "If the source contains SRT/VTT/TSV/JSON timestamps, preserve important timestamp ranges.\n\n"
            f"{analysis_language_instruction(analysis_language)}\n\n"
            f"Transcript:\n{transcript_chunk}"
        )

    return (
        f"这是长视频字幕的第 {index}/{total} 段。"
        "请提取本段覆盖的起止时间、主要内容、关键观点、术语和可能的行动项。"
        "如果原文包含 SRT/VTT/TSV/JSON 时间戳，必须在摘要中保留关键时间段。\n\n"
        f"{analysis_language_instruction(analysis_language)}\n\n"
        f"字幕：\n{transcript_chunk}"
    )


def final_analysis_prompt(transcript: str, task: str, analysis_language: str | None) -> str:
    normalized = normalize_analysis_language(analysis_language)
    effective_task = DEFAULT_ENGLISH_TASK if normalized == "English" and task == DEFAULT_TASK else task
    if normalized in {"English", "auto"}:
        return (
            f"{effective_task}\n\n"
            f"{analysis_language_instruction(analysis_language)}\n"
            f"{output_sections_instruction(analysis_language)}\n"
            f"{timestamp_instruction(analysis_language)}\n\n"
            f"Transcript:\n{transcript}"
        )

    return (
        f"{effective_task}\n\n"
        f"{analysis_language_instruction(analysis_language)}\n"
        f"{output_sections_instruction(analysis_language)}\n"
        f"{timestamp_instruction(analysis_language)}\n\n"
        f"字幕：\n{transcript}"
    )


def analyze_subtitles(
    config: LLMConfig,
    transcript: str,
    task: str = DEFAULT_TASK,
    analysis_language: str | None = DEFAULT_ANALYSIS_LANGUAGE,
) -> str:
    transcript = transcript.strip()
    if not transcript:
        raise ValueError("Transcript is empty.")

    chunks = list(chunk_text(transcript))
    if len(chunks) == 1:
        return analyze_chunk(config, chunks[0], task, analysis_language)

    partial_summaries = []
    for index, chunk in enumerate(chunks, start=1):
        partial_summaries.append(summarize_chunk(config, chunk, index, len(chunks), analysis_language))

    combined = "\n\n".join(partial_summaries)
    combined_task = task
    if normalize_analysis_language(analysis_language) == "English":
        combined_task = DEFAULT_ENGLISH_TASK if task == DEFAULT_TASK else task
        combined_task = (
            f"{combined_task}\n\nThese are partial summaries of a long video. "
            "Merge them into a final analysis."
        )
    else:
        combined_task = f"{combined_task}\n\n这些内容是长视频分段摘要，请整合成最终分析。"

    return analyze_chunk(
        config,
        combined,
        combined_task,
        analysis_language,
    )


def summarize_chunk(
    config: LLMConfig,
    transcript_chunk: str,
    index: int,
    total: int,
    analysis_language: str | None = DEFAULT_ANALYSIS_LANGUAGE,
) -> str:
    return chat_completion(
        config,
        messages=[
            {
                "role": "system",
                "content": system_prompt(analysis_language),
            },
            {
                "role": "user",
                "content": chunk_prompt(transcript_chunk, index, total, analysis_language),
            },
        ],
    )


def analyze_chunk(
    config: LLMConfig,
    transcript: str,
    task: str,
    analysis_language: str | None = DEFAULT_ANALYSIS_LANGUAGE,
) -> str:
    return chat_completion(
        config,
        messages=[
            {
                "role": "system",
                "content": system_prompt(analysis_language),
            },
            {
                "role": "user",
                "content": final_analysis_prompt(transcript, task, analysis_language),
            },
        ],
    )
