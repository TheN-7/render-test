"""Resolve WoWS modernization (ship upgrade slot) data from the replay.

The replay encodes the six mounted upgrades inside ``shipConfigDump`` -- not as
ASCII strings but as 32-bit little-endian unsigned consumable IDs.  The layout
observed in extracted replays is::

    uint32[0]    constant 1
    uint32[1]    ship_params_id
    uint32[2..3] dump lengths
    uint32[4..18] ship module ids + zero padding
    uint32[19]   modernization count (6 for tier 10s, fewer for low tiers)
    uint32[20..20+N-1]  mounted modernization consumable IDs (in slot order)
    ...          signals, flags, etc.

This module loads ``content/modernizations_cache.json`` (built offline from the
public WG ``/wows/encyclopedia/consumables/?type=Modernization`` endpoint) and
exposes a helper that turns the binary dump into a list of
``{"code", "label", "slot", ...}`` records ordered by upgrade slot.
"""
from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MODERNIZATIONS_CACHE_PATH = ROOT / "content" / "modernizations_cache.json"

# Offset (in uint32 units) at which the modernization count appears in the
# decoded ``shipConfigDump``.  Determined empirically from extracted replays --
# the same offsets are produced regardless of ship tier.
MOD_COUNT_OFFSET = 19
MOD_LIST_OFFSET = 20
MOD_MAX_SLOTS = 6


@lru_cache(maxsize=1)
def _load_modernizations_cache() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(MODERNIZATIONS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _id_to_pcm_index() -> dict[int, str]:
    out: dict[int, str] = {}
    for pcm, info in _load_modernizations_cache().items():
        try:
            out[int(info.get("consumable_id"))] = pcm
        except (TypeError, ValueError):
            continue
    return out


def resolve_modernization(consumable_id: int) -> dict[str, Any] | None:
    pcm = _id_to_pcm_index().get(int(consumable_id))
    if not pcm:
        return None
    info = _load_modernizations_cache().get(pcm) or {}
    return {
        "code": pcm,
        "consumable_id": int(consumable_id),
        "name": info.get("name") or pcm,
        "slot": info.get("slot"),
        "image": info.get("image"),
        "effects": info.get("effects") or [],
    }


def parse_mounted_modernizations(config_dump_hex: str | None) -> list[dict[str, Any]]:
    """Decode the six mounted upgrades from ``shipConfigDumpHex``.

    Returns one entry per occupied slot, in slot order.  Unknown IDs are
    skipped silently so the caller doesn't render mystery tiles.
    """
    if not config_dump_hex:
        return []
    try:
        payload = bytes.fromhex(str(config_dump_hex).strip())
    except ValueError:
        return []
    n = len(payload) // 4
    if n <= MOD_LIST_OFFSET:
        return []
    uints = struct.unpack(f"<{n}I", payload[: n * 4])
    count = uints[MOD_COUNT_OFFSET]
    if not (0 < count <= MOD_MAX_SLOTS):
        # Defensive: cap to the WoWS-supported maximum of 6 slots.
        count = min(MOD_MAX_SLOTS, max(0, count))
    upgrades: list[dict[str, Any]] = []
    for slot_idx in range(count):
        position = MOD_LIST_OFFSET + slot_idx
        if position >= n:
            break
        mod_id = uints[position]
        if mod_id == 0:
            continue
        resolved = resolve_modernization(mod_id)
        if resolved is None:
            # Unknown / event-only mod: still surface it as a raw entry so the
            # caller knows the slot was occupied.
            upgrades.append({
                "code": f"ID:{mod_id}",
                "consumable_id": int(mod_id),
                "name": f"Unknown upgrade ({mod_id})",
                "slot": slot_idx + 1,
                "image": None,
                "effects": [],
                "slot_position": slot_idx + 1,
            })
            continue
        resolved["slot_position"] = slot_idx + 1
        upgrades.append(resolved)
    return upgrades
