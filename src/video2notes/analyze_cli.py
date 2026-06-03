import argparse
from pathlib import Path

from video2notes.exports import export_summary_artifacts
from video2notes.llm import DEFAULT_ANALYSIS_LANGUAGE, DEFAULT_TASK, LLMConfig, analyze_subtitles
from video2notes.paths import display_path, user_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze an existing subtitle transcript with an LLM.")
    parser.add_argument("--subtitle", required=True, type=Path, help="Path to the transcript text file.")
    parser.add_argument("--output", required=True, type=Path, help="Path to the Markdown analysis output.")
    parser.add_argument("--task", default=DEFAULT_TASK, help="Instruction for subtitle analysis.")
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
    args = build_parser().parse_args()
    transcript = user_path(args.subtitle).read_text(encoding="utf-8")
    config = LLMConfig.from_env()
    summary = analyze_subtitles(config, transcript, args.task, args.analysis_language)

    output_path = user_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary, encoding="utf-8")
    print(f"LLM analysis saved: {display_path(output_path)}")
    if args.export_artifacts:
        artifact_paths = export_summary_artifacts(summary, output_path.parent, output_path.stem)
        for artifact_name, artifact_path in artifact_paths.items():
            print(f"Exported {artifact_name}: {display_path(artifact_path)}")
