#!/usr/bin/env python3
"""Refresh render asset files from an unpacked WoWS client tree or directly via wowsunpack."""

from __future__ import annotations

import argparse
import os
import re
import stat
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Iterable, List, Optional, Sequence, Tuple


UNPACK_PATTERNS: Tuple[str, ...] = (
    "content/*.data",
    "gui/consumables/*",
    "gui/service_kit/plane_types/*",
    "gui/battle_tasks/rules/icon_rules_gamemode_arms_race_*",
    "gui/battle_hud/GameParams.json",
    "gui/battle_hud/own_ship_health/*",
    "gui/ship_previews/*",
    "gui/ship_previews/medium/*",
    "gui/ship_icons/*",
    "gui/ships_silhouettes/*",
    "gui/ship_dead_icons/*",
    "gui/ribbons/*",
    "gui/ribbons/Icons/*",
    "gui/ribbons/subribbons/*",
    "spaces/*",
)


DIR_SYNC_SPECS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("content/texts", ("content/texts", "texts")),
    ("gui/consumables", ("gui/consumables",)),
    ("gui/service_kit/plane_types", ("gui/service_kit/plane_types",)),
    ("gui/battle_tasks/rules", ("gui/battle_tasks/rules",)),
    ("gui/battle_hud/own_ship_health", ("gui/battle_hud/own_ship_health",)),
    ("gui/ship_previews", ("gui/ship_previews",)),
    ("gui/ship_icons", ("gui/ship_icons",)),
    ("gui/ships_silhouettes", ("gui/ships_silhouettes",)),
    ("gui/ship_dead_icons", ("gui/ship_dead_icons",)),
    ("gui/ribbons", ("gui/ribbons",)),
    ("gui/spaces", ("gui/spaces", "spaces")),
)


FILE_SYNC_SPECS: Tuple[Tuple[str, Tuple[str, ...], bool], ...] = (
    ("content/GameParams.data", ("content/GameParams.data",), False),
    ("content/UIParams.data", ("content/UIParams.data",), True),
    ("gui/battle_hud/GameParams.json", ("gui/battle_hud/GameParams.json",), False),
    ("gui/spaces/overviewmaps.txt", ("gui/spaces/overviewmaps.txt", "spaces/overviewmaps.txt", "overviewmaps.txt"), True),
)


_OVERVIEW_REPLAY_LINE_RE = re.compile(r"^Replay File Name:\s*(.+)$", re.IGNORECASE)
_OVERVIEW_VALID_SUFFIX_RE = re.compile(r"\.wowsrepla(?:y)?\s*$", re.IGNORECASE)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_game_root_from_file() -> str:
    path_file = _root_dir() / "game.path"
    if not path_file.exists():
        return ""
    try:
        return str(path_file.read_text(encoding="utf-8").strip())
    except Exception:
        return ""


def _latest_bin_folder(game_root: Path) -> Path:
    bin_root = game_root / "bin"
    if not bin_root.exists():
        raise FileNotFoundError(f"bin folder not found under {game_root}")
    choices = [child for child in bin_root.iterdir() if child.is_dir() and child.name.isdigit()]
    if not choices:
        raise FileNotFoundError(f"no numeric bin folders found under {bin_root}")
    return sorted(choices, key=lambda item: int(item.name))[-1]


def _wowsunpack_exe(game_root: Path) -> Path:
    candidates = (
        game_root / "wowsunpack" / "wowsunpack.exe",
        _root_dir() / "src" / "wowsunpack" / "wowsunpack.exe",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("wowsunpack.exe not found under the game root or project src/wowsunpack")


def _run_unpack(game_root: Path, output_dir: Path, patterns: Sequence[str]) -> None:
    latest_bin = _latest_bin_folder(game_root)
    unpacker = _wowsunpack_exe(game_root)
    cmd = [
        str(unpacker),
        str(latest_bin / "idx"),
        "--extract",
        "--output",
        str(output_dir),
        "--packages",
        r"..\..\..\res_packages",
    ]
    for pattern in patterns:
        cmd.extend(["--include", str(pattern)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"wowsunpack failed for patterns {list(patterns)!r} with exit code {proc.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )


def _stage_texts_from_game_root(game_root: Path, output_dir: Path) -> None:
    try:
        latest_bin = _latest_bin_folder(game_root)
    except Exception:
        return
    src = latest_bin / "res" / "texts"
    if not src.exists() or not src.is_dir():
        return
    dest = output_dir / "texts"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _find_existing(base: Path, candidates: Sequence[str]) -> Optional[Path]:
    for rel in candidates:
        path = base / rel
        if path.exists():
            return path
    return None


def _merge_dir(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if item.is_file():
            _copy_file(item, target)


def _copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            dest.chmod(stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass
        try:
            shutil.copy2(src, dest)
            return
        except PermissionError:
            pass
    fd, tmp_name = tempfile.mkstemp(prefix=f"{dest.name}_stage_", dir=str(dest.parent))
    os.close(fd)
    staged = Path(tmp_name)
    try:
        shutil.copy2(src, staged)
        staged.replace(dest)
    finally:
        if staged.exists():
            staged.unlink()


def _sync_from_asset_root(asset_root: Path, repo_root: Path) -> List[str]:
    updated: List[str] = []
    sync_total = len(DIR_SYNC_SPECS) + len(FILE_SYNC_SPECS) + 1
    sync_index = 0

    for dest_rel, candidate_sources in DIR_SYNC_SPECS:
        sync_index += 1
        print(f"  [sync {sync_index}/{sync_total}] {dest_rel}")
        src = _find_existing(asset_root, candidate_sources)
        if src is None or not src.is_dir():
            print("    source missing, keeping existing files")
            continue
        dest = repo_root / dest_rel
        _merge_dir(src, dest)
        updated.append(dest_rel)

    for dest_rel, candidate_sources, required in FILE_SYNC_SPECS:
        sync_index += 1
        print(f"  [sync {sync_index}/{sync_total}] {dest_rel}")
        src = _find_existing(asset_root, candidate_sources)
        if src is None:
            dest = repo_root / dest_rel
            if required and not dest.exists():
                raise FileNotFoundError(f"required asset not found in source root: one of {candidate_sources}")
            print("    source missing, keeping existing file")
            continue
        if not src.is_file():
            print("    source is not a file, skipping")
            continue
        dest = repo_root / dest_rel
        _copy_file(src, dest)
        updated.append(dest_rel)

    # Keep the render's content copy in sync even if the source tree does not provide it.
    sync_index += 1
    print(f"  [sync {sync_index}/{sync_total}] content/overviewmaps.txt")
    gui_overview = repo_root / "gui" / "spaces" / "overviewmaps.txt"
    if gui_overview.exists():
        content_overview = repo_root / "content" / "overviewmaps.txt"
        _copy_file(gui_overview, content_overview)
        if "content/overviewmaps.txt" not in updated:
            updated.append("content/overviewmaps.txt")
    else:
        print("    gui/spaces/overviewmaps.txt missing, keeping existing file")

    return updated


def _validate_overviewmaps_file(path: Path) -> List[str]:
    issues: List[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        return [f"unable to read {path.name}: {exc}"]

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        match = _OVERVIEW_REPLAY_LINE_RE.match(line)
        if match is None:
            continue
        value = match.group(1).strip()
        if not _OVERVIEW_VALID_SUFFIX_RE.search(value):
            issues.append(f"line {idx}: unexpected replay file suffix -> {value}")
        elif not value.lower().endswith(".wowsreplay"):
            issues.append(f"line {idx}: truncated replay suffix tolerated -> {value}")
    return issues


def _report_overviewmaps_validation(repo_root: Path) -> None:
    targets = (
        repo_root / "gui" / "spaces" / "overviewmaps.txt",
        repo_root / "content" / "overviewmaps.txt",
    )
    print("  [validate] overviewmaps.txt")
    any_issue = False
    for target in targets:
        if not target.exists():
            print(f"    missing: {target.relative_to(repo_root)}")
            continue
        issues = _validate_overviewmaps_file(target)
        if not issues:
            print(f"    ok: {target.relative_to(repo_root)}")
            continue
        any_issue = True
        print(f"    warnings in {target.relative_to(repo_root)}:")
        for issue in issues[:10]:
            print(f"      - {issue}")
        if len(issues) > 10:
            print(f"      - ... {len(issues) - 10} more")
    if not any_issue:
        print("    no replay-name suffix issues detected")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh render asset files from a WoWS client install or unpacked asset tree.")
    parser.add_argument(
        "--assets-root",
        default="",
        help="Path to an already-unpacked asset root. If omitted, the tool unpacks assets from the WoWS install in game.path or --game-root.",
    )
    parser.add_argument(
        "--game-root",
        default="",
        help="Path to the WoWS install root (default: read from game.path). Used only when --assets-root is not provided.",
    )
    parser.add_argument(
        "--keep-stage",
        action="store_true",
        help="Keep the temporary unpacked staging directory for inspection when unpacking from the WoWS install.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = _root_dir()

    asset_root_arg = str(args.assets_root or "").strip()
    if asset_root_arg:
        asset_root = Path(asset_root_arg).expanduser().resolve()
        if not asset_root.exists():
            raise FileNotFoundError(f"asset root not found: {asset_root}")
        print(f"Using unpacked asset root: {asset_root}")
        started = perf_counter()
        updated = _sync_from_asset_root(asset_root, repo_root)
        _report_overviewmaps_validation(repo_root)
        print(f"Refreshed {len(updated)} asset targets from {asset_root} in {perf_counter() - started:.1f}s")
        for rel in updated:
            print(f"  - {rel}")
        return 0

    game_root_raw = str(args.game_root or "").strip() or _read_game_root_from_file()
    if not game_root_raw:
        raise FileNotFoundError("game root not provided and game.path is missing or empty")
    game_root = Path(game_root_raw).expanduser().resolve()
    if not game_root.exists():
        raise FileNotFoundError(f"game root not found: {game_root}")

    keep_stage = bool(args.keep_stage)
    with tempfile.TemporaryDirectory(prefix="render_asset_refresh_", dir=str(repo_root)) as tmp_name:
        stage_root = Path(tmp_name)
        print(f"Unpacking client assets from: {game_root}")
        unpack_started = perf_counter()
        _run_unpack(game_root, stage_root, UNPACK_PATTERNS)
        _stage_texts_from_game_root(game_root, stage_root)
        print(f"Unpack complete in {perf_counter() - unpack_started:.1f}s")
        sync_started = perf_counter()
        updated = _sync_from_asset_root(stage_root, repo_root)
        _report_overviewmaps_validation(repo_root)
        if keep_stage:
            retained = repo_root / "_asset_stage"
            if retained.exists():
                shutil.rmtree(retained)
            shutil.copytree(stage_root, retained)
            print(f"Retained asset stage at {retained}")
        print(f"Refreshed {len(updated)} asset targets from {game_root} in {perf_counter() - sync_started:.1f}s")
        for rel in updated:
            print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
