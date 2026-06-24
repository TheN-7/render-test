from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from core.consumable_resolver import build_consumable_entries, find_consumable_icon_path
from core.modernization_resolver import parse_mounted_modernizations
from core.module_name_resolver import SLOT_TO_UC_TYPE, resolve_proper_module_name

ROOT = Path(__file__).resolve().parent.parent
MODULE_ICON_ROOT = ROOT / "gui" / "modules"
MODERNIZATION_ICON_ROOT = ROOT / "gui" / "modernization_icons"
CONSUMABLE_ICON_ROOT = ROOT / "gui" / "consumables"

# Per-slot icon overrides used by ``load_module_tile_icon``.  These bypass the
# modernization-icon fallback so the displayed icon always matches the slot's
# real-world role rather than whatever upgrade happens to be mounted in it.
MODULE_ICON_PATH_OVERRIDES: dict[str, Path] = {
    "engine": MODULE_ICON_ROOT / "icon_module_Engine_installed.png",
    "fireControl": MODULE_ICON_ROOT / "icon_module_Suo_installed.png",
    "artillery": MODULE_ICON_ROOT / "icon_module_Artillery_installed.png",
    "torpedoes": MODULE_ICON_ROOT / "icon_module_Torpedoes_installed.png",
}
LAYOUT_PATH = ROOT / "content" / "ship_build_layout.json"

HIDDEN_COMPONENT_KEYS = {
    "abilities",
    "abilitiesSlot0",
    "abilitiesSlot1",
    "abilitiesSlot2",
    "abilitiesSlot3",
    "aiParams",
    "airshipPlane",
    "antiMissile",
    "auxiliaryPlane",
    "axisLaser",
    "cameras",
    "chargeLasers",
    "finders",
    "impulseLasers",
    "innateSkills",
    "missiles",
    "phaserLasers",
    "scout",
    "specials",
    "underwaterCamera",
    "waves",
    "wcs",
    "directors",
}

COMPONENT_SLOT_ICON: dict[str, str] = {
    "artillery": "Artillery",
    "hull": "Hull",
    "engine": "Engine",
    "torpedoes": "Torpedoes",
    "fighter": "Fighter",
    "diveBomber": "DiveBomber",
    "torpedoBomber": "TorpedoBomber",
    "skipBomber": "SkipBomber",
    "flightControl": "PrimaryWeapons",
    "fireControl": "Suo",
    "airDefense": "SecondaryWeapons",
    "atba": "SecondaryWeapons",
    "airArmament": "Artillery",
    "airSupport": "Fighter",
    "pinger": "Sonar",
    "depthCharges": "Torpedoes",
    "sonar": "Sonar",
    "radars": "Sonar",
    "hydroSearch": "Sonar",
    "torpedoLaunchers": "Torpedoes",
}

COMPONENT_MODERNIZATION_KIND: dict[str, str] = {
    "artillery": "MainGun",
    "torpedoes": "Torpedo",
    "engine": "Engine",
    "flightControl": "FlightControl",
    "fireControl": "FireControl",
    "airDefense": "AirDefense",
    "atba": "SecondaryGun",
    "fighter": "Fighter",
    "diveBomber": "DiveBomber",
    "torpedoBomber": "TorpedoBomber",
    "skipBomber": "SkipBomber",
    "pinger": "Pinger",
    "depthCharges": "DepthCharges",
    "sonar": "SonarSearch",
    "hydroSearch": "Hydrophone",
    "radars": "LookoutStation",
}


def normalize_ship_type_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    aliases = {
        "aircraftcarrier": "aircarrier",
        "carrier": "aircarrier",
        "cv": "aircarrier",
        "sub": "submarine",
    }
    return aliases.get(text, text)


def _layout_label_for_ship_type(ship_type: str) -> str:
    data = _load_ship_build_layout()
    target = normalize_ship_type_key(ship_type)
    for label in data:
        if normalize_ship_type_key(label) == target:
            return label
    return ""


@lru_cache(maxsize=1)
def _load_ship_build_layout() -> dict[str, Any]:
    try:
        raw = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


@lru_cache(maxsize=1)
def _modernization_icon_index() -> dict[str, str]:
    index: dict[str, str] = {}
    if not MODERNIZATION_ICON_ROOT.is_dir():
        return index
    for path in MODERNIZATION_ICON_ROOT.glob("icon_modernization_*.png"):
        match = re.search(r"(PCM\d+)", path.name)
        if match:
            index[match.group(1)] = path.name
    return index


@lru_cache(maxsize=1)
def _modernization_kind_index() -> dict[str, str]:
    """Map modernization kind (MainGun, FlightControl, ...) to a tier-I icon filename."""
    by_kind: dict[str, str] = {}
    if not MODERNIZATION_ICON_ROOT.is_dir():
        return by_kind
    for path in sorted(MODERNIZATION_ICON_ROOT.glob("icon_modernization_PCM*.png")):
        match = re.match(r"icon_modernization_PCM\d+_(.+)_Mod_([IVX]+)\.png$", path.name)
        if not match:
            continue
        kind, tier = match.group(1), match.group(2)
        if tier == "I" and kind not in by_kind:
            by_kind[kind] = path.name
    return by_kind


def parse_mounted_upgrades(config_dump_hex: str | None) -> list[dict[str, str]]:
    """Return the six mounted modernizations with proper localized names.

    Entries are ordered by upgrade slot (slot 1 .. slot 6) and carry both the
    legacy ``code``/``label``/``icon`` keys used by the renderer and richer
    metadata (``name``, ``slot_position``, ``effects``) for tooltips.
    """
    upgrades_meta = parse_mounted_modernizations(config_dump_hex)
    icon_index = _modernization_icon_index()
    rows: list[dict[str, str]] = []
    for meta in upgrades_meta:
        code = str(meta.get("code") or "")
        icon_name = icon_index.get(code, "")
        rows.append({
            "code": code,
            "label": str(meta.get("name") or code),
            "icon": icon_name,
            "slot_position": meta.get("slot_position"),
            "effects": meta.get("effects") or [],
            "consumable_id": meta.get("consumable_id"),
        })
    return rows


def _modernization_label_from_icon(icon_name: str, code: str) -> str:
    match = re.match(r"icon_modernization_PCM\d+_(.+)_Mod_[IVX]+\.png$", icon_name)
    if not match:
        return code
    kind = match.group(1)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", kind)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    tier_match = re.search(r"_Mod_([IVX]+)\.png$", icon_name)
    tier = tier_match.group(1) if tier_match else ""
    if tier:
        return f"{text} {tier}".strip()
    return text.strip()


def _component_is_default(raw_value: Any) -> bool:
    text = str(raw_value or "").strip()
    return not text or text.endswith("Default")


def _split_layout_keys(components: dict[str, Any], ship_type: str) -> tuple[list[str], list[str]]:
    layout_label = _layout_label_for_ship_type(ship_type)
    layout = _load_ship_build_layout().get(layout_label, {}) if layout_label else {}
    # Restrict to slots that map to user-pickable WoWS upgrades. Bundled
    # sub-components (airDefense, atba, radars, ...) are hidden because they
    # always travel with the hull and are not independently selectable.
    upgradeable = set(SLOT_TO_UC_TYPE.keys())
    stock_keys = [
        str(key)
        for key in (layout.get("stock") or [])
        if key in components and key in upgradeable
    ]
    fitted_keys = [
        str(key)
        for key in (layout.get("fitted") or [])
        if key in components and key in upgradeable
    ]
    known = set(stock_keys) | set(fitted_keys)
    for key in sorted(components):
        if key in known or key in HIDDEN_COMPONENT_KEYS or key not in upgradeable:
            continue
        if _component_is_default(components.get(key)):
            continue
        fitted_keys.append(key)
    return stock_keys, fitted_keys


def build_module_entries(
    components: dict[str, Any],
    *,
    ship_type: str,
    ship_id: Any = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    stock_keys, fitted_keys = _split_layout_keys(components, ship_type)
    stock = [_module_entry(key, components.get(key), ship_id=ship_id) for key in stock_keys if not _component_is_default(components.get(key))]
    fitted = [_module_entry(key, components.get(key), ship_id=ship_id) for key in fitted_keys if not _component_is_default(components.get(key))]
    return [row for row in stock if row], [row for row in fitted if row]


def _module_entry(component_key: str, raw_value: Any, *, ship_id: Any = None) -> dict[str, str]:
    value = str(raw_value or "").strip()
    proper_name = resolve_proper_module_name(ship_id, component_key, value) if ship_id else None
    return {
        "key": component_key,
        "slot_label": _slot_label(component_key),
        "variant": proper_name or _variant_label(value),
        "raw_variant": _variant_label(value),
        "proper_name": proper_name or "",
        "icon_module": _module_icon_basename(component_key),
        "icon_modernization": _modernization_icon_for_component(component_key, value),
    }


def _slot_label(component_key: str) -> str:
    replacements = {
        "atba": "Secondaries",
        "airDefense": "AA",
        "flightControl": "Flight Control",
        "fireControl": "Fire Control",
        "diveBomber": "Dive Bomber",
        "torpedoBomber": "Torpedo Bomber",
        "skipBomber": "Skip Bomber",
        "depthCharges": "Depth Charges",
        "hydroSearch": "Hydro",
        "torpedoLaunchers": "Torpedoes",
    }
    if component_key in replacements:
        return replacements[component_key]
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", component_key)
    return text.replace("_", " ").strip().title()


def _variant_label(raw_value: str) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[A-Z]_", "", text)
    text = re.sub(r"TypeDefault$", "", text)
    text = re.sub(r"Default$", "", text)
    text = re.sub(r"Type$", "", text)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _module_icon_basename(component_key: str) -> str:
    return COMPONENT_SLOT_ICON.get(component_key, "PrimaryWeapons")


def _modernization_icon_for_component(component_key: str, raw_value: str) -> str:
    code_match = re.search(r"(PCM\d{3})", raw_value)
    if code_match:
        icon_name = _modernization_icon_index().get(code_match.group(1))
        if icon_name:
            return icon_name
    kind = COMPONENT_MODERNIZATION_KIND.get(component_key)
    if kind:
        return _modernization_kind_index().get(kind, "")
    return ""


def find_module_icon_path(icon_module_basename: str, *, installed: bool = True) -> Path | None:
    suffix = "_installed" if installed else ""
    candidate = MODULE_ICON_ROOT / f"icon_module_{icon_module_basename}{suffix}.png"
    if candidate.is_file():
        return candidate
    fallback = MODULE_ICON_ROOT / f"icon_module_{icon_module_basename}.png"
    if fallback.is_file():
        return fallback
    return None


def find_modernization_icon_path(icon_name: str) -> Path | None:
    if not icon_name:
        return None
    path = MODERNIZATION_ICON_ROOT / icon_name
    return path if path.is_file() else None


def load_module_tile_icon(entry: dict[str, str], size: int) -> Image.Image | None:
    override = MODULE_ICON_PATH_OVERRIDES.get(str(entry.get("key") or ""))
    if override is not None and override.is_file():
        path: Path | None = override
    else:
        icon_name = entry.get("icon_modernization") or ""
        path = find_modernization_icon_path(icon_name)
        if path is None:
            path = find_module_icon_path(entry.get("icon_module") or "")
    if path is None:
        return None
    try:
        icon = Image.open(path).convert("RGBA")
    except Exception:
        return None
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    return icon


def load_upgrade_tile_icon(upgrade: dict[str, str], size: int) -> Image.Image | None:
    path = find_modernization_icon_path(upgrade.get("icon") or "")
    if path is None:
        return None
    try:
        icon = Image.open(path).convert("RGBA")
    except Exception:
        return None
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    return icon


def load_consumable_tile_icon(entry: dict[str, str], size: int) -> Image.Image | None:
    path = find_consumable_icon_path(entry.get("icon") or "")
    if path is None:
        return None
    try:
        icon = Image.open(path).convert("RGBA")
    except Exception:
        return None
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    return icon
