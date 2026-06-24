"""Resolve human-readable WoWS module names from raw replay ``shipComponents`` values.

The replay only stores internal component variant tokens (e.g. ``"A_Hull"`` or
``"A1_Artillery"``).  This module bridges those tokens to the proper in-game
module names ("Vermont", "457 mm/45 Mk.A in a turret", ...).

Resolution strategy:

1. Parse ``content/GameParams.data`` once (lazily) and index every Ship's
   ``ShipUpgradeInfo`` entries.  Each upgrade exposes a ``ucType`` (e.g.
   ``"_Hull"``), the variant token list per slot (``components`` dict), and the
   upgrade's numeric ``id`` (which is the WG module id).
2. Use ``ships_cache.json`` (already populated from the public WG API) as the
   canonical source for the localized module names by module id.
3. As a final fallback, return ``None`` so the caller can keep its own
   prettified label.
"""
from __future__ import annotations

import json
import pickle
import struct
import sys
import zlib
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GAMEPARAMS_PATH = ROOT / "content" / "GameParams.data"
SHIPS_CACHE_PATH = ROOT / "ships_cache.json"

# Map replay ``shipComponents`` slot keys to the matching ``ucType`` used by
# ShipUpgradeInfo entries.  Only slots that map to user-pickable upgrades are
# listed -- bundled sub-components (airDefense, atba, radars, ...) intentionally
# fall through so the UI does not mislabel them with the hull name.
SLOT_TO_UC_TYPE: dict[str, str] = {
    "hull": "_Hull",
    "artillery": "_Artillery",
    "engine": "_Engine",
    "fireControl": "_Suo",
    "torpedoes": "_Torpedoes",
    "fighter": "_Fighter",
    "diveBomber": "_DiveBomber",
    "torpedoBomber": "_TorpedoBomber",
    "skipBomber": "_SkipBomber",
    "flightControl": "_PrimaryWeapons",
}


def _install_gameparams_module() -> None:
    if "GameParams" in sys.modules:
        return

    class GameParams(ModuleType):
        class TypeInfo:
            pass

        class GPData:
            pass

    sys.modules["GameParams"] = GameParams("GameParams")


def _as_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dict__"):
        return vars(obj)
    if isinstance(obj, dict):
        return obj
    return {}


@lru_cache(maxsize=1)
def _load_gameparams_root() -> dict[str, Any]:
    if not GAMEPARAMS_PATH.is_file():
        return {}
    _install_gameparams_module()
    raw = GAMEPARAMS_PATH.read_bytes()
    raw = struct.pack("B" * len(raw), *raw[::-1])
    raw = zlib.decompress(raw)
    try:
        loaded = pickle.loads(raw, encoding="latin1")
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    inner = loaded.get("")
    return inner if isinstance(inner, dict) else {}


@lru_cache(maxsize=1)
def _load_ships_cache() -> dict[str, Any]:
    try:
        data = json.loads(SHIPS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _ships_by_id() -> dict[int, dict[str, Any]]:
    """Build a ``ship_id -> GameParams ship attrs`` lookup."""
    root = _load_gameparams_root()
    out: dict[int, dict[str, Any]] = {}
    for value in root.values():
        attrs = _as_dict(value)
        if not attrs:
            continue
        typeinfo = _as_dict(attrs.get("typeinfo"))
        if str(typeinfo.get("type") or "") != "Ship":
            continue
        try:
            sid = int(attrs.get("id"))
        except (TypeError, ValueError):
            continue
        out[sid] = attrs
    return out


@lru_cache(maxsize=512)
def _ship_slot_index(ship_id: int) -> dict[str, dict[str, int]]:
    """Return ``{slot_name: {variant_token: module_id}}`` for ``ship_id``."""
    ship_attrs = _ships_by_id().get(int(ship_id))
    if not ship_attrs:
        return {}
    upgrade_info = _as_dict(ship_attrs.get("ShipUpgradeInfo"))
    if not upgrade_info:
        return {}
    root = _load_gameparams_root()
    result: dict[str, dict[str, int]] = {}
    for upgrade_name, upgrade in upgrade_info.items():
        upgrade_attrs = _as_dict(upgrade)
        if not upgrade_attrs:
            continue
        uc_type = upgrade_attrs.get("ucType")
        components = upgrade_attrs.get("components")
        if not isinstance(uc_type, str) or not isinstance(components, dict):
            continue
        # Stubs inside ShipUpgradeInfo lack the numeric id -- look it up on the
        # top-level entry.
        module_id = upgrade_attrs.get("id")
        if module_id is None:
            top_entry = _as_dict(root.get(upgrade_name))
            module_id = top_entry.get("id")
        try:
            module_id_int = int(module_id) if module_id is not None else None
        except (TypeError, ValueError):
            module_id_int = None
        if module_id_int is None:
            continue
        for slot, variants in components.items():
            if SLOT_TO_UC_TYPE.get(str(slot)) != uc_type:
                continue
            if not isinstance(variants, (list, tuple)):
                continue
            for token in variants:
                if token:
                    result.setdefault(str(slot), {})[str(token)] = module_id_int
    return result


def resolve_proper_module_name(
    ship_id: Any,
    slot: str,
    raw_value: Any,
) -> str | None:
    """Return the localized module name for a replay component or ``None``."""
    try:
        sid = int(ship_id)
    except (TypeError, ValueError):
        return None
    if not slot or not raw_value:
        return None
    module_id = _ship_slot_index(sid).get(str(slot), {}).get(str(raw_value))
    if module_id is None:
        return None
    ship_entry = _load_ships_cache().get(str(sid))
    if not isinstance(ship_entry, dict):
        return None
    modules_tree = ship_entry.get("modules_tree")
    if not isinstance(modules_tree, dict):
        return None
    info = modules_tree.get(str(module_id))
    if not isinstance(info, dict):
        return None
    name = str(info.get("name") or "").strip()
    return name or None


def resolve_module_names_for_ship(
    ship_id: Any,
    components: dict[str, Any],
) -> dict[str, str]:
    """Resolve every component value in one go -- useful for batch updates."""
    out: dict[str, str] = {}
    if not isinstance(components, dict):
        return out
    for slot, raw_value in components.items():
        name = resolve_proper_module_name(ship_id, slot, raw_value)
        if name:
            out[str(slot)] = name
    return out
