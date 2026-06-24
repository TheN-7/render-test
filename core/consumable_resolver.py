"""Resolve ship battle consumables from replay config dump and GameParams reference."""

from __future__ import annotations

import json
import logging
import re
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SHIP_CONSUMABLES_PATH = ROOT / "content" / "ship_consumables.json"
CONSUMABLE_ICON_ROOT = ROOT / "gui" / "consumables"

MOD_COUNT_OFFSET = 19
MOD_LIST_OFFSET = 20
MOD_MAX_SLOTS = 6

# Preferred display order for the build card (matches typical port UI).
CONSUMABLE_KIND_ORDER: dict[str, int] = {
    "dcp": 0,
    "heal": 1,
    "engine": 2,
    "smoke": 3,
    "radar": 4,
    "hydro": 5,
    "dfaa": 6,
    "fighter": 7,
    "spotter": 8,
    "torpedo_reload": 9,
    "reload_booster": 10,
    "locator": 11,
    "maneuver": 12,
    "airstrike_countermeasures": 13,
    "submarine": 14,
}

CONSUMABLE_KIND_LABELS: dict[str, str] = {
    "dcp": "Damage Control",
    "heal": "Repair Party",
    "engine": "Engine Boost",
    "smoke": "Smoke Generator",
    "radar": "Surveillance Radar",
    "hydro": "Hydroacoustic Search",
    "dfaa": "Defensive AA Fire",
    "fighter": "Fighter",
    "spotter": "Spotting Aircraft",
    "torpedo_reload": "Torpedo Reload",
    "reload_booster": "Reload Booster",
    "locator": "Surveillance Radar",
    "maneuver": "Engine Boost",
    "airstrike_countermeasures": "AA Defense Dispersion",
    "submarine": "Reserve battery unit",
}

SUBMARINE_BASE_LABELS: dict[str, str] = {
    "PCY045_Hydrophone": "Hydrophone",
    "PCY047_SubmarineEnergyFreeze": "Reserve battery unit",
    "PCY048_SubmarineLocator": "Submarine Surveillance",
}


def _slot_sort_key(slot_name: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", str(slot_name or ""))
    return (int(match.group(1)) if match else 99, str(slot_name or ""))


@lru_cache(maxsize=1)
def _load_ship_consumables() -> dict[str, Any]:
    try:
        raw = json.loads(SHIP_CONSUMABLES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def parse_mounted_consumable_ids(config_dump_hex: str | None) -> list[int]:
    """Return signal-flag/camo IDs that follow the modernization block.

    These are NOT actual consumable abilities — they sit right after the
    modernization slots.  See :func:`parse_mounted_consumable_gp_ids` for
    the real consumable section.
    """
    if not config_dump_hex:
        return []
    try:
        payload = bytes.fromhex(str(config_dump_hex).strip())
    except ValueError:
        return []
    count_uints = len(payload) // 4
    if count_uints <= MOD_LIST_OFFSET:
        return []
    uints = struct.unpack(f"<{count_uints}I", payload[: count_uints * 4])
    mod_count = int(uints[MOD_COUNT_OFFSET])
    if not (0 < mod_count <= MOD_MAX_SLOTS):
        mod_count = min(MOD_MAX_SLOTS, max(0, mod_count))
    consumable_count_index = MOD_LIST_OFFSET + mod_count
    if consumable_count_index >= len(uints):
        return []
    consumable_count = int(uints[consumable_count_index])
    if consumable_count <= 0 or consumable_count > 16:
        return []
    ids: list[int] = []
    for offset in range(consumable_count_index + 1, consumable_count_index + 1 + consumable_count):
        if offset >= len(uints):
            break
        value = int(uints[offset])
        if value > 0:
            ids.append(value)
    return ids


def parse_mounted_consumable_gp_ids(config_dump_hex: str | None) -> list[int]:
    """Return the GameParams IDs of actually mounted consumables.

    The ``shipConfigDump`` layout after the modernization block is::

        [signal_count] [signal_ids...] [2 unknowns] [consumable_count] [consumable_gp_ids...]

    Non-zero entries in the consumable section are the GP IDs of the
    abilities the player equipped.
    """
    if not config_dump_hex:
        return []
    try:
        payload = bytes.fromhex(str(config_dump_hex).strip())
    except ValueError:
        return []
    count_uints = len(payload) // 4
    if count_uints <= MOD_LIST_OFFSET:
        return []
    uints = struct.unpack(f"<{count_uints}I", payload[: count_uints * 4])
    mod_count = int(uints[MOD_COUNT_OFFSET])
    if not (0 < mod_count <= MOD_MAX_SLOTS):
        mod_count = min(MOD_MAX_SLOTS, max(0, mod_count))
    signal_count_index = MOD_LIST_OFFSET + mod_count
    if signal_count_index >= len(uints):
        return []
    signal_count = int(uints[signal_count_index])
    if signal_count < 0 or signal_count > 20:
        return []
    # Skip signal IDs + 2 unknown values to reach the consumable section.
    consumable_count_index = signal_count_index + 1 + signal_count + 2
    if consumable_count_index >= len(uints):
        return []
    consumable_count = int(uints[consumable_count_index])
    if consumable_count <= 0 or consumable_count > 16:
        return []
    ids: list[int] = []
    for offset in range(consumable_count_index + 1, consumable_count_index + 1 + consumable_count):
        if offset >= len(uints):
            break
        value = int(uints[offset])
        if value > 0:
            ids.append(value)
    return ids


def _icon_path_for_base_key(base_key: str) -> str:
    key = str(base_key or "").strip()
    if not key:
        return ""
    candidates = [
        CONSUMABLE_ICON_ROOT / f"consumable_{key}.png",
        CONSUMABLE_ICON_ROOT / f"consumable_{key}_Premium.png",
    ]
    for path in candidates:
        if path.is_file():
            return path.name
    # Fuzzy match on PCY prefix (e.g. PCY010_RegenCrew -> PCY010_RegenCrewPremium.png).
    prefix = key.split("_", 1)[0] if "_" in key else key
    if prefix.startswith("PCY"):
        matches = sorted(CONSUMABLE_ICON_ROOT.glob(f"consumable_{prefix}*.png"))
        for path in matches:
            if "_empty" not in path.name.lower():
                return path.name
    return ""


def _label_for_ability(ability: dict[str, Any]) -> str:
    base = str(ability.get("base_key") or "").strip()
    if base in SUBMARINE_BASE_LABELS:
        return SUBMARINE_BASE_LABELS[base]

    consumable_type = str(ability.get("consumable_type") or "").strip().lower()
    if consumable_type == "hydrophone":
        return "Hydrophone"
    if consumable_type == "submarinelocator":
        return "Submarine Surveillance"
    if consumable_type == "subsenergyfreeze":
        return "Reserve battery unit"

    kind = str(ability.get("kind") or "").strip().lower()
    if kind in CONSUMABLE_KIND_LABELS:
        return CONSUMABLE_KIND_LABELS[kind]
    variant = str(ability.get("variant_key") or "").strip()
    if variant and not variant.endswith("Default"):
        text = re.sub(r"^[A-Z]_", "", variant)
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
        return re.sub(r"\s+", " ", text).strip()
    if base.startswith("PCY"):
        text = re.sub(r"^PCY\d+_", "", base)
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
        return text.replace("_", " ").strip() or kind.title()
    return kind.replace("_", " ").title() if kind else "Consumable"


def _ship_abilities(ship_id: Any) -> list[dict[str, Any]]:
    sid = None
    try:
        sid = str(int(ship_id))
    except (TypeError, ValueError):
        return []
    payload = _load_ship_consumables()
    by_ship = payload.get("by_ship_id", {}) if isinstance(payload, dict) else {}
    entry = by_ship.get(sid)
    if not isinstance(entry, dict):
        return []
    abilities = entry.get("abilities", [])
    if not isinstance(abilities, list):
        return []
    rows = [row for row in abilities if isinstance(row, dict)]
    rows.sort(
        key=lambda row: (
            CONSUMABLE_KIND_ORDER.get(str(row.get("kind") or "").lower(), 99),
            _slot_sort_key(str(row.get("slot") or "")),
        )
    )
    return rows


@lru_cache(maxsize=1)
def _gp_id_to_base_key() -> dict[int, str]:
    """Build a mapping from GameParams ID → consumable base_key (e.g. PCY009_CrashCrewPremium)."""
    try:
        from core.module_name_resolver import _load_gameparams_root
    except ImportError:
        return {}
    try:
        root = _load_gameparams_root()
    except Exception:
        return {}
    mapping: dict[int, str] = {}
    for key, val in root.items():
        obj = vars(val) if hasattr(val, "__dict__") else (val if isinstance(val, dict) else {})
        gp_id = obj.get("id")
        if isinstance(gp_id, int) and isinstance(key, str) and key.startswith("PCY"):
            mapping[gp_id] = key
    return mapping


def _mounted_base_keys(config_dump_hex: str) -> set[str] | None:
    """Return the set of mounted consumable base_keys, or *None* when the
    dump cannot be parsed (so callers can fall back to showing everything)."""
    gp_ids = parse_mounted_consumable_gp_ids(config_dump_hex)
    if not gp_ids:
        return None
    id_map = _gp_id_to_base_key()
    if not id_map:
        return None
    keys = {id_map[gp_id] for gp_id in gp_ids if gp_id in id_map}
    return keys if keys else None


def build_consumable_entries(
    ship_build: dict[str, Any] | None,
    *,
    ship_id: Any = None,
) -> list[dict[str, str]]:
    """Build consumable tiles for the local player's mounted battle consumables."""
    if ship_id is None and isinstance(ship_build, dict):
        ship_id = ship_build.get("ship_id")
    abilities = _ship_abilities(ship_id)
    if not abilities:
        return []

    config_hex = (
        str((ship_build or {}).get("config_dump_hex") or "")
        if isinstance(ship_build, dict)
        else ""
    )
    mounted_keys = _mounted_base_keys(config_hex)

    entries: list[dict[str, str]] = []
    seen_slots: set[str] = set()
    for ability in abilities:
        base_key = str(ability.get("base_key") or "").strip()
        slot = str(ability.get("slot") or "")

        if mounted_keys is not None and base_key not in mounted_keys:
            continue

        if slot in seen_slots:
            continue
        seen_slots.add(slot)

        variant_key = str(ability.get("variant_key") or "").strip()
        kind = str(ability.get("kind") or "").strip().lower()
        icon_name = _icon_path_for_base_key(variant_key) or _icon_path_for_base_key(base_key)
        label = _label_for_ability(ability)
        entries.append(
            {
                "kind": kind,
                "label": label,
                "base_key": base_key,
                "variant_key": variant_key,
                "icon": icon_name,
                "slot": slot,
            }
        )

    return entries


def find_consumable_icon_path(icon_name: str) -> Path | None:
    if not icon_name:
        return None
    path = CONSUMABLE_ICON_ROOT / icon_name
    return path if path.is_file() else None
