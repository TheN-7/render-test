#!/usr/bin/env python3
"""Build a ship -> aircraft support reference for cautious squadron fallback typing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ship_catalog_entry(payload: Dict[str, Any], ship_key: str) -> Dict[str, Any]:
    by_ship = payload.get("by_ship_id", {}) if isinstance(payload, dict) else {}
    entry = by_ship.get(str(ship_key)) if isinstance(by_ship, dict) else None
    return entry if isinstance(entry, dict) else {}


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _map_aircraft_module_type(raw_type: Any) -> str | None:
    text = str(raw_type or "").strip().lower()
    if not text:
        return None
    if "asw" in text or "depthcharge" in text or "depth charge" in text:
        return "asw"
    if "airdrop" in text or "air drop" in text or "asup" in text:
        return "airdrop_he" if "he" in text else "airdrop"
    if "mine" in text:
        return "asw_mine"
    if "fighter" in text:
        return "fighter"
    if "attack" in text or "rocket" in text:
        return "rocket_ap" if "armor piercing" in text or "_ap" in text or " ap " in f" {text} " else "rocket"
    if "torpedo" in text:
        return "torpedo_deepwater" if "deep" in text else "torpedo"
    if "skip" in text:
        return "skip_ap" if "armor piercing" in text or "_ap" in text or " ap " in f" {text} " else "skip"
    if "dive" in text or "bomb" in text:
        return "bomber_ap" if "armor piercing" in text or "_ap" in text or " ap " in f" {text} " else "bomber"
    return None


def _module_ids(module: Any) -> Tuple[List[str], List[str]]:
    ids: List[str] = []
    names: List[str] = []
    if not isinstance(module, dict):
        return ids, names
    if isinstance(module.get("ids"), list):
        for mid in module.get("ids", []):
            sid = _safe_int(mid)
            if sid is not None:
                ids.append(str(sid))
    elif module.get("id") is not None:
        sid = _safe_int(module.get("id"))
        if sid is not None:
            ids.append(str(sid))
    if isinstance(module.get("names"), list):
        for raw in module.get("names", []):
            text = str(raw or "").strip()
            if text:
                names.append(text)
    else:
        text = str(module.get("name") or "").strip()
        if text:
            names.append(text)
    return ids, names


def _infer_kind_from_names(names: List[str], fallback: str) -> str:
    text = " ".join(names).lower()
    if not text:
        return fallback
    if "asw" in text or "depth charge" in text or "depthcharge" in text:
        return "asw"
    if "airdrop" in text or "air drop" in text or "asup" in text:
        return "airdrop_he" if "he" in text else "airdrop"
    if "mine" in text:
        return "asw_mine"
    if "torpedo" in text:
        return "torpedo"
    if "skip" in text:
        return "skip"
    if "dive" in text or "bomb" in text:
        return "bomber"
    if "rocket" in text or "hvar" in text or "tiny tim" in text or "ffar" in text or "projectile" in text:
        return "rocket"
    if "fighter" in text:
        return "fighter"
    return fallback


def _looks_like_aircraft_module_meta(meta: Dict[str, Any]) -> bool:
    combined = " ".join(
        str(part or "").strip().lower()
        for part in (
            meta.get("type"),
            meta.get("name"),
            meta.get("group"),
            meta.get("category"),
        )
    )
    if not combined:
        return False
    tokens = (
        "plane",
        "squad",
        "aircraft",
        "bomber",
        "dive",
        "skip",
        "fighter",
        "rocket",
        "attack",
        "projectile",
        "scout",
        "asw",
        "airdrop",
        "depthcharge",
        "depth charge",
        "mine",
        "torpedo bomber",
        "torpedobomber",
    )
    return any(token in combined for token in tokens)


def _default_cv_fighter_kind(names: List[str]) -> str:
    text = " ".join(names).lower()
    if "rocket" in text or "hvar" in text or "tiny tim" in text or "ffar" in text or "projectile" in text:
        return "rocket"
    return "rocket"


def build_reference(root: Path) -> Dict[str, Any]:
    ship_consumables = _read_json(root / "content" / "ship_consumables.json")
    by_ship_consumables = ship_consumables.get("by_ship_id", {}) if isinstance(ship_consumables, dict) else {}
    ships_cache = _read_json(root / "ships_cache.json")
    ships_gameparams = _read_json(root / "content" / "ships_gameparams.json")

    by_ship_id: Dict[str, Any] = {}
    ship_ids: set[str] = set()
    if isinstance(by_ship_consumables, dict):
        ship_ids.update(str(key) for key in by_ship_consumables.keys())
    if isinstance(ships_cache, dict):
        ship_ids.update(str(key) for key in ships_cache.keys() if str(key).isdigit())
    by_ship_gameparams = ships_gameparams.get("by_ship_id", {}) if isinstance(ships_gameparams, dict) else {}
    if isinstance(by_ship_gameparams, dict):
        ship_ids.update(str(key) for key in by_ship_gameparams.keys())

    for ship_key in sorted(ship_ids, key=lambda value: int(value)):
        cache_entry = ships_cache.get(ship_key, {}) if isinstance(ships_cache, dict) else {}
        if not isinstance(cache_entry, dict):
            cache_entry = {}
        catalog_entry = _ship_catalog_entry(ships_gameparams, ship_key)
        consumable_entry = by_ship_consumables.get(ship_key, {}) if isinstance(by_ship_consumables, dict) else {}
        if not isinstance(consumable_entry, dict):
            consumable_entry = {}

        support_types: set[str] = set()
        support_details: List[Dict[str, Any]] = []
        by_kind = consumable_entry.get("by_kind", {})
        if isinstance(by_kind, dict):
            for support_kind in ("fighter", "spotter"):
                rows = by_kind.get(support_kind, [])
                if not isinstance(rows, list) or not rows:
                    continue
                support_types.add(support_kind)
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    support_details.append(
                        {
                            "kind": support_kind,
                            "slot": str(row.get("slot") or ""),
                            "base_key": str(row.get("base_key") or ""),
                            "variant_key": str(row.get("variant_key") or ""),
                            "work_time": row.get("work_time"),
                            "reload_time": row.get("reload_time"),
                            "consumable_type": str(row.get("consumable_type") or ""),
                        }
                    )

        module_types: set[str] = set()
        module_details: List[Dict[str, Any]] = []
        preferred_kind_by_module_id: Dict[str, str] = {}
        ship_kind = str(cache_entry.get("type") or catalog_entry.get("type") or catalog_entry.get("species") or "").strip()
        modules = cache_entry.get("modules", {})
        if isinstance(modules, dict):
            for module_key, fallback in (
                ("torpedo_bomber", "torpedo"),
                ("dive_bomber", "bomber"),
                ("bomber", "bomber"),
                ("skip_bomber", "skip"),
                ("fighter", "fighter"),
                ("rocket", "rocket"),
            ):
                ids, names = _module_ids(modules.get(module_key))
                if not ids and not names:
                    continue
                if ship_kind == "AirCarrier" and module_key == "fighter":
                    fallback = _default_cv_fighter_kind(names)
                kind = _infer_kind_from_names(names, fallback)
                module_types.add(kind)
                for mid in ids:
                    preferred_kind_by_module_id[str(mid)] = kind
                module_details.append(
                    {
                        "module_key": module_key,
                        "kind": kind,
                        "module_ids": ids,
                        "names": names,
                    }
                )

        modules_tree = cache_entry.get("modules_tree", {})
        if isinstance(modules_tree, dict):
            for module_id, meta in modules_tree.items():
                if not isinstance(meta, dict):
                    continue
                if not _looks_like_aircraft_module_meta(meta):
                    continue
                sid = _safe_int(module_id)
                key = str(sid) if sid is not None else str(module_id)
                kind = preferred_kind_by_module_id.get(key)
                if not kind:
                    kind = _map_aircraft_module_type(meta.get("type"))
                if not kind:
                    continue
                module_types.add(kind)
                module_details.append(
                    {
                        "module_key": "modules_tree",
                        "kind": kind,
                        "module_ids": [key],
                        "names": [str(meta.get("name") or "").strip()] if str(meta.get("name") or "").strip() else [],
                    }
                )

        render_support_types = sorted({"fighter" if kind == "spotter" else kind for kind in support_types if kind in {"fighter", "spotter"}})
        attack_types = sorted(
            t for t in module_types
            if t in {"rocket", "rocket_ap", "bomber", "bomber_ap", "torpedo", "torpedo_deepwater", "skip", "skip_ap", "asw", "asw_mine", "airdrop", "airdrop_he"}
        )

        by_ship_id[ship_key] = {
            "ship_id": int(ship_key),
            "display_name": str(
                cache_entry.get("name")
                or catalog_entry.get("name")
                or catalog_entry.get("display_name")
                or consumable_entry.get("display_name")
                or ""
            ),
            "type": str(cache_entry.get("type") or catalog_entry.get("type") or catalog_entry.get("species") or consumable_entry.get("type") or ""),
            "tier": cache_entry.get("tier", catalog_entry.get("tier", consumable_entry.get("tier"))),
            "nation": str(cache_entry.get("nation") or catalog_entry.get("nation") or consumable_entry.get("nation") or ""),
            "support_types": sorted(support_types),
            "render_support_types": render_support_types,
            "attack_types": attack_types,
            "support_details": support_details,
            "module_details": module_details,
            "all_render_types": sorted(set(render_support_types) | set(attack_types)),
            "has_attack_squadrons": bool(attack_types),
            "has_support_planes": bool(render_support_types),
        }

    return {
        "source_ship_consumables": str(root / "content" / "ship_consumables.json"),
        "source_ships_cache": str(root / "ships_cache.json"),
        "source_ships_gameparams": str(root / "content" / "ships_gameparams.json"),
        "ship_count": len(by_ship_id),
        "by_ship_id": by_ship_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ship aircraft support reference")
    parser.add_argument("--out", default="", help="Output JSON path (default: content/ship_aircraft_support.json)")
    args = parser.parse_args()

    root = _root_dir()
    out_path = Path(args.out) if args.out else root / "content" / "ship_aircraft_support.json"
    payload = build_reference(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out_path} with {int(payload.get('ship_count', 0))} ships.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
