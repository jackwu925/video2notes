import json
import re
from pathlib import Path


SECTION_ALIASES = {
    "chapters": ("章节", "时间线", "timeline", "chapter"),
    "key_points": ("关键观点", "key points", "main points"),
    "concepts": ("重要概念", "概念", "术语", "concept", "terms"),
    "takeaways": ("结论与启发", "结论", "启发", "takeaway", "implication"),
}

TIME_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?)\s*(?:-|--|–|—|至|到)\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?)"
)


def export_summary_artifacts(summary: str, output_dir: Path, key: str) -> dict[str, Path]:
    artifact_dir = output_dir / key
    artifact_dir.mkdir(parents=True, exist_ok=True)

    sections = split_markdown_sections(summary)
    artifacts: dict[str, Path] = {}

    for artifact_name, aliases in SECTION_ALIASES.items():
        content = find_section(sections, aliases)
        if content:
            path = artifact_dir / f"{artifact_name}.md"
            path.write_text(content, encoding="utf-8")
            artifacts[artifact_name] = path

    timeline_source = ""
    chapters_path = artifacts.get("chapters")
    if chapters_path:
        timeline_source = chapters_path.read_text(encoding="utf-8")
    timeline = extract_timeline(timeline_source)
    if timeline:
        path = artifact_dir / "timeline.json"
        path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["timeline"] = path

    return artifacts


def split_markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_title = "summary"
    sections[current_title] = []

    for line in markdown.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            current_title = heading.group(1).strip()
            sections.setdefault(current_title, [])
            continue
        sections.setdefault(current_title, []).append(line)

    return {title: "\n".join(lines).strip() for title, lines in sections.items() if "\n".join(lines).strip()}


def find_section(sections: dict[str, str], aliases: tuple[str, ...]) -> str:
    for title, content in sections.items():
        normalized_title = title.lower()
        if any(alias.lower() in normalized_title for alias in aliases):
            return f"# {title}\n\n{content}\n"
    return ""


def extract_timeline(markdown: str) -> list[dict[str, str]]:
    timeline = []
    for line in markdown.splitlines():
        match = TIME_RANGE_RE.search(line)
        if not match:
            continue
        title = TIME_RANGE_RE.sub("", line).strip(" -*:：")
        timeline.append(
            {
                "start": match.group("start"),
                "end": match.group("end"),
                "title": title,
            }
        )
    return timeline
