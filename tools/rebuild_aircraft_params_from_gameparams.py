#!/usr/bin/env python3
"""
Rebuild aircraft_params.json from GameParams.data (authoritative aircraft params_id mapping).

Usage:
  python tools/rebuild_aircraft_params_from_gameparams.py
  python tools/rebuild_aircraft_params_from_gameparams.py --gameparams .\\content\\GameParams.data --out .\\aircraft_params.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from renderers import minimap_renderer as mr
from tools.update_aircraft_params import _build_by_cv


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild aircraft_params.json from GameParams.data")
    parser.add_argument("--gameparams", default="", help="Path to GameParams.data (default: content/GameParams.data)")
    parser.add_argument("--out", default="", help="Output aircraft_params.json (default: aircraft_params.json)")
    args = parser.parse_args()

    root = _root_dir()
    gp_path = Path(args.gameparams) if args.gameparams else root / "content" / "GameParams.data"
    out_path = Path(args.out) if args.out else root / "aircraft_params.json"

    mapping = mr._aircraft_params_from_gameparams_data(gp_path)
    if not mapping:
        print(f"No mapping extracted from {gp_path}")
        return 1

    payload = {"by_plane_id": {str(k): str(v) for k, v in mapping.items() if str(v).strip()}}
    by_cv = {}
    ships_cache_path = root / "ships_cache.json"
    if ships_cache_path.exists():
        try:
            ships_cache = json.loads(ships_cache_path.read_text(encoding="utf-8"))
            if isinstance(ships_cache, dict):
                by_cv = _build_by_cv(ships_cache)
        except Exception:
            by_cv = {}
    if by_cv:
        payload["by_cv"] = by_cv
    elif out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and "by_cv" in existing:
                payload["by_cv"] = existing.get("by_cv")
        except Exception:
            pass

    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out_path} with {len(payload['by_plane_id'])} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
