#!/usr/bin/env python3
"""WoWS Replay Analysis - Main Entry Point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable


def _print_usage() -> None:
    print("WoWS Replay Analysis Tools")
    print("=" * 70)
    print("python main.py analyze <replay.wowsreplay or replay.json>")
    print("python main.py extract <replay.wowsreplay> [output.json] [--legacy legacy.json]")
    print("python main.py entities <replay.json>")
    print("python main.py battle-stats <replay.json> [output.json]")
    print("python main.py comprehensive <replay.json> [--output dir]")
    print("python main.py setup")
    print("python main.py status")
    print("python main.py update-render <baseline_replay.wowsreplay> <candidate_replay.wowsreplay> [options]")


def _invoke_main(module_main: Callable[[], None], argv: list[str]) -> int:
    old_argv = sys.argv[:]
    sys.argv = argv
    try:
        module_main()
    finally:
        sys.argv = old_argv
    return 0


def _run_extract(args: list[str]) -> int:
    if not args:
        print("Error: Replay file required")
        return 1

    from core.replay_extract import extract_replay_to_files

    replay_path = args[0]
    output_json = args[1] if len(args) > 1 and not args[1].startswith("--") else str(Path(replay_path).with_suffix(".json"))

    legacy_output = None
    if "--legacy" in args:
        idx = args.index("--legacy")
        if idx + 1 < len(args):
            legacy_output = args[idx + 1]

    extract_replay_to_files(replay_path, output_json, legacy_output)
    print(f"Extraction complete: {output_json}")
    if legacy_output:
        print(f"Legacy export: {legacy_output}")
    return 0


def _run_analyze(args: list[str]) -> int:
    if not args:
        print("Error: Replay file required")
        return 1

    replay_input = Path(args[0])
    replay_to_analyze = replay_input

    if replay_input.suffix.lower() == ".wowsreplay":
        from core.replay_extract import extract_replay_to_files

        canonical_path = replay_input.with_suffix(".json")
        extract_replay_to_files(str(replay_input), str(canonical_path))
        replay_to_analyze = canonical_path
        print(f"Extracted canonical JSON: {canonical_path.name}")

    from tools.dev_tools.comprehensive_replay_analysis import ComprehensiveReplayAnalyzer

    analyzer = ComprehensiveReplayAnalyzer(str(replay_to_analyze))
    results = analyzer.analyze_complete()
    if not results:
        print("Analysis failed")
        return 1

    analyzer.save_all_analysis()
    analyzer.print_summary()
    print("Analysis complete")
    return 0


def _run_entities(args: list[str]) -> int:
    if not args:
        print("Error: Replay JSON file required")
        return 1
    from tools.dev_tools.entities_analyzer import main as entities_main

    return _invoke_main(entities_main, ["entities_analyzer.py", args[0]] + args[1:])


def _run_battle_stats(args: list[str]) -> int:
    if not args:
        print("Error: Replay JSON file required")
        return 1
    from tools.dev_tools.battle_stats_extractor import main as stats_main

    return _invoke_main(stats_main, ["battle_stats_extractor.py", args[0]] + args[1:])


def _run_comprehensive(args: list[str]) -> int:
    if not args:
        print("Error: Replay JSON file required")
        return 1
    from tools.dev_tools.comprehensive_replay_analysis import main as comprehensive_main

    return _invoke_main(comprehensive_main, ["comprehensive_replay_analysis.py"] + args)


def _run_setup(args: list[str]) -> int:
    from api.setup_api import main as setup_main

    setup_args = args if args else ["setup"]
    return _invoke_main(setup_main, ["setup_api.py"] + setup_args)


def _run_update_render(args: list[str]) -> int:
    from tools.update_render_bundle import main as update_main

    return _invoke_main(update_main, ["update_render_bundle.py"] + args)


def _run_status() -> int:
    from api.setup_api import show_status

    show_status()
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        _print_usage()
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    handlers = {
        "analyze": _run_analyze,
        "extract": _run_extract,
        "entities": _run_entities,
        "battle-stats": _run_battle_stats,
        "comprehensive": _run_comprehensive,
        "setup": _run_setup,
        "update-render": _run_update_render,
    }

    if command == "status":
        raise SystemExit(_run_status())

    fn = handlers.get(command)
    if fn is None:
        print(f"Unknown command: {command}")
        _print_usage()
        raise SystemExit(1)

    raise SystemExit(fn(args))


if __name__ == "__main__":
    main()
