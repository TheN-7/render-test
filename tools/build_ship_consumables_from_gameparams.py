#!/usr/bin/env python3
"""Build an authoritative ship -> consumables reference from GameParams.data."""

from __future__ import annotations

import argparse
import json
import pickle
import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, List, Optional, Tuple

UNIT_TO_METERS = 30.0


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _install_gameparams_module() -> None:
    class GameParams(ModuleType):
        class TypeInfo(object):
            pass

        class GPData(object):
            pass

    sys.modules[GameParams.__name__] = GameParams(GameParams.__name__)


def _read_gameparams(path: Path) -> Any:
    _install_gameparams_module()
    raw = path.read_bytes()
    raw = struct.pack("B" * len(raw), *raw[::-1])
    raw = zlib.decompress(raw)
    return pickle.loads(raw, encoding="latin1")


def _unwrap_gameparams_source(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict) and "" in obj and isinstance(obj[""], dict):
        return obj[""]
    if isinstance(obj, (list, tuple)):
        for elem in obj:
            if isinstance(elem, dict) and "" in elem and isinstance(elem[""], dict):
                return elem[""]
    return {}


def _load_ship_cache(root: Path) -> Dict[str, Any]:
    path = root / "ships_cache.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_ship_gameparams_reference(root: Path) -> Dict[str, Any]:
    path = root / "content" / "ships_gameparams.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    attrs = getattr(value, "__dict__", None)
    return attrs if isinstance(attrs, dict) else {}


def _iter_ship_abilities(ship_abilities: Any) -> Iterable[Tuple[str, str, str]]:
    for slot_name, slot in getattr(ship_abilities, "__dict__", {}).items():
        abils = getattr(slot, "__dict__", {}).get("abils", []) or []
        if not isinstance(abils, list):
            continue
        for ability in abils:
            if not isinstance(ability, (list, tuple)) or not ability:
                continue
            base_key = str(ability[0] or "").strip()
            variant_key = str(ability[1] or "").strip() if len(ability) > 1 else ""
            if base_key:
                yield str(slot_name), base_key, variant_key


def _map_ability_key_to_kind(base_key: str) -> Optional[str]:
    key = str(base_key or "").strip().lower()
    if not key:
        return None
    if "crashcrew" in key or "crashall" in key or "damagecontrol" in key:
        return "dcp"
    if (
        "regencrew" in key
        or "healaura" in key
        or "healall" in key
        or "healshell" in key
        or "healzone" in key
        or "mass_heal" in key
        or "invisibleregen" in key
        or "regen_" in key
    ):
        return "heal"
    if "vampiric" in key or "lifedrain" in key or "drainzone" in key or "improveregen" in key:
        return "heal"
    if "airdefensedisp" in key:
        return "dfaa"
    if "fighter" in key or "reconnaissancesquad" in key:
        return "fighter"
    if "spotter" in key:
        return "spotter"
    if "smokegenerator" in key:
        return "smoke"
    if "speedbooster" in key or "speedbuff" in key or "improvespeed" in key:
        return "engine"
    if "sonarsearch" in key:
        return "hydro"
    if "rlssearch" in key:
        return "radar"
    if "hydrophone" in key or "submarinelocator" in key or "mass_target" in key:
        return "locator"
    if "torpedoreloader" in key:
        return "torpedo_reload"
    if "artillerybooster" in key or "gmshotdelay" in key:
        return "reload_booster"
    if "fastdeeprudders" in key or "turnaround" in key:
        return "maneuver"
    if "submarineenergyfreeze" in key or "godeep" in key:
        return "submarine"
    if "armorbuff" in key or "protection" in key or "livingarmor" in key or "resist" in key or "invulnerable" in key or "immortal" in key:
        return "defense"
    if "airstrikecountermeasures" in key:
        return "airstrike_countermeasures"
    if "holyweapon" in key or "sniper" in key or "filthpower" in key or "orbital_strike" in key or "circlewave" in key:
        return "offense"
    if "mindcontrol" in key or "stealth" in key or "silence" in key or "taunt" in key or "addconsumable" in key or "improve_" in key:
        return "utility"
    return None


def _map_consumable_type_to_kind(raw_type: Any) -> Optional[str]:
    value = str(raw_type or "").strip().lower()
    if not value:
        return None
    mapping = {
        "crashcrew": "dcp",
        "regencrew": "heal",
        "airdefensedisp": "dfaa",
        "fighter": "fighter",
        "scout": "spotter",
        "smokegenerator": "smoke",
        "speedbooster": "engine",
        "sonar": "hydro",
        "rls": "radar",
        "hydrophone": "locator",
        "submarinelocator": "locator",
        "torpedoreloader": "torpedo_reload",
        "artillerybooster": "reload_booster",
        "fastdeeprudders": "maneuver",
        "godeep": "submarine",
        "submarineenergyfreeze": "submarine",
        "airstrikecountermeasures": "airstrike_countermeasures",
    }
    return mapping.get(value)


def _meters_from_gameparams_units(value: Any) -> Optional[float]:
    number = _safe_float(value)
    if number is None or number <= 0.0:
        return None
    return round(float(number) * UNIT_TO_METERS, 3)


def _string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        result: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    return []


def _extract_variant_details(
    gameparams_source: Dict[str, Any],
    base_key: str,
    variant_key: str,
) -> Dict[str, Any]:
    entry = _as_dict(gameparams_source.get(base_key))
    variant = _as_dict(entry.get(variant_key))
    tactical = _as_dict(variant.get("tacticalParams"))
    logic = _as_dict(variant.get("logic"))
    consumable_type = str(variant.get("consumableType") or "").strip()
    kind = _map_consumable_type_to_kind(consumable_type) or _map_ability_key_to_kind(base_key)
    dist_ship_m = _meters_from_gameparams_units(logic.get("distShip"))
    dist_torpedo_m = _meters_from_gameparams_units(logic.get("distTorpedo"))
    tactical_work_range_m = _meters_from_gameparams_units(tactical.get("workRange"))
    if kind not in {"radar", "hydro", "locator"}:
        dist_ship_m = None
        dist_torpedo_m = None
    return {
        "kind": kind or "",
        "consumable_type": consumable_type,
        "title_ids": _string_list(variant.get("titleIDs")),
        "desc_ids": _string_list(variant.get("descIDs")),
        "icon_ids": _string_list(variant.get("iconIDs")),
        "group": str(variant.get("group") or ""),
        "work_time": _safe_float(variant.get("workTime")),
        "reload_time": _safe_float(variant.get("reloadTime")),
        "preparation_time": _safe_float(variant.get("preparationTime")),
        "num_consumables": _safe_int(variant.get("numConsumables")),
        "dist_ship_m": dist_ship_m,
        "dist_torpedo_m": dist_torpedo_m,
        "tactical_work_range_m": tactical_work_range_m,
    }


def build_reference(gameparams_path: Path, ship_cache: Dict[str, Any], ship_catalog: Dict[str, Any]) -> Dict[str, Any]:
    root = _read_gameparams(gameparams_path)
    source = _unwrap_gameparams_source(root)
    catalog_by_ship = ship_catalog.get("by_ship_id", {}) if isinstance(ship_catalog, dict) else {}
    payload: Dict[str, Any] = {
        "source": str(gameparams_path),
        "source_ships_gameparams": str(_root_dir() / "content" / "ships_gameparams.json"),
        "ship_count": 0,
        "by_ship_id": {},
        "unmapped_ability_keys": [],
    }
    if not isinstance(source, dict):
        return payload

    unmapped_keys: set[str] = set()
    by_ship_id: Dict[str, Any] = {}

    for internal_name, entry in source.items():
        attrs = getattr(entry, "__dict__", {})
        ship_abilities = attrs.get("ShipAbilities")
        if ship_abilities is None:
            continue
        ship_id = _safe_int(attrs.get("id"))
        if ship_id is None:
            continue
        cache_entry = ship_cache.get(str(ship_id))
        if not isinstance(cache_entry, dict):
            cache_entry = {}
        catalog_entry = catalog_by_ship.get(str(ship_id)) if isinstance(catalog_by_ship, dict) else None
        if not isinstance(catalog_entry, dict):
            catalog_entry = {}
        abilities: List[Dict[str, str]] = []
        by_kind: Dict[str, List[Dict[str, Any]]] = {}
        normalized: set[str] = set()
        raw_keys: List[str] = []
        for slot_name, base_key, variant_key in _iter_ship_abilities(ship_abilities):
            raw_keys.append(base_key)
            detail = _extract_variant_details(source, base_key, variant_key)
            kind = str(detail.get("kind") or "").strip().lower() or _map_ability_key_to_kind(base_key)
            if kind:
                normalized.add(kind)
            else:
                unmapped_keys.add(base_key)
            ability_entry = {
                "slot": slot_name,
                "base_key": base_key,
                "variant_key": variant_key,
                "kind": kind or "",
                "consumable_type": str(detail.get("consumable_type") or ""),
                "title_ids": list(detail.get("title_ids") or []),
                "desc_ids": list(detail.get("desc_ids") or []),
                "icon_ids": list(detail.get("icon_ids") or []),
                "group": str(detail.get("group") or ""),
                "work_time": detail.get("work_time"),
                "reload_time": detail.get("reload_time"),
                "preparation_time": detail.get("preparation_time"),
                "num_consumables": detail.get("num_consumables"),
                "dist_ship_m": detail.get("dist_ship_m"),
                "dist_torpedo_m": detail.get("dist_torpedo_m"),
                "tactical_work_range_m": detail.get("tactical_work_range_m"),
            }
            abilities.append(ability_entry)
            if kind:
                by_kind.setdefault(kind, []).append(dict(ability_entry))
        by_ship_id[str(ship_id)] = {
            "ship_id": int(ship_id),
            "index": str(attrs.get("index") or ""),
            "internal_name": str(internal_name or attrs.get("name") or ""),
            "display_name": str(cache_entry.get("name") or catalog_entry.get("name") or catalog_entry.get("display_name") or ""),
            "type": str(cache_entry.get("type") or catalog_entry.get("type") or catalog_entry.get("species") or ""),
            "tier": _safe_int(cache_entry.get("tier")) or _safe_int(catalog_entry.get("tier")) or _safe_int(attrs.get("level")),
            "nation": str(cache_entry.get("nation") or catalog_entry.get("nation") or ""),
            "consumables": sorted(normalized),
            "raw_ability_keys": sorted(set(raw_keys)),
            "abilities": abilities,
            "by_kind": dict(sorted(by_kind.items())),
        }

    payload["ship_count"] = len(by_ship_id)
    payload["by_ship_id"] = dict(sorted(by_ship_id.items(), key=lambda item: int(item[0])))
    payload["unmapped_ability_keys"] = sorted(unmapped_keys)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ship consumables reference from GameParams.data")
    parser.add_argument("--gameparams", default="", help="Path to GameParams.data (default: content/GameParams.data)")
    parser.add_argument("--out", default="", help="Output JSON path (default: content/ship_consumables.json)")
    args = parser.parse_args()

    root = _root_dir()
    gameparams_path = Path(args.gameparams) if args.gameparams else root / "content" / "GameParams.data"
    out_path = Path(args.out) if args.out else root / "content" / "ship_consumables.json"

    payload = build_reference(
        gameparams_path,
        _load_ship_cache(root),
        _load_ship_gameparams_reference(root),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"Wrote {out_path} with {int(payload.get('ship_count', 0))} ships.")
    if payload.get("unmapped_ability_keys"):
        print(f"Unmapped ability keys: {len(payload['unmapped_ability_keys'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
