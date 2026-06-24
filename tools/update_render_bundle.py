#!/usr/bin/env python3
"""One-shot render updater for a new WoWS version and all render metadata caches."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable, List


DEFAULT_RENDER_CONSUMABLE_KEYS = (
    "PCY020_RLSSearchPremium",
    "PCY016_SonarSearchPremium",
)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _invoke_main(module_main: Callable[[], int | None], argv: list[str]) -> int:
    old_argv = sys.argv[:]
    sys.argv = argv
    try:
        result = module_main()
    finally:
        sys.argv = old_argv
    if result is None:
        return 0
    return int(result)


@dataclass
class StepResult:
    name: str
    status: str
    detail: str


def _parse_args() -> argparse.Namespace:
    root = _root_dir()
    parser = argparse.ArgumentParser(
        description="Update replay-version support and refresh all core render metadata in one command.",
    )
    parser.add_argument("baseline_replay", help="Replay from the last known supported WoWS version")
    parser.add_argument("candidate_replay", help="Replay from the new WoWS version you want to support")
    parser.add_argument(
        "--gameparams",
        default=str(root / "content" / "GameParams.data"),
        help="Path to GameParams.data (default: content/GameParams.data)",
    )
    parser.add_argument(
        "--texts-root",
        default=str(root / "content" / "texts"),
        help="Path to unpacked client texts (default: content/texts)",
    )
    parser.add_argument(
        "--report-dir",
        default=str(root / "replay_debug" / "version_updates"),
        help="Directory for version update reports",
    )
    parser.add_argument("--skip-assets", action="store_true", help="Skip refreshing unpacked client assets before rebuilding metadata")
    parser.add_argument(
        "--assets-root",
        default="",
        help="Path to an already-unpacked asset root. If omitted, assets are unpacked from --game-root / game.path with wowsunpack.",
    )
    parser.add_argument(
        "--game-root",
        default="",
        help="Path to the WoWS install root (default: read from game.path). Used only when --assets-root is not provided.",
    )
    parser.add_argument("--keep-asset-stage", action="store_true", help="Keep the temporary unpacked asset staging directory")
    parser.add_argument("--no-apply", action="store_true", help="Do not create the new vendor version folder")
    parser.add_argument(
        "--allow-manual-review",
        action="store_true",
        help="Continue metadata rebuilds even if the replay-version report flags suspicious parser drift",
    )
    parser.add_argument("--skip-canonical-dump", action="store_true", help="Skip canonical JSON dumps in the version report")
    parser.add_argument("--dump-raw-packets", action="store_true", help="Dump all raw packet names for both replays")
    parser.add_argument("--dump-render-packets", action="store_true", help="Dump only render-relevant raw packets for both replays")
    parser.add_argument("--skip-ships-cache", action="store_true", help="Skip refreshing ships_cache.json from the WoWS API")
    parser.add_argument("--ships-limit", type=int, default=0, help="Limit ship-cache refresh to N ships (0 = all)")
    parser.add_argument("--ships-concurrency", type=int, default=6, help="Concurrent requests for ships_cache refresh")
    parser.add_argument("--ships-sleep", type=float, default=0.0, help="Sleep seconds between ship-cache API requests")
    parser.add_argument(
        "--consumable-keys",
        nargs="+",
        default=list(DEFAULT_RENDER_CONSUMABLE_KEYS),
        help="GameParams consumable keys to extract (default: standard radar/hydro keys)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = _root_dir()
    gameparams_path = Path(args.gameparams).expanduser().resolve()
    texts_root = Path(args.texts_root).expanduser().resolve()
    baseline_replay = Path(args.baseline_replay).expanduser().resolve()
    candidate_replay = Path(args.candidate_replay).expanduser().resolve()
    report_dir = Path(args.report_dir).expanduser().resolve()

    if not baseline_replay.exists():
        print(f"Baseline replay not found: {baseline_replay}")
        return 1
    if not candidate_replay.exists():
        print(f"Candidate replay not found: {candidate_replay}")
        return 1
    if not gameparams_path.exists():
        print(f"GameParams.data not found: {gameparams_path}")
        return 1

    results: List[StepResult] = []
    planned_steps = [
        ("render asset refresh", not args.skip_assets),
        ("overviewmaps.txt validation", True),
        ("Replay version support report", True),
        ("ships_cache.json refresh", not args.skip_ships_cache),
        ("ships_gameparams.json rebuild", True),
        ("aircraft_params.json rebuild", True),
        ("ship_consumables.json rebuild", True),
        ("ship_aircraft_support.json rebuild", True),
        ("gameparams_consumables.json rebuild", True),
    ]
    total_steps = sum(1 for _name, enabled in planned_steps if enabled)

    def _run_step(name: str, fn: Callable[[], int]) -> bool:
        step_no = sum(1 for item in results if item.status != "SKIPPED") + 1
        print(f"\n[{step_no}/{max(1, total_steps)}] {name}")
        started = perf_counter()
        try:
            rc = int(fn())
        except Exception as exc:
            results.append(StepResult(name, "FAILED", str(exc)))
            print(f"FAILED after {perf_counter() - started:.1f}s: {exc}")
            return False
        if rc != 0:
            results.append(StepResult(name, "FAILED", f"exit code {rc}"))
            print(f"FAILED after {perf_counter() - started:.1f}s: exit code {rc}")
            return False
        elapsed = perf_counter() - started
        results.append(StepResult(name, "OK", f"completed in {elapsed:.1f}s"))
        print(f"OK ({elapsed:.1f}s)")
        return True

    from tools import update_wows_version
    from tools import refresh_render_assets
    from tools import rebuild_aircraft_params_from_gameparams
    from tools import build_ships_gameparams
    from tools import build_ship_consumables_from_gameparams
    from tools import build_ship_aircraft_support
    from tools import extract_gameparams_consumables
    import ships as ships_tool

    if args.skip_assets:
        results.append(StepResult("render asset refresh", "SKIPPED", "requested by --skip-assets"))
    else:
        if not _run_step(
            "render asset refresh",
            lambda: _invoke_main(
                refresh_render_assets.main,
                [
                    "refresh_render_assets.py",
                    *(["--assets-root", str(args.assets_root)] if str(args.assets_root or "").strip() else []),
                    *(["--game-root", str(args.game_root)] if str(args.game_root or "").strip() else []),
                    *(["--keep-stage"] if args.keep_asset_stage else []),
                ],
            ),
        ):
            return _print_summary(results)

    if not _run_step(
        "overviewmaps.txt validation",
        lambda: (
            refresh_render_assets._report_overviewmaps_validation(root),  # type: ignore[attr-defined]
            0,
        )[1],
    ):
        return _print_summary(results)

    if not _run_step(
        "Replay version support report",
        lambda: _invoke_main(
            update_wows_version.main,
            [
                "update_wows_version.py",
                str(baseline_replay),
                str(candidate_replay),
                "--output-dir",
                str(report_dir),
                *(["--no-apply"] if args.no_apply else []),
                *(["--skip-canonical-dump"] if args.skip_canonical_dump else []),
                *(["--dump-raw-packets"] if args.dump_raw_packets else []),
                *(["--dump-render-packets"] if args.dump_render_packets else []),
                *(["--fail-on-review"] if not args.allow_manual_review else []),
            ],
        ),
    ):
        return _print_summary(results)

    if args.skip_ships_cache:
        results.append(StepResult("ships_cache.json refresh", "SKIPPED", "requested by --skip-ships-cache"))
    else:
        if not _run_step(
            "ships_cache.json refresh",
            lambda: _invoke_main(
                ships_tool.main,
                [
                    "ships.py",
                    "--update-cache",
                    "--concurrency",
                    str(max(1, int(args.ships_concurrency))),
                    "--sleep",
                    str(max(0.0, float(args.ships_sleep))),
                    *(["--limit", str(int(args.ships_limit))] if int(args.ships_limit) > 0 else []),
                ],
            ),
        ):
            return _print_summary(results)

    if not _run_step(
        "ships_gameparams.json rebuild",
        lambda: _invoke_main(
            build_ships_gameparams.main,
            [
                "build_ships_gameparams.py",
                "--gameparams",
                str(gameparams_path),
                "--texts-root",
                str(texts_root),
                "--out",
                str(root / "content" / "ships_gameparams.json"),
            ],
        ),
    ):
        return _print_summary(results)

    if not _run_step(
        "aircraft_params.json rebuild",
        lambda: _invoke_main(
            rebuild_aircraft_params_from_gameparams.main,
            [
                "rebuild_aircraft_params_from_gameparams.py",
                "--gameparams",
                str(gameparams_path),
                "--out",
                str(root / "aircraft_params.json"),
            ],
        ),
    ):
        return _print_summary(results)

    if not _run_step(
        "ship_consumables.json rebuild",
        lambda: _invoke_main(
            build_ship_consumables_from_gameparams.main,
            [
                "build_ship_consumables_from_gameparams.py",
                "--gameparams",
                str(gameparams_path),
                "--out",
                str(root / "content" / "ship_consumables.json"),
            ],
        ),
    ):
        return _print_summary(results)

    if not _run_step(
        "ship_aircraft_support.json rebuild",
        lambda: _invoke_main(
            build_ship_aircraft_support.main,
            [
                "build_ship_aircraft_support.py",
                "--out",
                str(root / "content" / "ship_aircraft_support.json"),
            ],
        ),
    ):
        return _print_summary(results)

    if not _run_step(
        "gameparams_consumables.json rebuild",
        lambda: _invoke_main(
            extract_gameparams_consumables.main,
            [
                "extract_gameparams_consumables.py",
                "--gameparams",
                str(gameparams_path),
                "--out",
                str(root / "content" / "gameparams_consumables.json"),
                "--keys",
                *[str(key) for key in args.consumable_keys if str(key).strip()],
            ],
        ),
    ):
        return _print_summary(results)

    return _print_summary(results)


def _print_summary(results: List[StepResult]) -> int:
    print("\nSummary")
    print("-" * 60)
    for result in results:
        print(f"{result.status:8} {result.name} - {result.detail}")
    failures = [item for item in results if item.status == "FAILED"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
