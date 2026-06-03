import argparse

from video2notes import __version__
from video2notes import analyze_cli, pipeline, transcriber
from video2notes.paths import display_path, user_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video2notes",
        description="Download videos, transcribe them with Whisper, and analyze subtitles with an LLM.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full video2notes pipeline.")
    for action in pipeline.build_parser()._actions:
        if action.dest == "help":
            continue
        run_parser._add_action(action)
    run_parser.set_defaults(func=pipeline.run_many)

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe an existing audio file.")
    for action in transcriber.build_parser()._actions:
        if action.dest == "help":
            continue
        transcribe_parser._add_action(action)
    transcribe_parser.set_defaults(func=_run_transcriber)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze an existing subtitle file.")
    for action in analyze_cli.build_parser()._actions:
        if action.dest == "help":
            continue
        analyze_parser._add_action(action)
    analyze_parser.set_defaults(func=_run_analyzer)

    return parser


def _run_transcriber(args: argparse.Namespace) -> None:
    language = args.language or None
    output_path = transcriber.transcribe_audio(
        audio_path=args.audio,
        output_dir=args.output_dir,
        model=args.model,
        language=language,
        output_format=args.output_format,
        device=args.device,
    )
    print(f"Subtitles saved: {display_path(output_path)}")


def _run_analyzer(args: argparse.Namespace) -> None:
    transcript = user_path(args.subtitle).read_text(encoding="utf-8")
    config = analyze_cli.LLMConfig.from_env()
    summary = analyze_cli.analyze_subtitles(config, transcript, args.task, args.analysis_language)
    output_path = user_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary, encoding="utf-8")
    print(f"LLM analysis saved: {display_path(output_path)}")
    if args.export_artifacts:
        artifact_paths = analyze_cli.export_summary_artifacts(summary, output_path.parent, output_path.stem)
        for artifact_name, artifact_path in artifact_paths.items():
            print(f"Exported {artifact_name}: {display_path(artifact_path)}")


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
