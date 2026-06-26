from __future__ import annotations

import json
import math
import os
import pickle
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

try:
    from utils.map_names import get_battlearena_entry
except Exception:
    get_battlearena_entry = None


WOWS_BG = (10, 17, 28)
WOWS_PANEL = (20, 28, 40)
WOWS_PANEL_ALT = (25, 34, 49)
WOWS_PANEL_INNER = (13, 18, 26)
WOWS_OUTLINE = (86, 114, 149)
WOWS_OUTLINE_SOFT = (58, 72, 88)
WOWS_TEXT = (238, 244, 250)
WOWS_TEXT_SUB = (173, 185, 199)
WOWS_TEXT_DIM = (130, 141, 155)
WOWS_ACCENT = (124, 179, 232)
WOWS_FRIENDLY = (93, 214, 105)
WOWS_ENEMY = (234, 92, 92)
WOWS_UNKNOWN = (203, 209, 218)
WOWS_NEUTRAL = (196, 202, 212)
WOWS_WHITE = (248, 248, 248)
WOWS_GOLD = (246, 214, 104)
WOWS_WARNING = (255, 184, 96)
COLOR_BG = WOWS_BG
COLOR_UNSPOTTED = WOWS_NEUTRAL
COLOR_SUNK = (90, 90, 90)
WG_ICON_HEADING_OFFSET_DEG = -90.0
RENDER_PRESTART_LEAD_S = 5.0
_MOVEMENT_THRESHOLD = 5.0
COLOR_FRIENDLY = WOWS_FRIENDLY
COLOR_ENEMY = WOWS_ENEMY
COLOR_UNKNOWN = WOWS_UNKNOWN
INGAME_FONT_FACE = "discord"
SIDEBAR_TEXT_SCALE = 1.5
SIDEBAR_WIDTH_SCALE = 1.3
PLAYER_CARD_TEXT_SCALE = 1.37
SHIP_TYPE_TO_CODE = {
    "Destroyer": "DD",
    "Cruiser": "CA",
    "Battleship": "BB",
    "AirCarrier": "CV",
    "Submarine": "SS",
}
ARMS_RACE_ZONE_PARAM_KIND_FALLBACK = {
    4292757424: "regeneration",   
    4291708848: "shot_delay",    
    4251862960: "health",         
    4250814384: "weapon_damage",  
}
ARMS_RACE_KIND_TO_RULE_ICON = {
    "regeneration": "icon_rules_gamemode_arms_race_0.png",
    "shot_delay": "icon_rules_gamemode_arms_race_1.png",
    "weapon_damage": "icon_rules_gamemode_arms_race_2.png",
    "health": "icon_rules_gamemode_arms_race_3.png",
}
SQUADRON_TYPE_TO_ICON = {
    "torpedo": "icon_default_plane_torpedo.png",
    "torpedo_deepwater": "icon_default_plane_torpedo_deepwater.png",
    "bomber": "icon_default_plane_bomb_he.png",
    "bomber_ap": "icon_default_plane_bomb_ap.png",
    "skip": "icon_default_plane_skip_bomb_he.png",
    "skip_ap": "icon_default_plane_skip_bomb_ap.png",
    "rocket": "icon_default_plane_projectile.png",
    "rocket_ap": "icon_default_plane_projectile_ap.png",
    "fighter": "icon_default_plane_fighter_.png",
    "asw": "icon_default_asup_bomb_depthcharge.png",
    "asw_mine": "icon_default_asup_mine.png",
    "airdrop": "icon_default_asup.png",
    "airdrop_he": "icon_default_asup_bomb_he.png",
    "main": "icon_default_plane_projectile.png",
    "default": "icon_default_plane_projectile.png",
}
SQUADRON_TYPE_LABELS = {
    "fighter": "Fighter",
    "rocket": "Rocket",
    "rocket_ap": "AP Rocket",
    "torpedo": "Torpedo",
    "torpedo_deepwater": "Deepwater Torp",
    "bomber": "HE Bomber",
    "bomber_ap": "AP Bomber",
    "skip": "Skip Bomber",
    "skip_ap": "AP Skip",
    "asw": "ASW",
    "asw_mine": "ASW Mine",
    "airdrop": "Airdrop",
    "airdrop_he": "HE Airdrop",
    "main": "Aircraft",
    "default": "Aircraft",
}
SQUADRON_LEGEND_ORDER = [
    "fighter",
    "rocket",
    "rocket_ap",
    "torpedo",
    "torpedo_deepwater",
    "bomber",
    "bomber_ap",
    "skip",
    "skip_ap",
    "airdrop",
    "airdrop_he",
    "asw",
    "asw_mine",
    "main",
]
AIRCRAFT_ICON_HEADING_OFFSET_DEG = 35.0
DEFAULT_SMOKE_DURATION_S = 90.0
LINEUP_CLASS_ORDER = {
    "Submarine": 0,
    "Destroyer": 1,
    "Cruiser": 2,
    "Battleship": 3,
    "AirCarrier": 4,
}
RIBBON_ID_TO_ASSET = {
    0: "main_caliber",
    1: "torpedo",
    2: "bomb",
    3: "plane",
    4: "crit",
    5: "frag",
    6: "burn",
    7: "flood",
    8: "citadel",
    9: "base_defense",
    10: "base_capture",
    11: "base_capture_assist",
    12: "suppressed",
    13: "secondary_caliber",
    14: "subribbons/subribbon_main_caliber_over_penetration.png",
    15: "subribbons/subribbon_main_caliber_penetration.png",
    16: "subribbons/subribbon_main_caliber_no_penetration.png",
    17: "subribbons/subribbon_main_caliber_ricochet.png",
    18: "building_kill",
    19: "detected",
    20: "subribbons/subribbon_bomb_over_penetration.png",
    21: "subribbons/subribbon_bomb_penetration.png",
    22: "subribbons/subribbon_bomb_no_penetration.png",
    23: "subribbons/subribbon_bomb_ricochet.png",
    24: "rocket",
    25: "subribbons/subribbon_rocket_penetration.png",
    26: "subribbons/subribbon_rocket_no_penetration.png",
    27: "splane",
    28: "subribbons/subribbon_bulge.png",
    29: "subribbons/subribbon_bomb_bulge.png",
    30: "subribbons/subribbon_rocket_bulge.png",
    31: "dbomb",
    32: "acoustic_hit",
    33: "drop",
    34: "subribbons/subribbon_rocket_ricochet.png",
    35: "subribbons/subribbon_rocket_over_penetration.png",
    39: "subribbons/subribbon_acoustic_hit_vehicle_new.png",
    40: "subribbons/subribbon_acoustic_hit_vehicle_curr.png",
    41: "subribbons/subribbon_acoustic_hit_vehicle_block.png",
    43: "subribbons/subribbon_dbomb_full_damage.png",
    44: "subribbons/subribbon_dbomb_partial_damage.png",
    45: "mine",
    46: "demining_mine",
    47: "demining_minefield",
}


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _median_value(values: List[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) / 2.0
    return float(ordered[mid])


@lru_cache(maxsize=192)
def _load_font(size: int, bold: bool = True, face: str = INGAME_FONT_FACE):
    fonts_dir = _root_dir() / "gui" / "fonts"
    bundled_fonts = (
        [fonts_dir / "WarHeliosCondCBold (1).ttf", fonts_dir / "WarHeliosCondC (1).ttf"]
        if bold
        else [fonts_dir / "WarHeliosCondC (1).ttf", fonts_dir / "WarHeliosCondCBold (1).ttf"]
    )
    for font_path in bundled_fonts:
        try:
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size)
        except Exception:
            continue

    face_key = str(face or "default").strip().lower()
    if face_key in {"discord", "discord font", "discord_ui", "discord ui"}:
        font_names = (
            ["gg sans.ttf", "ggsans.ttf", "whitney.ttf", "seguisb.ttf", "segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"]
            if bold
            else ["gg sans.ttf", "ggsans.ttf", "whitney.ttf", "segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf"]
        )
    elif face_key in {"default", "panel", "ingame", "hud"}:
        font_names = (
            ["verdanab.ttf", "trebucbd.ttf", "segoeuib.ttf", "arialbd.ttf", "arial.ttf"]
            if bold
            else ["verdana.ttf", "trebuc.ttf", "segoeui.ttf", "arial.ttf", "arialbd.ttf"]
        )
    else:
        font_names = (
            ["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"]
            if bold
            else ["segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf"]
        )
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=2048)
def _text_sprite(
    text: str,
    size: int,
    fill: Tuple[int, int, int],
    shadow: Tuple[int, int, int] | None = None,
    bold: bool = True,
    stroke_width: int = 0,
    stroke_fill: Tuple[int, int, int] | None = None,
    face: str = INGAME_FONT_FACE,
) -> Image.Image | None:
    if not text:
        return None
    font = _load_font(size, bold=bold, face=face)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe)
    bbox = probe_draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    shadow_pad = 1 if shadow is not None else 0
    width = max(1, (bbox[2] - bbox[0]) + shadow_pad + stroke_width + 1)
    height = max(1, (bbox[3] - bbox[1]) + shadow_pad + stroke_width + 1)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    ox = -bbox[0]
    oy = -bbox[1]
    if shadow is not None:
        draw.text((ox + 1, oy + 1), text, fill=shadow, font=font, stroke_width=stroke_width, stroke_fill=stroke_fill)
    draw.text((ox, oy), text, fill=fill, font=font, stroke_width=stroke_width, stroke_fill=stroke_fill)
    return img


@lru_cache(maxsize=4096)
def _fit_text_to_width(
    text: str,
    size: int,
    max_width: int,
    bold: bool = True,
    stroke_width: int = 0,
    face: str = INGAME_FONT_FACE,
    ellipsis: str = "~",
) -> str:
    text = str(text or "").strip()
    if not text or max_width <= 0:
        return ""
    font = _load_font(size, bold=bold, face=face)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe)

    def _width(value: str) -> int:
        if not value:
            return 0
        bbox = probe_draw.textbbox((0, 0), value, font=font, stroke_width=stroke_width)
        return max(0, int(bbox[2] - bbox[0]))

    if _width(text) <= max_width:
        return text

    suffix = ellipsis if ellipsis else ""
    lo, hi = 0, len(text)
    best = suffix if _width(suffix) <= max_width else ""
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip()
        if mid < len(text) and suffix:
            candidate = (candidate + suffix) if candidate else suffix
        w = _width(candidate)
        if w <= max_width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _paste_sprite(img: Image.Image, sprite: Image.Image | None, x: int, y: int) -> None:
    if sprite is None:
        return
    img.paste(sprite, (x, y), sprite)


def _paste_center_rgba(img: Image.Image, sprite: Image.Image | None, cx: int, cy: int) -> None:
    if sprite is None:
        return
    x = int(round(cx - sprite.width / 2))
    y = int(round(cy - sprite.height / 2))
    img.paste(sprite, (x, y), sprite)


@lru_cache(maxsize=96)
def _smoke_cloud_sprite(radius_px: int, scale_key: int = 100) -> Image.Image | None:
    base_radius = max(6, int(radius_px))
    scale = max(0.6, float(scale_key) / 100.0)

    outer_fill = (156, 162, 170, 36)
    inner_fill = (212, 216, 222, 88)
    core_fill = (246, 247, 249, 88)
    center_fill = (252, 252, 253, 76)

    outer_r = max(10, int(round(base_radius * 1.45 * scale)))
    inner_r = max(8, int(round(base_radius * 1.05 * scale)))
    core_r = max(5, int(round(base_radius * 0.68 * scale)))
    center_r = max(5, int(round(base_radius * 0.5 * scale)))

    max_offset = outer_r + int(math.ceil(outer_r * 0.42))
    size = max(18, max_offset * 2 + 8)
    cx = size // 2
    cy = size // 2

    sprite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(sprite, "RGBA")
    lobes = (
        (0.0, 0.0, 1.00),
        (-0.34, -0.10, 0.82),
        (0.28, 0.16, 0.78),
    )
    for ox, oy, lobe_scale in lobes:
        lobe_outer = max(8, int(round(outer_r * lobe_scale)))
        lobe_inner = max(6, int(round(inner_r * lobe_scale)))
        lobe_core = max(4, int(round(core_r * lobe_scale)))
        lx = cx + ox * outer_r
        ly = cy + oy * outer_r
        overlay_draw.ellipse([lx - lobe_outer, ly - lobe_outer, lx + lobe_outer, ly + lobe_outer], fill=outer_fill)
        overlay_draw.ellipse([lx - lobe_inner, ly - lobe_inner, lx + lobe_inner, ly + lobe_inner], fill=inner_fill)
        overlay_draw.ellipse([lx - lobe_core, ly - lobe_core, lx + lobe_core, ly + lobe_core], fill=core_fill)

    overlay_draw.ellipse([cx - center_r, cy - center_r, cx + center_r, cy + center_r], fill=center_fill)
    blur_radius = max(2.0, base_radius * 0.3 * scale)
    return sprite.filter(ImageFilter.GaussianBlur(radius=blur_radius))


@lru_cache(maxsize=1)
def _load_ship_cache() -> Dict[str, Dict[str, Any]]:
    cache_path = Path(__file__).resolve().parent.parent / "ships_cache.json"
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _load_ship_gameparams_reference() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "content" / "ships_gameparams.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ship_reference_entry(ship_id: Any) -> Dict[str, Any]:
    sid = _safe_int(ship_id)
    if sid is None:
        return {}
    payload = _load_ship_gameparams_reference()
    by_ship = payload.get("by_ship_id", {}) if isinstance(payload, dict) else {}
    entry = by_ship.get(str(int(sid))) if isinstance(by_ship, dict) else None
    return entry if isinstance(entry, dict) else {}


@lru_cache(maxsize=1)
def _load_ship_aircraft_support_reference() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "content" / "ship_aircraft_support.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ship_aircraft_support(ship_id: Any) -> Dict[str, Any]:
    sid = _safe_int(ship_id)
    if sid is None:
        return {}
    payload = _load_ship_aircraft_support_reference()
    by_ship = payload.get("by_ship_id", {}) if isinstance(payload, dict) else {}
    entry = by_ship.get(str(int(sid))) if isinstance(by_ship, dict) else None
    return entry if isinstance(entry, dict) else {}


@lru_cache(maxsize=1)
def _load_ship_consumables_reference() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "content" / "ship_consumables.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ship_has_consumable(ship_id: Any, kind: str) -> bool:
    sid = _safe_int(ship_id)
    if sid is None:
        return False
    payload = _load_ship_consumables_reference()
    by_ship = payload.get("by_ship_id", {}) if isinstance(payload, dict) else {}
    entry = by_ship.get(str(int(sid))) if isinstance(by_ship, dict) else None
    if not isinstance(entry, dict):
        return False
    by_kind = entry.get("by_kind", {})
    if isinstance(by_kind, dict):
        rows = by_kind.get(str(kind or "").strip().lower())
        if isinstance(rows, list) and rows:
            return True
    values = entry.get("consumables", [])
    if not isinstance(values, list):
        return False
    target = str(kind or "").strip().lower()
    return any(str(value or "").strip().lower() == target for value in values)


def _ship_entry(ship_id: Any) -> Dict[str, Any]:
    cache = _load_ship_cache()
    try:
        key = str(int(ship_id))
    except (TypeError, ValueError):
        return {}
    cache_entry = cache.get(key, {})
    if not isinstance(cache_entry, dict):
        cache_entry = {}
    ref_entry = _ship_reference_entry(ship_id)
    if not ref_entry:
        return cache_entry
    if not cache_entry:
        return dict(ref_entry)
    merged = dict(ref_entry)
    merged.update(cache_entry)
    for field in ("name", "display_name", "type", "species", "nation", "index", "internal_name"):
        if not merged.get(field):
            merged[field] = ref_entry.get(field) or cache_entry.get(field)
    if merged.get("tier") in (None, ""):
        merged["tier"] = ref_entry.get("tier")
    return merged


def _ship_type(ship_id: Any) -> str:
    entry = _ship_entry(ship_id)
    return str(entry.get("type") or entry.get("species") or "")


def _ship_class_code(ship_id: Any) -> str:
    return SHIP_TYPE_TO_CODE.get(_ship_type(ship_id), "??")


def _ship_name(ship_id: Any) -> str:
    entry = _ship_entry(ship_id)
    return str(entry.get("name") or entry.get("display_name") or "")


def _root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _battle_hud_dir() -> Path:
    return _root_dir() / "gui" / "battle_hud"


def _ship_icons_dir() -> Path:
    return _root_dir() / "gui" / "ship_icons"


def _ships_silhouettes_dir() -> Path:
    return _root_dir() / "gui" / "ships_silhouettes"


def _ship_dead_icons_dir() -> Path:
    return _root_dir() / "gui" / "ship_dead_icons"


def _aircraft_dir() -> Path:
    return _root_dir() / "gui" / "service_kit" / "plane_types"


@lru_cache(maxsize=1)
def _load_gameparams_ship_meta() -> Dict[str, Dict[str, Dict[str, Any]]]:
    gameparams_path = _battle_hud_dir() / "GameParams.json"
    try:
        payload = json.loads(gameparams_path.read_text(encoding="utf-8"))
    except Exception:
        return {"by_id": {}, "by_index": {}, "by_name": {}}

    by_id: Dict[str, Dict[str, Any]] = {}
    by_index: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return {"by_id": by_id, "by_index": by_index, "by_name": by_name}

    for value in payload.values():
        if not isinstance(value, dict):
            continue
        typeinfo = value.get("typeinfo")
        if not isinstance(typeinfo, dict) or str(typeinfo.get("type") or "") != "Ship":
            continue
        ship_id = _safe_int(value.get("id"))
        ship_index = str(value.get("index") or "").strip()
        ship_name = str(value.get("name") or "").strip()
        if ship_id is None or not ship_index:
            continue
        meta = {
            "id": ship_id,
            "index": ship_index,
            "name": ship_name,
            "originShipName": str(value.get("originShipName") or "").strip(),
            "species": str(typeinfo.get("species") or "").strip(),
            "nation": str(typeinfo.get("nation") or "").strip(),
        }
        by_id[str(ship_id)] = meta
        by_index[ship_index] = meta
        if ship_name:
            by_name[ship_name] = meta
    return {"by_id": by_id, "by_index": by_index, "by_name": by_name}


def _gameparams_ship_entry(ship_id: Any) -> Dict[str, Any]:
    key = str(_safe_int(ship_id) or "")
    if not key:
        return {}
    entry = _load_gameparams_ship_meta().get("by_id", {}).get(key, {})
    if isinstance(entry, dict) and entry:
        return entry
    return _ship_reference_entry(ship_id)


def _icon_cache_dir() -> Path:
    p = _root_dir() / "content" / "wg_ship_type_icons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _kill_icon_cache_dir() -> Path:
    p = _root_dir() / "content" / "sessionstats_kill_icons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _consumables_dir() -> Path:
    return _root_dir() / "gui" / "consumables"


def _status_icons_dir() -> Path:
    return _root_dir() / "gui" / "battle_hud" / "own_ship_health"


def _load_status_icon(kind: str, size: int) -> Image.Image | None:
    if size <= 0:
        return None
    key = (kind, int(size))
    cached = _STATUS_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    mapping = {
        "fire": "icon_fire_small.png",
        "flood": "icon_flooding_small.png",
    }
    filename = mapping.get(kind)
    if not filename:
        return None
    path = _status_icons_dir() / filename
    if not path.exists():
        return None
    try:
        icon = Image.open(path).convert("RGBA")
    except Exception:
        return None
    target_h = max(8, int(size))
    scale = target_h / max(1, icon.height)
    target_w = max(1, int(round(icon.width * scale)))
    if icon.size != (target_w, target_h):
        icon = icon.resize((target_w, target_h), Image.Resampling.LANCZOS)
    _STATUS_ICON_CACHE[key] = icon
    return icon


def _load_consumable_icon(kind: str, size: int) -> Image.Image | None:
    if size <= 0:
        return None
    key = (kind, int(size))
    cached = _CONSUMABLE_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    mapping = {
        "radar": "consumable_PCY020_RLSSearchPremium.png",
        "hydro": "consumable_PCY016_SonarSearchPremium.png",
        "smoke": "consumable_PCY006_SmokeGenerator.png",
        "heal": "consumable_PCY002_RegenCrew.png",
        "engine": "consumable_PXY027_SpeedBooster.png",
    }
    filename = mapping.get(kind)
    if not filename:
        return None
    path = _consumables_dir() / filename
    if not path.exists():
        return None
    try:
        icon = Image.open(path).convert("RGBA")
    except Exception:
        return None
    target_h = max(8, int(size))
    scale = target_h / max(1, icon.height)
    target_w = max(1, int(round(icon.width * scale)))
    if icon.size != (target_w, target_h):
        icon = icon.resize((target_w, target_h), Image.Resampling.LANCZOS)
    _CONSUMABLE_ICON_CACHE[key] = icon
    return icon


def _map_cache_dir() -> Path:
    p = _root_dir() / "content" / "wg_map_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _map_assets_root() -> Path:
    return _root_dir() / "gui" / "spaces"


def _overviewmaps_path() -> Path:
    return _root_dir() / "content" / "overviewmaps.txt"


def _read_api_config() -> Tuple[str, str]:
    cfg_path = _root_dir() / "wws_api_config.json"
    app_id = ""
    realm = "eu"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        app_id = str(cfg.get("app_id", "")).strip()
        realm = str(cfg.get("realm", "eu")).strip().lower() or "eu"
    except Exception:
        pass
    return app_id, realm


def _base_url_for_realm(realm: str) -> str:
    realms = {
        "na": "https://api.worldofwarships.com/wows/",
        "eu": "https://api.worldofwarships.eu/wows/",
        "asia": "https://api.worldofwarships.asia/wows/",
        "ru": "https://api.worldofwarships.ru/wows/",
    }
    return realms.get(realm, realms["eu"])


def _download_bytes(url: str) -> bytes:
    with urlopen(url, timeout=20) as resp:
        return resp.read()


def _map_icon_url(canonical: Dict[str, Any]) -> str:
    meta = canonical.get("meta", {}) or {}
    icon_url = str(meta.get("map_icon_url", "") or "").strip()
    if icon_url:
        return icon_url
    if get_battlearena_entry is not None:
        entry = get_battlearena_entry(meta.get("mapId"))
        if isinstance(entry, dict):
            return str(entry.get("icon", "") or "").strip()
    return ""


def _local_map_slug(canonical: Dict[str, Any]) -> str:
    meta = canonical.get("meta", {}) or {}
    candidates = [
        str(meta.get("mapDisplayName") or "").strip(),
        str(meta.get("mapName") or "").strip(),
        str(meta.get("map_name_resolved") or "").strip(),
    ]
    for value in candidates:
        if not value:
            continue
        token = value.replace("\\", "/").split("/")[-1]
        if token and (_map_assets_root() / token).is_dir():
            return token
    return ""


@lru_cache(maxsize=64)
def _load_local_map_icon(slug: str) -> Image.Image | None:
    if not slug:
        return None
    file_path = _map_assets_root() / slug / "minimap.png"
    try:
        if file_path.exists():
            return Image.open(file_path).convert("RGBA")
    except Exception:
        return None
    return None


@lru_cache(maxsize=1)
def _load_overview_map_sizes() -> Dict[str, float]:
    path = _overviewmaps_path()
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return {}

    size_by_slug: Dict[str, float] = {}
    current_size_km: float | None = None
    size_re = re.compile(r"Size:\s*([0-9]+(?:\.[0-9]+)?)x([0-9]+(?:\.[0-9]+)?)\s*km", re.IGNORECASE)
    # Some unpacked overviewmaps files ship with truncated replay suffixes
    # like ".wowsrepla". Accept the full and truncated forms so map extents
    # still resolve to the intended overview size.
    replay_re = re.compile(
        r"Replay File Name:\s*.+?_([A-Za-z0-9_]+)\.wowsrepla(?:y)?",
        re.IGNORECASE,
    )

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        size_match = size_re.search(line)
        if size_match:
            try:
                current_size_km = float(size_match.group(1))
            except ValueError:
                current_size_km = None
            continue
        replay_match = replay_re.search(line)
        if replay_match and current_size_km is not None:
            slug = replay_match.group(1).strip()
            if slug:
                size_by_slug[slug] = current_size_km
    return size_by_slug


def _overview_half_extent(slug: str) -> float | None:
    if not slug:
        return None
    size_km = _load_overview_map_sizes().get(slug)
    if size_km is None or size_km <= 0.0:
        return None
    # WoWS minimap coordinates map cleanly when one render unit is treated as
    # roughly 30 meters of overview-map size. Example: 42 km -> 1400 wide.
    return float(size_km) * 1000.0 / 60.0


@lru_cache(maxsize=64)
def _load_map_world_bounds(slug: str) -> Tuple[float, float, float, float] | None:
    if not slug:
        return None
    settings_path = _map_assets_root() / slug / "space.settings"
    if not settings_path.exists():
        return None
    try:
        root = ET.fromstring(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    bounds = root.find("bounds")
    if bounds is None:
        return None

    def _read_bound(name: str) -> float | None:
        raw = bounds.attrib.get(name)
        if raw is not None and str(raw).strip():
            try:
                return float(str(raw).strip())
            except ValueError:
                return None
        child = bounds.find(name)
        if child is not None and (child.text or "").strip():
            try:
                return float((child.text or "").strip())
            except ValueError:
                return None
        return None

    try:
        chunk_node = root.find("chunkSize")
        chunk_size = float((chunk_node.text or "100").strip()) if chunk_node is not None and (chunk_node.text or "").strip() else 100.0
    except (TypeError, ValueError):
        chunk_size = 100.0

    min_chunk_x = _read_bound("minX")
    max_chunk_x = _read_bound("maxX")
    min_chunk_z = _read_bound("minY")
    max_chunk_z = _read_bound("maxY")
    if None in (min_chunk_x, max_chunk_x, min_chunk_z, max_chunk_z):
        return None

    min_x = float(min_chunk_x) * chunk_size
    max_x = (float(max_chunk_x) + 1.0) * chunk_size
    min_z = float(min_chunk_z) * chunk_size
    max_z = (float(max_chunk_z) + 1.0) * chunk_size
    if max_x <= min_x or max_z <= min_z:
        return None
    return (min_x, max_x, min_z, max_z)


def _unique_sorted(values: List[float], tolerance: float = 0.05) -> List[float]:
    unique: List[float] = []
    for value in sorted(float(v) for v in values):
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    return unique


@lru_cache(maxsize=64)
def _load_space_bin_world_bounds(slug: str) -> Tuple[float, float, float, float] | None:
    if not slug:
        return None

    space_path = _map_assets_root() / slug / "space.bin"
    if not space_path.exists():
        return None

    try:
        data = space_path.read_bytes()
    except Exception:
        return None

    # WoWS map space files store fixed-size records. The first vec4 in each
    # record is a world-space vertex, and the first record gives a stable
    # corner/edge seed we can use to recover the coarse map lattice.
    record_size = 112
    first_vec4_offset = 144
    tolerance = 0.05

    records: List[Tuple[float, float, float]] = []
    for offset in range(first_vec4_offset, len(data) - 16, record_size):
        try:
            x, y, z, w = struct.unpack_from("<ffff", data, offset)
        except struct.error:
            break
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z) and math.isfinite(w)):
            continue
        if abs(w - 1.0) > 1e-4:
            continue
        if max(abs(x), abs(y), abs(z)) > 20000.0:
            continue
        records.append((x, y, z))

    if not records:
        return None

    seed_x, seed_y, seed_z = records[0]
    row_z_values = _unique_sorted(
        [z for x, y, z in records if abs(x - seed_x) <= tolerance and abs(y - seed_y) <= tolerance],
        tolerance=tolerance,
    )
    col_x_values = _unique_sorted(
        [x for x, y, z in records if abs(z - seed_z) <= tolerance and abs(y - seed_y) <= tolerance],
        tolerance=tolerance,
    )

    if len(row_z_values) < 4 or len(col_x_values) < 4:
        return None

    min_x = float(col_x_values[0])
    max_x = float(col_x_values[-1])
    min_z = float(row_z_values[0])
    max_z = float(row_z_values[-1])
    if max_x <= min_x or max_z <= min_z:
        return None

    settings_bounds = _load_map_world_bounds(slug)
    if settings_bounds is not None:
        settings_min_x, settings_max_x, settings_min_z, settings_max_z = settings_bounds
        settings_span_x = max(1e-6, settings_max_x - settings_min_x)
        settings_span_z = max(1e-6, settings_max_z - settings_min_z)
        span_x_ratio = (max_x - min_x) / settings_span_x
        span_z_ratio = (max_z - min_z) / settings_span_z
        if not (0.55 <= span_x_ratio <= 1.05 and 0.55 <= span_z_ratio <= 1.05):
            return None

    return (min_x, max_x, min_z, max_z)


@lru_cache(maxsize=32)
def _load_map_icon(url: str) -> Image.Image | None:
    if not url:
        return None
    filename = Path(url.split("?", 1)[0]).name or "map_icon.png"
    file_path = _map_cache_dir() / filename
    try:
        if not file_path.exists():
            file_path.write_bytes(_download_bytes(url))
        return Image.open(file_path).convert("RGBA")
    except Exception:
        return None


def _native_map_size(canonical: Dict[str, Any], fallback: int) -> int:
    local_icon = _load_local_map_icon(_local_map_slug(canonical))
    if local_icon is not None:
        return int(max(int(fallback), int(local_icon.width)))
    url = _map_icon_url(canonical)
    icon = _load_map_icon(url) if url else None
    if icon is None:
        return int(fallback)
    return int(max(int(fallback), int(icon.width)))


def _map_margin(canonical: Dict[str, Any], fallback: int = 40) -> int:
    local_icon = _load_local_map_icon(_local_map_slug(canonical))
    if local_icon is None:
        return int(fallback)
    return 0


def _fit_icon_to_square(icon: Image.Image, map_size: int) -> Image.Image:
    rgba = icon.convert("RGBA")
    if rgba.size == (map_size, map_size):
        return rgba
    if rgba.width == rgba.height:
        fitted = rgba.resize((map_size, map_size), Image.Resampling.LANCZOS)
        if map_size > max(rgba.width, rgba.height):
            fitted = fitted.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))
        return fitted

    scale = min(map_size / max(1, rgba.width), map_size / max(1, rgba.height))
    target = (
        max(1, int(round(rgba.width * scale))),
        max(1, int(round(rgba.height * scale))),
    )
    fitted = rgba.resize(target, Image.Resampling.LANCZOS)
    if target[0] > rgba.width or target[1] > rgba.height:
        fitted = fitted.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))
    square = Image.new("RGBA", (map_size, map_size), (0, 0, 0, 0))
    ox = (map_size - fitted.width) // 2
    oy = (map_size - fitted.height) // 2
    square.paste(fitted, (ox, oy), fitted)
    return square


@lru_cache(maxsize=64)
def _local_map_background_layer(slug: str, map_size: int) -> Image.Image | None:
    icon = _load_local_map_icon(slug)
    if icon is None:
        return None
    return _fit_icon_to_square(icon, map_size)


def _uniform_playfield_bbox(icon: Image.Image) -> Tuple[int, int, int, int] | None:
    rgba = icon.convert("RGBA")
    width, height = rgba.size
    if width <= 0 or height <= 0:
        return None
    px = rgba.load()

    def _uniform_col(x: int) -> bool:
        first = px[x, 0]
        for y in range(1, height):
            if px[x, y] != first:
                return False
        return True

    def _uniform_row(y: int) -> bool:
        first = px[0, y]
        for x in range(1, width):
            if px[x, y] != first:
                return False
        return True

    left = 0
    while left < width and _uniform_col(left):
        left += 1
    right = width - 1
    while right >= 0 and _uniform_col(right):
        right -= 1
    top = 0
    while top < height and _uniform_row(top):
        top += 1
    bottom = height - 1
    while bottom >= 0 and _uniform_row(bottom):
        bottom -= 1

    if left > right or top > bottom:
        return None
    return (left, top, right, bottom)


@lru_cache(maxsize=64)
def _map_projection_rect_cached(slug: str, url: str, map_size: int, margin: int) -> Tuple[int, int, int, int]:
    icon: Image.Image | None = None
    if url:
        icon = _load_map_icon(url)
    if icon is None and slug:
        icon = _load_local_map_icon(slug)
    if icon is None:
        return (margin, margin, map_size - margin - 1, map_size - margin - 1)

    bbox = _uniform_playfield_bbox(icon)
    if bbox is None:
        return (margin, margin, map_size - margin - 1, map_size - margin - 1)

    left, top, right, bottom = bbox
    raw_w = right - left + 1
    raw_h = bottom - top + 1
    side = min(raw_w, raw_h)
    if side < int(min(icon.width, icon.height) * 0.60):
        return (margin, margin, map_size - margin - 1, map_size - margin - 1)

    left += max(0, (raw_w - side) // 2)
    top += max(0, (raw_h - side) // 2)
    right = left + side - 1
    bottom = top + side - 1

    sx = map_size / max(1, icon.width)
    sy = map_size / max(1, icon.height)
    scaled_left = int(round(left * sx))
    scaled_top = int(round(top * sy))
    scaled_right = int(round((right + 1) * sx)) - 1
    scaled_bottom = int(round((bottom + 1) * sy)) - 1

    scaled_left = max(0, min(map_size - 1, scaled_left))
    scaled_top = max(0, min(map_size - 1, scaled_top))
    scaled_right = max(scaled_left + 1, min(map_size - 1, scaled_right))
    scaled_bottom = max(scaled_top + 1, min(map_size - 1, scaled_bottom))
    return (scaled_left, scaled_top, scaled_right, scaled_bottom)


def _map_projection_rect(canonical: Dict[str, Any], map_size: int, margin: int) -> Tuple[int, int, int, int]:
    if _load_local_map_icon(_local_map_slug(canonical)) is not None:
        return (margin, margin, map_size - margin - 1, map_size - margin - 1)
    return _map_projection_rect_cached(_local_map_slug(canonical), _map_icon_url(canonical), int(map_size), int(margin))


@lru_cache(maxsize=32)
def _map_background_layer(url: str, map_size: int, margin: int) -> Image.Image | None:
    icon = _load_map_icon(url)
    if icon is None:
        return None

    usable = map_size - 2 * margin
    if usable <= 0:
        return None

    # WG minimap assets can include transparent padding. Crop to the visible map
    # area first so the island layout stays centered against the replay coordinates.
    alpha = icon.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is not None:
        cropped = icon.crop(bbox)
    else:
        cropped = icon

    side = max(cropped.width, cropped.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox = (side - cropped.width) // 2
    oy = (side - cropped.height) // 2
    square.paste(cropped, (ox, oy), cropped)

    # Keep a small inset after cropping so the visible map art does not end up
    # slightly oversized relative to the replay coordinate plane.
    scaled_usable = max(1, int(round(usable * 0.97)))
    bg = square.resize((scaled_usable, scaled_usable), Image.Resampling.LANCZOS)
    # Keep map readable but subtle so tracks/icons stay visible.
    bg = ImageEnhance.Brightness(bg).enhance(0.75)
    bg_alpha = bg.getchannel("A").point(lambda a: min(185, a))
    bg.putalpha(bg_alpha)

    layer = Image.new("RGBA", (map_size, map_size), (0, 0, 0, 0))
    inset = (usable - scaled_usable) // 2
    layer.paste(bg, (margin + inset, margin + inset), bg)
    return layer


def _apply_map_background(img: Image.Image, canonical: Dict[str, Any], margin: int, map_size: int, offset_x: int = 0) -> Image.Image:
    local_layer = _local_map_background_layer(_local_map_slug(canonical), map_size)
    if local_layer is not None:
        base = img.convert("RGBA")
        base.alpha_composite(local_layer, (offset_x, 0))
        return base.convert("RGB")

    url = _map_icon_url(canonical)
    layer = _map_background_layer(url, map_size, margin) if url else None
    if layer is None:
        return img
    base = img.convert("RGBA")
    base.alpha_composite(layer, (offset_x, 0))
    return base.convert("RGB")


@lru_cache(maxsize=1)
def _load_wg_ship_type_images_meta() -> Dict[str, Dict[str, str]]:
    meta_path = _icon_cache_dir() / "ship_type_images.json"
    try:
        if meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass

    app_id, realm = _read_api_config()
    if not app_id:
        return {}

    params = urlencode({"application_id": app_id, "fields": "ship_type_images"})
    url = f"{_base_url_for_realm(realm)}encyclopedia/info/?{params}"
    try:
        payload = json.loads(_download_bytes(url).decode("utf-8"))
        data = payload.get("data", {}).get("ship_type_images", {})
        if isinstance(data, dict) and data:
            meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
    except Exception:
        return {}
    return {}


@lru_cache(maxsize=1)
def _load_wg_class_icons() -> Dict[str, Image.Image]:
    icons: Dict[str, Image.Image] = {}
    meta = _load_wg_ship_type_images_meta()
    icon_dir = _icon_cache_dir()
    for ship_type in SHIP_TYPE_TO_CODE:
        # Prefer standard icon, then premium/elite as fallback.
        entry = meta.get(ship_type, {})
        url = entry.get("image") or entry.get("image_premium") or entry.get("image_elite")
        file_path = icon_dir / f"{ship_type}.png"
        try:
            if not file_path.exists() and url:
                file_path.write_bytes(_download_bytes(url))
            if file_path.exists():
                icons[ship_type] = Image.open(file_path).convert("RGBA")
        except Exception:
            continue
    return icons


@lru_cache(maxsize=128)
def _wg_tinted_icon(ship_type: str, color: Tuple[int, int, int], size: int) -> Image.Image | None:
    base_icon = _load_wg_class_icons().get(ship_type)
    if base_icon is None:
        return None
    target = max(12, size * 2 + 6)
    icon = base_icon.resize((target, target), Image.Resampling.LANCZOS)
    alpha = icon.getchannel("A")
    tinted = Image.new("RGBA", icon.size, (color[0], color[1], color[2], 0))
    tinted.putalpha(alpha)
    return tinted


def _value_attr(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _unwrap_gameparams_source(obj: Any) -> Dict[str, Any] | None:
    if isinstance(obj, (list, tuple)):
        for elem in obj:
            if isinstance(elem, dict) and "" in elem and isinstance(elem[""], dict):
                return elem[""]
        return None
    if isinstance(obj, dict) and "" in obj and isinstance(obj[""], dict):
        return obj[""]
    return None


def _arms_race_zone_kind_from_name(name: Any) -> Optional[str]:
    label = str(name or "").strip()
    if not label:
        return None
    mapping = {
        "PCOD002_Regeneration": "regeneration",
        "PCOD003_ShotDelay": "shot_delay",
        "PCOD041_AR_AddHeath": "health",
        "PCOD042_AR_AddWeaponDamage": "weapon_damage",
    }
    return mapping.get(label)


@lru_cache(maxsize=1)
def _load_arms_race_zone_param_kinds() -> Dict[int, str]:
    mapping: Dict[int, str] = dict(ARMS_RACE_ZONE_PARAM_KIND_FALLBACK)
    data_path = _root_dir() / "content" / "GameParams.data"
    if not data_path.exists():
        return mapping
    try:
        class GameParams(ModuleType):
            class TypeInfo(object):
                pass

            class GPData(object):
                pass

        sys.modules[GameParams.__name__] = GameParams(GameParams.__name__)
        raw = data_path.read_bytes()
        raw = struct.pack("B" * len(raw), *raw[::-1])
        raw = zlib.decompress(raw)
        obj = pickle.loads(raw, encoding="latin1")
    except Exception:
        return mapping
    source = _unwrap_gameparams_source(obj)
    if not isinstance(source, dict):
        return mapping
    for value in source.values():
        if not isinstance(value, dict):
            continue
        params_id = _safe_int(value.get("id"))
        if params_id is None:
            continue
        kind = _arms_race_zone_kind_from_name(value.get("name"))
        if kind:
            mapping[int(params_id)] = kind
    return mapping


def _arms_race_zone_kind(params_id: Any) -> Optional[str]:
    pid = _safe_int(params_id)
    if pid is None:
        return None
    return _load_arms_race_zone_param_kinds().get(int(pid))


@lru_cache(maxsize=16)
def _load_arms_race_zone_icon(kind: str) -> Image.Image | None:
    icon_name = ARMS_RACE_KIND_TO_RULE_ICON.get(str(kind or "").strip().lower())
    if not icon_name:
        return None
    path = _root_dir() / "gui" / "battle_tasks" / "rules" / icon_name
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _aircraft_params_from_gameparams_payload(payload: Any) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not isinstance(payload, dict):
        return mapping

    def _collect_tokens(obj: Any, depth: int = 0, limit: int = 80) -> List[str]:
        if obj is None or limit <= 0:
            return []
        tokens: List[str] = []
        if isinstance(obj, bytes):
            try:
                text = obj.decode("utf-8", errors="ignore").strip()
            except Exception:
                text = ""
            if text:
                tokens.append(text)
            return tokens
        if isinstance(obj, str):
            text = obj.strip()
            if text:
                tokens.append(text)
            return tokens
        if depth >= 2:
            return tokens
        if isinstance(obj, dict):
            for key, value in obj.items():
                if limit <= 0:
                    break
                tokens.extend(_collect_tokens(key, depth + 1, limit))
                limit -= len(tokens)
                if limit <= 0:
                    break
                tokens.extend(_collect_tokens(value, depth + 1, limit))
                limit -= len(tokens)
            return tokens
        if isinstance(obj, (list, tuple, set)):
            for item in obj:
                if limit <= 0:
                    break
                tokens.extend(_collect_tokens(item, depth + 1, limit))
                limit -= len(tokens)
            return tokens
        if hasattr(obj, "__dict__"):
            try:
                return _collect_tokens(vars(obj), depth + 1, limit)
            except Exception:
                return tokens
        slots = getattr(obj, "__slots__", None)
        if isinstance(slots, (list, tuple)):
            slot_dict: Dict[str, Any] = {}
            for name in slots:
                try:
                    slot_dict[name] = getattr(obj, name)
                except Exception:
                    continue
            return _collect_tokens(slot_dict, depth + 1, limit)
        # Last resort: use string representation if it looks informative.
        try:
            text = str(obj).strip()
        except Exception:
            text = ""
        if text and "object at" not in text:
            tokens.append(text)
        return tokens

    def _collect_int_refs(obj: Any, depth: int = 0, limit: int = 80, key_hint: str = "") -> List[int]:
        if obj is None or limit <= 0:
            return []
        refs: List[int] = []
        key_hint_l = str(key_hint).lower()
        key_relevant = any(token in key_hint_l for token in ("plane", "squad", "air", "aircraft", "params", "id"))
        if isinstance(obj, (int, float)) and key_relevant:
            try:
                refs.append(int(obj))
            except Exception:
                return refs
            return refs
        if isinstance(obj, str) and key_relevant:
            try:
                refs.append(int(obj))
            except Exception:
                return refs
            return refs
        if isinstance(obj, dict) and depth < 3:
            for key, value in obj.items():
                if limit <= 0:
                    break
                found = _collect_int_refs(value, depth + 1, limit, str(key))
                refs.extend(found)
                limit -= len(found)
            return refs
        if isinstance(obj, (list, tuple, set)) and depth < 3:
            for item in obj:
                if limit <= 0:
                    break
                found = _collect_int_refs(item, depth + 1, limit, key_hint)
                refs.extend(found)
                limit -= len(found)
            return refs
        if hasattr(obj, "__dict__") and depth < 3:
            try:
                for key, value in vars(obj).items():
                    if limit <= 0:
                        break
                    found = _collect_int_refs(value, depth + 1, limit, str(key))
                    refs.extend(found)
                    limit -= len(found)
            except Exception:
                pass
            return refs
        slots = getattr(obj, "__slots__", None)
        if isinstance(slots, (list, tuple)) and depth < 3:
            for name in slots:
                if limit <= 0:
                    break
                try:
                    value = getattr(obj, name)
                except Exception:
                    continue
                found = _collect_int_refs(value, depth + 1, limit, str(name))
                refs.extend(found)
                limit -= len(found)
        return refs

    allowed_types = {"Plane", "Squadron", "Aircraft", "AirGroup", "AirStrike"}
    entries: List[Tuple[str, str, str, List[int]]] = []

    for value in payload.values():
        if not isinstance(value, dict):
            continue
        typeinfo = value.get("typeinfo")
        if not isinstance(typeinfo, dict):
            continue
        typeinfo_type = str(typeinfo.get("type") or "")
        if typeinfo_type not in allowed_types:
            continue
        plane_id = _safe_int(value.get("id")) or _safe_int(value.get("planeID"))
        if plane_id is None:
            continue
        tokens = _collect_tokens(typeinfo) + _collect_tokens(value)
        text = " ".join(tok for tok in tokens if tok)
        refs = _collect_int_refs(value) + _collect_int_refs(typeinfo)
        entries.append((str(plane_id), typeinfo_type, text, refs))
        species = str(typeinfo.get("species") or "").strip()
        nation = str(typeinfo.get("nation") or "").strip()
        _AIRCRAFT_PARAMS_DEBUG.setdefault(str(plane_id), {}).update(
            {
                "typeinfo": typeinfo_type,
                "text": text,
                "refs": refs,
                "species": species,
                "nation": nation,
            }
        )
        stype = _map_aircraft_gameparams_type(species, text)
        if stype:
            mapping[str(plane_id)] = stype
    if entries:
        module_map = _load_aircraft_module_params()
        for entry_id, entry_type, _text, refs in entries:
            if entry_id in mapping:
                continue
            if entry_type not in allowed_types:
                continue
            for ref in refs:
                ref_key = str(ref)
                mapped = mapping.get(ref_key)
                if mapped:
                    mapping[entry_id] = mapped
                    _AIRCRAFT_PARAMS_DEBUG.setdefault(entry_id, {}).update({"linked_from": ref_key, "linked_kind": "plane"})
                    break
                mapped = module_map.get(ref_key)
                if mapped:
                    mapping[entry_id] = mapped
                    _AIRCRAFT_PARAMS_DEBUG.setdefault(entry_id, {}).update({"linked_from": ref_key, "linked_kind": "module"})
                    break
    return mapping


def _aircraft_params_from_gameparams_json(path: Path) -> Dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="latin1"))
    except Exception:
        return {}
    return _aircraft_params_from_gameparams_payload(payload)


def _aircraft_params_from_gameparams_data(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    # Allow pickle to resolve GameParams types used by WoWS.
    try:
        class GameParams(ModuleType):
            class TypeInfo(object):
                pass

            class GPData(object):
                pass

        sys.modules[GameParams.__name__] = GameParams(GameParams.__name__)
    except Exception:
        return {}
    try:
        raw = path.read_bytes()
        raw = struct.pack("B" * len(raw), *raw[::-1])
        raw = zlib.decompress(raw)
        obj = pickle.loads(raw, encoding="latin1")
    except Exception:
        return {}
    source = _unwrap_gameparams_source(obj)
    if not isinstance(source, dict):
        return {}
    mapping: Dict[str, str] = {}
    def _collect_tokens(obj: Any, depth: int = 0, limit: int = 80) -> List[str]:
        if obj is None or limit <= 0:
            return []
        tokens: List[str] = []
        if isinstance(obj, bytes):
            try:
                text = obj.decode("utf-8", errors="ignore").strip()
            except Exception:
                text = ""
            if text:
                tokens.append(text)
            return tokens
        if isinstance(obj, str):
            text = obj.strip()
            if text:
                tokens.append(text)
            return tokens
        if depth >= 2:
            return tokens
        if isinstance(obj, dict):
            for key, value in obj.items():
                if limit <= 0:
                    break
                tokens.extend(_collect_tokens(key, depth + 1, limit))
                limit -= len(tokens)
                if limit <= 0:
                    break
                tokens.extend(_collect_tokens(value, depth + 1, limit))
                limit -= len(tokens)
            return tokens
        if isinstance(obj, (list, tuple, set)):
            for item in obj:
                if limit <= 0:
                    break
                tokens.extend(_collect_tokens(item, depth + 1, limit))
                limit -= len(tokens)
            return tokens
        if hasattr(obj, "__dict__"):
            try:
                return _collect_tokens(vars(obj), depth + 1, limit)
            except Exception:
                return tokens
        slots = getattr(obj, "__slots__", None)
        if isinstance(slots, (list, tuple)):
            slot_dict: Dict[str, Any] = {}
            for name in slots:
                try:
                    slot_dict[name] = getattr(obj, name)
                except Exception:
                    continue
            return _collect_tokens(slot_dict, depth + 1, limit)
        try:
            text = str(obj).strip()
        except Exception:
            text = ""
        if text and "object at" not in text:
            tokens.append(text)
        return tokens

    def _collect_int_refs(obj: Any, depth: int = 0, limit: int = 80, key_hint: str = "") -> List[int]:
        if obj is None or limit <= 0:
            return []
        refs: List[int] = []
        key_hint_l = str(key_hint).lower()
        key_relevant = any(token in key_hint_l for token in ("plane", "squad", "air", "aircraft", "params", "id"))
        if isinstance(obj, (int, float)) and key_relevant:
            try:
                refs.append(int(obj))
            except Exception:
                return refs
            return refs
        if isinstance(obj, str) and key_relevant:
            try:
                refs.append(int(obj))
            except Exception:
                return refs
            return refs
        if isinstance(obj, dict) and depth < 3:
            for key, value in obj.items():
                if limit <= 0:
                    break
                found = _collect_int_refs(value, depth + 1, limit, str(key))
                refs.extend(found)
                limit -= len(found)
            return refs
        if isinstance(obj, (list, tuple, set)) and depth < 3:
            for item in obj:
                if limit <= 0:
                    break
                found = _collect_int_refs(item, depth + 1, limit, key_hint)
                refs.extend(found)
                limit -= len(found)
            return refs
        if hasattr(obj, "__dict__") and depth < 3:
            try:
                for key, value in vars(obj).items():
                    if limit <= 0:
                        break
                    found = _collect_int_refs(value, depth + 1, limit, str(key))
                    refs.extend(found)
                    limit -= len(found)
            except Exception:
                pass
            return refs
        slots = getattr(obj, "__slots__", None)
        if isinstance(slots, (list, tuple)) and depth < 3:
            for name in slots:
                if limit <= 0:
                    break
                try:
                    value = getattr(obj, name)
                except Exception:
                    continue
                found = _collect_int_refs(value, depth + 1, limit, str(name))
                refs.extend(found)
                limit -= len(found)
        return refs

    allowed_types = {"Plane", "Squadron", "Aircraft", "AirGroup", "AirStrike"}
    entries: List[Tuple[str, str, str, List[int]]] = []

    for key, value in source.items():
        typeinfo = _value_attr(value, "typeinfo")
        typeinfo_type = str(_value_attr(typeinfo, "type") or "")
        if typeinfo_type not in allowed_types:
            continue
        plane_id = _safe_int(_value_attr(value, "id")) or _safe_int(key)
        if plane_id is None:
            continue
        tokens = _collect_tokens(typeinfo) + _collect_tokens(value)
        text = " ".join(tok for tok in tokens if tok)
        refs = _collect_int_refs(value) + _collect_int_refs(typeinfo)
        entries.append((str(plane_id), typeinfo_type, text, refs))
        species = str(_value_attr(typeinfo, "species") or "").strip()
        nation = str(_value_attr(typeinfo, "nation") or "").strip()
        _AIRCRAFT_PARAMS_DEBUG.setdefault(str(plane_id), {}).update(
            {
                "typeinfo": typeinfo_type,
                "text": text,
                "refs": refs,
                "species": species,
                "nation": nation,
            }
        )
        stype = _map_aircraft_gameparams_type(species, text)
        if stype:
            mapping[str(plane_id)] = stype
    if entries:
        module_map = _load_aircraft_module_params()
        for entry_id, entry_type, _text, refs in entries:
            if entry_id in mapping:
                continue
            if entry_type not in allowed_types:
                continue
            for ref in refs:
                ref_key = str(ref)
                mapped = mapping.get(ref_key)
                if mapped:
                    mapping[entry_id] = mapped
                    _AIRCRAFT_PARAMS_DEBUG.setdefault(entry_id, {}).update({"linked_from": ref_key, "linked_kind": "plane"})
                    break
                mapped = module_map.get(ref_key)
                if mapped:
                    mapping[entry_id] = mapped
                    _AIRCRAFT_PARAMS_DEBUG.setdefault(entry_id, {}).update({"linked_from": ref_key, "linked_kind": "module"})
                    break
    return mapping


@lru_cache(maxsize=1)
def _load_aircraft_params_from_gameparams() -> Dict[str, str]:
    # Prefer a json export if present.
    json_path = _battle_hud_dir() / "GameParams.json"
    if json_path.exists():
        mapping = _aircraft_params_from_gameparams_json(json_path)
        if mapping:
            return mapping
    # Fallback to a decoded GameParams-0.json if present.
    fallback_json = _root_dir() / "GameParams-0.json"
    if fallback_json.exists():
        mapping = _aircraft_params_from_gameparams_json(fallback_json)
        if mapping:
            return mapping
    # Final fallback: decode GameParams.data directly.
    data_path = _root_dir() / "content" / "GameParams.data"
    return _aircraft_params_from_gameparams_data(data_path)


@lru_cache(maxsize=1)
def _load_aircraft_params() -> Dict[str, str]:
    params_path = _root_dir() / "aircraft_params.json"
    mapping: Dict[str, str] = {}
    # Prefer GameParams mapping (authoritative params_id -> type) when available.
    gp_mapping = _load_aircraft_params_from_gameparams()
    if gp_mapping:
        mapping.update({str(k): str(v) for k, v in gp_mapping.items() if str(v).strip()})

    if os.environ.get("RENDER_AIRCRAFT_FORCE_GAMEPARAMS") != "1":
        try:
            if params_path.exists():
                payload = json.loads(params_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    if "by_plane_id" in payload and isinstance(payload.get("by_plane_id"), dict):
                        for k, v in payload["by_plane_id"].items():
                            if str(v).strip():
                                mapping.setdefault(str(k), str(v))
                    else:
                        for k, v in payload.items():
                            if str(v).strip():
                                mapping.setdefault(str(k), str(v))
        except Exception:
            pass

        cache = _load_ship_cache()
        cache_map = cache.get("__aircraft_params__") if isinstance(cache, dict) else None
        if isinstance(cache_map, dict):
            for key, value in cache_map.items():
                if str(value).strip():
                    mapping.setdefault(str(key), str(value))

    return mapping


def _map_aircraft_module_type(raw_type: Any) -> Optional[str]:
    t = str(raw_type or "").strip().lower()
    if not t:
        return None
    # Detect AP in a token-safe way (avoid matching "japan" etc).
    ap_flag = bool(re.search(r"(^|[^a-z])ap([^a-z]|$)", t)) or "armor piercing" in t or "armor_piercing" in t
    # Prefer explicit fighter/rocket signals over torpedo/bomber to avoid
    # misclassifying attack aircraft when other fields mention torpedoes.
    # ASW/air support needs to win over generic torpedo/bomber tokens.
    if "asw" in t or "depthcharge" in t or "depth charge" in t:
        return "asw"
    if "airdrop" in t or "air drop" in t or "asup" in t:
        return "airdrop_he" if "he" in t else "airdrop"
    if "mine" in t:
        return "asw_mine"
    if "species scout" in t or re.search(r"(^|[^a-z])scout([^a-z]|$)", t):
        return "fighter"
    if "fighter" in t:
        return "fighter"
    if "attack" in t or "rocket" in t:
        return "rocket_ap" if ap_flag else "rocket"
    if "torpedo" in t:
        if "deep" in t:
            return "torpedo_deepwater"
        return "torpedo"
    if "skip" in t:
        return "skip_ap" if ap_flag else "skip"
    if "dive" in t or "bomb" in t:
        return "bomber_ap" if ap_flag else "bomber"
    if "asw" in t:
        return "asw"
    return None


def _map_aircraft_gameparams_type(species: Any, raw_text: Any) -> Optional[str]:
    species_l = str(species or "").strip().lower()
    text_l = str(raw_text or "").strip().lower()
    if species_l == "scout":
        return "fighter"
    if species_l in ("fighter", "interceptor"):
        return "fighter"
    if species_l in ("attack", "rocket"):
        return "rocket_ap" if re.search(r"(^|[^a-z])ap([^a-z]|$)", text_l) else "rocket"
    if species_l in ("torpedo", "torpedobomber"):
        return "torpedo_deepwater" if "deep" in text_l else "torpedo"
    if species_l in ("skip", "skipbomber"):
        return "skip_ap" if re.search(r"(^|[^a-z])ap([^a-z]|$)", text_l) else "skip"
    if "depthcharge" in text_l or "depth charge" in text_l or "asw" in text_l:
        return "asw"
    if "airdrop" in text_l or "air drop" in text_l or "asup" in text_l:
        return "airdrop_he" if "he" in text_l else "airdrop"
    if "mine" in text_l:
        return "asw_mine"
    if species_l in ("dive", "bomber", "divebomber"):
        return "bomber_ap" if re.search(r"(^|[^a-z])ap([^a-z]|$)", text_l) else "bomber"
    return _map_aircraft_module_type(raw_text)


def _looks_like_aircraft_module_meta(meta: Any) -> bool:
    if not isinstance(meta, dict):
        return False
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


@lru_cache(maxsize=1)
def _load_aircraft_module_params() -> Dict[str, str]:
    cache = _load_ship_cache()
    mapping: Dict[str, str] = {}
    if not isinstance(cache, dict):
        return mapping

    def _module_ids(module: Any) -> Tuple[List[str], List[str]]:
        ids: List[str] = []
        names: List[str] = []
        if not isinstance(module, dict):
            return ids, names
        if isinstance(module.get("ids"), list):
            for mid in module.get("ids", []):
                try:
                    ids.append(str(int(mid)))
                except Exception:
                    continue
        elif module.get("id") is not None:
            try:
                ids.append(str(int(module.get("id"))))
            except Exception:
                pass
        if isinstance(module.get("names"), list):
            names.extend([str(n) for n in module.get("names", []) if n is not None])
        elif module.get("name"):
            names.append(str(module.get("name")))
        return ids, names

    def _guess_fighter_kind(names: List[str]) -> str:
        text = " ".join(names).lower()
        rocket_tokens = ("rocket", "rockets", "hvar", "tiny tim", "tinytim", "ffar", "projectile")
        if any(token in text for token in rocket_tokens):
            return "rocket"
        # Most CV "fighter" modules in ships_cache are rocket attack aircraft.
        return "rocket"

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
        return fallback

    for ship_data in cache.values():
        if not isinstance(ship_data, dict):
            continue
        modules = ship_data.get("modules")
        if isinstance(modules, dict):
            ids, names = _module_ids(modules.get("torpedo_bomber"))
            kind = _infer_kind_from_names(names, "torpedo")
            for mid in ids:
                mapping[mid] = kind
            ids, names = _module_ids(modules.get("dive_bomber"))
            kind = _infer_kind_from_names(names, "bomber")
            for mid in ids:
                mapping[mid] = kind
            ids, names = _module_ids(modules.get("bomber"))
            kind = _infer_kind_from_names(names, "bomber")
            for mid in ids:
                mapping[mid] = kind
            ids, names = _module_ids(modules.get("skip_bomber"))
            kind = _infer_kind_from_names(names, "skip")
            for mid in ids:
                mapping[mid] = kind
            ids, names = _module_ids(modules.get("fighter"))
            if ids:
                kind = _infer_kind_from_names(names, _guess_fighter_kind(names))
                for mid in ids:
                    mapping[mid] = kind
            ids, _ = _module_ids(modules.get("rocket"))
            for mid in ids:
                mapping[mid] = "rocket"

        modules_tree = ship_data.get("modules_tree", {})
        if not isinstance(modules_tree, dict):
            continue
        for module_id, meta in modules_tree.items():
            if not isinstance(meta, dict):
                continue
            if not _looks_like_aircraft_module_meta(meta):
                continue
            try:
                key = str(int(module_id))
            except Exception:
                key = str(module_id)
            if key in mapping:
                # Prefer the ship module bucket mapping when available. Some CV
                # attack squadrons sit under a generic "Fighter" modules_tree
                # type even though they are the rocket attack squadron.
                continue
            stype = _map_aircraft_module_type(meta.get("type"))
            if not stype:
                continue
            mapping[key] = stype
    return mapping


def _squadron_type_from_params(params_id: Any) -> str:
    pid = _safe_int(params_id)
    if pid is None:
        return "main"
    mapping = _load_aircraft_params()
    lookup = str(pid)
    mapped = str(mapping.get(lookup, "")).strip().lower()
    if mapped:
        return mapped
    module_map = _load_aircraft_module_params()
    mapped = str(module_map.get(lookup, "")).strip().lower()
    return mapped or "main"


def _squadron_type_with_source(params_id: Any) -> Tuple[str, str]:
    pid = _safe_int(params_id)
    if pid is None:
        return "main", "none"
    lookup = str(pid)
    gp_mapping = _load_aircraft_params_from_gameparams()
    mapped = str(gp_mapping.get(lookup, "")).strip().lower()
    if mapped:
        return mapped, "gameparams"
    mapping = _load_aircraft_params()
    mapped = str(mapping.get(lookup, "")).strip().lower()
    if mapped:
        return mapped, "aircraft_params"
    module_map = _load_aircraft_module_params()
    mapped = str(module_map.get(lookup, "")).strip().lower()
    if mapped:
        return mapped, "modules_tree"
    return "main", "default"


@lru_cache(maxsize=64)
def _load_aircraft_icon_base(filename: str) -> Image.Image | None:
    path = _aircraft_dir() / filename
    if not path.exists():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _tint_icon(base: Image.Image, color: Tuple[int, int, int]) -> Image.Image:
    alpha = base.getchannel("A")
    tinted = Image.new("RGBA", base.size, (color[0], color[1], color[2], 0))
    tinted.putalpha(alpha)
    return tinted


@lru_cache(maxsize=512)
def _squadron_icon_image(
    squadron_type: str,
    color: Tuple[int, int, int],
    size: int,
    heading_bucket: int,
    bucket_deg: float = 6.0,
) -> Image.Image | None:
    stype = str(squadron_type or "main").strip().lower()
    filename = SQUADRON_TYPE_TO_ICON.get(stype, SQUADRON_TYPE_TO_ICON["main"])
    base_icon = _load_aircraft_icon_base(filename)
    if base_icon is None:
        return None
    tinted = _tint_icon(base_icon, color)
    target = max(10, int(size))
    scale = float(target) / max(tinted.width, tinted.height)
    scaled = tinted.resize((max(1, int(tinted.width * scale)), max(1, int(tinted.height * scale))), Image.Resampling.LANCZOS)
    heading_deg = (heading_bucket * bucket_deg) % 360.0
    return scaled.rotate(-(heading_deg + AIRCRAFT_ICON_HEADING_OFFSET_DEG), resample=Image.Resampling.BICUBIC, expand=True)


def _normalize_vehicle_code(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = re.match(r"^[A-Za-z0-9]+", text)
    if match:
        return match.group(0).upper()
    return text.split("_", 1)[0].split("-", 1)[0].strip().upper()


def _player_vehicle_code(canonical: Dict[str, Any], ship_id: Any) -> str:
    meta = canonical.get("meta", {}) or {}
    player_vehicle = _normalize_vehicle_code(meta.get("playerVehicle"))
    if player_vehicle:
        return player_vehicle
    ship_meta = _gameparams_ship_entry(ship_id)
    return _normalize_vehicle_code(ship_meta.get("index"))


def _resize_fit(base: Image.Image, max_w: int, max_h: int) -> Image.Image:
    target_w = max(1, int(max_w))
    target_h = max(1, int(max_h))
    ratio = min(target_w / max(1, base.width), target_h / max(1, base.height))
    ratio = max(1e-6, ratio)
    size = (
        max(1, int(round(base.width * ratio))),
        max(1, int(round(base.height * ratio))),
    )
    if size == base.size:
        return base
    return base.resize(size, Image.Resampling.LANCZOS)


_SHIP_ALIVE_ICON_CACHE: Dict[Tuple[str, int, int], Image.Image] = {}


def _load_ship_alive_icon(vehicle_code: str, max_w: int, max_h: int) -> Image.Image | None:
    vehicle_code = _normalize_vehicle_code(vehicle_code)
    if not vehicle_code:
        return None
    cache_key = (vehicle_code, int(max_w), int(max_h))
    cached = _SHIP_ALIVE_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    candidates = [
        _ship_icons_dir() / f"{vehicle_code}.png",
        _ships_silhouettes_dir() / f"{vehicle_code}.png",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.stat().st_size <= 0:
                continue
            icon = _resize_fit(Image.open(path).convert("RGBA"), max_w, max_h)
            _SHIP_ALIVE_ICON_CACHE[cache_key] = icon
            return icon
        except Exception:
            continue
    return None


_SHIP_DEAD_ICON_CACHE: Dict[Tuple[str, int, int], Image.Image] = {}


def _load_ship_dead_icon(vehicle_code: str, max_w: int, max_h: int) -> Image.Image | None:
    vehicle_code = _normalize_vehicle_code(vehicle_code)
    if not vehicle_code:
        return None
    cache_key = (vehicle_code, int(max_w), int(max_h))
    cached = _SHIP_DEAD_ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached
    candidates = [_ship_dead_icons_dir() / f"{vehicle_code}.png"]
    base = None
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.stat().st_size <= 0:
                continue
            base = Image.open(path).convert("RGBA")
            break
        except Exception:
            continue
    if base is None:
        return None
    icon = _resize_fit(base, max_w, max_h)
    _SHIP_DEAD_ICON_CACHE[cache_key] = icon
    return icon


def _compose_ship_status_icon(
    alive_icon: Image.Image | None,
    dead_icon: Image.Image | None,
    max_w: int,
    max_h: int,
    hp_ratio: float,
    sunk: bool,
    restorable_ratio: float = 0.0,
) -> Image.Image | None:
    hp_ratio = max(0.0, min(1.0, float(hp_ratio)))
    restorable_ratio = max(0.0, min(1.0, float(restorable_ratio)))
    if sunk:
        return dead_icon or alive_icon
    if alive_icon is None:
        return dead_icon
    if dead_icon is None:
        return alive_icon

    canvas_w = max(1, int(max_w))
    canvas_h = max(1, int(max_h))
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    dead_x = (canvas_w - dead_icon.width) // 2
    dead_y = (canvas_h - dead_icon.height) // 2
    canvas.paste(dead_icon, (dead_x, dead_y), dead_icon)

    alive_x = (canvas_w - alive_icon.width) // 2
    alive_y = (canvas_h - alive_icon.height) // 2
    alive_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    alive_layer.paste(alive_icon, (alive_x, alive_y), alive_icon)

    visible_w = max(0, min(alive_icon.width, int(round(alive_icon.width * hp_ratio))))
    if visible_w <= 0:
        return canvas

    mask = Image.new("L", (canvas_w, canvas_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle(
        [
            alive_x,
            alive_y,
            alive_x + max(0, visible_w - 1),
            alive_y + alive_icon.height - 1,
        ],
        fill=255,
    )
    canvas = Image.composite(alive_layer, canvas, mask)

    recover_end = max(
        visible_w,
        min(alive_icon.width, int(round(alive_icon.width * min(1.0, hp_ratio + restorable_ratio)))),
    )
    if recover_end > visible_w:
        recover_icon = _tint_icon(alive_icon, WOWS_TEXT_SUB)
        recover_alpha = recover_icon.getchannel("A").point(lambda a: int(a * 0.72))
        recover_icon.putalpha(recover_alpha)
        recover_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        recover_layer.paste(recover_icon, (alive_x, alive_y), recover_icon)
        recover_mask = Image.new("L", (canvas_w, canvas_h), 0)
        recover_draw = ImageDraw.Draw(recover_mask)
        recover_draw.rectangle(
            [
                alive_x + visible_w,
                alive_y,
                alive_x + max(0, recover_end - 1),
                alive_y + alive_icon.height - 1,
            ],
            fill=255,
        )
        canvas = Image.composite(recover_layer, canvas, recover_mask)
    return canvas


@lru_cache(maxsize=1)
def _gameparams_supported_ribbon_ids() -> frozenset[int]:
    gameparams_path = _battle_hud_dir() / "GameParams.json"
    try:
        raw = gameparams_path.read_text(encoding="utf-8")
    except Exception:
        return frozenset(RIBBON_ID_TO_ASSET.keys())

    ribbon_ids: set[int] = set()
    for match in re.finditer(r'"(?:subRibbons|triggerRibbonsTypes)"\s*:\s*\[(.*?)\]', raw, flags=re.S):
        for value in re.findall(r"-?\d+", match.group(1)):
            try:
                ribbon_ids.add(int(value))
            except ValueError:
                continue
    if not ribbon_ids:
        ribbon_ids.update(RIBBON_ID_TO_ASSET.keys())
    return frozenset(ribbon_ids)


@lru_cache(maxsize=1)
def _ribbon_asset_roots() -> Tuple[str, ...]:
    roots: List[str] = []
    local_root = _root_dir() / "gui" / "ribbons"
    if local_root.exists():
        roots.append(str(local_root))
    return tuple(roots)


@lru_cache(maxsize=128)
def _load_ribbon_icon(ribbon_id: int, size: int) -> Image.Image | None:
    rid = int(ribbon_id)
    if rid not in _gameparams_supported_ribbon_ids():
        return None
    asset_name = RIBBON_ID_TO_ASSET.get(rid)
    if not asset_name:
        return None
    for root in _ribbon_asset_roots():
        if asset_name.endswith(".png"):
            file_path = Path(root) / asset_name
        else:
            file_path = Path(root) / f"ribbon_{asset_name}.png"
        if not file_path.exists():
            continue
        try:
            icon = Image.open(file_path).convert("RGBA")
        except Exception:
            continue
        if size > 0:
            target_side = max(1, int(size))
            scale = min(target_side / max(1, icon.width), target_side / max(1, icon.height))
            target_w = max(1, int(round(icon.width * scale)))
            target_h = max(1, int(round(icon.height * scale)))
            if icon.size != (target_w, target_h):
                icon = icon.resize((target_w, target_h), Image.Resampling.LANCZOS)
            if icon.size != (target_side, target_side):
                canvas = Image.new("RGBA", (target_side, target_side), (0, 0, 0, 0))
                paste_x = (target_side - icon.width) // 2
                paste_y = (target_side - icon.height) // 2
                canvas.paste(icon, (paste_x, paste_y), icon)
                icon = canvas
        return icon
    return None


def _world_half(canonical: Dict[str, Any]) -> float:
    meta = canonical.get("meta", {}) or {}
    for key in ("world_half", "map_half", "map_extent_half"):
        try:
            value = float(meta.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0:
            return value

    max_extent = 0.0
    for track in canonical.get("tracks", {}).values():
        for p in track.get("points", []):
            max_extent = max(max_extent, abs(float(p.get("x", 0.0))), abs(float(p.get("z", 0.0))))

    control_points = meta.get("control_points", []) or []
    if isinstance(control_points, list):
        for cp in control_points:
            if not isinstance(cp, dict):
                continue
            try:
                x = abs(float(cp.get("x", 0.0) or 0.0))
                z = abs(float(cp.get("z", 0.0) or 0.0))
                r = max(0.0, float(cp.get("radius", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
            max_extent = max(max_extent, x + r, z + r)

    if max_extent <= 0.0:
        return 700.0

    # Track-only bounds underfit maps where ships never reach the edge.
    # Include cap extents, but keep the padding modest so movement does not look compressed.
    padded = max_extent * 1.10
    return max(700.0, math.ceil(padded / 50.0) * 50.0)


def _prefer_settings_bounds_for_overlay(
    canonical: Dict[str, Any],
    settings_bounds: Tuple[float, float, float, float] | None,
    space_bin_bounds: Tuple[float, float, float, float] | None,
) -> bool:
    if settings_bounds is None or space_bin_bounds is None:
        return False

    s_min_x, s_max_x, s_min_z, s_max_z = [float(v) for v in settings_bounds]
    b_min_x, b_max_x, b_min_z, b_max_z = [float(v) for v in space_bin_bounds]
    s_span_x = max(1e-6, s_max_x - s_min_x)
    s_span_z = max(1e-6, s_max_z - s_min_z)
    b_span_x = max(1e-6, b_max_x - b_min_x)
    b_span_z = max(1e-6, b_max_z - b_min_z)

    # Some maps have a terrain lattice in space.bin that is slightly inset from
    # the nominal map bounds used by the minimap art. On those maps, static
    # overlays like Arms Race buff zones land a little off unless we use the
    # symmetric settings bounds instead.
    ratio_x = b_span_x / s_span_x
    ratio_z = b_span_z / s_span_z
    centered = abs((s_min_x + s_max_x) * 0.5) <= 2.0 and abs((s_min_z + s_max_z) * 0.5) <= 2.0
    control_points = (canonical.get("meta", {}) or {}).get("control_points", [])
    has_zone_layout = isinstance(control_points, list) and any(isinstance(cp, dict) for cp in control_points)
    return bool(has_zone_layout and centered and ratio_x <= 0.97 and ratio_z <= 0.97)


def _world_bounds(canonical: Dict[str, Any]) -> Tuple[float, float, float, float]:
    slug = _local_map_slug(canonical)
    overview_half = _overview_half_extent(slug)
    if overview_half is not None:
        return (-overview_half, overview_half, -overview_half, overview_half)
    settings_bounds = _load_map_world_bounds(slug)
    space_bin_bounds = _load_space_bin_world_bounds(slug)
    if _prefer_settings_bounds_for_overlay(canonical, settings_bounds, space_bin_bounds):
        return settings_bounds  # type: ignore[return-value]
    if space_bin_bounds is not None:
        return space_bin_bounds
    if settings_bounds is not None:
        return settings_bounds
    half = _world_half(canonical)
    return (-half, half, -half, half)


def _to_px(
    x: float,
    z: float,
    half: float,
    size: int,
    margin: int = 40,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> Tuple[int, int]:
    if map_rect is None:
        left = margin
        top = margin
        right = size - margin - 1
        bottom = size - margin - 1
    else:
        left, top, right, bottom = [int(v) for v in map_rect]
    usable_w = max(1, right - left)
    usable_h = max(1, bottom - top)
    if world_bounds is None:
        min_x = -half
        max_x = half
        min_z = -half
        max_z = half
    else:
        min_x, max_x, min_z, max_z = [float(v) for v in world_bounds]
    span_x = max(1e-6, max_x - min_x)
    span_z = max(1e-6, max_z - min_z)
    px = int((x - min_x) / span_x * usable_w + left)
    py = int((1.0 - (z - min_z) / span_z) * usable_h + top)
    return px, py


def _find_death_times(canonical: Dict[str, Any]) -> Dict[str, float]:
    deaths: Dict[str, float] = {}
    entities = canonical.get("entities", {}) or {}
    if isinstance(entities, dict):
        for entity_key, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            try:
                death_t = float(entity.get("death_time"))
            except (TypeError, ValueError):
                death_t = -1.0
            if death_t >= 0.0:
                key = str(entity_key)
                if key and (key not in deaths or death_t < deaths[key]):
                    deaths[key] = death_t
    for event in canonical.get("events", {}).get("deaths", []):
        key = str(event.get("entity_key", ""))
        t = float(event.get("time_s", 0.0))
        if key and (key not in deaths or t < deaths[key]):
            deaths[key] = t
    for snap in canonical.get("events", {}).get("health", []):
        if not isinstance(snap, dict):
            continue
        t = float(snap.get("time_s", 0.0) or 0.0)
        entities_raw = snap.get("entities", {})
        if not isinstance(entities_raw, dict):
            continue
        for entity_key, state in entities_raw.items():
            if not isinstance(state, dict):
                continue
            alive = bool(state.get("alive", True))
            hp = _safe_int(state.get("hp"))
            if alive and (hp is None or hp > 0):
                continue
            key = str(entity_key)
            if key and (key not in deaths or t < deaths[key]):
                deaths[key] = t
    return deaths


def _find_explicit_death_times(canonical: Dict[str, Any]) -> Dict[str, float]:
    deaths: Dict[str, float] = {}
    entities = canonical.get("entities", {}) or {}
    if isinstance(entities, dict):
        for entity_key, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            try:
                death_t = float(entity.get("death_time"))
            except (TypeError, ValueError):
                death_t = -1.0
            if death_t >= 0.0:
                key = str(entity_key)
                if key and (key not in deaths or death_t < deaths[key]):
                    deaths[key] = death_t
    for event in canonical.get("events", {}).get("deaths", []):
        if not isinstance(event, dict):
            continue
        key = str(event.get("entity_key", ""))
        t = float(event.get("time_s", 0.0) or 0.0)
        if key and (key not in deaths or t < deaths[key]):
            deaths[key] = t
    for event in canonical.get("events", {}).get("kills", []):
        if not isinstance(event, dict):
            continue
        key = str(event.get("victim_entity_key", ""))
        t = float(event.get("time_s", 0.0) or 0.0)
        if key and (key not in deaths or t < deaths[key]):
            deaths[key] = t
    return deaths


def _find_kill_feed_death_times(canonical: Dict[str, Any]) -> Dict[str, float]:
    deaths: Dict[str, float] = {}
    for event in canonical.get("events", {}).get("kills", []):
        if not isinstance(event, dict):
            continue
        key = str(event.get("victim_entity_key", ""))
        t = float(event.get("time_s", 0.0) or 0.0)
        if key and (key not in deaths or t < deaths[key]):
            deaths[key] = t
    return deaths


def _team_side(value: Any) -> str:
    s = str(value or "").lower()
    if s in ("enemy", "foe", "red"):
        return "enemy"
    if s in ("ally", "player", "friendly", "green"):
        return "friendly"
    return "unknown"


def _status_color(team_side: str, spotted: bool, sunk: bool, ever_spotted: bool = False) -> Tuple[int, int, int]:
    if sunk:
        return COLOR_SUNK
    # Keep allied side consistently green for easier ownership checks.
    if team_side == "friendly":
        return COLOR_FRIENDLY
    if team_side == "enemy":
        if (not spotted) and ever_spotted:
            return COLOR_UNSPOTTED
        return COLOR_ENEMY
    if not spotted:
        return COLOR_UNSPOTTED
    return COLOR_UNKNOWN


def _color_side(track: Dict[str, Any]) -> str:
    # Prefer explicit replay team labels when available (ally/player/enemy).
    hinted = _team_side(track.get("team_label_side"))
    if hinted in ("friendly", "enemy"):
        return hinted
    return _team_side(track.get("team_side"))


def _spread_marker_position(cx: int, cy: int, idx: int, cell: int = 16) -> Tuple[int, int]:
    # Small deterministic spread so overlapping spawn clusters remain distinguishable.
    if idx <= 0:
        return cx, cy
    ring = 1 + (idx - 1) // 8
    pos = (idx - 1) % 8
    angle = (pos * 45.0) * math.pi / 180.0
    radius = ring * (cell // 2)
    return int(cx + math.cos(angle) * radius), int(cy + math.sin(angle) * radius)


def _spread_world_position(x: float, z: float, idx: int, cell: float = 40.0) -> Tuple[float, float]:
    if idx <= 0:
        return x, z
    ring = 1 + (idx - 1) // 8
    pos = (idx - 1) % 8
    angle = (pos * 45.0) * math.pi / 180.0
    radius = ring * (cell * 0.5)
    return x + math.cos(angle) * radius, z + math.sin(angle) * radius


def _map_title(canonical: Dict[str, Any]) -> str:
    meta = canonical.get("meta", {}) or {}
    title = meta.get("map_name_resolved") or meta.get("mapDisplayName") or meta.get("mapName")
    if title is None:
        return "Unknown Map"
    return str(title)


def _norm_name(value: Any) -> str:
    s = str(value or "").strip().lower()
    # Keep letters, digits, underscore and dash to match player names robustly.
    return re.sub(r"[^a-z0-9_-]+", "", s)


def _lineup_number_text(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "?"


def _marker_name_text(value: Any, max_len: int = 14) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "~"


def _sidebar_width(map_size: int) -> int:
    width = max(500, min(760, int(map_size * 0.72)))
    width = max(500, min(1040, int(round(width * SIDEBAR_WIDTH_SCALE))))
    if width % 2:
        width += 1
    return width


def _player_ribbon_icon_height(font_size: int, ribbon_count: int = 0, panel_width: int = 0, max_rows: int = 2) -> int:
    base_size = max(32, int(font_size * 2.8))
    if ribbon_count <= 0:
        return base_size
    # Scale down icon size as ribbon count increases to fit more ribbons
    # Minimum size is 16px, maximum is the base_size
    # Scale factor: 1.0 for 1-3 ribbons, then gradually decreases
    scale_factor = max(0.5, min(1.0, 3.0 / max(3, ribbon_count)))
    icon_size = max(16, int(base_size * scale_factor))
    
    # Further adjust if panel_width and max_rows are provided to ensure all ribbons fit
    if panel_width > 0 and max_rows > 0:
        # Estimate average badge width based on icon size
        badge_font = _player_ribbon_badge_font(font_size)
        # Rough estimate: icon + count text + padding
        estimated_badge_w = icon_size + 30 + badge_font * 3
        usable_w = max(60, int(panel_width) - 20)  # inner_left + inner_right
        badges_per_row = max(1, usable_w // estimated_badge_w)
        total_rows_needed = (ribbon_count + badges_per_row - 1) // badges_per_row
        
        # If we need more rows than available, scale down further
        if total_rows_needed > max_rows:
            additional_scale = max_rows / total_rows_needed
            icon_size = max(16, int(icon_size * additional_scale))
    
    return icon_size


def _player_ribbon_badge_font(font_size: int) -> int:
    return max(11, font_size + 1)


def _split_lineups(render_tracks: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    friendly = [v for v in render_tracks.values() if v.get("team_side") == "friendly"]
    enemy = [v for v in render_tracks.values() if v.get("team_side") == "enemy"]
    def _sort_key(item: Dict[str, Any]) -> Tuple[int, int, str]:
        ship_type = _ship_type(item.get("ship_id"))
        class_rank = LINEUP_CLASS_ORDER.get(ship_type, 99)
        team_no = int(item.get("team_number_local") or 999)
        player_name = str(item.get("player_name") or "").lower()
        return (class_rank, team_no, player_name)
    friendly.sort(key=_sort_key)
    enemy.sort(key=_sort_key)
    return friendly, enemy


def _render_layout(render_tracks: Dict[str, Dict[str, Any]], map_size: int, *, hide_player_card: bool = False) -> Dict[str, Any]:
    sidebar_w = _sidebar_width(map_size)
    total_w = map_size + sidebar_w
    pad = max(10, map_size // 90)
    panel_w = sidebar_w - pad * 2
    top_y = pad
    base_font_size = max(11, map_size // 82)
    font_size = max(base_font_size, int(round(base_font_size * SIDEBAR_TEXT_SCALE)))
    line_h = max(17, int(round((base_font_size + 6) * SIDEBAR_TEXT_SCALE)))
    header_h = max(22, int(round((base_font_size + 10) * SIDEBAR_TEXT_SCALE)))
    friendly, enemy = _split_lineups(render_tracks)
    lineup_rows = max(len(friendly), len(enemy))
    lineup_h = lineup_rows * line_h + 10
    player_h = 0 if hide_player_card else max(186, min(236, int(map_size * 0.23)))
    feed_min_h = max(96, int(round(96 * SIDEBAR_TEXT_SCALE)))
    lineup_y = map_size - lineup_h
    feed_y = top_y if hide_player_card else top_y + player_h + pad
    feed_bottom = max(feed_y + feed_min_h, lineup_y - pad)
    feed_rect = (map_size + pad, feed_y, map_size + pad + panel_w, feed_bottom)
    col_gap = max(14, pad + 2)
    col_w = max(120, (panel_w - col_gap) // 2)
    friendly_rect = (map_size + pad, lineup_y, map_size + pad + col_w, lineup_y + lineup_h)
    enemy_rect = (friendly_rect[2] + col_gap, lineup_y, map_size + pad + panel_w, lineup_y + lineup_h)
    return {
        "map_size": map_size,
        "width": total_w,
        "height": map_size,
        "sidebar_x": map_size,
        "sidebar_width": sidebar_w,
        "sidebar_pad": pad,
        "panel_width": panel_w,
        "base_font_size": base_font_size,
        "font_size": font_size,
        "line_h": line_h,
        "header_h": header_h,
        "friendly_items": friendly,
        "enemy_items": enemy,
        "player_rect": (0, 0, 0, 0) if hide_player_card else (map_size + pad, top_y, map_size + pad + panel_w, top_y + player_h),
        "hide_player_card": bool(hide_player_card),
        "feed_rect": feed_rect,
        "friendly_rect": friendly_rect,
        "enemy_rect": enemy_rect,
    }


def _sorted_supported_ribbons(ribbons: Dict[str, Any]) -> List[Tuple[str, int]]:
    supported_ribbons = _gameparams_supported_ribbon_ids()
    items: List[Tuple[str, int]] = []
    if not isinstance(ribbons, dict):
        return items
    for ribbon_id, count in ribbons.items():
        rid = _safe_int(ribbon_id)
        cnt = _safe_int(count)
        if rid is None or cnt is None or cnt <= 0 or rid not in supported_ribbons:
            continue
        items.append((str(ribbon_id), int(cnt)))
    items.sort(key=lambda item: (-int(item[1]), int(item[0])))
    return items


def _ribbon_badge_size(ribbon_id: str, count: int, icon_size: int, badge_font: int) -> Tuple[int, int]:
    rid = _safe_int(ribbon_id)
    icon = _load_ribbon_icon(rid or -1, icon_size) if rid is not None else None
    count_sprite = _text_sprite(f"x{int(count)}", badge_font, WOWS_TEXT, shadow=(0, 0, 0), bold=True)
    if icon is not None and count_sprite is not None:
        badge_w = icon.width + 16 + count_sprite.width + 20
        badge_h = max(icon.height, count_sprite.height) + 6
        return badge_w, badge_h
    fallback = _text_sprite(f"R{int(ribbon_id)} x{int(count)}", badge_font, WOWS_TEXT, shadow=None, bold=True)
    if fallback is None:
        return 0, 0
    return fallback.width + 14, fallback.height + 6


def _ribbon_row_count(panel_width: int, font_size: int, ribbons: Dict[str, Any]) -> Tuple[int, int]:
    items = _sorted_supported_ribbons(ribbons)
    if not items:
        return 0, 0
    icon_size = _player_ribbon_icon_height(font_size, len(items), panel_width, max_rows=3)
    badge_font = _player_ribbon_badge_font(font_size)
    inner_left = 10
    inner_right = 10
    usable_w = max(60, int(panel_width) - inner_left - inner_right)
    rows = 1
    row_w = 0
    max_badge_h = 0
    for ribbon_id, count in items:
        badge_w, badge_h = _ribbon_badge_size(ribbon_id, count, icon_size, badge_font)
        if badge_w <= 0 or badge_h <= 0:
            continue
        if row_w > 0 and row_w + 6 + badge_w > usable_w:
            rows += 1
            row_w = badge_w
        else:
            row_w = badge_w if row_w == 0 else row_w + 6 + badge_w
        max_badge_h = max(max_badge_h, badge_h)
    return rows, max_badge_h


def _player_panel_required_height(panel_width: int, font_size: int, ribbons: Dict[str, Any]) -> int:
    font_size = max(10, int(round(float(font_size) * PLAYER_CARD_TEXT_SCALE)))
    line_gap = max(18, font_size + 5)
    top_pad = 12
    preview_w = max(112, min(220, int(panel_width * 0.44)))
    preview_h = max(60, min(90, int(round(preview_w * 0.45))))
    hp_line_h = font_size + 6
    preview_bottom = top_pad + preview_h + 6 + hp_line_h
    info_bottom = top_pad + line_gap * 3 + max(font_size + 4, int(round(font_size * 1.2)))
    content_bottom = max(preview_bottom, info_bottom)

    rows, badge_h = _ribbon_row_count(panel_width, font_size, ribbons)
    if rows <= 0 or badge_h <= 0:
        return max(186, content_bottom + 14)

    title_y = content_bottom + 10
    badges_top = title_y + font_size + 5
    badges_bottom = badges_top + rows * badge_h + max(0, rows - 1) * 4
    return max(186, badges_bottom + 6)


def _layout_for_player_status(layout: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
    player_rect = tuple(layout.get("player_rect", (0, 0, 0, 0)))
    feed_rect = tuple(layout.get("feed_rect", (0, 0, 0, 0)))
    friendly_rect = tuple(layout.get("friendly_rect", (0, 0, 0, 0)))
    if player_rect[2] <= player_rect[0] or feed_rect[2] <= feed_rect[0] or friendly_rect[3] <= friendly_rect[1]:
        return layout

    x0, y0, x1, y1 = map(int, player_rect)
    panel_width = x1 - x0
    base_player_h = y1 - y0
    pad = int(layout.get("sidebar_pad", 10))
    lineup_y = int(friendly_rect[1])
    font_size = max(10, int(layout.get("font_size", 10)))
    target_h = _player_panel_required_height(panel_width, font_size, dict(status.get("ribbons") or {}))

    min_feed_h = max(44, int(round(44 * SIDEBAR_TEXT_SCALE)))
    max_player_h = max(base_player_h, lineup_y - y0 - pad * 2 - min_feed_h)
    target_h = max(base_player_h, min(int(target_h), int(max_player_h)))

    if target_h == base_player_h:
        return layout

    feed_y = y0 + target_h + pad
    feed_bottom = max(feed_y + min_feed_h, lineup_y - pad)
    updated = dict(layout)
    updated["player_rect"] = (x0, y0, x1, y0 + target_h)
    updated["feed_rect"] = (int(feed_rect[0]), feed_y, int(feed_rect[2]), feed_bottom)
    return updated


def _draw_polyline_with_gaps(
    draw: ImageDraw.ImageDraw,
    poly: List[Tuple[int, int]],
    color: Tuple[int, int, int],
    width: int = 2,
    max_jump_px: int = 30,
) -> None:
    if len(poly) < 2:
        return
    max_jump_sq = max_jump_px * max_jump_px
    start = 0
    for i in range(1, len(poly)):
        dx = poly[i][0] - poly[i - 1][0]
        dy = poly[i][1] - poly[i - 1][1]
        if dx * dx + dy * dy > max_jump_sq:
            if i - start >= 2:
                draw.line(poly[start:i], fill=color, width=width)
            start = i
    if len(poly) - start >= 2:
        draw.line(poly[start:], fill=color, width=width)


def _extract_artillery_traces(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    fires = events.get("fires", [])
    if not isinstance(fires, list):
        return []
    traces: List[Dict[str, Any]] = []
    for fire in fires:
        if not isinstance(fire, dict):
            continue
        if str(fire.get("kind") or "") not in ("", "artillery_trace"):
            continue
        t0 = float(fire.get("time_s", 0.0) or 0.0)
        t1 = float(fire.get("time_end_s", t0) or t0)
        if t1 < t0:
            t1 = t0
        traces.append(
            {
                "time_s": t0,
                "time_end_s": t1,
                "params_id": _safe_int(fire.get("params_id")) or -1,
                "battery_kind": str(fire.get("battery_kind") or "").strip().lower(),
                "shell_kind": str(fire.get("shell_kind") or "").strip().lower(),
                "x0": float(fire.get("x0", 0.0) or 0.0),
                "z0": float(fire.get("z0", 0.0) or 0.0),
                "x1": float(fire.get("x1", 0.0) or 0.0),
                "z1": float(fire.get("z1", 0.0) or 0.0),
            }
        )
    traces.sort(key=lambda item: float(item.get("time_s", 0.0)))
    return traces


def _extract_kill_feed(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("kills", [])
    if not isinstance(raw, list):
        return []
    
    # Deduplication: same killer + victim within 2 second window
    kills: List[Dict[str, Any]] = []
    seen_pairs: Dict[Tuple[str, str], float] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        killer_key = str(row.get("killer_entity_key") or "-1")
        victim_key = str(row.get("victim_entity_key") or "-1")
        time_s = float(row.get("time_s", 0.0) or 0.0)
        
        pair_key = (killer_key, victim_key)
        last_time = seen_pairs.get(pair_key)
        if last_time is not None and (time_s - last_time) < 2.0:
            continue
        seen_pairs[pair_key] = time_s
        
        kills.append(
            {
                "time_s": time_s,
                "killer_entity_key": killer_key,
                "victim_entity_key": victim_key,
                "reason_code": _safe_int(row.get("reason_code")) or -1,
                "weapon_kind": str(row.get("weapon_kind") or "other"),
                "weapon_label": str(row.get("weapon_label") or "KILL"),
                "shell_kind": str(row.get("shell_kind") or "").strip().lower(),
            }
        )
    
    kills.sort(key=lambda item: float(item.get("time_s", 0.0)))
    return kills


def _extract_chat_feed(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("chat", [])
    if not isinstance(raw, list):
        return []
    chat: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        message = str(row.get("message") or "").strip()
        if not message:
            continue
        chat.append(
            {
                "time_s": float(row.get("time_s", 0.0) or 0.0),
                "sender": str(row.get("sender") or "").strip(),
                "message": message,
            }
        )
    chat.sort(key=lambda item: float(item.get("time_s", 0.0)))
    return chat


def _extract_health_timelines(canonical: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("health", [])
    if not isinstance(raw, list):
        return {}

    timelines: Dict[str, Dict[str, Any]] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        t = float(row.get("time_s", 0.0) or 0.0)
        entities = row.get("entities", {})
        if not isinstance(entities, dict):
            continue
        for entity_key, state in entities.items():
            if not isinstance(state, dict):
                continue
            key = str(entity_key)
            timeline = timelines.setdefault(
                key,
                {
                    "times": [],
                    "hp": [],
                    "alive": [],
                    "fire": [],
                    "flood": [],
                    "restorable_hp": [],
                    "regenerated_hp": [],
                    "max_hp": 0,
                    "first_live_time": None,
                    "has_live_sample": False,
                },
            )
            hp = max(0, _safe_int(state.get("hp")) or 0)
            alive = bool(state.get("alive", True))
            max_hp = max(0, _safe_int(state.get("max_hp")) or 0)
            timeline["times"].append(t)
            timeline["hp"].append(hp)
            timeline["alive"].append(alive)
            timeline["fire"].append(bool(state.get("on_fire", False)))
            timeline["flood"].append(bool(state.get("flooding", False)))
            timeline["restorable_hp"].append(max(0, _safe_int(state.get("restorable_hp")) or 0))
            timeline["regenerated_hp"].append(max(0, _safe_int(state.get("regenerated_hp")) or 0))
            timeline["max_hp"] = max(int(timeline.get("max_hp", 0) or 0), max_hp)
            if alive or hp > 0:
                timeline["has_live_sample"] = True
                if timeline.get("first_live_time") is None:
                    timeline["first_live_time"] = t
    return timelines


def _health_state_at(health_timelines: Dict[str, Dict[str, Any]], entity_key: Any, t: float) -> Optional[Dict[str, Any]]:
    timeline = health_timelines.get(str(entity_key))
    if not isinstance(timeline, dict):
        return None
    times = timeline.get("times", [])
    hp_values = timeline.get("hp", [])
    alive_values = timeline.get("alive", [])
    fire_values = timeline.get("fire", [])
    flood_values = timeline.get("flood", [])
    restorable_values = timeline.get("restorable_hp", [])
    regenerated_values = timeline.get("regenerated_hp", [])
    if not isinstance(times, list) or not times:
        return None
    if not bool(timeline.get("has_live_sample", False)):
        return None
    first_live_time = timeline.get("first_live_time")
    if first_live_time is not None and float(t) < float(first_live_time):
        return None
    idx = bisect_right(times, t) - 1
    if idx < 0:
        idx = 0
    idx = min(
        idx,
        len(times) - 1,
        len(hp_values) - 1,
        len(alive_values) - 1,
        len(fire_values) - 1 if isinstance(fire_values, list) and fire_values else len(times) - 1,
        len(flood_values) - 1 if isinstance(flood_values, list) and flood_values else len(times) - 1,
        len(restorable_values) - 1 if isinstance(restorable_values, list) and restorable_values else len(times) - 1,
        len(regenerated_values) - 1 if isinstance(regenerated_values, list) and regenerated_values else len(times) - 1,
    )
    max_hp = max(0, int(timeline.get("max_hp", 0) or 0))
    hp = max(0, int(hp_values[idx]))
    ratio = float(hp) / float(max_hp) if max_hp > 0 else 0.0
    return {
        "hp": hp,
        "max_hp": max_hp,
        "alive": bool(alive_values[idx]),
        "ratio": max(0.0, min(1.0, ratio)),
        "on_fire": bool(fire_values[idx]) if isinstance(fire_values, list) and fire_values else False,
        "flooding": bool(flood_values[idx]) if isinstance(flood_values, list) and flood_values else False,
        "restorable_hp": max(0, int(restorable_values[idx])) if isinstance(restorable_values, list) and restorable_values else 0,
        "regenerated_hp": max(0, int(regenerated_values[idx])) if isinstance(regenerated_values, list) and regenerated_values else 0,
    }


def _extract_player_status_timeline(canonical: Dict[str, Any]) -> Dict[str, Any]:
    events = canonical.get("events", {}) or {}
    raw = events.get("player_status", [])
    if not isinstance(raw, list):
        raw = []

    status = {
        "times": [],
        "damage_total": [],
        "potential_damage": [],
        "spotting_damage": [],
        "ribbons": [],
        "player_name": str((canonical.get("meta", {}) or {}).get("playerName") or "").strip(),
        "ship_entity_key": str((canonical.get("meta", {}) or {}).get("player_ship_entity_id") or ""),
        "ship_id": _safe_int((canonical.get("meta", {}) or {}).get("player_ship_id")) or -1,
        "team_id": _safe_int((canonical.get("meta", {}) or {}).get("local_team_id")) if _safe_int((canonical.get("meta", {}) or {}).get("local_team_id")) is not None else -1,
        "max_health": 0,
    }
    for row in raw:
        if not isinstance(row, dict):
            continue
        ribbons_raw = row.get("ribbons", {})
        ribbons: Dict[str, int] = {}
        if isinstance(ribbons_raw, dict):
            for ribbon_id, count in ribbons_raw.items():
                rid = _safe_int(ribbon_id)
                cnt = _safe_int(count)
                if rid is None or cnt is None or cnt <= 0:
                    continue
                ribbons[str(rid)] = cnt
        status["times"].append(float(row.get("time_s", 0.0) or 0.0))
        status["damage_total"].append(float(row.get("damage_total", 0.0) or 0.0))
        status["potential_damage"].append(float(row.get("potential_damage", 0.0) or 0.0))
        status["spotting_damage"].append(float(row.get("spotting_damage", 0.0) or 0.0))
        status["ribbons"].append(ribbons)
        if str(row.get("player_name") or "").strip():
            status["player_name"] = str(row.get("player_name") or "").strip()
        ship_entity_key = str(row.get("ship_entity_key") or "").strip()
        if ship_entity_key and ship_entity_key != "-1":
            status["ship_entity_key"] = ship_entity_key
        ship_id = _safe_int(row.get("ship_id"))
        if ship_id is not None and ship_id >= 0:
            status["ship_id"] = ship_id
        team_id = _safe_int(row.get("team_id"))
        if team_id is not None and team_id >= 0:
            status["team_id"] = team_id
        status["max_health"] = max(int(status.get("max_health", 0) or 0), max(0, _safe_int(row.get("max_health")) or 0))
    return status


def _player_status_at(status_timeline: Dict[str, Any], t: float) -> Dict[str, Any]:
    times = status_timeline.get("times", [])
    if not isinstance(times, list) or not times:
        return {
            "damage_total": 0.0,
            "potential_damage": 0.0,
            "spotting_damage": 0.0,
            "ribbons": {},
            "player_name": str(status_timeline.get("player_name") or "").strip(),
            "ship_entity_key": str(status_timeline.get("ship_entity_key") or ""),
            "ship_id": _safe_int(status_timeline.get("ship_id")) or -1,
            "team_id": _safe_int(status_timeline.get("team_id")) if _safe_int(status_timeline.get("team_id")) is not None else -1,
            "max_health": max(0, _safe_int(status_timeline.get("max_health")) or 0),
        }
    idx = bisect_right(times, t) - 1
    if idx < 0:
        idx = 0
    idx = min(idx, len(times) - 1, len(status_timeline.get("damage_total", [])) - 1, len(status_timeline.get("ribbons", [])) - 1)
    return {
        "damage_total": float(status_timeline.get("damage_total", [0.0])[idx] or 0.0),
        "potential_damage": float(status_timeline.get("potential_damage", [0.0])[idx] or 0.0),
        "spotting_damage": float(status_timeline.get("spotting_damage", [0.0])[idx] or 0.0),
        "ribbons": dict(status_timeline.get("ribbons", [{}])[idx] or {}),
        "player_name": str(status_timeline.get("player_name") or "").strip(),
        "ship_entity_key": str(status_timeline.get("ship_entity_key") or ""),
        "ship_id": _safe_int(status_timeline.get("ship_id")) or -1,
        "team_id": _safe_int(status_timeline.get("team_id")) if _safe_int(status_timeline.get("team_id")) is not None else -1,
        "max_health": max(0, _safe_int(status_timeline.get("max_health")) or 0),
    }


def _feed_name_key(value: Any) -> str:
    s = str(value or "").strip()
    s = re.sub(r"^\[[^\]]+\]\s*", "", s)
    return _norm_name(s)


def _feed_name_color(team_side: str) -> Tuple[int, int, int]:
    if team_side == "friendly":
        return COLOR_FRIENDLY
    if team_side == "enemy":
        return COLOR_ENEMY
    return WOWS_TEXT_SUB


def _player_team_side(render_tracks: Dict[str, Dict[str, Any]], player_name: str) -> str:
    target = _feed_name_key(player_name)
    if not target:
        return "unknown"
    for track in render_tracks.values():
        if _feed_name_key(track.get("player_name")) == target:
            return str(track.get("team_side") or "unknown")
    return "unknown"


def _ship_state_at(track: Dict[str, Any], t: float, max_gap_s: float = 4.0) -> Optional[Dict[str, float]]:
    points = list(track.get("points", []) or [])
    if not points:
        return None
    times = [float(p.get("t", 0.0)) for p in points]
    idx = bisect_right(times, t) - 1
    if idx < 0:
        idx = 0
    if idx >= len(points) - 1:
        p = points[idx]
        return {
            "x": float(p.get("x", 0.0)),
            "z": float(p.get("z", 0.0)),
            "yaw": float(p.get("yaw", 0.0) or 0.0),
        }
    p0 = points[idx]
    p1 = points[idx + 1]
    t0 = float(p0.get("t", 0.0))
    t1 = float(p1.get("t", t0))
    if (t1 - t0) > max_gap_s:
        return {
            "x": float(p0.get("x", 0.0)),
            "z": float(p0.get("z", 0.0)),
            "yaw": float(p0.get("yaw", 0.0) or 0.0),
        }
    if t1 <= t0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
    raw_yaw0 = float(p0.get("yaw", 0.0) or 0.0)
    raw_yaw1 = float(p1.get("yaw", p0.get("yaw", 0.0)) or 0.0)
    yaw0 = _yaw_to_heading_deg(raw_yaw0)
    yaw1 = _yaw_to_heading_deg(raw_yaw1)
    # For sparse ship updates, a fully interpolated yaw can look "ahead" of the
    # visible hull while the ship is maneuvering slowly (for example while
    # capping). In those cases, prefer the nearer observed packet yaw instead of
    # inventing a continuous turn between wide samples.
    segment_dt = max(0.0, t1 - t0)
    yaw_delta = abs(_angle_delta_deg(yaw1, yaw0))
    if segment_dt > 0.45 and yaw_delta > 6.0:
        yaw_interp = yaw0 if ratio < 0.5 else yaw1
    else:
        yaw_interp = _lerp_angle_deg(yaw0, yaw1, ratio)
    if abs(raw_yaw0) <= (2.0 * math.pi + 0.5) and abs(raw_yaw1) <= (2.0 * math.pi + 0.5):
        yaw_value = math.radians(yaw_interp)
    else:
        yaw_value = yaw_interp
    return {
        "x": float(p0.get("x", 0.0)) + (float(p1.get("x", 0.0)) - float(p0.get("x", 0.0))) * ratio,
        "z": float(p0.get("z", 0.0)) + (float(p1.get("z", 0.0)) - float(p0.get("z", 0.0))) * ratio,
        "yaw": float(yaw_value),
    }


def _ship_packet_state_at(track: Dict[str, Any], t: float) -> Optional[Dict[str, float]]:
    points = list(track.get("points", []) or [])
    if not points:
        return None
    times = [float(p.get("t", 0.0)) for p in points]
    idx = bisect_right(times, t) - 1
    if idx < 0:
        idx = 0
    if idx >= len(points):
        idx = len(points) - 1
    p = points[idx]
    return {
        "x": float(p.get("x", 0.0)),
        "z": float(p.get("z", 0.0)),
        "yaw": float(p.get("yaw", 0.0) or 0.0),
    }


def _estimate_torpedo_speed(tracks: Dict[str, Dict[str, Any]]) -> float:
    samples: List[float] = []
    for track in tracks.values():
        points = track.get("points", [])
        if len(points) < 2:
            continue
        for p0, p1 in zip(points, points[1:5]):
            t0 = float(p0.get("t", 0.0))
            t1 = float(p1.get("t", t0))
            if t1 <= t0:
                continue
            dist = math.hypot(float(p1.get("x", 0.0)) - float(p0.get("x", 0.0)), float(p1.get("z", 0.0)) - float(p0.get("z", 0.0)))
            speed = dist / (t1 - t0)
            if 1.0 <= speed <= 100.0:
                samples.append(speed)
                break
    if not samples:
        return 7.5
    samples.sort()
    return float(samples[len(samples) // 2])


def _normalize_dir(vec: Tuple[float, float] | None) -> Tuple[float, float] | None:
    if vec is None:
        return None
    dx, dz = float(vec[0]), float(vec[1])
    dist = math.hypot(dx, dz)
    if dist < 1e-6:
        return None
    return dx / dist, dz / dist


def _angular_diff_deg(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    ax, az = _normalize_dir(a) or (0.0, 0.0)
    bx, bz = _normalize_dir(b) or (0.0, 0.0)
    dot = max(-1.0, min(1.0, ax * bx + az * bz))
    return math.degrees(math.acos(dot))


def _stabilize_single_point_torpedo_dirs(tracks: Dict[str, Dict[str, Any]], cluster_gap_s: float = 2.5) -> None:
    by_owner: Dict[str, List[Dict[str, Any]]] = {}
    for track in tracks.values():
        points = track.get("points", [])
        if len(points) != 1:
            continue
        if bool(track.get("has_raw_dir")):
            continue
        direction = _normalize_dir(track.get("dir"))
        if direction is None:
            continue
        t0 = float(points[0].get("t", 0.0))
        track["_launch_t"] = t0
        by_owner.setdefault(str(track.get("owner_entity_key") or "-1"), []).append(track)

    for owner_tracks in by_owner.values():
        owner_tracks.sort(key=lambda item: float(item.get("_launch_t", 0.0)))
        cluster: List[Dict[str, Any]] = []

        def _flush_cluster(items: List[Dict[str, Any]]) -> None:
            if len(items) < 2:
                return
            dirs = [_normalize_dir(item.get("dir")) for item in items]
            dirs = [d for d in dirs if d is not None]
            if len(dirs) < 2:
                return
            avg_x = sum(d[0] for d in dirs)
            avg_z = sum(d[1] for d in dirs)
            avg_dir = _normalize_dir((avg_x, avg_z))
            if avg_dir is None:
                return
            if max(_angular_diff_deg(avg_dir, d) for d in dirs) > 25.0:
                return
            for item in items:
                item["dir"] = avg_dir

        for track in owner_tracks:
            if not cluster:
                cluster = [track]
                continue
            prev_t = float(cluster[-1].get("_launch_t", 0.0))
            cur_t = float(track.get("_launch_t", 0.0))
            if (cur_t - prev_t) <= cluster_gap_s:
                cluster.append(track)
            else:
                _flush_cluster(cluster)
                cluster = [track]
        _flush_cluster(cluster)

    for track in tracks.values():
        track.pop("_launch_t", None)


def _extract_torpedo_tracks(canonical: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("torpedoes", [])
    if not isinstance(raw, list):
        return {}

    tracks: Dict[str, Dict[str, Any]] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        owner_key = str(row.get("owner_entity_key") or "-1")
        torpedo_id = _safe_int(row.get("torpedo_id"))
        torpedo_id = torpedo_id if torpedo_id is not None else -1
        track_key = f"{owner_key}:{torpedo_id}"
        track = tracks.setdefault(
            track_key,
            {
                "owner_entity_key": owner_key,
                "torpedo_id": torpedo_id,
                "team_side": str(row.get("team_side") or "unknown"),
                "points": [],
                "times": [],
                "dir": None,
                "has_raw_dir": False,
                "speed": None,
                "predict_s": 0.0,
            },
        )
        raw_dir = _normalize_dir(
            (
                float(row.get("dir_x", 0.0) or 0.0),
                float(row.get("dir_z", 0.0) or 0.0),
            )
        )
        if raw_dir is not None:
            track["dir"] = raw_dir
            track["has_raw_dir"] = True
        t = float(row.get("time_s", 0.0) or 0.0)
        x = float(row.get("x", 0.0) or 0.0)
        z = float(row.get("z", 0.0) or 0.0)
        track["points"].append({"t": t, "x": x, "z": z})

    for track in tracks.values():
        points = track.get("points", [])
        points.sort(key=lambda item: float(item.get("t", 0.0)))
        deduped: List[Dict[str, float]] = []
        last = None
        for p in points:
            key = (round(float(p.get("t", 0.0)), 3), round(float(p.get("x", 0.0)), 2), round(float(p.get("z", 0.0)), 2))
            if key == last:
                continue
            deduped.append(p)
            last = key
        track["points"] = deduped
        track["times"] = [float(p.get("t", 0.0)) for p in deduped]

    default_speed = _estimate_torpedo_speed(tracks)
    owner_tracks = canonical.get("tracks", {}) or {}
    for track in tracks.values():
        points = track.get("points", [])
        if not points:
            continue
        direction = _normalize_dir(track.get("dir"))
        speed = default_speed
        if len(points) >= 2:
            p0 = points[0]
            p1 = points[1]
            dt = max(1e-3, float(p1.get("t", 0.0)) - float(p0.get("t", 0.0)))
            dx = float(p1.get("x", 0.0)) - float(p0.get("x", 0.0))
            dz = float(p1.get("z", 0.0)) - float(p0.get("z", 0.0))
            dist = math.hypot(dx, dz)
            if dist >= 1e-6:
                direction = (dx / dist, dz / dist)
                speed = dist / dt
        if direction is None:
            owner_track = owner_tracks.get(str(track.get("owner_entity_key") or ""))
            if isinstance(owner_track, dict):
                ship_state = _ship_state_at(owner_track, float(points[0].get("t", 0.0)))
            else:
                ship_state = None
            if ship_state is not None:
                dx = float(points[0].get("x", 0.0)) - float(ship_state.get("x", 0.0))
                dz = float(points[0].get("z", 0.0)) - float(ship_state.get("z", 0.0))
                dist = math.hypot(dx, dz)
                if dist >= 0.2:
                    direction = (dx / dist, dz / dist)
                else:
                    heading = _yaw_to_heading_deg(ship_state.get("yaw", 0.0))
                    rad = math.radians(heading)
                    direction = (math.sin(rad), math.cos(rad))
        track["dir"] = direction
        track["speed"] = float(speed if speed > 0.0 else default_speed)
        if len(points) == 1:
            track["predict_s"] = 22.0 if str(track.get("team_side")) == "friendly" else 14.0
        else:
            track["predict_s"] = 6.0

    _stabilize_single_point_torpedo_dirs(tracks)

    for track in tracks.values():
        track.pop("has_raw_dir", None)

    return tracks


def _torpedo_position_at(track: Dict[str, Any], t: float, max_stale_s: float = 3.5, max_gap_s: float = 4.0) -> Tuple[float, float] | None:
    points = track.get("points", [])
    times = track.get("times", [])
    if not points or not times:
        return None
    idx = bisect_right(times, t) - 1
    if idx < 0:
        return None
    if idx >= len(points) - 1:
        last_t = float(times[-1])
        predict_s = float(track.get("predict_s", 0.0) or 0.0)
        direction = track.get("dir")
        speed = float(track.get("speed", 0.0) or 0.0)
        if direction is not None and speed > 0.0 and (t - last_t) <= predict_s:
            dx, dz = direction
            dt = max(0.0, t - last_t)
            return float(points[-1]["x"]) + dx * speed * dt, float(points[-1]["z"]) + dz * speed * dt
        if t - last_t > max_stale_s:
            return None
        return float(points[-1]["x"]), float(points[-1]["z"])

    p0 = points[idx]
    p1 = points[idx + 1]
    t0 = float(p0.get("t", 0.0))
    t1 = float(p1.get("t", t0))
    if t1 <= t0:
        return float(p0.get("x", 0.0)), float(p0.get("z", 0.0))
    if (t1 - t0) > max_gap_s:
        direction = track.get("dir")
        speed = float(track.get("speed", 0.0) or 0.0)
        predict_s = float(track.get("predict_s", 0.0) or 0.0)
        if direction is not None and speed > 0.0 and (t - t0) <= min(predict_s, t1 - t0):
            dx, dz = direction
            dt = max(0.0, t - t0)
            return float(p0.get("x", 0.0)) + dx * speed * dt, float(p0.get("z", 0.0)) + dz * speed * dt
        if (t - t0) > max_stale_s:
            return None
        return float(p0.get("x", 0.0)), float(p0.get("z", 0.0))

    ratio = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
    x = float(p0.get("x", 0.0)) + (float(p1.get("x", 0.0)) - float(p0.get("x", 0.0))) * ratio
    z = float(p0.get("z", 0.0)) + (float(p1.get("z", 0.0)) - float(p0.get("z", 0.0))) * ratio
    return x, z


def _torpedo_direction_at(track: Dict[str, Any], t: float) -> Tuple[float, float] | None:
    points = track.get("points", [])
    times = track.get("times", [])
    if not points or not times:
        return None
    if len(points) < 2:
        direction = track.get("dir")
        if isinstance(direction, tuple):
            return float(direction[0]), float(direction[1])
        return None
    idx = bisect_right(times, t) - 1
    if idx < 0:
        return None
    if idx >= len(points) - 1:
        direction = track.get("dir")
        if isinstance(direction, tuple):
            return float(direction[0]), float(direction[1])
        idx = len(points) - 2
    p0 = points[idx]
    p1 = points[idx + 1]
    dx = float(p1.get("x", 0.0)) - float(p0.get("x", 0.0))
    dz = float(p1.get("z", 0.0)) - float(p0.get("z", 0.0))
    dist = math.hypot(dx, dz)
    if dist < 1e-6:
        return None
    return dx / dist, dz / dist


def _draw_torpedoes(
    draw: ImageDraw.ImageDraw,
    torpedo_tracks: Dict[str, Dict[str, Any]],
    t: float,
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> None:
    for track in torpedo_tracks.values():
        pos = _torpedo_position_at(track, t)
        if pos is None:
            continue
        x, z = pos
        px, py = _to_px(x, z, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        direction = _torpedo_direction_at(track, t)
        side = str(track.get("team_side") or "unknown")
        if side == "friendly":
            color = (255, 255, 255)
        elif side == "enemy":
            color = (255, 70, 70)
        else:
            color = (180, 180, 180)

        if direction is None:
            points = [(px, py - 4), (px + 4, py), (px, py + 4), (px - 4, py)]
            draw.polygon(points, fill=color, outline=(20, 20, 20))
            continue

        dx, dz = direction
        front = _to_px(x + dx * 10.0, z + dz * 10.0, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        back = _to_px(x - dx * 8.0, z - dz * 8.0, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        left = _to_px(x - dz * 5.0, z + dx * 5.0, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        right = _to_px(x + dz * 5.0, z - dx * 5.0, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        wake = _to_px(x - dx * 18.0, z - dz * 18.0, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        draw.line([wake, back], fill=color, width=1)
        draw.polygon([front, right, back, left], fill=color, outline=(20, 20, 20))


def _extract_squadron_tracks(canonical: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    events = (canonical.get("events", {}) or {}).get("squadrons", [])
    if not isinstance(events, list):
        return {}

    tracks: Dict[str, Dict[str, Any]] = {}
    for row in events:
        if not isinstance(row, dict):
            continue
        squadron_id = _safe_int(row.get("squadron_id"))
        if squadron_id is None:
            continue
        key = str(squadron_id)
        track = tracks.setdefault(
            key,
            {
                "squadron_id": squadron_id,
                "team_side": str(row.get("team_side") or "unknown"),
                "params_id": _safe_int(row.get("params_id")) or -1,
                "type": str(row.get("squadron_type") or "").strip().lower(),
                "points": [],
                "times": [],
                "visible_times": [],
                "visible_values": [],
                "removed_at": None,
                "default_visible": True,
            },
        )
        event = str(row.get("event") or "update").strip().lower()
        t = float(row.get("time_s", 0.0) or 0.0)
        if "team_side" in row and str(row.get("team_side") or ""):
            track["team_side"] = str(row.get("team_side") or track["team_side"])
        if row.get("params_id") is not None:
            track["params_id"] = _safe_int(row.get("params_id")) or track.get("params_id", -1)
        if row.get("squadron_type"):
            track["type"] = str(row.get("squadron_type") or "").strip().lower()
        if "visible" in row:
            vis = bool(row.get("visible"))
            track["visible_times"].append(t)
            track["visible_values"].append(vis)
            if event == "add":
                track["default_visible"] = vis
        if event == "remove":
            track["removed_at"] = t
            continue
        if event in ("add", "update"):
            x = row.get("x")
            z = row.get("z")
            if x is None or z is None:
                continue
            track["points"].append({"t": t, "x": float(x), "z": float(z)})

    for track in tracks.values():
        points = track.get("points", [])
        points.sort(key=lambda item: float(item.get("t", 0.0)))
        deduped: List[Dict[str, float]] = []
        last = None
        for p in points:
            key = (round(float(p.get("t", 0.0)), 3), round(float(p.get("x", 0.0)), 2), round(float(p.get("z", 0.0)), 2))
            if key == last:
                continue
            deduped.append(p)
            last = key
        track["points"] = deduped
        track["times"] = [float(p.get("t", 0.0)) for p in deduped]
        mapped_type = _squadron_type_from_params(track.get("params_id"))
        track["mapped_type"] = mapped_type
        stype = str(track.get("type") or "").strip().lower()
        if not stype or stype == "main":
            track["type"] = mapped_type

    team_aircraft_caps = {
        "friendly": _team_aircraft_capabilities(canonical, "friendly"),
        "enemy": _team_aircraft_capabilities(canonical, "enemy"),
        "unknown": _empty_team_aircraft_capabilities(),
    }

    for track in tracks.values():
        stype = str(track.get("type") or "").strip().lower()
        if stype not in ("", "main", "default"):
            continue
        team_side = str(track.get("team_side") or "unknown")
        inferred = _infer_unknown_squadron_type(track, team_aircraft_caps.get(team_side, _empty_team_aircraft_capabilities()))
        if inferred:
            track["type"] = inferred
            track["mapped_type"] = inferred

    _refine_squadron_types(canonical, tracks, team_aircraft_caps)

    _assign_fallback_squadron_types(canonical, tracks)

    if os.environ.get("RENDER_AIRCRAFT_DEBUG") == "1":
        debug_entries: Dict[str, Dict[str, Any]] = {}
        for track in tracks.values():
            pid = _safe_int(track.get("params_id"))
            if pid is None:
                continue
            key = str(pid)
            if key in debug_entries:
                continue
            stype = str(track.get("type") or "").strip().lower() or "main"
            _raw_stype, source = _squadron_type_with_source(pid)
            extra = _AIRCRAFT_PARAMS_DEBUG.get(key, {})
            debug_entries[key] = {
                "params_id": pid,
                "mapped_type": stype,
                "source": source,
                "typeinfo": extra.get("typeinfo"),
                "species": extra.get("species"),
                "nation": extra.get("nation"),
                "text": extra.get("text"),
            }
        payload = {
            "tracks_count": len(tracks),
            "entries": debug_entries,
        }
        try:
            path = _root_dir() / "content" / "aircraft_params_debug.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass
    return tracks


def _squadron_track_mobility(track: Dict[str, Any]) -> Tuple[float, float]:
    points = track.get("points", []) or []
    if len(points) < 2:
        return 0.0, 0.0
    path_len = 0.0
    for a, b in zip(points, points[1:]):
        path_len += math.hypot(
            float(b.get("x", 0.0)) - float(a.get("x", 0.0)),
            float(b.get("z", 0.0)) - float(a.get("z", 0.0)),
        )
    disp = math.hypot(
        float(points[-1].get("x", 0.0)) - float(points[0].get("x", 0.0)),
        float(points[-1].get("z", 0.0)) - float(points[0].get("z", 0.0)),
    )
    return path_len, disp


def _refine_squadron_types(
    canonical: Dict[str, Any],
    tracks: Dict[str, Dict[str, Any]],
    team_aircraft_caps: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    if not tracks:
        return
    if team_aircraft_caps is None:
        team_aircraft_caps = {
            "friendly": _team_aircraft_capabilities(canonical, "friendly"),
            "enemy": _team_aircraft_capabilities(canonical, "enemy"),
            "unknown": _empty_team_aircraft_capabilities(),
        }

    tracks_by_side: Dict[str, List[Dict[str, Any]]] = {"friendly": [], "enemy": [], "unknown": []}
    for track in tracks.values():
        side = str(track.get("team_side") or "unknown")
        tracks_by_side.setdefault(side, []).append(track)

    for side, side_tracks in tracks_by_side.items():
        if not side_tracks:
            continue
        caps = team_aircraft_caps.get(side, _empty_team_aircraft_capabilities()) if isinstance(team_aircraft_caps, dict) else _empty_team_aircraft_capabilities()
        carrier_attack = {str(v or "").strip().lower() for v in (caps.get("carrier_attack_types") or []) if str(v or "").strip()}
        support_types = {str(v or "").strip().lower() for v in (caps.get("support_types") or []) if str(v or "").strip()}

        fighter_tracks: List[Dict[str, Any]] = []
        bomber_tracks: List[Dict[str, Any]] = []
        dive_tracks: List[Dict[str, Any]] = []
        for track in side_tracks:
            meta = _aircraft_param_meta(track.get("params_id"))
            species = str(meta.get("species") or "").strip().lower()
            current = str(track.get("type") or "").strip().lower()
            if current == "fighter" and species == "fighter":
                fighter_tracks.append(track)
            elif current == "bomber" and species == "bomber":
                bomber_tracks.append(track)
            elif current == "bomber" and species == "dive":
                dive_tracks.append(track)

        if "rocket" in carrier_attack and fighter_tracks:
            if "fighter" not in support_types:
                for track in fighter_tracks:
                    track["type"] = "rocket"
                    track["mapped_type"] = "rocket"
            elif len(fighter_tracks) == 1:
                path_len, disp = _squadron_track_mobility(fighter_tracks[0])
                if path_len >= 450.0 or disp >= 260.0:
                    fighter_tracks[0]["type"] = "rocket"
                    fighter_tracks[0]["mapped_type"] = "rocket"
            else:
                fighter_by_pid: Dict[int, List[Dict[str, Any]]] = {}
                for track in fighter_tracks:
                    pid = _safe_int(track.get("params_id"))
                    if pid is None:
                        continue
                    fighter_by_pid.setdefault(pid, []).append(track)
                best_pid: Optional[int] = None
                best_score: Tuple[float, float] = (0.0, 0.0)
                for pid, pid_tracks in fighter_by_pid.items():
                    path_vals = []
                    disp_vals = []
                    for track in pid_tracks:
                        path_len, disp = _squadron_track_mobility(track)
                        path_vals.append(path_len)
                        disp_vals.append(disp)
                    score = (_median_value([int(round(v)) for v in path_vals]), _median_value([int(round(v)) for v in disp_vals]))
                    if score > best_score:
                        best_pid = pid
                        best_score = score
                if best_pid is not None and (best_score[0] >= 250.0 or best_score[1] >= 180.0):
                    for track in fighter_by_pid.get(best_pid, []):
                        track["type"] = "rocket"
                        track["mapped_type"] = "rocket"

        if "torpedo" in carrier_attack and "bomber" in carrier_attack and dive_tracks and bomber_tracks:
            for track in bomber_tracks:
                track["type"] = "torpedo"
                track["mapped_type"] = "torpedo"


def _empty_team_aircraft_capabilities() -> Dict[str, Any]:
    return {
        "carrier_attack_types": [],
        "surface_attack_types": [],
        "all_attack_types": [],
        "support_types": [],
        "fallback_types": [],
        "has_cv_attack": False,
        "has_surface_attack": False,
        "has_support": False,
    }


def _prefer_aircraft_type(available: List[str], preferred: Tuple[str, ...]) -> str:
    if not available:
        return ""
    for choice in preferred:
        if choice in available:
            return choice
    return str(available[0] or "").strip().lower()


def _infer_unknown_squadron_type(track: Dict[str, Any], caps: Dict[str, Any]) -> str:
    if not isinstance(track, dict):
        return ""
    if not isinstance(caps, dict):
        caps = _empty_team_aircraft_capabilities()

    meta = _aircraft_param_meta(track.get("params_id"))
    species = str(meta.get("species") or "").strip().lower()
    nation = str(meta.get("nation") or "").strip().lower()

    carrier_attack = [str(v or "").strip().lower() for v in (caps.get("carrier_attack_types") or []) if str(v or "").strip()]
    surface_attack = [str(v or "").strip().lower() for v in (caps.get("surface_attack_types") or []) if str(v or "").strip()]
    all_attack = [str(v or "").strip().lower() for v in (caps.get("all_attack_types") or []) if str(v or "").strip()]
    support_types = [str(v or "").strip().lower() for v in (caps.get("support_types") or []) if str(v or "").strip()]
    has_cv_attack = bool(caps.get("has_cv_attack"))

    if species == "scout":
        return "fighter" if support_types or not all_attack else ""

    if species in ("attack", "rocket"):
        return _prefer_aircraft_type(carrier_attack or all_attack, ("rocket", "rocket_ap"))

    if species in ("torpedo", "torpedobomber"):
        return _prefer_aircraft_type(carrier_attack or all_attack, ("torpedo", "torpedo_deepwater"))

    if species in ("skip", "skipbomber"):
        return _prefer_aircraft_type(carrier_attack or all_attack, ("skip", "skip_ap", "bomber", "bomber_ap"))

    if species in ("dive", "bomber", "divebomber"):
        if not has_cv_attack:
            preferred = ("asw", "airdrop_he", "airdrop", "asw_mine")
            if nation == "netherlands":
                preferred = ("airdrop_he", "airdrop", "asw", "asw_mine")
            return _prefer_aircraft_type(surface_attack, preferred)
        return _prefer_aircraft_type(carrier_attack or all_attack, ("bomber", "bomber_ap", "skip", "skip_ap", "asw", "airdrop_he", "airdrop", "asw_mine"))

    if not all_attack:
        return "fighter" if support_types else ""

    if len(surface_attack) == 1 and not has_cv_attack:
        return str(surface_attack[0] or "").strip().lower()
    if len(all_attack) == 1:
        return str(all_attack[0] or "").strip().lower()
    return ""


def _assign_fallback_squadron_types(canonical: Dict[str, Any], tracks: Dict[str, Dict[str, Any]]) -> None:
    # If params_id mapping failed for some squadrons, try assigning types
    # based on team-side aircraft support and first-seen order.
    if not tracks:
        return

    # Group unknown tracks by team side.
    unknown_by_side: Dict[str, List[Dict[str, Any]]] = {"friendly": [], "enemy": [], "unknown": []}
    for track in tracks.values():
        stype = str(track.get("type") or "").strip().lower()
        if stype and stype != "main":
            continue
        side = str(track.get("team_side") or "unknown")
        unknown_by_side.setdefault(side, []).append(track)

    for side, items in unknown_by_side.items():
        if not items:
            continue
        # Sort by first seen time for stable assignment.
        items.sort(key=lambda tr: float(tr.get("times", [0.0])[0] if tr.get("times") else 0.0))
        available = _team_available_squadron_types(canonical, side)
        if not available:
            continue
        # Assign types by order of first appearance.
        idx = 0
        for track in items:
            track["type"] = available[idx % len(available)]
            idx += 1


def _team_available_squadron_types(canonical: Dict[str, Any], team_side: str) -> List[str]:
    caps = _team_aircraft_capabilities(canonical, team_side)
    return [str(v or "").strip().lower() for v in (caps.get("fallback_types") or []) if str(v or "").strip()]


def _team_aircraft_capabilities(canonical: Dict[str, Any], team_side: str) -> Dict[str, Any]:
    carrier_attack_types: set[str] = set()
    surface_attack_types: set[str] = set()
    support_types: set[str] = set()
    for entry in (canonical.get("entities", {}) or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("team")) not in ("ally", "enemy", "player"):
            continue
        side = "friendly" if str(entry.get("team")) in ("ally", "player") else "enemy"
        if side != team_side:
            continue
        ship_id = entry.get("ship_id")
        ship_kind = _ship_type(ship_id)
        target_attack = carrier_attack_types if ship_kind == "AirCarrier" else surface_attack_types
        support = _ship_aircraft_support(ship_id)
        if support:
            for value in support.get("attack_types", []) or []:
                name = str(value or "").strip().lower()
                if name:
                    target_attack.add(name)
            for value in support.get("render_support_types", []) or []:
                name = str(value or "").strip().lower()
                if name:
                    support_types.add(name)
            continue

        # Fallback to ships_cache when the dedicated support reference is
        # missing for this ship, so older caches still behave sensibly.
        ship_entry = _ship_entry(ship_id)
        modules = ship_entry.get("modules") if isinstance(ship_entry, dict) else {}
        if not isinstance(modules, dict):
            continue
        if modules.get("fighter") or modules.get("rocket"):
            target_attack.add("rocket")
        if modules.get("dive_bomber") or modules.get("bomber"):
            target_attack.add("bomber")
        if modules.get("torpedo_bomber"):
            target_attack.add("torpedo")
        if modules.get("skip_bomber"):
            target_attack.add("skip")

    ordered_carrier_attack = [
        t for t in ("rocket", "rocket_ap", "torpedo", "torpedo_deepwater", "bomber", "bomber_ap", "skip", "skip_ap", "airdrop", "airdrop_he", "asw", "asw_mine")
        if t in carrier_attack_types
    ]
    ordered_support = [t for t in ("fighter",) if t in support_types]
    ordered_surface_attack = [
        t for t in ("airdrop_he", "airdrop", "asw", "asw_mine", "rocket", "rocket_ap", "torpedo", "torpedo_deepwater", "bomber", "bomber_ap", "skip", "skip_ap")
        if t in surface_attack_types
    ]
    ordered_all_attack = list(dict.fromkeys(ordered_carrier_attack + ordered_surface_attack))
    fallback_types = list(dict.fromkeys(ordered_all_attack + ordered_support))
    return {
        "carrier_attack_types": ordered_carrier_attack,
        "surface_attack_types": ordered_surface_attack,
        "all_attack_types": ordered_all_attack,
        "support_types": ordered_support,
        "fallback_types": fallback_types,
        "has_cv_attack": bool(ordered_carrier_attack),
        "has_surface_attack": bool(ordered_surface_attack),
        "has_support": bool(ordered_support),
    }


def _has_cv_entities(canonical: Dict[str, Any]) -> bool:
    for entry in (canonical.get("entities", {}) or {}).values():
        if not isinstance(entry, dict):
            continue
        ship_id = entry.get("ship_id")
        if _ship_type(ship_id) == "AirCarrier":
            return True
    return False


def _aircraft_param_meta(params_id: Any) -> Dict[str, Any]:
    pid = _safe_int(params_id)
    if pid is None:
        return {}
    _load_aircraft_params_from_gameparams()
    meta = _AIRCRAFT_PARAMS_DEBUG.get(str(pid), {})
    return meta if isinstance(meta, dict) else {}


def _squadron_position_at(track: Dict[str, Any], t: float, max_stale_s: float = 6.0, max_gap_s: float = 4.0) -> Tuple[float, float] | None:
    points = track.get("points", [])
    times = track.get("times", [])
    if not points or not times:
        return None
    idx = bisect_right(times, t) - 1
    if idx < 0:
        return None
    if idx >= len(points) - 1:
        last_t = float(times[-1])
        if (t - last_t) > max_stale_s:
            return None
        return float(points[-1]["x"]), float(points[-1]["z"])
    p0 = points[idx]
    p1 = points[idx + 1]
    t0 = float(p0.get("t", 0.0))
    t1 = float(p1.get("t", t0))
    if t1 <= t0:
        return float(p0.get("x", 0.0)), float(p0.get("z", 0.0))
    if (t1 - t0) > max_gap_s:
        if (t - t0) > max_stale_s:
            return None
        return float(p0.get("x", 0.0)), float(p0.get("z", 0.0))
    ratio = max(0.0, min(1.0, (t - t0) / (t1 - t0)))
    x = float(p0.get("x", 0.0)) + (float(p1.get("x", 0.0)) - float(p0.get("x", 0.0))) * ratio
    z = float(p0.get("z", 0.0)) + (float(p1.get("z", 0.0)) - float(p0.get("z", 0.0))) * ratio
    return x, z


def _squadron_heading_at(track: Dict[str, Any], t: float) -> float | None:
    points = track.get("points", [])
    times = track.get("times", [])
    if not points or not times or len(points) < 2:
        return None
    idx = bisect_right(times, t) - 1
    if idx <= 0:
        return None
    idx = min(idx, len(points) - 1)
    p0 = points[idx - 1]
    p1 = points[idx]
    dx = float(p1.get("x", 0.0)) - float(p0.get("x", 0.0))
    dz = float(p1.get("z", 0.0)) - float(p0.get("z", 0.0))
    dist = math.hypot(dx, dz)
    if dist < 1e-6:
        return None
    return math.degrees(math.atan2(dx, dz)) % 360.0


def _squadron_visible_at(track: Dict[str, Any], t: float) -> bool:
    times = track.get("visible_times", [])
    values = track.get("visible_values", [])
    if not times or not values:
        return bool(track.get("default_visible", True))
    idx = bisect_right(times, t) - 1
    if idx < 0:
        return bool(track.get("default_visible", True))
    idx = min(idx, len(values) - 1)
    return bool(values[idx])


def _squadron_legend_types(squadron_tracks: Dict[str, Dict[str, Any]]) -> List[str]:
    types: set[str] = set()
    for track in squadron_tracks.values():
        stype = str(track.get("type") or "").strip().lower()
        if not stype:
            stype = _squadron_type_from_params(track.get("params_id"))
        if stype not in SQUADRON_TYPE_LABELS:
            stype = "main"
        types.add(stype)
    ordered = [t for t in SQUADRON_LEGEND_ORDER if t in types]
    for t in sorted(types):
        if t not in ordered:
            ordered.append(t)
    return ordered


def _legend_aircraft_icon(stype: str, size: int) -> Image.Image | None:
    filename = SQUADRON_TYPE_TO_ICON.get(stype, SQUADRON_TYPE_TO_ICON["main"])
    base_icon = _load_aircraft_icon_base(filename)
    if base_icon is None:
        return None
        tinted = _tint_icon(base_icon, WOWS_TEXT_SUB)
    target = max(10, int(size))
    scale = float(target) / max(tinted.width, tinted.height)
    return tinted.resize((max(1, int(tinted.width * scale)), max(1, int(tinted.height * scale))), Image.Resampling.LANCZOS)


def _draw_squadron_legend(
    img: Image.Image,
    squadron_tracks: Dict[str, Dict[str, Any]],
    canvas_size: int,
    margin: int,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> None:
    types = _squadron_legend_types(squadron_tracks)
    if not types:
        return

    icon_size = max(10, canvas_size // 90)
    font_size = max(10, canvas_size // 70)
    padding = 6
    row_gap = 4
    label_color = WOWS_TEXT_SUB

    title_sprite = _text_sprite("Squadrons", font_size, WOWS_TEXT_SUB, shadow=(0, 0, 0), bold=True)
    rows: List[Tuple[str, Image.Image | None, Image.Image | None]] = []
    text_w = 0
    for stype in types:
        label = SQUADRON_TYPE_LABELS.get(stype, stype.title())
        label_sprite = _text_sprite(label, font_size, label_color, shadow=(0, 0, 0))
        icon_sprite = _legend_aircraft_icon(stype, icon_size)
        if label_sprite is not None:
            text_w = max(text_w, label_sprite.width)
        rows.append((stype, icon_sprite, label_sprite))

    row_h = max(icon_size, font_size) + row_gap
    title_h = title_sprite.height + row_gap if title_sprite is not None else 0
    panel_w = padding * 2 + icon_size + 8 + text_w
    panel_h = padding * 2 + title_h + (row_h * len(rows) - row_gap if rows else 0)

    if map_rect is None:
        left = margin
        top = margin
        right = canvas_size - margin
        bottom = canvas_size - margin
    else:
        left, top, right, bottom = [int(v) for v in map_rect]

    x0 = max(left + 4, right - panel_w - 6)
    y0 = max(top + 4, bottom - panel_h - 6)
    draw_rgba = ImageDraw.Draw(img, "RGBA")
    draw_rgba.rectangle([x0, y0, x0 + panel_w, y0 + panel_h], fill=(12, 16, 26, 185), outline=(45, 45, 45, 210))

    y = y0 + padding
    if title_sprite is not None:
        _paste_sprite(img, title_sprite, x0 + padding, y)
        y += title_h

    for _, icon_sprite, label_sprite in rows:
        if icon_sprite is not None:
            ix = x0 + padding
            iy = y + (row_h - icon_sprite.height) // 2
            img.paste(icon_sprite, (ix, iy), icon_sprite)
        if label_sprite is not None:
            lx = x0 + padding + icon_size + 6
            ly = y + (row_h - label_sprite.height) // 2
            img.paste(label_sprite, (lx, ly), label_sprite)
        y += row_h


def _draw_squadrons(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    squadron_tracks: Dict[str, Dict[str, Any]],
    t: float,
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> None:
    if not squadron_tracks:
        return
    icon_size = int(max(12, canvas_size // 75) * 1.25)
    for track in squadron_tracks.values():
        removed_at = track.get("removed_at")
        if removed_at is not None and t >= float(removed_at):
            continue
        side = str(track.get("team_side") or "unknown")
        visible = _squadron_visible_at(track, t)
        if side == "enemy" and not visible:
            times = track.get("times", [])
            if not times:
                continue
            last_t = float(times[-1])
            if (t - last_t) > 2.5:
                continue
        pos = _squadron_position_at(track, t)
        if pos is None:
            continue
        x, z = pos
        px, py = _to_px(x, z, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        if side == "friendly":
            color = COLOR_FRIENDLY
        elif side == "enemy":
            color = COLOR_ENEMY
        else:
            color = COLOR_UNKNOWN
        stype = str(track.get("type") or track.get("mapped_type") or "main").strip().lower()
        # Keep squadron icons locked (no rotation).
        heading_bucket = 0
        shadow = _squadron_icon_image(stype, (0, 0, 0), icon_size + 2, heading_bucket, bucket_deg=6.0)
        icon = _squadron_icon_image(stype, color, icon_size, heading_bucket, bucket_deg=6.0)
        if shadow is not None:
            shadow = shadow.copy()
            shadow.putalpha(shadow.getchannel("A").point(lambda a: min(120, int(a * 0.55))))
            img.paste(shadow, (px - shadow.width // 2 + 1, py - shadow.height // 2 + 1), shadow)
        if icon is not None:
            img.paste(icon, (px - icon.width // 2, py - icon.height // 2), icon)
        else:
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=color, outline=(20, 20, 20))

        if os.environ.get("RENDER_AIRCRAFT_DEBUG") == "1":
            pid = _safe_int(track.get("params_id"))
            label = stype[:4] if stype else "unk"
            if pid is not None:
                label = f"{label}:{str(pid)[-4:]}"
            sprite = _text_sprite(label, max(9, icon_size // 2), WOWS_TEXT_SUB, shadow=(0, 0, 0))
            if sprite is not None:
                img.paste(sprite, (px + icon_size // 2 + 2, py - sprite.height // 2), sprite)


def _draw_artillery_traces(
    img: Image.Image,
    traces: List[Dict[str, Any]],
    t: float,
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> None:
    if not traces:
        return
    draw_rgba = ImageDraw.Draw(img, "RGBA")
    for trace in traces:
        t0 = float(trace.get("time_s", 0.0))
        t1 = float(trace.get("time_end_s", t0))
        if t < t0 or t > t1:
            continue
        span = max(0.1, t1 - t0)
        progress = min(1.0, max(0.0, (t - t0) / span))
        x0 = float(trace.get("x0", 0.0))
        z0 = float(trace.get("z0", 0.0))
        x1 = float(trace.get("x1", 0.0))
        z1 = float(trace.get("z1", 0.0))
        xp = x0 + (x1 - x0) * progress
        zp = z0 + (z1 - z0) * progress

        dx = x1 - x0
        dz = z1 - z0
        dist = math.hypot(dx, dz)
        if dist < 1e-6:
            continue
        ux = dx / dist
        uz = dz / dist
        seg_world = max(10.0, min(55.0, dist * 0.05))
        hx = ux * (seg_world * 0.5)
        hz = uz * (seg_world * 0.5)
        sx, sy = _to_px(xp - hx, zp - hz, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        ex, ey = _to_px(xp + hx, zp + hz, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        alpha = int(160 + 60 * (1.0 - progress))
        shell_kind = str(trace.get("shell_kind") or "").strip().lower()
        if shell_kind == "he":
            color = (255, 238, 170, alpha)
        elif shell_kind == "cs":
            color = (255, 224, 160, alpha)
        else:
            color = (245, 245, 245, alpha)
        draw_rgba.line([(sx, sy), (ex, ey)], fill=color, width=2)


def _entity_name_for_feed(canonical: Dict[str, Any], entity_key: str) -> str:
    key = str(entity_key or "-1")
    if key in ("", "-1"):
        return "Environment"
    entities = canonical.get("entities", {}) or {}
    entity = entities.get(key, {}) if isinstance(entities, dict) else {}
    name = str(entity.get("player_name") or "").strip()
    if name:
        return name
    return f"entity_{key}"


def _kill_panel_style(entry: Dict[str, Any]) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    shell_kind = str(entry.get("shell_kind") or "").strip().lower()
    weapon_kind = str(entry.get("weapon_kind") or "other")
    if shell_kind == "ap":
        return (245, 245, 245), (20, 20, 20)
    if shell_kind == "he":
        return (255, 238, 170), (30, 30, 30)
    if shell_kind == "cs":
        return (255, 224, 160), (40, 35, 20)
    if weapon_kind == "torpedo":
        return (255, 84, 84), (255, 255, 255)
    if weapon_kind == "bomb":
        return (255, 185, 120), (30, 30, 30)
    return (150, 150, 150), (255, 255, 255)


def _kill_icon_filename(entry: Dict[str, Any]) -> str:
    reason_code = _safe_int(entry.get("reason_code"))
    if reason_code in (1, 16, 17, 18, 19):
        return "icon_frag_main_caliber.png"
    if reason_code == 2:
        return "icon_frag_atba.png"
    if reason_code in (3, 5, 11, 13):
        return "icon_frag_torpedo.png"
    if reason_code in (4, 28):
        return "icon_frag_bomb.png"
    if reason_code == 6:
        return "icon_frag_burning.png"
    if reason_code == 9:
        return "icon_frag_flood.png"
    if reason_code == 14:
        return "icon_frag_rocket.png"
    if reason_code == 22:
        return "icon_frag_skip.png"

    weapon_kind = str(entry.get("weapon_kind") or "other")
    if weapon_kind == "gun":
        return "icon_frag_main_caliber.png"
    if weapon_kind == "torpedo":
        return "icon_frag_torpedo.png"
    if weapon_kind == "bomb":
        return "icon_frag_bomb.png"
    return "frags.png"


@lru_cache(maxsize=64)
def _load_kill_icon(filename: str, size: int) -> Image.Image | None:
    candidates = [
        _battle_hud_dir() / "icon_frag" / filename,
        _kill_icon_cache_dir() / filename,
    ]
    for file_path in candidates:
        if not file_path.exists():
            continue
        try:
            icon = Image.open(file_path).convert("RGBA")
        except Exception:
            continue
        if size > 0 and icon.size != (size, size):
            icon = icon.resize((size, size), Image.Resampling.LANCZOS)
        return icon
    return None


def _draw_kill_feed_panel(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    canonical: Dict[str, Any],
    render_tracks: Dict[str, Dict[str, Any]],
    kill_feed: List[Dict[str, Any]],
    t: float,
    layout: Dict[str, Any],
) -> None:
    feed_stroke = 2
    chat_feed = _extract_chat_feed(canonical)
    entity_sides = {str(key): str(track.get("team_side") or "unknown") for key, track in render_tracks.items()}
    canonical_entities = canonical.get("entities", {}) or {}
    if isinstance(canonical_entities, dict):
        for key, row in canonical_entities.items():
            if not isinstance(row, dict):
                continue
            team = str(row.get("team") or "unknown")
            if team == "player":
                team = "friendly"
            elif team == "ally":
                team = "friendly"
            elif team == "enemy":
                team = "enemy"
            entity_sides.setdefault(str(key), team)
    rows: List[Dict[str, Any]] = []
    for row in kill_feed:
        if float(row.get("time_s", 0.0)) <= t + 1e-6:
            rows.append({"type": "kill", **row})
    for row in chat_feed:
        if float(row.get("time_s", 0.0)) <= t + 1e-6:
            rows.append({"type": "chat", **row})
    if not rows:
        return

    map_size = int(layout.get("map_size", 600))
    font_size = max(10, int(layout.get("font_size", 10)))
    time_font_size = max(9, font_size - 1)
    icon_size = max(14, map_size // 42)
    line_h = max(19, max(icon_size + 5, font_size + 10))
    panel_rect = tuple(layout.get("feed_rect", (0, 0, 0, 0)))
    panel_x = int(panel_rect[0])
    panel_y = int(panel_rect[1])
    col_w = max(100, int(panel_rect[2]) - int(panel_rect[0]))
    panel_h_max = max(60, int(panel_rect[3]) - int(panel_rect[1]))
    top_pad = 8
    available_rows = max(1, min(14, (panel_h_max - (top_pad + 8)) // line_h))
    rows.sort(key=lambda item: (float(item.get("time_s", 0.0)), 0 if str(item.get("type")) == "kill" else 1))
    visible = rows[-available_rows:]
    panel_h = min(panel_h_max, top_pad + len(visible) * line_h + 8)

    draw_rgba = ImageDraw.Draw(img, "RGBA")
    draw_rgba.rounded_rectangle(
        [panel_x, panel_y, panel_x + col_w, panel_y + panel_h],
        radius=8,
        fill=(7, 10, 14, 170),
        outline=(124, 132, 144, 220),
        width=1,
    )

    y = panel_y + top_pad
    for entry in reversed(visible):
        mins, secs = divmod(int(float(entry.get("time_s", 0.0))), 60)
        stamp = f"{mins}:{secs:02d}"
        stamp_sprite = _text_sprite(stamp, time_font_size + 1, WOWS_TEXT_SUB, shadow=(0, 0, 0), bold=True, stroke_width=feed_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
        _paste_sprite(img, stamp_sprite, panel_x + 6, y + 1)

        tx = panel_x + 6 + (stamp_sprite.width if stamp_sprite is not None else 0) + 10
        if str(entry.get("type")) == "chat":
            sender_raw = str(entry.get("sender") or "").strip()
            sender = _marker_name_text(sender_raw, max_len=14)
            sender_side = _player_team_side(render_tracks, sender_raw)
            sender_sprite = _text_sprite(sender or "chat", font_size + 1, _feed_name_color(sender_side), shadow=(0, 0, 0), bold=True, stroke_width=feed_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
            _paste_sprite(img, sender_sprite, tx, y)
            msg_x = tx + (sender_sprite.width if sender_sprite is not None else 0) + 6
            message = str(entry.get("message") or "").strip()
            if len(message) > 34:
                message = message[:33] + "~"
            msg_sprite = _text_sprite(f": {message}", time_font_size + 1, WOWS_TEXT, shadow=(0, 0, 0), bold=True, stroke_width=feed_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
            _paste_sprite(img, msg_sprite, msg_x, y + 1)
        else:
            killer = _entity_name_for_feed(canonical, str(entry.get("killer_entity_key") or "-1"))
            victim = _entity_name_for_feed(canonical, str(entry.get("victim_entity_key") or "-1"))
            killer = _marker_name_text(killer, max_len=13)
            victim = _marker_name_text(victim, max_len=13)
            weapon_label = str(entry.get("weapon_label") or "KILL")
            pill_fill, pill_text = _kill_panel_style(entry)
            killer_side = entity_sides.get(str(entry.get("killer_entity_key") or "-1"), _player_team_side(render_tracks, killer))
            victim_side = entity_sides.get(str(entry.get("victim_entity_key") or "-1"), _player_team_side(render_tracks, victim))

            killer_sprite = _text_sprite(killer, font_size + 1, _feed_name_color(killer_side), shadow=(0, 0, 0), bold=True, stroke_width=feed_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
            _paste_sprite(img, killer_sprite, tx, y)
            icon_x = tx + (killer_sprite.width if killer_sprite is not None else 0) + 6
            icon_y = y - 1
            icon = _load_kill_icon(_kill_icon_filename(entry), icon_size)
            if icon is not None:
                img.paste(icon, (icon_x, icon_y), icon)
                victim_x = icon_x + icon_size + 6
            else:
                pill_sprite = _text_sprite(weapon_label, time_font_size + 1, pill_text, bold=True, stroke_width=feed_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
                pill_w = (pill_sprite.width if pill_sprite is not None else 0) + 8
                draw.rectangle([icon_x, y, icon_x + pill_w, y + 11], fill=pill_fill, outline=(20, 20, 20))
                _paste_sprite(img, pill_sprite, icon_x + 4, y + 1)
                victim_x = icon_x + pill_w + 6
            victim_sprite = _text_sprite(victim, font_size + 1, _feed_name_color(victim_side), shadow=(0, 0, 0), bold=True, stroke_width=feed_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
            _paste_sprite(img, victim_sprite, victim_x, y)
        y += line_h


def _fit_linear_axis(samples: List[Tuple[float, float]]) -> Tuple[float, float, float] | None:
    if len(samples) < 2:
        return None
    xs = [float(x) for x, _ in samples]
    ys = [float(y) for _, y in samples]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 1e-9:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    rmse = math.sqrt(sum(((slope * x + intercept) - y) ** 2 for x, y in zip(xs, ys)) / len(xs))
    return (float(slope), float(intercept), float(rmse))


def _unwrap_minimap_axis(values: List[int]) -> Tuple[int | None, List[int]]:
    ordered = sorted(int(v) for v in values)
    if len(ordered) < 2:
        return None, ordered
    best_gap = -1
    threshold = None
    for left, right in zip(ordered, ordered[1:]):
        gap = int(right) - int(left)
        if gap > best_gap:
            best_gap = gap
            threshold = int((int(left) + int(right)) / 2)
    if threshold is None or best_gap < 200:
        return None, ordered
    adjusted = [int(v) + 1024 if int(v) < threshold else int(v) for v in values]
    return threshold, adjusted


def _minimap_vision_decode_model(
    canonical: Dict[str, Any],
    normalized: Dict[str, Dict[str, Any]],
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], int | None] | None:
    meta = canonical.get("meta", {}) or {}
    raw = meta.get("minimap_vision_initial", {})
    if not isinstance(raw, dict):
        return None
    entries_raw = raw.get("entries", [])
    if not isinstance(entries_raw, list):
        return None

    parsed: List[Tuple[str, int, int]] = []
    for row in entries_raw:
        if not isinstance(row, dict):
            continue
        entity_id = _safe_int(row.get("entity_id"))
        packed_data = _safe_int(row.get("packed_data"))
        if entity_id is None or packed_data is None:
            continue
        px = int(packed_data) & 0x3FF
        pz = (int(packed_data) >> 10) & 0x3FF
        parsed.append((str(entity_id), px, pz))
    if not parsed:
        return None

    x_threshold, _ = _unwrap_minimap_axis([px for _, px, _ in parsed])

    x_samples: List[Tuple[float, float]] = []
    z_samples: List[Tuple[float, float]] = []
    for entity_key, px, pz in parsed:
        item = normalized.get(entity_key)
        if not isinstance(item, dict):
            continue
        if str(item.get("team_side") or "") != "friendly":
            continue
        if bool(item.get("always_unspotted", False)):
            continue
        points = list(item.get("points", []) or [])
        if not points:
            continue
        first = points[0] or {}
        first_t = float(first.get("t", 0.0) or 0.0)
        if first_t > 5.0:
            continue
        px_value = int(px) + 1024 if x_threshold is not None and int(px) < int(x_threshold) else int(px)
        x_samples.append((float(px_value), float(first.get("x", 0.0) or 0.0)))
        z_samples.append((float(pz), float(first.get("z", 0.0) or 0.0)))

    fit_x = _fit_linear_axis(x_samples)
    fit_z = _fit_linear_axis(z_samples)
    if fit_x is None or fit_z is None:
        return None
    if fit_x[2] > 12.0 or fit_z[2] > 12.0:
        return None
    return fit_x, fit_z, x_threshold


def _decode_minimap_vision_entries(
    entries_raw: Any,
    decode_model: Tuple[Tuple[float, float, float], Tuple[float, float, float], int | None] | None,
) -> Dict[str, Dict[str, float]]:
    if decode_model is None or not isinstance(entries_raw, list):
        return {}
    fit_x, fit_z, x_threshold = decode_model

    placeholders: Dict[str, Dict[str, float]] = {}
    for row in entries_raw:
        if not isinstance(row, dict):
            continue
        entity_id = _safe_int(row.get("entity_id"))
        packed_data = _safe_int(row.get("packed_data"))
        if entity_id is None or packed_data is None:
            continue
        px = int(packed_data) & 0x3FF
        pz = (int(packed_data) >> 10) & 0x3FF
        px_value = int(px) + 1024 if x_threshold is not None and int(px) < int(x_threshold) else int(px)
        placeholders[str(entity_id)] = {
            "x": round(float(fit_x[0] * float(px_value) + fit_x[1]), 3),
            "z": round(float(fit_z[0] * float(pz) + fit_z[1]), 3),
            "yaw": 0.0,
        }
    return placeholders


def _minimap_vision_start_placeholders(canonical: Dict[str, Any], normalized: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    meta = canonical.get("meta", {}) or {}
    raw = meta.get("minimap_vision_initial", {})
    if not isinstance(raw, dict):
        return {}
    decode_model = _minimap_vision_decode_model(canonical, normalized)
    return _decode_minimap_vision_entries(raw.get("entries", []), decode_model)


def _minimap_vision_tracks(canonical: Dict[str, Any], normalized: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, float]]]:
    meta = canonical.get("meta", {}) or {}
    raw_timeline = meta.get("minimap_vision_timeline", [])
    if not isinstance(raw_timeline, list) or not raw_timeline:
        return {}
    decode_model = _minimap_vision_decode_model(canonical, normalized)
    if decode_model is None:
        return {}
    world_bounds = _world_bounds(canonical)

    per_entity: Dict[str, List[Dict[str, float]]] = {}
    for snapshot in raw_timeline:
        if not isinstance(snapshot, dict):
            continue
        t = float(snapshot.get("time_s", 0.0) or 0.0)
        decoded = _decode_minimap_vision_entries(snapshot.get("entries", []), decode_model)
        for entity_key, row in decoded.items():
            per_entity.setdefault(str(entity_key), []).append(
                {
                    "t": round(t, 3),
                    "x": float(row.get("x", 0.0) or 0.0),
                    "z": float(row.get("z", 0.0) or 0.0),
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "roll": 0.0,
                    "y": 0.0,
                }
            )

    fit_x, fit_z, _x_threshold = decode_model
    wrap_x = abs(float(fit_x[0])) * 1024.0
    wrap_z = abs(float(fit_z[0])) * 1024.0
    for entity_key, points in per_entity.items():
        points.sort(key=lambda item: float(item.get("t", 0.0)))
        _unwrap_vision_points_continuity(points, wrap_x, wrap_z)
        per_entity[entity_key] = _sanitize_minimap_vision_points(points, world_bounds=world_bounds)
    return per_entity


def _unwrap_vision_points_continuity(
    points: List[Dict[str, float]],
    wrap_x: float,
    wrap_z: float,
) -> List[Dict[str, float]]:
    # The 10-bit packed minimap axes wrap at 1024 levels. When a ship crosses a
    # packing boundary the decoded coordinate jumps by ~one full map span, which
    # would otherwise be discarded as out-of-bounds and truncate the track. Undo
    # those wraps by keeping each point continuous with the previous one.
    if len(points) < 2:
        return points
    prev_x = float(points[0].get("x", 0.0) or 0.0)
    prev_z = float(points[0].get("z", 0.0) or 0.0)
    for p in points[1:]:
        x = float(p.get("x", 0.0) or 0.0)
        z = float(p.get("z", 0.0) or 0.0)
        if wrap_x > 1.0:
            while x - prev_x > wrap_x / 2.0:
                x -= wrap_x
            while x - prev_x < -wrap_x / 2.0:
                x += wrap_x
        if wrap_z > 1.0:
            while z - prev_z > wrap_z / 2.0:
                z -= wrap_z
            while z - prev_z < -wrap_z / 2.0:
                z += wrap_z
        p["x"] = round(x, 3)
        p["z"] = round(z, 3)
        prev_x = x
        prev_z = z
    return points


def _sanitize_minimap_vision_points(
    points: List[Dict[str, float]],
    world_bounds: Tuple[float, float, float, float] | None = None,
) -> List[Dict[str, float]]:
    if len(points) <= 1:
        return points

    min_x = max_x = min_z = max_z = None
    if world_bounds is not None and len(world_bounds) == 4:
        min_x, max_x, min_z, max_z = [float(v) for v in world_bounds]

    cleaned: List[Dict[str, float]] = [points[0]]
    prev = points[0]
    for point in points[1:]:
        x = float(point.get("x", 0.0) or 0.0)
        z = float(point.get("z", 0.0) or 0.0)
        if min_x is not None and max_x is not None and min_z is not None and max_z is not None:
            margin = 80.0
            if x < (min_x - margin) or x > (max_x + margin) or z < (min_z - margin) or z > (max_z + margin):
                continue
        dt = max(1e-6, float(point.get("t", 0.0) or 0.0) - float(prev.get("t", 0.0) or 0.0))
        dx = x - float(prev.get("x", 0.0) or 0.0)
        dz = z - float(prev.get("z", 0.0) or 0.0)
        dist = math.hypot(dx, dz)
        # Minimap-vision-only updates can occasionally teleport to a bad packed
        # position. Keep realistic movement and discard impossible jumps.
        max_dist = max(70.0, dt * 42.0 + 60.0)
        if dist > max_dist:
            continue
        cleaned.append(point)
        prev = point
    return cleaned


def _merge_friendly_track_with_vision(
    points: List[Dict[str, Any]],
    vision_points: List[Dict[str, float]],
    fallback_yaw: float,
    max_nearby_s: float = 1.5,
) -> List[Dict[str, Any]]:
    if not points:
        return vision_points
    if not vision_points:
        return points

    merged: List[Dict[str, Any]] = [dict(p) for p in points]
    merged.sort(key=lambda item: float(item.get("t", 0.0)))
    merged_times = [float(p.get("t", 0.0)) for p in merged]

    for vision_point in vision_points:
        vt = float(vision_point.get("t", 0.0) or 0.0)
        insert_at = bisect_right(merged_times, vt)
        nearest = float("inf")
        if insert_at > 0:
            nearest = min(nearest, abs(vt - merged_times[insert_at - 1]))
        if insert_at < len(merged_times):
            nearest = min(nearest, abs(merged_times[insert_at] - vt))
        if nearest <= max_nearby_s:
            continue

        source_yaw = float(fallback_yaw)
        if insert_at > 0:
            source_yaw = float(merged[insert_at - 1].get("yaw", source_yaw) or source_yaw)
        elif merged:
            source_yaw = float(merged[0].get("yaw", source_yaw) or source_yaw)

        new_point = {
            "t": round(vt, 3),
            "x": float(vision_point.get("x", 0.0) or 0.0),
            "y": 0.0,
            "z": float(vision_point.get("z", 0.0) or 0.0),
            "yaw": float(source_yaw),
            "pitch": 0.0,
            "roll": 0.0,
            "vision": True,
        }
        merged.insert(insert_at, new_point)
        merged_times.insert(insert_at, float(new_point["t"]))

    deduped: List[Dict[str, Any]] = []
    last_key: Tuple[float, float, float] | None = None
    for row in merged:
        key = (
            round(float(row.get("t", 0.0)), 3),
            round(float(row.get("x", 0.0)), 2),
            round(float(row.get("z", 0.0)), 2),
        )
        if key == last_key:
            continue
        deduped.append(row)
        last_key = key
    return deduped


def _maybe_write_track_debug(render_tracks: Dict[str, Dict[str, Any]]) -> None:
    raw = str(os.environ.get("RENDER_TRACK_DEBUG") or "").strip()
    if not raw:
        return
    filters = {token.strip().lower() for token in raw.split(",") if token.strip()}
    if not filters:
        return

    payload: Dict[str, Any] = {}
    for entity_key, track in render_tracks.items():
        if not isinstance(track, dict):
            continue
        player_name = str(track.get("player_name") or "").strip()
        ship_id = str(_safe_int(track.get("ship_id")) or "")
        entity_id = str(track.get("entity_id") or entity_key)
        ship_name = _ship_name(track.get("ship_id"))
        candidates = {
            str(entity_key).lower(),
            entity_id.lower(),
            player_name.lower(),
            ship_name.lower(),
            ship_id.lower(),
        }
        if filters.isdisjoint({c for c in candidates if c}):
            continue
        payload[str(entity_key)] = {
            "entity_id": entity_id,
            "player_name": player_name,
            "ship_name": ship_name,
            "ship_id": ship_id,
            "team_side": str(track.get("team_side") or ""),
            "always_unspotted": bool(track.get("always_unspotted", False)),
            "first_real_t": float(track.get("first_real_t", 0.0) or 0.0),
            "start_placeholder": track.get("start_placeholder"),
            "late_start_placeholder": track.get("late_start_placeholder"),
            "points": list(track.get("points", []) or []),
        }

    if not payload:
        return
    try:
        out_path = _root_dir() / "content" / "track_debug.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _heading_debug_filters() -> set[str]:
    raw = str(os.environ.get("RENDER_HEADING_DEBUG") or "").strip()
    if not raw:
        return set()
    return {token.strip().lower() for token in raw.split(",") if token.strip()}


def _heading_debug_match(entity_key: Any, track: Dict[str, Any], filters: set[str]) -> bool:
    if not filters or not isinstance(track, dict):
        return False
    player_name = str(track.get("player_name") or "").strip()
    ship_id = str(_safe_int(track.get("ship_id")) or "")
    entity_id = str(track.get("entity_id") or entity_key)
    ship_name = _ship_name(track.get("ship_id"))
    candidates = {
        str(entity_key).lower(),
        entity_id.lower(),
        player_name.lower(),
        ship_name.lower(),
        ship_id.lower(),
    }
    return not filters.isdisjoint({c for c in candidates if c})


def _write_heading_debug(samples: List[Dict[str, Any]]) -> None:
    if not samples:
        return
    try:
        out_path = _root_dir() / "content" / "heading_debug.json"
        out_path.write_text(json.dumps(samples, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _normalize_render_tracks(canonical: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    tracks = canonical.get("tracks", {}) or {}
    entities = canonical.get("entities", {}) or {}
    meta_vehicles = canonical.get("meta", {}).get("vehicles", []) or []

    # Build immutable lineup from replay roster.
    lineup: List[Dict[str, Any]] = []
    for idx, v in enumerate(meta_vehicles):
        relation = int(v.get("relation", 2) if v.get("relation") is not None else 2)
        team_side = "enemy" if relation == 2 else "friendly"
        account_id = str(v.get("id", "")).strip()
        name = str(v.get("name", "")).strip()
        ship_id = v.get("shipId")
        lineup.append(
            {
                "slot_id": idx,
                "team_side": team_side,
                "relation": relation,
                "account_id": account_id,
                "name": name,
                "name_norm": _norm_name(name),
                "ship_id": ship_id,
                "used": False,
            }
        )

    # Assign stable lineup numbers from replay roster:
    # friendly team gets 1..N, enemy team gets N+1..N+M (globally unique).
    friendly_slots = [s for s in lineup if s["team_side"] == "friendly"]
    enemy_slots = [s for s in lineup if s["team_side"] == "enemy"]
    friendly_slots.sort(key=lambda s: s["slot_id"])
    enemy_slots.sort(key=lambda s: s["slot_id"])

    for i, slot in enumerate(friendly_slots, start=1):
        slot["team_number_local"] = i
        slot["team_number"] = i

    offset = len(friendly_slots)
    for i, slot in enumerate(enemy_slots, start=1):
        slot["team_number_local"] = i
        slot["team_number"] = offset + i

    for slot in lineup:
        if "team_number" not in slot:
            slot["team_number_local"] = None
            slot["team_number"] = None

    lineup_by_account: Dict[str, Dict[str, Any]] = {s["account_id"]: s for s in lineup if s["account_id"]}
    lineup_by_name: Dict[str, List[Dict[str, Any]]] = {}
    lineup_by_ship: Dict[str, List[Dict[str, Any]]] = {}
    for slot in lineup:
        if slot["name_norm"]:
            lineup_by_name.setdefault(slot["name_norm"], []).append(slot)
        if slot["ship_id"] is not None:
            lineup_by_ship.setdefault(str(slot["ship_id"]), []).append(slot)
    for slots in lineup_by_name.values():
        slots.sort(key=lambda s: (s["used"], 0 if s["relation"] == 0 else 1))
    for slots in lineup_by_ship.values():
        slots.sort(key=lambda s: (s["used"], 0 if s["relation"] == 0 else 1))

    normalized: Dict[str, Dict[str, Any]] = {}
    friendly_starts: List[Tuple[float, float]] = []
    enemy_starts: List[Tuple[float, float]] = []
    unresolved: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]], str, str, str]] = []

    for entity_key, track in tracks.items():
        points = list(track.get("points", []) or [])
        if not points:
            continue
        player_name = str(track.get("player_name") or f"entity_{entity_key}")
        clan_tag = str(track.get("clan_tag") or "").strip()
        name_norm = _norm_name(player_name)
        entity_meta = entities.get(str(entity_key), {}) or {}
        team_hint = _team_side(track.get("team") or entity_meta.get("team"))
        account_entity_id = entity_meta.get("account_entity_id")
        account_id = str(account_entity_id) if account_entity_id is not None else ""

        slot = None
        if account_id:
            maybe = lineup_by_account.get(account_id)
            if maybe and (not maybe["used"]) and (team_hint == "unknown" or maybe.get("team_side") == team_hint):
                slot = maybe
        if slot is None and name_norm:
            by_name = [
                s
                for s in lineup_by_name.get(name_norm, [])
                if (not s["used"]) and (team_hint == "unknown" or s.get("team_side") == team_hint)
            ]
            if len(by_name) == 1:
                slot = by_name[0]
        if slot is None:
            ship_id = track.get("ship_id")
            if ship_id is not None:
                by_ship = [
                    s
                    for s in lineup_by_ship.get(str(ship_id), [])
                    if (not s["used"]) and (team_hint == "unknown" or s.get("team_side") == team_hint)
                ]
                if len(by_ship) == 1:
                    slot = by_ship[0]

        if slot:
            slot["used"] = True
            team_side = team_hint if team_hint in ("friendly", "enemy") else slot["team_side"]
            ship_id = slot.get("ship_id", track.get("ship_id"))
            account_resolved = slot.get("account_id") or account_id or None
            label_name = slot.get("name") or player_name
            team_number = slot.get("team_number")
            team_number_local = slot.get("team_number_local")
        else:
            team_side = team_hint if team_hint in ("friendly", "enemy") else "unknown"
            ship_id = track.get("ship_id")
            account_resolved = account_id or None
            label_name = player_name
            team_number = None
            team_number_local = None

        first = points[0]
        start = (float(first.get("x", 0.0)), float(first.get("z", 0.0)))
        if team_side == "friendly":
            friendly_starts.append(start)
        elif team_side == "enemy":
            enemy_starts.append(start)
        if slot is None:
            unresolved.append((str(entity_key), track, points, player_name, account_id, team_hint))

        normalized[str(entity_key)] = {
            "entity_id": track.get("entity_id", entity_key),
            "player_name": label_name,
            "clan_tag": clan_tag,
            "ship_id": ship_id,
            "team_side": team_side,
            "team_label_side": team_hint,
            "team_number": team_number,
            "team_number_local": team_number_local,
            "account_entity_id": account_resolved,
            "points": points,
            "first_real_t": float(first.get("t", 0.0) or 0.0),
            "always_unspotted": False,
        }

    def _avg(points: List[Tuple[float, float]], default_x: float, default_z: float) -> Tuple[float, float]:
        if not points:
            return default_x, default_z
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )

    half = _world_half(canonical)
    friendly_center = _avg(friendly_starts, -half * 0.55, 0.0)
    enemy_center = _avg(enemy_starts, half * 0.55, 0.0)

    # Resolve unmatched tracks by positional fallback onto remaining lineup slots.
    def _choose_slot(side: str, ship_id_value: Any) -> Dict[str, Any] | None:
        candidates = [s for s in lineup if (not s["used"]) and s["team_side"] == side]
        if not candidates:
            return None
        if ship_id_value is not None:
            exact = [s for s in candidates if str(s.get("ship_id")) == str(ship_id_value)]
            if len(exact) == 1:
                return exact[0]
        return candidates[0]

    if unresolved:
        half = _world_half(canonical)
        friendly_center = (
            sum(p[0] for p in friendly_starts) / len(friendly_starts) if friendly_starts else -half * 0.55,
            sum(p[1] for p in friendly_starts) / len(friendly_starts) if friendly_starts else 0.0,
        )
        enemy_center = (
            sum(p[0] for p in enemy_starts) / len(enemy_starts) if enemy_starts else half * 0.55,
            sum(p[1] for p in enemy_starts) / len(enemy_starts) if enemy_starts else 0.0,
        )

        for ek, raw_track, pts, raw_name, raw_acc, team_hint in unresolved:
            if not pts:
                continue
            x0 = float(pts[0].get("x", 0.0))
            z0 = float(pts[0].get("z", 0.0))
            if team_hint in ("friendly", "enemy"):
                guessed_side = team_hint
            else:
                d_f = math.hypot(x0 - friendly_center[0], z0 - friendly_center[1])
                d_e = math.hypot(x0 - enemy_center[0], z0 - enemy_center[1])
                guessed_side = "friendly" if d_f <= d_e else "enemy"
            chosen = _choose_slot(guessed_side, raw_track.get("ship_id"))
            if chosen is None:
                # Last resort: any side with remaining slot.
                chosen = _choose_slot("friendly", raw_track.get("ship_id")) or _choose_slot("enemy", raw_track.get("ship_id"))
            if chosen is None:
                # No lineup slots left; keep unknown as friendly by default to avoid random red/green mixes.
                if guessed_side not in ("friendly", "enemy"):
                    guessed_side = "friendly"
                chosen_name = raw_name
                chosen_ship_id = raw_track.get("ship_id")
                chosen_account = raw_acc or None
            else:
                chosen["used"] = True
                if team_hint in ("friendly", "enemy"):
                    guessed_side = team_hint
                else:
                    guessed_side = chosen["team_side"]
                chosen_name = chosen.get("name") or raw_name
                chosen_ship_id = chosen.get("ship_id", raw_track.get("ship_id"))
                chosen_account = chosen.get("account_id") or raw_acc or None

            normalized[ek]["team_side"] = guessed_side
            normalized[ek]["player_name"] = chosen_name
            normalized[ek]["ship_id"] = chosen_ship_id
            normalized[ek]["account_entity_id"] = chosen_account
            normalized[ek]["team_number"] = chosen.get("team_number") if chosen is not None else None
            normalized[ek]["team_number_local"] = chosen.get("team_number_local") if chosen is not None else None

    def _mean_start_yaw(side: str, default_yaw: float) -> float:
        vals: List[float] = []
        for item in normalized.values():
            if str(item.get("team_side") or "") != side:
                continue
            if bool(item.get("always_unspotted", False)):
                continue
            points = list(item.get("points", []) or [])
            if not points:
                continue
            first = points[0] or {}
            vals.append(float(first.get("yaw", default_yaw) or default_yaw))
        if not vals:
            return float(default_yaw)
        s = sum(math.sin(v) for v in vals)
        c = sum(math.cos(v) for v in vals)
        if abs(s) < 1e-9 and abs(c) < 1e-9:
            return float(default_yaw)
        return math.atan2(s, c)

    friendly_spawn_yaw = _mean_start_yaw("friendly", math.pi)
    enemy_spawn_yaw = _mean_start_yaw("enemy", 0.0)

    vision_placeholders = _minimap_vision_start_placeholders(canonical, normalized)
    vision_tracks = _minimap_vision_tracks(canonical, normalized)
    for entity_key, placeholder in vision_placeholders.items():
        if entity_key not in normalized:
            continue
        side = str(normalized[entity_key].get("team_side") or "unknown")
        yaw = friendly_spawn_yaw if side == "friendly" else enemy_spawn_yaw
        normalized[entity_key]["start_placeholder"] = {
            "x": float(placeholder.get("x", 0.0) or 0.0),
            "z": float(placeholder.get("z", 0.0) or 0.0),
            "yaw": float(yaw),
        }

    # Keep real ship tracks packet-accurate during spotting. For allies, fill the
    # gaps after a ship leaves spotting range with decoded minimap-vision points
    # so friendly ships keep moving on the render exactly like the in-game minimap
    # (they stay visible instead of vanishing). Vision-filled points are tagged so
    # the renderer can show them as a faded "last-known" marker rather than a solid
    # actively-spotted icon. Real spotted segments are left untouched.
    for entity_key, item in normalized.items():
        if str(item.get("team_side") or "") != "friendly":
            continue
        if bool(item.get("always_unspotted", False)):
            continue
        real_points = list(item.get("points", []) or [])
        if not real_points:
            continue
        vpoints = list(vision_tracks.get(str(entity_key), []) or [])
        if not vpoints:
            continue
        fallback_yaw = float(real_points[0].get("yaw", friendly_spawn_yaw) or friendly_spawn_yaw)
        merged_points = _merge_friendly_track_with_vision(real_points, vpoints, fallback_yaw)
        if len(merged_points) > len(real_points):
            item["points"] = merged_points
            item["has_minimap_vision"] = True

    def _find_lineup_slot_for_entity(entity_row: Dict[str, Any]) -> Dict[str, Any] | None:
        account_id = str(entity_row.get("account_entity_id") or "").strip()
        player_name = str(entity_row.get("player_name") or "").strip().lower()
        ship_id_value = _safe_int(entity_row.get("ship_id"))
        candidates = [slot for slot in lineup if (not slot["used"]) and slot.get("team_side") == "friendly"]
        if account_id:
            exact = [slot for slot in candidates if str(slot.get("account_id") or "").strip() == account_id]
            if len(exact) == 1:
                return exact[0]
        if player_name:
            exact = [slot for slot in candidates if str(slot.get("name") or "").strip().lower() == player_name]
            if len(exact) == 1:
                return exact[0]
        if ship_id_value is not None:
            exact = [slot for slot in candidates if _safe_int(slot.get("ship_id")) == ship_id_value]
            if len(exact) == 1:
                return exact[0]
        return None

    for entity_key, entity_row in entities.items():
        key = str(entity_key)
        if key in normalized:
            continue
        placeholder = vision_placeholders.get(key)
        if not isinstance(placeholder, dict):
            continue
        team_raw = str(entity_row.get("team") or "").strip().lower()
        if team_raw not in ("ally", "friendly"):
            continue
        slot = _find_lineup_slot_for_entity(entity_row if isinstance(entity_row, dict) else {})
        if slot is not None:
            slot["used"] = True
        account_id = str(entity_row.get("account_entity_id") or "").strip()
        player_name = str(entity_row.get("player_name") or "").strip()
        ship_id_value = _safe_int(entity_row.get("ship_id"))
        normalized[key] = {
            "entity_id": _safe_int(entity_row.get("entity_id")) or key,
            "player_name": (slot.get("name") if slot is not None else "") or player_name or f"entity_{key}",
            "ship_id": (slot.get("ship_id") if slot is not None else None) or ship_id_value,
            "team_side": "friendly",
            "team_label_side": "friendly",
            "team_number": slot.get("team_number") if slot is not None else None,
            "team_number_local": slot.get("team_number_local") if slot is not None else None,
            "account_entity_id": (slot.get("account_id") if slot is not None else "") or account_id or None,
            "points": [],
            "first_real_t": 0.0,
            "always_unspotted": True,
            "start_placeholder": {
                "x": float(placeholder.get("x", 0.0) or 0.0),
                "z": float(placeholder.get("z", 0.0) or 0.0),
                "yaw": float(friendly_spawn_yaw),
            },
        }
        vision_points = list(vision_tracks.get(key, []) or [])
        if vision_points:
            for point in vision_points:
                point["yaw"] = float(friendly_spawn_yaw)
                point["vision"] = True
            normalized[key]["points"] = vision_points
            normalized[key]["has_minimap_vision"] = True
        else:
            normalized[key]["points"] = [
                {
                    "t": 0.0,
                    "x": float(placeholder.get("x", 0.0) or 0.0),
                    "y": 0.0,
                    "z": float(placeholder.get("z", 0.0) or 0.0),
                    "yaw": float(friendly_spawn_yaw),
                    "pitch": 0.0,
                    "roll": 0.0,
                }
            ]

    # Create synthetic placeholders for lineup entries that still have no track.
    synth_idx_friendly = 0
    synth_idx_enemy = 0
    synth_entity_id = -1
    for slot in lineup:
        if slot["used"]:
            continue
        if slot.get("team_side") == "friendly":
            sx, sz = _spread_world_position(friendly_center[0], friendly_center[1], synth_idx_friendly, cell=42.0)
            synth_idx_friendly += 1
            yaw = float(friendly_spawn_yaw)
        else:
            sx, sz = _spread_world_position(enemy_center[0], enemy_center[1], synth_idx_enemy, cell=42.0)
            synth_idx_enemy += 1
            yaw = float(enemy_spawn_yaw)
        key = f"synthetic_{abs(synth_entity_id)}"
        synth_entity_id -= 1
        normalized[key] = {
            "entity_id": key,
            "player_name": slot.get("name") or f"entity_{key}",
            "ship_id": slot.get("ship_id"),
            "team_side": slot["team_side"],
            "team_label_side": slot["team_side"],
            "team_number": slot.get("team_number"),
            "team_number_local": slot.get("team_number_local"),
            "account_entity_id": slot.get("account_id") or None,
            "points": [{"t": 0.0, "x": sx, "y": 0.0, "z": sz, "yaw": yaw, "pitch": 0.0, "roll": 0.0}],
            "always_unspotted": True,
        }

    # Final fallback numbering for any unresolved entries: keep display numbers unique globally.
    max_display = max((int(v.get("team_number") or 0) for v in normalized.values()), default=0)
    next_display = max_display + 1
    max_friendly_local = max((int(v.get("team_number_local") or 0) for v in normalized.values() if v.get("team_side") == "friendly"), default=0)
    max_enemy_local = max((int(v.get("team_number_local") or 0) for v in normalized.values() if v.get("team_side") == "enemy"), default=0)
    next_friendly_local = max_friendly_local + 1
    next_enemy_local = max_enemy_local + 1
    for item in normalized.values():
        if item.get("team_number") is not None:
            continue
        if item.get("team_side") == "friendly":
            item["team_number"] = next_display
            item["team_number_local"] = next_friendly_local
            next_display += 1
            next_friendly_local += 1
        elif item.get("team_side") == "enemy":
            item["team_number"] = next_display
            item["team_number_local"] = next_enemy_local
            next_display += 1
            next_enemy_local += 1

    real_first_times = [
        float(item.get("first_real_t", 0.0) or 0.0)
        for item in normalized.values()
        if not bool(item.get("always_unspotted", False)) and list(item.get("points", []) or [])
    ]
    earliest_first_t = min(real_first_times) if real_first_times else 0.0
    late_start_cutoff_t = earliest_first_t + 45.0

    def _numbered_start_anchors(side: str) -> List[Tuple[int, float, float]]:
        anchors: List[Tuple[int, float, float]] = []
        for item in normalized.values():
            if item.get("team_side") != side:
                continue
            if bool(item.get("always_unspotted", False)):
                continue
            points = list(item.get("points", []) or [])
            if not points:
                continue
            first_real_t = float(item.get("first_real_t", 0.0) or 0.0)
            if first_real_t > late_start_cutoff_t:
                continue
            team_num_local = _safe_int(item.get("team_number_local"))
            if team_num_local is None:
                continue
            first_point = points[0] or {}
            anchors.append(
                (
                    int(team_num_local),
                    float(first_point.get("x", 0.0) or 0.0),
                    float(first_point.get("z", 0.0) or 0.0),
                )
            )
        anchors.sort(key=lambda row: row[0])
        return anchors

    def _mirror_axis_for_anchors(anchors: List[Tuple[int, float, float]]) -> str:
        if not anchors:
            return "x"
        xs = [float(row[1]) for row in anchors]
        zs = [float(row[2]) for row in anchors]
        return "x" if (max(xs) - min(xs)) >= (max(zs) - min(zs)) else "z"

    def _mirror_point(x: float, z: float, axis: str) -> Tuple[float, float]:
        if axis == "x":
            return (-float(x), float(z))
        return (float(x), -float(z))

    def _mirrored_anchors(anchors: List[Tuple[int, float, float]], axis: str) -> List[Tuple[int, float, float]]:
        if not anchors:
            return []
        mirrored: List[Tuple[int, float, float]] = []
        for number, x, z in anchors:
            mx, mz = _mirror_point(float(x), float(z), axis)
            mirrored.append((number, mx, mz))
        mirrored.sort(key=lambda row: row[0])
        return mirrored

    def _ship_start_anchors(side: str) -> Dict[str, List[Tuple[float, float]]]:
        anchors: Dict[str, List[Tuple[float, float]]] = {}
        for item in normalized.values():
            if item.get("team_side") != side:
                continue
            if bool(item.get("always_unspotted", False)):
                continue
            points = list(item.get("points", []) or [])
            if not points:
                continue
            first_real_t = float(item.get("first_real_t", 0.0) or 0.0)
            if first_real_t > late_start_cutoff_t:
                continue
            ship_key = str(_safe_int(item.get("ship_id")) or "")
            if not ship_key:
                continue
            first_point = points[0] or {}
            anchors.setdefault(ship_key, []).append(
                (
                    float(first_point.get("x", 0.0) or 0.0),
                    float(first_point.get("z", 0.0) or 0.0),
                )
            )
        return anchors

    def _placeholder_from_number(
        anchors: List[Tuple[int, float, float]],
        target_number: int,
        fallback_x: float,
        fallback_z: float,
    ) -> Tuple[float, float]:
        if not anchors:
            return fallback_x, fallback_z
        if len(anchors) == 1:
            return float(anchors[0][1]), float(anchors[0][2])
        lower = [row for row in anchors if row[0] <= target_number]
        upper = [row for row in anchors if row[0] >= target_number]
        if lower and upper:
            left = lower[-1]
            right = upper[0]
            if left[0] == right[0]:
                return float(left[1]), float(left[2])
            span = max(1, right[0] - left[0])
            ratio = max(0.0, min(1.0, float(target_number - left[0]) / float(span)))
            return (
                float(left[1]) + (float(right[1]) - float(left[1])) * ratio,
                float(left[2]) + (float(right[2]) - float(left[2])) * ratio,
            )
        if len(lower) >= 2:
            a = lower[-2]
            b = lower[-1]
            step = max(1, b[0] - a[0])
            ratio = float(target_number - b[0]) / float(step)
            return (
                float(b[1]) + (float(b[1]) - float(a[1])) * ratio,
                float(b[2]) + (float(b[2]) - float(a[2])) * ratio,
            )
        if len(upper) >= 2:
            a = upper[0]
            b = upper[1]
            step = max(1, b[0] - a[0])
            ratio = float(a[0] - target_number) / float(step)
            return (
                float(a[1]) - (float(b[1]) - float(a[1])) * ratio,
                float(a[2]) - (float(b[2]) - float(a[2])) * ratio,
            )
        return float(anchors[0][1]), float(anchors[0][2])

    friendly_anchors = _numbered_start_anchors("friendly")
    enemy_anchors = _numbered_start_anchors("enemy")
    friendly_axis = _mirror_axis_for_anchors(friendly_anchors)
    enemy_axis = _mirror_axis_for_anchors(enemy_anchors)
    friendly_mirrored = _mirrored_anchors(friendly_anchors, friendly_axis)
    enemy_mirrored = _mirrored_anchors(enemy_anchors, enemy_axis)
    friendly_ship_anchors = _ship_start_anchors("friendly")
    enemy_ship_anchors = _ship_start_anchors("enemy")

    for item in normalized.values():
        if bool(item.get("always_unspotted", False)):
            continue
        points = list(item.get("points", []) or [])
        if not points:
            continue
        first_real_t = float(item.get("first_real_t", 0.0) or 0.0)
        if first_real_t <= late_start_cutoff_t:
            continue
        side = str(item.get("team_side") or "unknown")
        if side not in ("friendly", "enemy"):
            continue
        team_num_local = _safe_int(item.get("team_number_local")) or 1
        ship_key = str(_safe_int(item.get("ship_id")) or "")
        if side == "friendly":
            ship_points = friendly_ship_anchors.get(ship_key, [])
            if ship_points:
                mx, mz = zip(*(_mirror_point(x, z, friendly_axis) for x, z in ship_points))
                px = sum(mx) / len(mx)
                pz = sum(mz) / len(mz)
            else:
                px, pz = _placeholder_from_number(friendly_mirrored, team_num_local, -half * 0.15, friendly_center[1])
        else:
            ship_points = enemy_ship_anchors.get(ship_key, [])
            if ship_points:
                mx, mz = zip(*(_mirror_point(x, z, enemy_axis) for x, z in ship_points))
                px = sum(mx) / len(mx)
                pz = sum(mz) / len(mz)
            else:
                px, pz = _placeholder_from_number(enemy_mirrored, team_num_local, half * 0.15, enemy_center[1])
        first_point = points[0] or {}
        item["late_start_placeholder"] = {
            "x": float(px),
            "z": float(pz),
            "yaw": float(friendly_spawn_yaw if side == "friendly" else enemy_spawn_yaw),
            "first_real_t": first_real_t,
        }

    _maybe_write_track_debug(normalized)
    return normalized


def _draw_ship_icon(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    code: str,
    fill_color: Tuple[int, int, int] | None,
    outline_color: Tuple[int, int, int],
    size: int = 7,
) -> None:
    if code == "DD":
        draw.polygon([(cx, cy - size - 1), (cx - size, cy + size), (cx + size, cy + size)], fill=fill_color, outline=outline_color)
    elif code == "BB":
        draw.polygon(
            [
                (cx - size - 1, cy),
                (cx - size // 2, cy - size),
                (cx + size // 2, cy - size),
                (cx + size + 1, cy),
                (cx + size // 2, cy + size),
                (cx - size // 2, cy + size),
            ],
            fill=fill_color,
            outline=outline_color,
        )
    elif code == "CA":
        draw.polygon([(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)], fill=fill_color, outline=outline_color)
    elif code == "CV":
        draw.rectangle([cx - size, cy - size + 1, cx + size, cy + size - 1], fill=fill_color, outline=outline_color)
        if fill_color is not None:
            draw.line([(cx, cy - size + 2), (cx, cy + size - 2)], fill=(30, 30, 30), width=1)
    elif code == "SS":
        draw.ellipse([cx - size - 1, cy - size // 2, cx + size + 1, cy + size // 2], fill=fill_color, outline=outline_color)
        draw.rectangle([cx - 2, cy - size, cx + 2, cy - size // 2], fill=fill_color, outline=outline_color)
    else:
        draw.ellipse([cx - size, cy - size, cx + size, cy + size], fill=fill_color, outline=outline_color)


_SVG_PATH_TOKEN_RE = re.compile(r"[MLZmlz]|-?\d+(?:\.\d+)?")


def _ship_icon_svg_name(ship_code: str, team_side: str) -> str:
    code = str(ship_code or "").strip().upper()
    suffix = "Blue" if str(team_side or "").strip().lower() == "friendly" else "Red"
    if code == "CA":
        code = "CR"
    if code not in ("BB", "CR", "CV", "DD", "SS"):
        code = "CR"
    return f"{code}_{suffix}.svg"


def _svg_points_from_path(path_d: str) -> List[List[Tuple[float, float]]]:
    tokens = _SVG_PATH_TOKEN_RE.findall(str(path_d or ""))
    if not tokens:
        return []
    paths: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    idx = 0
    cmd = ""
    while idx < len(tokens):
        token = tokens[idx]
        idx += 1
        if re.fullmatch(r"[MLZmlz]", token):
            cmd = token.upper()
            if cmd == "Z" and current:
                paths.append(current)
                current = []
            continue
        if cmd not in ("M", "L"):
            continue
        if idx >= len(tokens):
            break
        try:
            x = float(token)
            y = float(tokens[idx])
        except ValueError:
            break
        idx += 1
        current.append((x, y))
    if current:
        paths.append(current)
    return [pts for pts in paths if len(pts) >= 2]


@lru_cache(maxsize=32)
def _render_svg_ship_icon(ship_code: str, team_side: str, size: int) -> Image.Image | None:
    svg_path = _root_dir() / "gui" / "ribbons" / "Icons" / _ship_icon_svg_name(ship_code, team_side)
    if not svg_path.exists():
        return None
    try:
        root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    view_box = root.attrib.get("viewBox", "").strip().split()
    try:
        vb_w = float(view_box[2]) if len(view_box) == 4 else float(root.attrib.get("width", 52))
        vb_h = float(view_box[3]) if len(view_box) == 4 else float(root.attrib.get("height", 52))
    except Exception:
        vb_w = 52.0
        vb_h = 52.0
    if vb_w <= 0 or vb_h <= 0:
        vb_w = vb_h = 52.0

    target = max(12, int(size))
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    scale = min(target / vb_w, target / vb_h)
    offset_x = (target - vb_w * scale) / 2.0
    offset_y = (target - vb_h * scale) / 2.0

    ns = "{http://www.w3.org/2000/svg}"
    for path in root.iter(f"{ns}path"):
        fill = path.attrib.get("fill", "#FFFFFF")
        stroke = path.attrib.get("stroke", "black")
        try:
            stroke_width = float(path.attrib.get("stroke-width", 1.0)) * scale
        except Exception:
            stroke_width = 1.0 * scale
        for pts in _svg_points_from_path(path.attrib.get("d", "")):
            mapped = [(offset_x + x * scale, offset_y + y * scale) for x, y in pts]
            draw.polygon(mapped, fill=fill, outline=stroke, width=max(1, int(round(stroke_width))))
    return canvas


@lru_cache(maxsize=128)
def _wg_outline_icon_mask(ship_type: str, size: int, inner_filter_size: int = 3) -> Image.Image | None:
    base_icon = _load_wg_class_icons().get(ship_type)
    if base_icon is None:
        return None
    target = max(12, size * 2 + 6)
    icon = base_icon.resize((target, target), Image.Resampling.LANCZOS)
    alpha = icon.getchannel("A")
    inner_filter_size = max(3, int(inner_filter_size) | 1)
    inner = alpha.filter(ImageFilter.MinFilter(inner_filter_size))
    # Thin one-pixel inner edge mask for sunk-outline rendering.
    edge = ImageChops.subtract(alpha, inner)
    return edge


@lru_cache(maxsize=128)
def _wg_hollow_outline_icon(ship_type: str, color: Tuple[int, int, int], size: int, stroke_px: int = 3) -> Image.Image | None:
    base_icon = _load_wg_class_icons().get(ship_type)
    if base_icon is None:
        return None
    target = max(12, size * 2 + 6)
    icon = base_icon.resize((target, target), Image.Resampling.LANCZOS)
    alpha = icon.getchannel("A").point(lambda v: 255 if v >= 96 else 0)
    stroke_px = max(3, int(stroke_px) | 1)
    outer = alpha.filter(ImageFilter.MaxFilter(stroke_px))
    outline_alpha = ImageChops.subtract(outer, alpha)
    outline = Image.new("RGBA", icon.size, (color[0], color[1], color[2], 0))
    outline.putalpha(outline_alpha)
    return outline


def _friendly_stale_marker(team_side: str, spotted: bool, sunk: bool, synthetic_start: bool = False) -> bool:
    return team_side == "friendly" and (not spotted) and (not sunk) and (not synthetic_start)


def _heading_bucket(heading_deg: float, bucket_deg: float = 1.0) -> int:
    return int(round((heading_deg % 360.0) / bucket_deg)) % int(round(360.0 / bucket_deg))


@lru_cache(maxsize=16384)
def _ship_marker_image(
    ship_type: str,
    code: str,
    color: Tuple[int, int, int],
    size: int,
    sunk: bool,
    stale: bool,
    heading_bucket: int,
    bucket_deg: float = 1.0,
) -> Image.Image:
    heading_deg = (heading_bucket * bucket_deg) % 360.0
    if sunk:
        outline_color = (110, 110, 110)
        edge_mask = _wg_outline_icon_mask(ship_type, size)
        icon = None
        if edge_mask is not None:
            icon = Image.new("RGBA", edge_mask.size, (outline_color[0], outline_color[1], outline_color[2], 0))
            icon.putalpha(edge_mask)
    elif stale:
        icon = _wg_hollow_outline_icon(ship_type, color, size, stroke_px=3)
    else:
        icon = _wg_tinted_icon(ship_type, color, size)

    if icon is not None:
        resample = Image.Resampling.NEAREST if stale else Image.Resampling.BICUBIC
        rotated = icon.rotate(-(heading_deg + WG_ICON_HEADING_OFFSET_DEG), resample=resample, expand=True)
        if stale:
            alpha = rotated.getchannel("A").point(lambda v: 255 if v >= 192 else 0)
            outline = Image.new("RGBA", rotated.size, (color[0], color[1], color[2], 0))
            outline.putalpha(alpha)
            return outline
        return rotated

    local_size = max(18, size * 3)
    local = Image.new("RGBA", (local_size, local_size), (0, 0, 0, 0))
    local_draw = ImageDraw.Draw(local)
    lc = local_size // 2
    if sunk:
        _draw_ship_icon(
            local_draw,
            lc,
            lc,
            code,
            fill_color=None,
            outline_color=(110, 110, 110),
            size=max(4, size),
        )
    elif stale:
        _draw_ship_icon(
            local_draw,
            lc,
            lc,
            code,
            fill_color=None,
            outline_color=color,
            size=max(4, size),
        )
    else:
        _draw_ship_icon(
            local_draw,
            lc,
            lc,
            code,
            fill_color=color,
            outline_color=(220, 220, 220),
            size=max(4, size),
        )
    resample = Image.Resampling.BICUBIC
    return local.rotate(-(heading_deg + WG_ICON_HEADING_OFFSET_DEG), resample=resample, expand=True)


def _draw_ship_marker(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    ship_type: str,
    code: str,
    color: Tuple[int, int, int],
    heading_deg: float,
    marker_label: Any,
    size: int,
    sunk: bool = False,
    stale: bool = False,
    consumable_kind: Optional[str] = None,
) -> None:
    icon = _ship_marker_image(ship_type, code, color, size, sunk, stale, _heading_bucket(heading_deg))
    x = cx - icon.width // 2
    y = cy - icon.height // 2
    img.paste(icon, (x, y), icon)

    # Marker name overlay above icon.
    txt = _marker_name_text(marker_label)
    if txt:
        label = _text_sprite(txt, max(9, size + 3), (255, 255, 255), (0, 0, 0))
        if label is not None:
            tx = cx - label.width // 2
            ty = cy - size - label.height - 4
            img.paste(label, (tx, ty), label)

    if consumable_kind:
        icon_size = max(10, int(size * 2))
        cicon = _load_consumable_icon(consumable_kind, icon_size)
        if cicon is not None:
            ix = cx - cicon.width // 2
            iy = cy + size + 2
            img.paste(cicon, (ix, iy), cicon)


@lru_cache(maxsize=64)
def _ship_class_placeholder_icon(code: str, team_side: str, size: int) -> Image.Image:
    icon = _render_svg_ship_icon(code, team_side, max(12, int(size)))
    if icon is not None:
        return icon
    fallback_size = max(18, int(size) + 6)
    local = Image.new("RGBA", (fallback_size, fallback_size), (0, 0, 0, 0))
    local_draw = ImageDraw.Draw(local)
    lc = fallback_size // 2
    outline = COLOR_FRIENDLY if str(team_side or "").strip().lower() == "friendly" else COLOR_ENEMY
    _draw_ship_icon(local_draw, lc, lc, code, fill_color=None, outline_color=outline, size=max(4, fallback_size // 3))
    return local


def _draw_ship_class_placeholder(
    img: Image.Image,
    cx: int,
    cy: int,
    code: str,
    team_side: str,
    size: int,
) -> None:
    icon = _ship_class_placeholder_icon(code, team_side, size)
    x = cx - icon.width // 2
    y = cy - icon.height // 2
    img.paste(icon, (x, y), icon)


def _friendly_spawn_placeholder_state(track: Dict[str, Any]) -> Optional[Dict[str, float]]:
    if _color_side(track) != "friendly":
        return None
    start_placeholder = track.get("start_placeholder")
    if isinstance(start_placeholder, dict):
        return {
            "x": float(start_placeholder.get("x", 0.0) or 0.0),
            "z": float(start_placeholder.get("z", 0.0) or 0.0),
            "yaw": float(start_placeholder.get("yaw", 0.0) or 0.0),
        }
    placeholder = track.get("late_start_placeholder")
    if isinstance(placeholder, dict):
        return {
            "x": float(placeholder.get("x", 0.0) or 0.0),
            "z": float(placeholder.get("z", 0.0) or 0.0),
            "yaw": float(placeholder.get("yaw", 0.0) or 0.0),
        }
    points = list(track.get("points", []) or [])
    if not points:
        return None
    first = points[0] or {}
    return {
        "x": float(first.get("x", 0.0) or 0.0),
        "z": float(first.get("z", 0.0) or 0.0),
        "yaw": float(first.get("yaw", 0.0) or 0.0),
    }


def _draw_hp_bar(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    width: int,
    height: int,
    ratio: float,
    color: Tuple[int, int, int],
    sunk: bool = False,
) -> None:
    if sunk:
        return
    ratio = max(0.0, min(1.0, ratio))
    left = cx - width // 2
    top = cy
    right = left + width
    bottom = top + height
    draw.rectangle([left, top, right, bottom], fill=(12, 12, 12), outline=(80, 80, 80))
    if ratio <= 0.0:
        return
    fill_color = (135, 135, 135) if sunk else color
    inner_left = left + 1
    inner_top = top + 1
    inner_bottom = bottom - 1
    inner_right = inner_left + max(1, int((width - 2) * ratio))
    draw.rectangle([inner_left, inner_top, inner_right, inner_bottom], fill=fill_color)


def _active_sensor_kind(sensor_by_entity: Dict[int, List[Dict[str, Any]]], entity_id: int, t: float) -> Optional[str]:
    events = sensor_by_entity.get(int(entity_id), [])
    active_kind = None
    for event in events:
        start_time = float(event.get("start_time", 0.0))
        end_time = float(event.get("end_time", 0.0))
        if t < start_time or t > end_time:
            continue
        kind = str(event.get("kind") or "").lower()
        if kind == "radar":
            return "radar"
        if kind == "hydro":
            active_kind = "hydro"
    return active_kind


def _active_smoke_entities(snapshot: Optional[Dict[str, Any]]) -> set[int]:
    active: set[int] = set()
    if not snapshot or not isinstance(snapshot, dict):
        return active
    smokes = snapshot.get("smokes", [])
    if not isinstance(smokes, list):
        return active
    for smoke in smokes:
        if not isinstance(smoke, dict):
            continue
        if not bool(smoke.get("active", True)):
            continue
        entity_id = _safe_int(smoke.get("entity_id"))
        if entity_id is None:
            continue
        active.add(int(entity_id))
    return active


def _active_consumable_kind(consumable_by_entity: Dict[int, List[Dict[str, Any]]], entity_id: int, t: float) -> Optional[str]:
    events = consumable_by_entity.get(int(entity_id), [])
    if not events:
        return None
    active_heal = False
    active_engine = False
    active_smoke = False
    for event in events:
        start_time = float(event.get("start_time", 0.0))
        end_time = float(event.get("end_time", 0.0))
        if t < start_time or t > end_time:
            continue
        kind = str(event.get("kind") or "").lower()
        if kind == "heal":
            active_heal = True
        elif kind == "engine":
            active_engine = True
        elif kind == "smoke":
            active_smoke = True
    if active_heal:
        return "heal"
    if active_smoke:
        return "smoke"
    if active_engine:
        return "engine"
    return None


def _build_player_track_index(render_tracks: Dict[str, Dict[str, Any]]) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    index: Dict[str, Tuple[str, Dict[str, Any]]] = {}
    for key, track in render_tracks.items():
        target = _feed_name_key(track.get("player_name"))
        if target and target not in index:
            index[target] = (str(key), track)
    return index


def _is_local_player_track(canonical: Dict[str, Any], track: Dict[str, Any]) -> bool:
    meta = canonical.get("meta", {}) or {}
    local_name = _feed_name_key(meta.get("playerName"))
    track_name = _feed_name_key(track.get("player_name"))
    return bool(local_name and track_name and local_name == track_name)


def _entity_track_for_player(
    render_tracks: Dict[str, Dict[str, Any]],
    player_name: str,
    entity_key: str = "",
    player_track_index: Optional[Dict[str, Tuple[str, Dict[str, Any]]]] = None,
) -> tuple[str, Dict[str, Any]] | tuple[str, None]:
    if entity_key and entity_key in render_tracks:
        return entity_key, render_tracks[entity_key]
    target = _feed_name_key(player_name)
    if target:
        if isinstance(player_track_index, dict):
            match = player_track_index.get(target)
            if match is not None:
                return match
        for key, track in render_tracks.items():
            if _feed_name_key(track.get("player_name")) == target:
                return str(key), track
    return "", None


def _draw_player_status_panel(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    canonical: Dict[str, Any],
    render_tracks: Dict[str, Dict[str, Any]],
    health_timelines: Dict[str, Dict[str, Any]],
    player_status_timeline: Dict[str, Any],
    t: float,
    layout: Dict[str, Any],
    player_track_index: Optional[Dict[str, Tuple[str, Dict[str, Any]]]] = None,
) -> None:
    rect = tuple(layout.get("player_rect", (0, 0, 0, 0)))
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        return

    status = _player_status_at(player_status_timeline, t)
    player_name = str(status.get("player_name") or (canonical.get("meta", {}) or {}).get("playerName") or "").strip()
    ship_entity_key, track = _entity_track_for_player(
        render_tracks,
        player_name,
        str(status.get("ship_entity_key") or ""),
        player_track_index=player_track_index,
    )
    ship_id = _safe_int(status.get("ship_id"))
    if (ship_id is None or ship_id < 0) and isinstance(track, dict):
        ship_id = _safe_int(track.get("ship_id"))
    ship_id = ship_id if ship_id is not None else -1
    ship_type = _ship_type(ship_id)
    ship_code = _ship_class_code(ship_id)
    ship_name = _ship_name(ship_id) or "Unknown ship"
    vehicle_code = _player_vehicle_code(canonical, ship_id)
    if ship_name == "Unknown ship":
        raw_ship_name = str(_gameparams_ship_entry(ship_id).get("name") or "").strip()
        if raw_ship_name:
            ship_name = raw_ship_name.split("_", 1)[-1].replace("_", " ")
    font_size = max(10, int(round(int(layout.get("font_size", 10)) * PLAYER_CARD_TEXT_SCALE)))
    damage_font_size = max(font_size + 6, int(font_size * 1.45))
    title_font_size = font_size + 2
    base_font_size = max(10, int(round(int(layout.get("base_font_size", font_size)) * PLAYER_CARD_TEXT_SCALE)))
    x0, y0, x1, y1 = map(int, rect)
    top_pad = 12

    draw.rectangle(rect, fill=WOWS_PANEL_INNER, outline=WOWS_OUTLINE_SOFT)

    damage_text = f"{int(round(float(status.get('damage_total', 0.0) or 0.0))):,} DMG"
    damage_sprite = _text_sprite(damage_text, damage_font_size, WOWS_GOLD, shadow=(0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    damage_block_bottom = y0 + top_pad
    if damage_sprite is not None:
        _paste_sprite(img, damage_sprite, x1 - damage_sprite.width - 10, y0 + top_pad)
        damage_block_bottom = y0 + top_pad + damage_sprite.height

    ribbons = dict(status.get("ribbons") or {})
    badge_font = _player_ribbon_badge_font(font_size)
    supported_ribbons = _gameparams_supported_ribbon_ids()
    ribbon_items = sorted(
        (
            (ribbon_id, count)
            for ribbon_id, count in ribbons.items()
            if (_safe_int(ribbon_id) is not None and int(ribbon_id) in supported_ribbons)
        ),
        key=lambda item: (-int(item[1]), int(item[0])),
    )
    panel_w = x1 - x0
    ribbon_icon_size = _player_ribbon_icon_height(font_size, len(ribbon_items), panel_w, max_rows=3)
    preview_x = x0 + 10
    preview_y = y0 + top_pad
    preview_w = max(112, min(220, int((x1 - x0) * 0.44)))
    preview_h = max(60, min(90, int(round(preview_w * 0.45))))
    preview_h = min(preview_h, max(50, y1 - preview_y - 20))
    preview_rect = (preview_x, preview_y, preview_x + preview_w, preview_y + preview_h)
    draw.rounded_rectangle(preview_rect, radius=8, fill=WOWS_PANEL_INNER, outline=WOWS_OUTLINE_SOFT)
    health = _health_state_at(health_timelines, ship_entity_key, t) if ship_entity_key else None
    ship_has_heal = _ship_has_consumable(ship_id, "heal")
    player_sunk = health is not None and not bool(health.get("alive", True))
    hp_ratio = float(health.get("ratio", 1.0) or 1.0) if health is not None else 1.0
    max_hp_value = max(1, _safe_int(health.get("max_hp")) or 0) if health is not None else 1
    restorable_hp = max(0, _safe_int(health.get("restorable_hp")) or 0) if health is not None and ship_has_heal else 0
    restorable_ratio = min(1.0, float(restorable_hp) / float(max_hp_value)) if max_hp_value > 0 else 0.0
    alive_icon = _load_ship_alive_icon(vehicle_code, preview_w - 12, preview_h - 12)
    dead_icon = _load_ship_dead_icon(vehicle_code, preview_w - 12, preview_h - 12)
    preview = _compose_ship_status_icon(alive_icon, dead_icon, preview_w - 12, preview_h - 12, hp_ratio, player_sunk, restorable_ratio)
    if preview is not None:
        px = preview_x + (preview_w - preview.width) // 2
        py = preview_y + (preview_h - preview.height) // 2
        img.paste(preview, (px, py), preview)
    else:
        fallback_color = (160, 160, 160) if player_sunk else WOWS_TEXT
        fallback_icon = _wg_tinted_icon(ship_type, fallback_color, max(14, min(preview_w, preview_h) // 2))
        if fallback_icon is not None:
            px = preview_x + (preview_w - fallback_icon.width) // 2
            py = preview_y + (preview_h - fallback_icon.height) // 2
            img.paste(fallback_icon, (px, py), fallback_icon)
        else:
            local = ImageDraw.Draw(img)
            _draw_ship_icon(local, preview_x + preview_w // 2, preview_y + preview_h // 2, ship_code, fallback_color, (220, 220, 220), size=max(10, min(preview_w, preview_h) // 4))

    if health is not None:
        status_icons: List[Image.Image] = []
        status_icon_size = max(12, min(26, int(min(preview_w, preview_h) * 0.22)))
        if bool(health.get("on_fire", False)):
            icon = _load_status_icon("fire", status_icon_size)
            if icon is not None:
                status_icons.append(icon)
        if bool(health.get("flooding", False)):
            icon = _load_status_icon("flood", status_icon_size)
            if icon is not None:
                status_icons.append(icon)
        if status_icons:
            spacing = max(2, status_icon_size // 6)
            total_w = sum(icon.width for icon in status_icons) + spacing * (len(status_icons) - 1)
            start_x = preview_rect[0] + 6
            if start_x + total_w > preview_rect[2] - 6:
                start_x = max(preview_rect[0] + 2, preview_rect[2] - total_w - 6)
            y = preview_rect[3] - status_icon_size - 6
            x = start_x
            for icon in status_icons:
                img.paste(icon, (int(x), int(y)), icon)
                x += icon.width + spacing

        if restorable_hp > 0:
            heal_text = _text_sprite(
                f"+{restorable_hp:,}",
                max(9, font_size - 1),
                WOWS_FRIENDLY,
                shadow=None,
                bold=True,
                stroke_width=1,
                stroke_fill=WOWS_OUTLINE_SOFT,
                face=INGAME_FONT_FACE,
            )
            if heal_text is not None:
                hx = preview_rect[2] - heal_text.width - 6
                hy = preview_rect[3] - heal_text.height - 6
                img.paste(heal_text, (int(hx), int(hy)), heal_text)

    hp_text = ""
    hp_color = COLOR_FRIENDLY
    if health is not None:
        hp_ratio = max(0.0, min(1.0, float(health.get("ratio", 0.0) or 0.0)))
        hp_pct = int(round(hp_ratio * 100.0))
        hp_text = f"HP {int(health['hp']):,} / {int(health['max_hp']):,}  {hp_pct}%"
        hp_color = COLOR_FRIENDLY if bool(health.get("alive", True)) else WOWS_TEXT_DIM
        hp_sprite = _text_sprite(hp_text, font_size, hp_color, shadow=(0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
        if hp_sprite is not None:
            hp_x = preview_x + max(0, (preview_w - hp_sprite.width) // 2)
            hp_y = preview_rect[3] + 6
            _paste_sprite(img, hp_sprite, hp_x, hp_y)

    text_x = preview_rect[2] + 12
    info_y = y0 + top_pad
    line_gap = max(18, font_size + 5)
    _paste_sprite(img, _text_sprite(player_name or "Player", title_font_size + 1, COLOR_FRIENDLY, shadow=(0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE), text_x, info_y)
    _paste_sprite(img, _text_sprite(ship_name, font_size + 2, WOWS_TEXT, shadow=(0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE), text_x, info_y + line_gap)

    info_bottom = info_y + line_gap + max(font_size + 6, title_font_size + 4)
    if health is not None:
        info_bottom = max(info_bottom, preview_rect[3] + 6 + font_size + 6)

    optional_stats: List[Tuple[str, float, Tuple[int, int, int]]] = []
    potential_damage = float(status.get("potential_damage", 0.0) or 0.0)
    spotting_damage = float(status.get("spotting_damage", 0.0) or 0.0)
    if potential_damage > 0.0:
        optional_stats.append(("Potential damage", potential_damage, WOWS_GOLD))
    if spotting_damage > 0.0:
        optional_stats.append(("Spotting damage", spotting_damage, WOWS_ACCENT))
    stat_font_size = max(11, int(round(max(10, font_size - 1) * 1.15)))
    for i, (label, value, color) in enumerate(optional_stats[:2]):
        stat_sprite = _text_sprite(
            f"{label} {int(round(value)):,}",
            stat_font_size,
            color,
            shadow=(0, 0, 0),
            bold=True,
            stroke_width=1,
            stroke_fill=(0, 0, 0),
            face=INGAME_FONT_FACE,
        )
        if stat_sprite is None:
            continue
        stat_y = damage_block_bottom + 4 + i * (stat_sprite.height + 3)
        stat_x = x1 - stat_sprite.width - 10
        _paste_sprite(img, stat_sprite, stat_x, stat_y)
    content_bottom = max(preview_rect[3], info_bottom)
    ribbons_title_y = content_bottom + 10

    _paste_sprite(img, _text_sprite("Ribbons", font_size, WOWS_TEXT_SUB, shadow=(0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE), x0 + 10, ribbons_title_y)
    badge_x = x0 + 10
    badge_y = ribbons_title_y + font_size + 5
    badge_max_x = x1 - 10
    for ribbon_id, count in ribbon_items:
        rid = _safe_int(ribbon_id)
        icon = _load_ribbon_icon(rid or -1, ribbon_icon_size) if rid is not None else None
        count_sprite = _text_sprite(f"x{int(count)}", badge_font, WOWS_TEXT, shadow=(0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
        has_icon = icon is not None and count_sprite is not None
        if has_icon:
            badge_w = icon.width + 8 + count_sprite.width + 14
            badge_h = max(icon.height, count_sprite.height) + 6
        else:
            fallback = _text_sprite(f"R{int(ribbon_id)} x{int(count)}", badge_font, WOWS_TEXT, shadow=None, bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
            if fallback is None:
                continue
            icon = fallback
            count_sprite = None
            badge_w = fallback.width + 14
            badge_h = fallback.height + 6
        if badge_x + badge_w > badge_max_x:
            badge_x = x0 + 10
            badge_y += badge_h + 4
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=6, fill=WOWS_PANEL_INNER, outline=WOWS_OUTLINE)
        if has_icon:
            _paste_sprite(img, icon, badge_x + 6, badge_y + (badge_h - icon.height) // 2)
            _paste_sprite(img, count_sprite, badge_x + 6 + icon.width + 8, badge_y + (badge_h - count_sprite.height) // 2)
        else:
            _paste_sprite(img, icon, badge_x + 7, badge_y + 2)
        badge_x += badge_w + 6


def _draw_lineup_panel(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    layout: Dict[str, Any],
    current_t: float | None = None,
    death_times: Dict[str, float] | None = None,
    health_timelines: Dict[str, Dict[str, Any]] | None = None,
) -> None:
    lineup_stroke = 2
    friendly = list(layout.get("friendly_items", []))
    enemy = list(layout.get("enemy_items", []))
    line_h = int(layout.get("line_h", 12))
    header_h = int(layout.get("header_h", 20))
    font_size = int(layout.get("font_size", 10))
    friendly_rect = tuple(layout.get("friendly_rect", (0, 0, 0, 0)))
    enemy_rect = tuple(layout.get("enemy_rect", (0, 0, 0, 0)))

    draw.rectangle(friendly_rect, fill=None, outline=COLOR_FRIENDLY)
    draw.rectangle(enemy_rect, fill=None, outline=COLOR_ENEMY)
    row_top_pad = 6

    def _line_text(item: Dict[str, Any]) -> str:
        ship_name = str(_ship_name(item.get("ship_id")) or "").strip()
        player_name = str(item.get("player_name") or "").strip()
        if ship_name and player_name:
            return f"{ship_name} - {player_name}"
        if ship_name:
            return ship_name
        if player_name:
            return player_name
        return _ship_class_code(item.get("ship_id"))

    def _is_sunk(item: Dict[str, Any]) -> bool:
        if current_t is None or death_times is None:
            return False
        entity_key = str(item.get("entity_id", "") or "")
        if not entity_key:
            return False
        death_t = death_times.get(entity_key)
        return death_t is not None and float(current_t) >= float(death_t)

    def _fit_lineup_text(item: Dict[str, Any], max_width: int, font_size: int, stroke_width: int) -> str:
        """Smart text fitting that prioritizes player name over clan tag."""
        ship_name = str(_ship_name(item.get("ship_id")) or "").strip()
        player_name = str(item.get("player_name") or "").strip()
        clan_tag = str(item.get("clan_tag") or "").strip()
        
        # Try full text with clan tag first
        if ship_name and player_name:
            if clan_tag:
                full_text = f"{ship_name} - [{clan_tag}] {player_name}"
            else:
                full_text = f"{ship_name} - {player_name}"
        elif ship_name:
            full_text = ship_name
        elif player_name:
            if clan_tag:
                full_text = f"[{clan_tag}] {player_name}"
            else:
                full_text = player_name
        else:
            full_text = _ship_class_code(item.get("ship_id"))
        
        # Try to fit the full text
        fitted = _fit_text_to_width(
            full_text,
            font_size,
            max_width,
            bold=True,
            stroke_width=stroke_width,
            face=INGAME_FONT_FACE,
            ellipsis="~",
        )
        
        # If the text was truncated and we have a clan tag, try without it
        if fitted != full_text and clan_tag:
            if ship_name and player_name:
                no_clan_text = f"{ship_name} - {player_name}"
            elif player_name:
                no_clan_text = player_name
            else:
                no_clan_text = full_text
                
            fitted_no_clan = _fit_text_to_width(
                no_clan_text,
                font_size,
                max_width,
                bold=True,
                stroke_width=stroke_width,
                face=INGAME_FONT_FACE,
                ellipsis="~",
            )
            
            # Use the version without clan tag if it fits better
            if fitted_no_clan == no_clan_text or (len(fitted_no_clan) > len(fitted)):
                fitted = fitted_no_clan
        
        return fitted

    def _draw_row(item: Dict[str, Any], rect: Tuple[Any, Any, Any, Any], x: int, y: int, alive_fill: Tuple[int, int, int]) -> None:
        sunk = _is_sunk(item)
        fill = alive_fill if not sunk else WOWS_TEXT_DIM
        side = str(item.get("team_side") or "friendly")
        base_font_size = int(layout.get("base_font_size", font_size))
        icon_size = max(19, int(round((base_font_size + 6) * 1.2 * 1.65)))
        icon = _render_svg_ship_icon(_ship_class_code(item.get("ship_id")), side, icon_size)
        icon_x = x
        text_x = x
        center_y = y + (line_h // 2)
        
        # Calculate row width for container
        row_width = int(rect[2]) - int(rect[0]) - 12
        health_ratio = None
        hp_bar_width = 0
        hp_bar_gap = 0
        if current_t is not None and health_timelines is not None:
            entity_key = item.get("entity_id") or item.get("entity_key")
            if entity_key is not None:
                health = _health_state_at(health_timelines, entity_key, current_t)
                if health is not None and bool(health.get("alive", True)):
                    health_ratio = max(0.0, min(1.0, float(health.get("ratio", 0.0) or 0.0)))
                    hp_bar_width = min(60, max(36, int(row_width * 0.18)))
                    hp_bar_gap = 8
        
        # Draw row container background
        container_x = x - 4
        container_y = y + 2
        container_h = line_h - 4
        container_bg = (30, 30, 35) if not sunk else (20, 20, 25)
        draw.rectangle([container_x, container_y, container_x + row_width, container_y + container_h], fill=container_bg, outline=(50, 50, 55))
        
        if icon is not None:
            if sunk:
                icon = icon.copy()
                alpha = icon.getchannel("A").point(lambda v: int(v * 0.55))
                icon.putalpha(alpha)
            icon_y = center_y - (icon.height // 2)
            _paste_sprite(img, icon, icon_x, icon_y)
            text_x = icon_x + icon.width + 7

        hp_bar_right_pad = 8
        hp_bar_x = container_x + row_width - hp_bar_width - hp_bar_right_pad if hp_bar_width > 0 else 0
        max_text_w_with_hp = max(60, (hp_bar_x - hp_bar_gap) - text_x if hp_bar_width > 0 else row_width - (text_x - x) - 8)
        row_text = _fit_lineup_text(item, max_text_w_with_hp, font_size + 1, lineup_stroke)
        row_sprite = _text_sprite(row_text, font_size + 1, fill, shadow=(0, 0, 0), bold=True, stroke_width=lineup_stroke, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
        text_y = center_y - (row_sprite.height // 2) + 1
        _paste_sprite(img, row_sprite, text_x, text_y)

        if hp_bar_width > 0 and health_ratio is not None:
            hp_bar_y = center_y - 3
            hp_color = COLOR_FRIENDLY if side == "friendly" else COLOR_ENEMY
            _draw_hp_bar(draw, hp_bar_x + hp_bar_width // 2, hp_bar_y, hp_bar_width, 6, health_ratio, hp_color)

    rows = max(len(friendly), len(enemy))
    for i in range(rows):
        y_f = int(friendly_rect[1]) + row_top_pad + i * line_h
        y_e = int(enemy_rect[1]) + row_top_pad + i * line_h
        if i < len(friendly):
            _draw_row(friendly[i], friendly_rect, int(friendly_rect[0]) + 6, y_f, (225, 240, 225))
        if i < len(enemy):
            _draw_row(enemy[i], enemy_rect, int(enemy_rect[0]) + 6, y_e, (240, 225, 225))


def _build_frame_base(
    canonical: Dict[str, Any],
    layout: Dict[str, Any],
    margin: int,
    show_grid: bool,
    header_font_size: int,
    bg_color: Tuple[int, int, int] = COLOR_BG,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> Image.Image:
    map_size = int(layout.get("map_size", 600))
    canvas_w = int(layout.get("width", map_size))
    canvas_h = int(layout.get("height", map_size))
    sidebar_x = int(layout.get("sidebar_x", map_size))
    img = Image.new("RGB", (canvas_w, canvas_h), bg_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([sidebar_x, 0, canvas_w, canvas_h], fill=WOWS_BG)
    draw.line([(sidebar_x, 0), (sidebar_x, canvas_h)], fill=WOWS_OUTLINE_SOFT, width=2)
    img = _apply_map_background(img, canonical, margin, map_size)
    draw = ImageDraw.Draw(img)

    if show_grid:
        if map_rect is None:
            left = margin
            top = margin
            right = map_size - margin - 1
            bottom = map_size - margin - 1
        else:
            left, top, right, bottom = [int(v) for v in map_rect]
        grid_steps = 11
        grid_divisor = max(1, grid_steps - 1)
        for i in range(grid_steps):
            x = left + i * (right - left) // grid_divisor
            y = top + i * (bottom - top) // grid_divisor
            draw.line([(x, top), (x, bottom)], fill=WOWS_OUTLINE_SOFT, width=1)
            draw.line([(left, y), (right, y)], fill=WOWS_OUTLINE_SOFT, width=1)
        if map_size >= 800:
            draw.rectangle([left, top, right, bottom], outline=WOWS_OUTLINE, width=2)

    return img


def _prepare_track_render_data(
    render_tracks: Dict[str, Dict[str, Any]],
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> Dict[str, Dict[str, Any]]:
    prepared: Dict[str, Dict[str, Any]] = {}
    for entity_key, track in render_tracks.items():
        points = list(track.get("points", []) or [])
        if not points:
            continue
        times = [float(p.get("t", 0.0)) for p in points]
        real_times = [float(p.get("t", 0.0)) for p in points if not bool(p.get("vision"))]
        pixels = [
            _to_px(
                float(p.get("x", 0.0)),
                float(p.get("z", 0.0)),
                half,
                canvas_size,
                margin,
                world_bounds=world_bounds,
                map_rect=map_rect,
            )
            for p in points
        ]
        prepared[str(entity_key)] = {
            "track": track,
            "points": points,
            "times": times,
            "real_times": real_times,
            "pixels": pixels,
            "ship_type": _ship_type(track.get("ship_id")),
            "ship_class": _ship_class_code(track.get("ship_id")),
        }
    return prepared


def _capture_timeline(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("captures", [])
    if not isinstance(raw, list):
        return []
    timeline: List[Dict[str, Any]] = []
    for snap in raw:
        if not isinstance(snap, dict):
            continue
        time_s = float(snap.get("time_s", 0.0) or 0.0)
        team_scores_raw = snap.get("team_scores", {})
        team_scores: Dict[int, int] = {}
        if isinstance(team_scores_raw, dict):
            for key, value in team_scores_raw.items():
                team_id = _safe_int(key)
                score = _safe_int(value)
                if team_id is None or score is None:
                    continue
                team_scores[team_id] = score
        caps_raw = snap.get("caps", [])
        caps = caps_raw if isinstance(caps_raw, list) else []
        timeline.append(
            {
                "time_s": time_s,
                "team_scores": team_scores,
                "team_win_score": _safe_int(snap.get("team_win_score")) or 0,
                "caps": caps,
            }
        )
    timeline.sort(key=lambda item: float(item.get("time_s", 0.0)))
    return timeline


def _smoke_timeline(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    puffs = events.get("smoke_puffs", [])
    if isinstance(puffs, list) and puffs:
        has_timing = False
        for puff in puffs:
            if not isinstance(puff, dict):
                continue
            if float(puff.get("duration_s", 0.0) or 0.0) > 0.0:
                has_timing = True
                break
            if puff.get("end_time") is not None:
                has_timing = True
                break
        if not has_timing:
            puffs = []
    if isinstance(puffs, list) and puffs:
        normalized: List[Dict[str, Any]] = []
        for puff in puffs:
            if not isinstance(puff, dict):
                continue
            start_time = float(puff.get("start_time", puff.get("time_s", 0.0)) or 0.0)
            duration_s = float(puff.get("duration_s", 0.0) or 0.0)
            if puff.get("end_time") is not None:
                end_time = float(puff.get("end_time") or start_time)
            elif duration_s > 0.0:
                end_time = start_time + duration_s
            else:
                continue
            normalized.append(
                {
                    **puff,
                    "start_time": start_time,
                    "duration_s": duration_s,
                    "end_time": end_time,
                }
            )
        normalized.sort(key=lambda item: (float(item.get("start_time", 0.0)), int(_safe_int(item.get("entity_id")) or 0)))
        return normalized
    raw = events.get("smokes", [])
    if not isinstance(raw, list):
        return []
    timeline: List[Dict[str, Any]] = []
    for snap in raw:
        if not isinstance(snap, dict):
            continue
        smokes_raw = snap.get("smokes", [])
        smokes = smokes_raw if isinstance(smokes_raw, list) else []
        timeline.append(
            {
                "time_s": float(snap.get("time_s", 0.0) or 0.0),
                "smokes": smokes,
            }
        )
    timeline.sort(key=lambda item: float(item.get("time_s", 0.0)))
    return timeline


def _extract_sensor_events(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("sensors", [])
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        if kind not in ("radar", "hydro"):
            continue
        entity_id = _safe_int(row.get("entity_id"))
        if entity_id is None:
            continue
        radius = _safe_float(row.get("radius"), 0.0)
        start_time = _safe_float(row.get("start_time"), 0.0)
        end_time = _safe_float(row.get("end_time"), 0.0)
        if radius <= 0.0 or end_time <= start_time:
            continue
        out.append(
            {
                "entity_id": int(entity_id),
                "kind": kind,
                "radius": float(radius),
                "start_time": float(start_time),
                "end_time": float(end_time),
            }
        )
    out.sort(key=lambda item: (float(item.get("start_time", 0.0)), int(item.get("entity_id", -1)), str(item.get("kind", ""))))
    return out


def _extract_consumable_events(canonical: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = canonical.get("events", {}) or {}
    raw = events.get("consumables", [])
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("kind") or "").strip().lower()
        if kind not in ("heal", "engine", "smoke"):
            continue
        entity_id = _safe_int(row.get("entity_id"))
        if entity_id is None:
            continue
        start_time = _safe_float(row.get("start_time"), 0.0)
        end_time = _safe_float(row.get("end_time"), 0.0)
        if end_time <= start_time:
            continue
        out.append(
            {
                "entity_id": int(entity_id),
                "kind": kind,
                "start_time": float(start_time),
                "end_time": float(end_time),
            }
        )
    out.sort(key=lambda item: (float(item.get("start_time", 0.0)), int(item.get("entity_id", -1)), str(item.get("kind", ""))))
    return out


def _smoke_snapshot_at(timeline: List[Dict[str, Any]], t: float) -> Optional[Dict[str, Any]]:
    if not timeline:
        return None
    if isinstance(timeline[0], dict) and ("start_time" in timeline[0] or "end_time" in timeline[0]):
        smokes: List[Dict[str, Any]] = []
        for puff in timeline:
            if not isinstance(puff, dict):
                continue
            start_time = float(puff.get("start_time", puff.get("time_s", 0.0)) or 0.0)
            duration_s = float(puff.get("duration_s", 0.0) or 0.0)
            if puff.get("end_time") is not None:
                end_time = float(puff.get("end_time") or start_time)
            elif duration_s > 0.0:
                end_time = start_time + duration_s
            else:
                continue
            if t + 1e-6 < start_time or t - 1e-6 > end_time:
                continue
            smokes.append(puff)
        if not smokes:
            return {"time_s": float(t), "smokes": []}
        return {"time_s": float(t), "smokes": smokes}
    last = timeline[0]
    for snap in timeline:
        if float(snap.get("time_s", 0.0)) <= t + 1e-6:
            last = snap
        else:
            break
    return last


def _capture_snapshot_at(timeline: List[Dict[str, Any]], t: float) -> Optional[Dict[str, Any]]:
    if not timeline:
        return None
    last = timeline[0]
    for snap in timeline:
        if float(snap.get("time_s", 0.0)) <= t + 1e-6:
            last = snap
        else:
            break
    return last


def _resolve_score_team_ids(canonical: Dict[str, Any], team_scores: Dict[int, int]) -> Tuple[Optional[int], Optional[int]]:
    meta = canonical.get("meta", {}) or {}
    local_team_id = _safe_int(meta.get("local_team_id"))
    enemy_team_id = _safe_int(meta.get("enemy_team_id"))

    ids = sorted(team_scores.keys())
    if local_team_id is None and ids:
        local_team_id = ids[0]
    if enemy_team_id is None and local_team_id is not None:
        enemy_team_id = next((tid for tid in ids if tid != local_team_id), None)
    if enemy_team_id is None and len(ids) >= 2:
        enemy_team_id = ids[1]
    return local_team_id, enemy_team_id


def _score_overlay_state(canonical: Dict[str, Any], snapshot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    team_scores: Dict[int, int] = {}
    team_win_score = 0

    if isinstance(snapshot, dict):
        snap_scores = snapshot.get("team_scores", {})
        if isinstance(snap_scores, dict):
            for key, value in snap_scores.items():
                team_id = _safe_int(key)
                score = _safe_int(value)
                if team_id is None or score is None:
                    continue
                team_scores[team_id] = score
        team_win_score = _safe_int(snapshot.get("team_win_score")) or 0

    if not team_scores:
        stats = canonical.get("stats", {}) or {}
        raw_final = stats.get("team_scores_final", {})
        if isinstance(raw_final, dict):
            for key, value in raw_final.items():
                team_id = _safe_int(key)
                score = _safe_int(value)
                if team_id is None or score is None:
                    continue
                team_scores[team_id] = score
        team_win_score = _safe_int(stats.get("team_win_score")) or team_win_score

    if not team_scores:
        return None

    local_team_id, enemy_team_id = _resolve_score_team_ids(canonical, team_scores)
    ids = sorted(team_scores.keys())
    left_id = local_team_id if local_team_id in team_scores else (ids[0] if ids else None)
    right_id = enemy_team_id if enemy_team_id in team_scores else next((tid for tid in ids if tid != left_id), None)
    if right_id is None and len(ids) >= 2:
        right_id = ids[1]

    left_score = team_scores.get(left_id, 0) if left_id is not None else 0
    right_score = team_scores.get(right_id, 0) if right_id is not None else 0
    return {
        "team_scores": team_scores,
        "team_win_score": team_win_score,
        "local_team_id": local_team_id,
        "enemy_team_id": enemy_team_id,
        "left_id": left_id,
        "right_id": right_id,
        "left_score": left_score,
        "right_score": right_score,
    }


def _battle_clock_full_length_s(canonical: Dict[str, Any]) -> float:
    full_length_s = 1200.0
    events = canonical.get("events", {}) or {}
    captures = events.get("captures", [])
    if isinstance(captures, list):
        for row in captures:
            if not isinstance(row, dict):
                continue
            tl = _safe_float(row.get("time_left_s"))
            if tl is None:
                continue
            if tl > full_length_s:
                full_length_s = float(tl)
    return full_length_s


def _battle_clock_seconds(canonical: Dict[str, Any], snapshot: Optional[Dict[str, Any]], t_replay: float) -> float:
    def _snapshot_float(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    if isinstance(snapshot, dict):
        elapsed_s = _snapshot_float(snapshot.get("time_elapsed_s"))
        if elapsed_s is not None and elapsed_s >= 0.0:
            return max(0.0, float(elapsed_s))
        time_left_s = _snapshot_float(snapshot.get("time_left_s"))
        if time_left_s is not None and time_left_s >= 0.0:
            full_length_s = _battle_clock_full_length_s(canonical)
            return max(0.0, float(full_length_s) - float(time_left_s))
    battle_start = float(canonical.get("stats", {}).get("battle_start_s", 0.0))
    return max(0.0, float(t_replay) - battle_start)


def _team_color_for_id(team_id: Optional[int], local_team_id: Optional[int], enemy_team_id: Optional[int]) -> Tuple[int, int, int]:
    if team_id is None or team_id < 0:
        return COLOR_UNKNOWN
    if local_team_id is not None and team_id == local_team_id:
        return COLOR_FRIENDLY
    if enemy_team_id is not None and team_id == enemy_team_id:
        return COLOR_ENEMY
    return COLOR_UNKNOWN


def _snapshot_team_score(snapshot: Dict[str, Any], team_id: Optional[int]) -> int:
    if team_id is None:
        return 0
    scores = snapshot.get("team_scores", {})
    if not isinstance(scores, dict):
        return 0
    return _safe_int(scores.get(str(team_id))) or _safe_int(scores.get(team_id)) or 0


def _normalized_snapshot_scores(snapshot: Optional[Dict[str, Any]]) -> Dict[int, int]:
    scores: Dict[int, int] = {}
    if not isinstance(snapshot, dict):
        return scores
    raw = snapshot.get("team_scores", {})
    if not isinstance(raw, dict):
        return scores
    for key, value in raw.items():
        team_id = _safe_int(key)
        score = _safe_int(value)
        if team_id is None or score is None:
            continue
        scores[int(team_id)] = int(score)
    return scores


def _ttw_anchor_snapshot(
    capture_timeline: List[Dict[str, Any]],
    snapshot: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(snapshot, dict):
        return None
    if not capture_timeline:
        return snapshot
    current_t = float(snapshot.get("time_s", 0.0) or 0.0)
    last_scores: Optional[Dict[int, int]] = None
    anchor: Optional[Dict[str, Any]] = None
    for row in capture_timeline:
        if not isinstance(row, dict):
            continue
        row_t = float(row.get("time_s", 0.0) or 0.0)
        if row_t > current_t + 1e-6:
            break
        scores = _normalized_snapshot_scores(row)
        if last_scores is None or scores != last_scores:
            anchor = row
            last_scores = scores
    return anchor or snapshot


def _cap_owner_team_id(cap: Dict[str, Any]) -> Optional[int]:
    if not isinstance(cap, dict):
        return None
    team_id = _safe_int(cap.get("team_id"))
    if team_id is not None and team_id >= 0:
        return team_id
    owner_team_id = _safe_int(cap.get("owner_team_id"))
    if owner_team_id is not None and owner_team_id >= 0:
        return owner_team_id
    return None


def _control_point_counts(snapshot: Optional[Dict[str, Any]]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    if not isinstance(snapshot, dict):
        return counts
    caps = snapshot.get("caps", [])
    if not isinstance(caps, list):
        return counts
    for cap in caps:
        if not isinstance(cap, dict) or not bool(cap.get("is_control_point", False)):
            continue
        if not bool(cap.get("is_enabled", True)):
            continue
        owner_team_id = _cap_owner_team_id(cap)
        if owner_team_id is None:
            continue
        counts[int(owner_team_id)] = counts.get(int(owner_team_id), 0) + 1
    return counts


def _scoring_cap_counts(snapshot: Optional[Dict[str, Any]]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    if not isinstance(snapshot, dict):
        return counts
    caps = snapshot.get("caps", [])
    if not isinstance(caps, list):
        return counts
    for cap in caps:
        if not isinstance(cap, dict) or not bool(cap.get("is_control_point", False)):
            continue
        if not bool(cap.get("is_enabled", True)):
            continue
        team_id = _safe_int(cap.get("team_id"))
        if team_id is None or team_id < 0:
            continue
        if bool(cap.get("has_invaders", False)) or bool(cap.get("both_inside", False)):
            continue
        progress = _safe_float(cap.get("progress"), 0.0) or 0.0
        if progress > 0.0001:
            continue
        counts[int(team_id)] = counts.get(int(team_id), 0) + 1
    return counts


def _estimate_one_cap_score_rate(
    capture_timeline: List[Dict[str, Any]],
    snapshot: Optional[Dict[str, Any]],
    team_ids: List[Optional[int]],
) -> Optional[float]:
    if not capture_timeline or not isinstance(snapshot, dict):
        return None
    current_t = float(snapshot.get("time_s", 0.0) or 0.0)
    recent = [row for row in capture_timeline if isinstance(row, dict) and float(row.get("time_s", 0.0) or 0.0) <= current_t + 1e-6]
    if len(recent) < 2:
        return None

    active_team_ids = [int(tid) for tid in team_ids if tid is not None]
    if not active_team_ids:
        return None

    positive_gain_total = 0.0
    cap_time_total = 0.0
    for prev, curr in zip(recent, recent[1:]):
        t1 = float(curr.get("time_s", 0.0) or 0.0)
        t0 = float(prev.get("time_s", 0.0) or 0.0)
        dt = t1 - t0
        if dt <= 0.0:
            continue
        counts = _scoring_cap_counts(prev)
        if not counts:
            continue
        segment_cap_time = 0.0
        for team_id in active_team_ids:
            cap_count = max(0, counts.get(team_id, 0))
            if cap_count <= 0:
                continue
            segment_cap_time += float(cap_count) * float(dt)
            delta = _snapshot_team_score(curr, team_id) - _snapshot_team_score(prev, team_id)
            if delta <= 0:
                continue
            if delta > 8:
                continue
            positive_gain_total += float(delta)
        if segment_cap_time <= 0.0:
            continue
        cap_time_total += segment_cap_time

    if positive_gain_total <= 0.0 or cap_time_total <= 0.0:
        return None
    return float(positive_gain_total) / float(cap_time_total)


def _format_ttw(seconds: Optional[float]) -> str:
    if seconds is None or not math.isfinite(float(seconds)) or float(seconds) <= 0.0:
        return "--:--"
    total = int(round(float(seconds)))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _time_to_victory_state(
    canonical: Dict[str, Any],
    capture_timeline: List[Dict[str, Any]],
    snapshot: Optional[Dict[str, Any]],
    state: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    team_win_score = max(1, int(state.get("team_win_score") or 0))
    left_id = _safe_int(state.get("left_id"))
    right_id = _safe_int(state.get("right_id"))
    left_score = int(state.get("left_score") or 0)
    right_score = int(state.get("right_score") or 0)
    one_cap_rate = _estimate_one_cap_score_rate(capture_timeline, snapshot, [left_id, right_id])
    current_counts = _scoring_cap_counts(snapshot)

    def _ttw(team_id: Optional[int], score: int) -> Optional[float]:
        if team_id is None or score >= team_win_score:
            return 0.0 if score >= team_win_score else None
        if one_cap_rate is None or one_cap_rate <= 0.0:
            return None
        cap_count = max(0, current_counts.get(int(team_id), 0))
        if cap_count <= 0:
            return None
        rate = float(one_cap_rate) * float(cap_count)
        remaining = max(0, team_win_score - score)
        return float(remaining) / float(rate)

    return {
        "left": _ttw(left_id, left_score),
        "right": _ttw(right_id, right_score),
    }


def _draw_score_overlay(
    img: Image.Image,
    canonical: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]],
    capture_timeline: List[Dict[str, Any]],
    canvas_size: int,
) -> None:
    state = _score_overlay_state(canonical, snapshot)
    if state is None:
        return

    team_win_score = int(state.get("team_win_score") or 0)
    local_team_id = _safe_int(state.get("local_team_id"))
    enemy_team_id = _safe_int(state.get("enemy_team_id"))
    left_id = _safe_int(state.get("left_id"))
    right_id = _safe_int(state.get("right_id"))
    left_score = int(state.get("left_score") or 0)
    right_score = int(state.get("right_score") or 0)
    left_color = _team_color_for_id(left_id, local_team_id, enemy_team_id)
    right_color = _team_color_for_id(right_id, local_team_id, enemy_team_id)

    bar_goal = max(1, team_win_score or left_score or right_score or 1)
    left_ratio = max(0.0, min(1.0, float(left_score) / float(bar_goal)))
    right_ratio = max(0.0, min(1.0, float(right_score) / float(bar_goal)))
    mid_x = canvas_size // 2
    center_gap = max(4, canvas_size // 210)
    bar_h = max(10, canvas_size // 100)
    bar_y = 8
    side_pad = max(8, canvas_size // 72)
    bar_radius = max(8, bar_h // 2 + 2)
    draw_rgba = ImageDraw.Draw(img, "RGBA")
    left_box = [side_pad, bar_y, mid_x - center_gap, bar_y + bar_h]
    right_box = [mid_x + center_gap, bar_y, canvas_size - side_pad, bar_y + bar_h]
    draw_rgba.rounded_rectangle(left_box, radius=bar_radius, fill=(WOWS_PANEL_INNER[0], WOWS_PANEL_INNER[1], WOWS_PANEL_INNER[2], 222), outline=(WOWS_OUTLINE[0], WOWS_OUTLINE[1], WOWS_OUTLINE[2], 165), width=1)
    draw_rgba.rounded_rectangle(right_box, radius=bar_radius, fill=(WOWS_PANEL_INNER[0], WOWS_PANEL_INNER[1], WOWS_PANEL_INNER[2], 222), outline=(WOWS_OUTLINE[0], WOWS_OUTLINE[1], WOWS_OUTLINE[2], 165), width=1)
    left_span = max(0, int(left_box[2] - left_box[0]))
    right_span = max(0, int(right_box[2] - right_box[0]))
    left_fill_w = int(round(left_span * left_ratio))
    right_fill_w = int(round(right_span * right_ratio))
    if left_fill_w > 0:
        fill_radius = max(3, min(bar_radius, left_fill_w // 2))
        draw_rgba.rounded_rectangle([left_box[0], left_box[1], left_box[0] + left_fill_w, left_box[3]], radius=fill_radius, fill=left_color + (225,))
    if right_fill_w > 0:
        fill_radius = max(3, min(bar_radius, right_fill_w // 2))
        draw_rgba.rounded_rectangle([right_box[2] - right_fill_w, right_box[1], right_box[2], right_box[3]], radius=fill_radius, fill=right_color + (225,))

    font_score_size = max(14, canvas_size // 36)
    left_txt = str(left_score)
    right_txt = str(right_score)
    sep_txt = ":"
    gap = 8

    left_sprite = _text_sprite(left_txt, font_score_size, left_color, (0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    sep_sprite = _text_sprite(sep_txt, font_score_size, WOWS_TEXT, (0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    right_sprite = _text_sprite(right_txt, font_score_size, right_color, (0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    if left_sprite is None or sep_sprite is None or right_sprite is None:
        return
    lw = left_sprite.width
    sw = sep_sprite.width
    rw = right_sprite.width
    total_w = lw + sw + rw + gap * 2
    x = canvas_size // 2 - total_w // 2
    y = bar_y + bar_h + 6

    score_pad_x = max(10, font_score_size // 2)
    score_pad_y = max(4, font_score_size // 5)
    score_box = [
        x - score_pad_x,
        y - score_pad_y,
        x + total_w + score_pad_x,
        y + max(left_sprite.height, sep_sprite.height, right_sprite.height) + score_pad_y,
    ]
    score_radius = max(10, (score_box[3] - score_box[1]) // 2)
    draw_rgba.rounded_rectangle(
        score_box,
        radius=score_radius,
        fill=(WOWS_PANEL_INNER[0], WOWS_PANEL_INNER[1], WOWS_PANEL_INNER[2], 220),
        outline=(WOWS_OUTLINE[0], WOWS_OUTLINE[1], WOWS_OUTLINE[2], 185),
        width=2,
    )
    draw_rgba.rounded_rectangle(
        [score_box[0] + 2, score_box[1] + 2, score_box[2] - 2, score_box[3] - 2],
        radius=max(8, score_radius - 2),
        outline=(WOWS_OUTLINE_SOFT[0], WOWS_OUTLINE_SOFT[1], WOWS_OUTLINE_SOFT[2], 150),
        width=1,
    )

    _paste_sprite(img, left_sprite, x, y)
    x += lw + gap
    _paste_sprite(img, sep_sprite, x, y)
    x += sw + gap
    _paste_sprite(img, right_sprite, x, y)

    ttw_snapshot = _ttw_anchor_snapshot(capture_timeline, snapshot)
    ttw_overlay_state = _score_overlay_state(canonical, ttw_snapshot) if ttw_snapshot is not None else state
    ttw_state = _time_to_victory_state(canonical, capture_timeline, ttw_snapshot, ttw_overlay_state or state)
    ttw_font_size = max(11, canvas_size // 56)
    left_ttw_sprite = _text_sprite(_format_ttw(ttw_state.get("left")), ttw_font_size, left_color, (0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    ttw_label_sprite = _text_sprite("Time to win", ttw_font_size, WOWS_TEXT_SUB, (0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    right_ttw_sprite = _text_sprite(_format_ttw(ttw_state.get("right")), ttw_font_size, right_color, (0, 0, 0), bold=True, stroke_width=1, stroke_fill=(0, 0, 0), face=INGAME_FONT_FACE)
    if left_ttw_sprite is None or ttw_label_sprite is None or right_ttw_sprite is None:
        return

    t_gap = max(8, ttw_font_size // 2)
    ttw_total_w = left_ttw_sprite.width + ttw_label_sprite.width + right_ttw_sprite.width + t_gap * 2
    ttw_x = canvas_size // 2 - ttw_total_w // 2
    ttw_y = score_box[3] + 4
    ttw_pad_x = max(8, ttw_font_size // 2)
    ttw_pad_y = max(3, ttw_font_size // 4)
    ttw_h = max(left_ttw_sprite.height, ttw_label_sprite.height, right_ttw_sprite.height)
    ttw_box = [
        ttw_x - ttw_pad_x,
        ttw_y - ttw_pad_y,
        ttw_x + ttw_total_w + ttw_pad_x,
        ttw_y + ttw_h + ttw_pad_y,
    ]
    ttw_radius = max(8, (ttw_box[3] - ttw_box[1]) // 2)
    draw_rgba.rounded_rectangle(
        ttw_box,
        radius=ttw_radius,
        fill=(WOWS_PANEL_INNER[0], WOWS_PANEL_INNER[1], WOWS_PANEL_INNER[2], 208),
        outline=(WOWS_OUTLINE_SOFT[0], WOWS_OUTLINE_SOFT[1], WOWS_OUTLINE_SOFT[2], 175),
        width=1,
    )
    _paste_sprite(img, left_ttw_sprite, ttw_x, ttw_y)
    ttw_x += left_ttw_sprite.width + t_gap
    _paste_sprite(img, ttw_label_sprite, ttw_x, ttw_y)
    ttw_x += ttw_label_sprite.width + t_gap
    _paste_sprite(img, right_ttw_sprite, ttw_x, ttw_y)


def _draw_clock_overlay(img: Image.Image, battle_clock_s: float, canvas_size: int, ui_font_size: int) -> None:
    mins, secs = divmod(max(0, int(battle_clock_s)), 60)
    clock_text = f"{mins}:{secs:02d}"
    font_size = max(ui_font_size + 4, canvas_size // 32)
    clock_sprite = _text_sprite(
        clock_text,
        font_size,
        WOWS_TEXT,
        shadow=(0, 0, 0),
        bold=True,
        stroke_width=1,
        stroke_fill=(0, 0, 0),
        face=INGAME_FONT_FACE,
    )
    if clock_sprite is None:
        return

    pad_x = max(10, font_size // 2)
    pad_y = max(5, font_size // 4)
    box_w = clock_sprite.width + pad_x * 2
    box_h = clock_sprite.height + pad_y * 2
    x0 = canvas_size - box_w - 10
    top_bar_h = max(10, canvas_size // 100)
    y0 = 8 + top_bar_h + 2
    x1 = x0 + box_w
    y1 = y0 + box_h
    radius = max(10, box_h // 2)

    draw_rgba = ImageDraw.Draw(img, "RGBA")
    draw_rgba.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=radius,
        fill=(WOWS_PANEL_INNER[0], WOWS_PANEL_INNER[1], WOWS_PANEL_INNER[2], 195),
        outline=(WOWS_OUTLINE[0], WOWS_OUTLINE[1], WOWS_OUTLINE[2], 190),
        width=2,
    )
    draw_rgba.rounded_rectangle(
        [x0 + 2, y0 + 2, x1 - 2, y1 - 2],
        radius=max(8, radius - 2),
        outline=(WOWS_OUTLINE_SOFT[0], WOWS_OUTLINE_SOFT[1], WOWS_OUTLINE_SOFT[2], 150),
        width=1,
    )
    _paste_sprite(img, clock_sprite, x0 + pad_x, y0 + pad_y - 1)

def _battle_result_text(canonical: Dict[str, Any]) -> Optional[Tuple[str, Tuple[int, int, int]]]:
    state = _score_overlay_state(canonical, None)
    if state is None:
        return None
    local_team_id = _safe_int(state.get("local_team_id"))
    enemy_team_id = _safe_int(state.get("enemy_team_id"))
    team_scores = dict(state.get("team_scores") or {})
    if local_team_id is None or enemy_team_id is None:
        return None
    local_score = _safe_int(team_scores.get(local_team_id))
    enemy_score = _safe_int(team_scores.get(enemy_team_id))
    if local_score is None or enemy_score is None:
        return None
    if local_score > enemy_score:
        return "VICTORY", WOWS_FRIENDLY
    if local_score < enemy_score:
        return "DEFEAT", WOWS_ENEMY
    return "DRAW", WOWS_TEXT_SUB


def _draw_battle_result_overlay(img: Image.Image, canonical: Dict[str, Any], canvas_size: int, alpha: int = 255) -> None:
    result = _battle_result_text(canonical)
    if result is None:
        return
    text, color = result
    font_size = max(48, canvas_size // 11)
    stroke_width = max(3, canvas_size // 210)
    glow_sprite = _text_sprite(
        text,
        font_size,
        color,
        shadow=None,
        bold=True,
        stroke_width=stroke_width + 1,
        stroke_fill=(8, 12, 18),
        face=INGAME_FONT_FACE,
    )
    sprite = _text_sprite(
        text,
        font_size,
        color,
        shadow=None,
        bold=True,
        stroke_width=stroke_width,
        stroke_fill=(8, 12, 18),
        face=INGAME_FONT_FACE,
    )
    if sprite is None:
        return
    alpha = max(0, min(255, int(alpha)))
    if glow_sprite is not None:
        glow_sprite = glow_sprite.copy()
        glow_mask = glow_sprite.getchannel("A").point(lambda value: int(value * min(210, alpha) / 255.0))
        glow_sprite.putalpha(glow_mask)
    if alpha < 255:
        sprite = sprite.copy()
        mask = sprite.getchannel("A").point(lambda value: int(value * alpha / 255.0))
        sprite.putalpha(mask)
    pad_x = max(22, canvas_size // 26)
    pad_y = max(11, canvas_size // 42)
    box_w = sprite.width + pad_x * 2
    box_h = sprite.height + pad_y * 2
    box_x = canvas_size // 2 - box_w // 2
    box_y = canvas_size // 2 - box_h // 2
    draw_rgba = ImageDraw.Draw(img, "RGBA")
    radius = max(12, canvas_size // 60)
    draw_rgba.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=(4, 8, 12, min(220, alpha)),
        outline=(color[0], color[1], color[2], min(165, alpha)),
        width=max(1, canvas_size // 300),
    )
    accent_inset = max(5, canvas_size // 125)
    accent_y_top = box_y + accent_inset
    accent_y_bottom = box_y + box_h - accent_inset
    accent_x0 = box_x + accent_inset
    accent_x1 = box_x + box_w - accent_inset
    draw_rgba.line([(accent_x0, accent_y_top), (accent_x1, accent_y_top)], fill=(color[0], color[1], color[2], min(110, alpha)), width=max(1, canvas_size // 360))
    draw_rgba.line([(accent_x0, accent_y_bottom), (accent_x1, accent_y_bottom)], fill=(255, 255, 255, min(70, alpha)), width=max(1, canvas_size // 420))
    if glow_sprite is not None:
        glow_x = box_x + pad_x - (glow_sprite.width - sprite.width) // 2
        glow_y = box_y + pad_y - (glow_sprite.height - sprite.height) // 2
        _paste_sprite(img, glow_sprite, glow_x, glow_y)
    _paste_sprite(img, sprite, box_x + pad_x, box_y + pad_y)


def _cap_label(index: Any, fallback_i: int) -> str:
    idx = _safe_int(index)
    if idx is None or idx < 0:
        return str(fallback_i + 1)
    if idx < 26:
        return chr(ord("A") + idx)
    return str(idx + 1)


def _draw_capture_overlay(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    canonical: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]],
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> None:
    draw_rgba = ImageDraw.Draw(img, "RGBA")
    meta = canonical.get("meta", {}) or {}
    scenario = str(meta.get("scenario") or "").strip().lower()
    control_points = meta.get("control_points", [])
    if not isinstance(control_points, list):
        control_points = []

    caps_by_id: Dict[int, Dict[str, Any]] = {}
    team_scores: Dict[int, int] = {}
    if isinstance(snapshot, dict):
        snap_scores = snapshot.get("team_scores", {})
        if isinstance(snap_scores, dict):
            for key, value in snap_scores.items():
                team_id = _safe_int(key)
                score = _safe_int(value)
                if team_id is None or score is None:
                    continue
                team_scores[team_id] = score
        for cap in snapshot.get("caps", []):
            if not isinstance(cap, dict):
                continue
            cap_id = _safe_int(cap.get("entity_id"))
            if cap_id is None:
                continue
            caps_by_id[cap_id] = cap

    if caps_by_id:
        if control_points:
            filtered = [cp for cp in control_points if _safe_int(cp.get("entity_id")) in caps_by_id]
            if filtered:
                control_points = filtered
            else:
                control_points = list(caps_by_id.values())
        else:
            control_points = list(caps_by_id.values())

    if not control_points:
        return

    local_team_id, enemy_team_id = _resolve_score_team_ids(canonical, team_scores)
    if local_team_id is None:
        local_team_id = _safe_int(meta.get("local_team_id"))
    if enemy_team_id is None:
        enemy_team_id = _safe_int(meta.get("enemy_team_id"))

    font = _load_font(max(10, canvas_size // 70), bold=True, face=INGAME_FONT_FACE)

    def _as_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    ordered = sorted(control_points, key=lambda row: (_safe_int(row.get("index")) if _safe_int(row.get("index")) is not None else 999, _safe_int(row.get("entity_id")) or 0))
    for i, cp in enumerate(ordered):
        if not isinstance(cp, dict):
            continue
        cp_id = _safe_int(cp.get("entity_id"))
        current = caps_by_id.get(cp_id, cp) if cp_id is not None else cp
        zone_type = _safe_int(current.get("zone_type"))
        if zone_type is None:
            zone_type = _safe_int(cp.get("zone_type"))
        zone_params_id = _safe_int(current.get("zone_params_id"))
        if zone_params_id is None:
            zone_params_id = _safe_int(cp.get("zone_params_id"))
        is_control_point = bool(current.get("is_control_point", cp.get("is_control_point", False)))
        is_enabled = bool(current.get("is_enabled", cp.get("is_enabled", True)))
        is_visible = bool(current.get("is_visible", cp.get("is_visible", True)))

        x = _as_float(current.get("x", cp.get("x", 0.0)), 0.0)
        z = _as_float(current.get("z", cp.get("z", 0.0)), 0.0)
        px, py = _to_px(x, z, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)

        radius_world = _as_float(current.get("radius", cp.get("radius", 0.0)), 0.0)
        if world_bounds is None:
            world_span = 2.0 * half
        else:
            world_span = max(float(world_bounds[1]) - float(world_bounds[0]), float(world_bounds[3]) - float(world_bounds[2]))
        if map_rect is None:
            usable_span = canvas_size - 2 * margin
        else:
            usable_span = min(int(map_rect[2]) - int(map_rect[0]), int(map_rect[3]) - int(map_rect[1]))
        if radius_world > 0.0:
            radius_px = max(12, int(radius_world / max(1e-6, world_span) * usable_span * 1))
        else:
            radius_px = max(14, int(usable_span * 0.03))

        cap_team_id = _safe_int(current.get("team_id"))
        if cap_team_id is None:
            cap_team_id = _safe_int(cp.get("team_id"))
        invader_team_id = _safe_int(current.get("invader_team_id"))
        has_invaders = bool(current.get("has_invaders", False))
        both_inside = bool(current.get("both_inside", False))
        progress = max(0.0, min(1.0, _as_float(current.get("progress", 0.0), 0.0)))

        if scenario == "armsrace" and zone_type == 6 and not is_control_point:
            if not (is_enabled or is_visible):
                continue
            buff_radius_px = max(8, min(16, int(radius_px * 0.35)))
            glow_radius = buff_radius_px + 5
            buff_color = (246, 214, 104)
            draw_rgba.ellipse(
                [px - glow_radius, py - glow_radius, px + glow_radius, py + glow_radius],
                fill=(buff_color[0], buff_color[1], buff_color[2], 44),
            )
            draw.ellipse([px - buff_radius_px, py - buff_radius_px, px + buff_radius_px, py + buff_radius_px], outline=buff_color, width=2)
            kind = _arms_race_zone_kind(zone_params_id)
            icon = _load_arms_race_zone_icon(kind or "")
            if icon is not None:
                icon_size = max(14, min(28, buff_radius_px * 2 + 8))
                icon_img = ImageOps.contain(icon, (icon_size, icon_size))
                shadow = Image.new("RGBA", icon_img.size, (0, 0, 0, 0))
                shadow_alpha = icon_img.getchannel("A")
                shadow.putalpha(shadow_alpha)
                shadow = ImageEnhance.Brightness(shadow).enhance(0.0)
                shadow = shadow.filter(ImageFilter.GaussianBlur(radius=1.1))
                _paste_center_rgba(img, shadow, px + 1, py + 1)
                _paste_center_rgba(img, icon_img, px, py)
            else:
                diamond = [
                    (px, py - buff_radius_px + 1),
                    (px + buff_radius_px - 1, py),
                    (px, py + buff_radius_px - 1),
                    (px - buff_radius_px + 1, py),
                ]
                draw_rgba.polygon(diamond, fill=(255, 240, 170, 88))
                draw.line([diamond[0], diamond[1], diamond[2], diamond[3], diamond[0]], fill=(255, 238, 168), width=2)
            continue

        if is_control_point and not (is_enabled or is_visible or has_invaders or both_inside or progress > 0.0):
            continue

        if both_inside:
            ring_color = (240, 200, 90)
        elif has_invaders:
            ring_color = _team_color_for_id(invader_team_id, local_team_id, enemy_team_id)
        else:
            # Neutral points must stay gray/white until captured by a team.
            if cap_team_id is None or cap_team_id < 0:
                ring_color = (205, 205, 205)
            else:
                ring_color = _team_color_for_id(cap_team_id, local_team_id, enemy_team_id)

        if both_inside:
            fill_alpha = 58
        elif has_invaders:
            fill_alpha = 52
        elif cap_team_id is None or cap_team_id < 0:
            fill_alpha = 26
        else:
            fill_alpha = 42
        fill_color = (ring_color[0], ring_color[1], ring_color[2], fill_alpha)
        draw_rgba.ellipse([px - radius_px, py - radius_px, px + radius_px, py + radius_px], fill=fill_color)
        draw.ellipse([px - radius_px, py - radius_px, px + radius_px, py + radius_px], outline=ring_color, width=2)

        if has_invaders and progress > 0.0:
            arc_pad = max(2, radius_px // 6)
            draw.arc(
                [px - radius_px + arc_pad, py - radius_px + arc_pad, px + radius_px - arc_pad, py + radius_px - arc_pad],
                start=-90,
                end=-90 + int(360 * progress),
                fill=ring_color,
                width=3,
            )

        label = _cap_label(current.get("index", cp.get("index")), i)
        status = ""
        if both_inside:
            status = "contested"

        text = f"{label} {status}".strip()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = px - tw // 2
        ty = py - radius_px - th - 2
        draw.text((tx + 1, ty + 1), text, fill=(0, 0, 0), font=font)
        draw.text((tx, ty), text, fill=ring_color, font=font)
        draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=ring_color, outline=ring_color)


def _yaw_to_heading_deg(yaw_value: Any) -> float:
    try:
        yaw = float(yaw_value)
    except (TypeError, ValueError):
        return 0.0
    if abs(yaw) <= (2.0 * math.pi + 0.5):
        return math.degrees(yaw) % 360.0
    return yaw % 360.0


def _angle_delta_deg(target: float, base: float) -> float:
    return ((target - base + 180.0) % 360.0) - 180.0


def _lerp_angle_deg(base: float, target: float, factor: float) -> float:
    return (base + _angle_delta_deg(target, base) * factor) % 360.0


def _movement_heading_deg(points: List[Dict[str, Any]], window: int = 10, min_segment: float = 0.35) -> float | None:
    if len(points) < 2:
        return None
    tail = points[-window:]
    sum_dx = 0.0
    sum_dz = 0.0
    for i in range(1, len(tail)):
        x1 = float(tail[i - 1].get("x", 0.0))
        z1 = float(tail[i - 1].get("z", 0.0))
        x2 = float(tail[i].get("x", 0.0))
        z2 = float(tail[i].get("z", 0.0))
        dx = x2 - x1
        dz = z2 - z1
        dist = math.hypot(dx, dz)
        if dist < min_segment:
            continue
        sum_dx += dx
        sum_dz += dz
    if abs(sum_dx) < 1e-6 and abs(sum_dz) < 1e-6:
        return None
    return math.degrees(math.atan2(sum_dx, sum_dz)) % 360.0


def _movement_heading_metrics(points: List[Dict[str, Any]], window: int = 10, min_segment: float = 0.35) -> Tuple[float | None, float]:
    if len(points) < 2:
        return None, 0.0
    tail = points[-window:]
    sum_dx = 0.0
    sum_dz = 0.0
    total_dist = 0.0
    for i in range(1, len(tail)):
        x1 = float(tail[i - 1].get("x", 0.0))
        z1 = float(tail[i - 1].get("z", 0.0))
        x2 = float(tail[i].get("x", 0.0))
        z2 = float(tail[i].get("z", 0.0))
        dx = x2 - x1
        dz = z2 - z1
        dist = math.hypot(dx, dz)
        if dist < min_segment:
            continue
        sum_dx += dx
        sum_dz += dz
        total_dist += dist
    if abs(sum_dx) < 1e-6 and abs(sum_dz) < 1e-6:
        return None, float(total_dist)
    return math.degrees(math.atan2(sum_dx, sum_dz)) % 360.0, float(total_dist)


def _yaw_mean_heading_deg(points: List[Dict[str, Any]], window: int = 10) -> float:
    tail = points[-window:]
    vals = [_yaw_to_heading_deg(p.get("yaw", 0.0)) for p in tail]
    if not vals:
        return 0.0
    s = sum(math.sin(math.radians(v)) for v in vals)
    c = sum(math.cos(math.radians(v)) for v in vals)
    if abs(s) < 1e-9 and abs(c) < 1e-9:
        return vals[-1]
    return math.degrees(math.atan2(s, c)) % 360.0


def _stable_heading_deg(points: List[Dict[str, Any]], previous: float | None = None, max_step_deg: float = 30.0) -> float:
    if not points:
        return previous if previous is not None else 0.0

    # Use yaw-only so the icon always reflects the ship's nose, even when reversing.
    raw = _yaw_mean_heading_deg(points, window=10)

    if previous is None:
        return raw

    delta = _angle_delta_deg(raw, previous)
    if delta > max_step_deg:
        raw = (previous + max_step_deg) % 360.0
    elif delta < -max_step_deg:
        raw = (previous - max_step_deg) % 360.0

    return _lerp_angle_deg(previous, raw, 0.55)


def _resolved_ship_heading_deg(
    points: List[Dict[str, Any]],
    observed_heading_deg: float,
    previous_heading_deg: float | None = None,
    allow_movement_fallback: bool = True,
) -> float:
    if not allow_movement_fallback or len(points) < 2:
        return observed_heading_deg

    movement_heading, movement_dist = _movement_heading_metrics(points, window=min(6, len(points)), min_segment=0.45)
    if movement_heading is None:
        return observed_heading_deg

    delta = abs(_angle_delta_deg(observed_heading_deg, movement_heading))
    # Only correct the brief "sideways" cases. Do not override true reversing
    # behavior, which would look closer to 180 degrees from movement.
    if movement_dist >= 1.2 and 40.0 <= delta <= 140.0:
        candidate_forward = movement_heading
        candidate_reverse = (movement_heading + 180.0) % 360.0
        if previous_heading_deg is None:
            delta_forward = abs(_angle_delta_deg(candidate_forward, observed_heading_deg))
            delta_reverse = abs(_angle_delta_deg(candidate_reverse, observed_heading_deg))
            return candidate_forward if delta_forward <= delta_reverse else candidate_reverse

        prev_to_forward = abs(_angle_delta_deg(candidate_forward, previous_heading_deg))
        prev_to_reverse = abs(_angle_delta_deg(candidate_reverse, previous_heading_deg))
        chosen = candidate_forward if prev_to_forward <= prev_to_reverse else candidate_reverse

        max_step_deg = 28.0
        step = _angle_delta_deg(chosen, previous_heading_deg)
        if step > max_step_deg:
            chosen = (previous_heading_deg + max_step_deg) % 360.0
        elif step < -max_step_deg:
            chosen = (previous_heading_deg - max_step_deg) % 360.0
        return chosen
    return observed_heading_deg


def _clamp_track_to_time(points: List[Dict[str, Any]], t_limit: float) -> List[Dict[str, Any]]:
    if not points:
        return []
    out = [p for p in points if float(p.get("t", 0.0)) <= t_limit + 1e-6]
    if out:
        return out
    return [points[0]]


def render_static(canonical: Dict[str, Any], canvas_size: int = 1024, show_labels: bool = True, show_grid: bool = True, bg_color: Tuple[int, int, int] = COLOR_BG) -> Image.Image:
    font = _load_font(12, bold=True, face=INGAME_FONT_FACE)
    canvas_size = _native_map_size(canonical, canvas_size)
    half = _world_half(canonical)
    world_bounds = _world_bounds(canonical)
    margin = _map_margin(canonical)
    map_rect = _map_projection_rect(canonical, canvas_size, margin)
    death_times = _find_death_times(canonical)
    explicit_death_times = _find_explicit_death_times(canonical)
    render_tracks = _normalize_render_tracks(canonical)
    health_timelines = _extract_health_timelines(canonical)
    player_status_timeline = _extract_player_status_timeline(canonical)
    player_track_index = _build_player_track_index(render_tracks)
    hide_player_card = bool((canonical.get("meta", {}) or {}).get("hide_player_card", False))
    layout = _render_layout(render_tracks, canvas_size, hide_player_card=hide_player_card)
    img = _build_frame_base(canonical, layout, margin, show_grid, 12, bg_color=bg_color, map_rect=map_rect)
    draw = ImageDraw.Draw(img)
    battle_end = float(canonical.get("stats", {}).get("battle_end_s", 0.0))
    if battle_end <= 0:
        battle_end = max((float(p.get("t", 0.0)) for t in render_tracks.values() for p in t.get("points", [])), default=0.0)
    spot_timeout = 10.0
    capture_timeline = _capture_timeline(canonical)
    smoke_timeline = _smoke_timeline(canonical)
    sensor_events = _extract_sensor_events(canonical)
    consumable_events = _extract_consumable_events(canonical)
    capture_snapshot = _capture_snapshot_at(capture_timeline, battle_end)
    smoke_snapshot = _smoke_snapshot_at(smoke_timeline, battle_end)
    sensor_by_entity: Dict[int, List[Dict[str, Any]]] = {}
    for row in sensor_events:
        eid = _safe_int(row.get("entity_id"))
        if eid is None:
            continue
        sensor_by_entity.setdefault(int(eid), []).append(row)
    consumable_by_entity: Dict[int, List[Dict[str, Any]]] = {}
    for row in consumable_events:
        eid = _safe_int(row.get("entity_id"))
        if eid is None:
            continue
        consumable_by_entity.setdefault(int(eid), []).append(row)
    torpedo_tracks = _extract_torpedo_tracks(canonical)
    squadron_tracks = _extract_squadron_tracks(canonical)
    kill_feed = _extract_kill_feed(canonical)

    _draw_capture_overlay(img, draw, canonical, capture_snapshot, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
    _draw_smoke_overlay(img, draw, smoke_snapshot, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
    _draw_sensor_overlay(
        img,
        draw,
        sensor_events,
        render_tracks,
        battle_end,
        half,
        canvas_size,
        margin,
        world_bounds=world_bounds,
        map_rect=map_rect,
        spot_timeout=spot_timeout,
        death_times=death_times,
    )
    _draw_torpedoes(draw, torpedo_tracks, battle_end, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
    _draw_squadrons(img, draw, squadron_tracks, battle_end, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)

    ordered = sorted(render_tracks.items(), key=lambda kv: kv[1].get("team_side", "unknown"))
    for entity_key, track in ordered:
        pts = list(track.get("points", []) or [])
        if not pts:
            continue
        ship_type = _ship_type(track.get("ship_id"))
        ship_class = _ship_class_code(track.get("ship_id"))
        is_local_player = _is_local_player_track(canonical, track)
        death_t = death_times.get(str(entity_key))
        explicit_death_t = explicit_death_times.get(str(entity_key))
        if bool(track.get("always_unspotted", False)):
            death_t = explicit_death_t
        health = _health_state_at(health_timelines, entity_key, battle_end)
        health_sunk = health is not None and not bool(health.get("alive", True))
        if bool(track.get("always_unspotted", False)):
            sunk = death_t is not None and battle_end >= death_t
        else:
            sunk = (death_t is not None and battle_end >= death_t) or health_sunk
        render_pts = _clamp_track_to_time(pts, float(death_t)) if sunk and death_t is not None else pts
        last_t = float(render_pts[-1].get("t", 0.0))
        spotted = (battle_end - last_t) <= spot_timeout and not bool(track.get("always_unspotted", False))
        ever_spotted = (not bool(track.get("always_unspotted", False))) and bool(render_pts)
        color = _status_color(_color_side(track), spotted=spotted, sunk=sunk, ever_spotted=ever_spotted)
        placeholder = _friendly_spawn_placeholder_state(track)
        first_real_t = float(track.get("first_real_t", 0.0) or 0.0)
        placeholder_only = (
            isinstance(placeholder, dict)
            and (not sunk)
            and battle_end + 1e-6 < first_real_t
        )
        stale = (not placeholder_only) and _friendly_stale_marker(_color_side(track), spotted=spotted, sunk=sunk)
        marker_color = (245, 245, 245) if is_local_player and not sunk else color
        if placeholder_only:
            ex, ey = _to_px(
                float(placeholder.get("x", 0.0) or 0.0),
                float(placeholder.get("z", 0.0) or 0.0),
                half,
                canvas_size,
                margin,
                world_bounds=world_bounds,
                map_rect=map_rect,
            )
            placeholder_heading_deg = _yaw_to_heading_deg(float(placeholder.get("yaw", 0.0) or 0.0))
            _draw_ship_marker(
                img,
                draw,
                ex,
                ey,
                ship_type,
                ship_class,
                (245, 245, 245) if is_local_player else COLOR_FRIENDLY,
                placeholder_heading_deg,
                _ship_name(track.get("ship_id")) or track.get("player_name"),
                size=8,
                sunk=False,
                stale=True,
                consumable_kind=None,
            )
        else:
            marker_point = render_pts[-1]
            heading_deg = _resolved_ship_heading_deg(
                render_pts,
                _yaw_to_heading_deg(marker_point.get("yaw", 0.0)),
                previous_heading_deg=None,
                allow_movement_fallback=not bool(track.get("always_unspotted", False)),
            )
            poly = [_to_px(float(p.get("x", 0.0)), float(p.get("z", 0.0)), half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect) for p in render_pts]
            ex, ey = poly[-1]
            _draw_ship_marker(
                img,
                draw,
                ex,
                ey,
                ship_type,
                ship_class,
                marker_color,
                heading_deg,
                _ship_name(track.get("ship_id")) or track.get("player_name"),
                size=8,
                sunk=sunk,
                stale=stale,
                consumable_kind=(
                    (
                        _active_sensor_kind(
                            sensor_by_entity,
                            _safe_int(track.get("entity_id")) or _safe_int(entity_key) or 0,
                            battle_end,
                        )
                        or _active_consumable_kind(
                            consumable_by_entity,
                            _safe_int(track.get("entity_id")) or _safe_int(entity_key) or 0,
                            battle_end,
                        )
                    )
                    if not sunk
                    else None
                ),
            )
        if health is not None and not placeholder_only:
            _draw_hp_bar(draw, ex, ey + 13, 28, 5, float(health.get("ratio", 0.0)), color, sunk=sunk or (not bool(health.get("alive", True))))

        if show_labels:
            player_name = track.get("player_name") or f"entity_{entity_key}"
            ship_name = _ship_name(track.get("ship_id"))
            if ship_name and player_name:
                label = f"{ship_name} / {player_name}"
            elif ship_name:
                label = ship_name
            else:
                label = player_name
            draw.text((ex + 8, ey - 8), str(label), fill=marker_color, font=font)

    duration = int(battle_end)
    duration_sprite = _text_sprite(f"duration={duration}s tracked={len(render_tracks)}", 12, (220, 220, 220), face=INGAME_FONT_FACE)
    _paste_sprite(img, duration_sprite, 10, canvas_size - 22)
    _draw_score_overlay(img, canonical, capture_snapshot, capture_timeline, canvas_size)
    _draw_battle_result_overlay(img, canonical, canvas_size)
    status = _player_status_at(player_status_timeline, battle_end)
    frame_layout = _layout_for_player_status(layout, status)
    if not hide_player_card:
        _draw_player_status_panel(
            img,
            draw,
            canonical,
            render_tracks,
            health_timelines,
            player_status_timeline,
            battle_end,
            frame_layout,
            player_track_index=player_track_index,
        )
    _draw_kill_feed_panel(img, draw, canonical, render_tracks, kill_feed, battle_end, frame_layout)
    _draw_lineup_panel(img, draw, frame_layout, current_t=battle_end, death_times=death_times, health_timelines=health_timelines)
    return img


def _draw_sensor_overlay(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    sensors: List[Dict[str, Any]],
    render_tracks: Dict[str, Dict[str, Any]],
    t: float,
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
    spot_timeout: float = 6.0,
    death_times: Dict[str, float] | None = None,
) -> None:
    if not sensors:
        return
    if world_bounds is None:
        world_span = 2.0 * half
    else:
        world_span = max(float(world_bounds[1]) - float(world_bounds[0]), float(world_bounds[3]) - float(world_bounds[2]))
    if map_rect is None:
        usable_span = canvas_size - 2 * margin
    else:
        usable_span = min(int(map_rect[2]) - int(map_rect[0]), int(map_rect[3]) - int(map_rect[1]))

    track_by_id: Dict[int, Dict[str, Any]] = {}
    for key, track in render_tracks.items():
        if not isinstance(track, dict):
            continue
        eid = _safe_int(track.get("entity_id"))
        if eid is None:
            eid = _safe_int(key)
        if eid is None:
            continue
        track_by_id[int(eid)] = track

    draw_rgba = ImageDraw.Draw(img, "RGBA")
    for sensor in sensors:
        start_time = float(sensor.get("start_time", 0.0))
        end_time = float(sensor.get("end_time", 0.0))
        if t < start_time or t > end_time:
            continue
        entity_id = _safe_int(sensor.get("entity_id"))
        if entity_id is None:
            continue
        track = track_by_id.get(int(entity_id))
        if not track:
            continue
        if death_times:
            death_t = death_times.get(str(entity_id))
            if death_t is not None and float(t) >= float(death_t):
                continue
        side = str(track.get("team_side") or "unknown")
        points = list(track.get("points", []) or [])
        if not points:
            continue
        times = [float(p.get("t", 0.0)) for p in points]
        idx = bisect_right(times, t) - 1
        if idx < 0:
            continue
        last_t = times[idx]
        spotted = (t - last_t) <= spot_timeout and not bool(track.get("always_unspotted", False))
        kind = str(sensor.get("kind") or "").lower()
        # For enemy ships, keep standard spotting rules for most overlays, but
        # ALWAYS show active radar/hydro circles even if the ship itself is not
        # currently spotted. This makes enemy radar usage visible in the
        # minimap timeline.
        if side == "enemy" and not spotted and kind not in ("radar", "hydro"):
            continue
        state = _ship_state_at(track, t)
        if state is None:
            continue
        x = float(state.get("x", 0.0))
        z = float(state.get("z", 0.0))
        radius_world = float(sensor.get("radius", 0.0))
        if radius_world <= 0.0:
            continue
        px, py = _to_px(x, z, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        radius_px = max(6, int(radius_world / max(1e-6, world_span) * usable_span * 0.92))

        base = COLOR_FRIENDLY if side == "friendly" else COLOR_ENEMY if side == "enemy" else WOWS_NEUTRAL
        if kind == "radar":
            outline_alpha = 150
            fill_alpha = 24
            width = 2
        else:
            outline_alpha = 110
            fill_alpha = 16
            width = 1
        outline = (base[0], base[1], base[2], outline_alpha)
        fill = (base[0], base[1], base[2], fill_alpha)
        draw_rgba.ellipse([px - radius_px, py - radius_px, px + radius_px, py + radius_px], fill=fill, outline=outline, width=width)


def _draw_smoke_overlay(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    snapshot: Optional[Dict[str, Any]],
    half: float,
    canvas_size: int,
    margin: int,
    world_bounds: Tuple[float, float, float, float] | None = None,
    map_rect: Tuple[int, int, int, int] | None = None,
) -> None:
    if not snapshot or not isinstance(snapshot, dict):
        return
    smokes = snapshot.get("smokes", [])
    if not isinstance(smokes, list) or not smokes:
        return

    if world_bounds is None:
        world_span = 2.0 * half
    else:
        world_span = max(float(world_bounds[1]) - float(world_bounds[0]), float(world_bounds[3]) - float(world_bounds[2]))
    if map_rect is None:
        usable_span = canvas_size - 2 * margin
    else:
        usable_span = min(int(map_rect[2]) - int(map_rect[0]), int(map_rect[3]) - int(map_rect[1]))

    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for smoke in smokes:
        if not isinstance(smoke, dict):
            continue
        entity_id = _safe_int(smoke.get("entity_id")) or 0
        grouped.setdefault(entity_id, []).append(smoke)

    for entity_id, items in grouped.items():
        active_items = [s for s in items if bool(s.get("active", True))]
        if not active_items:
            continue
        active_items.sort(key=lambda s: int(_safe_int(s.get("index")) or 0))
        px_points: List[Tuple[int, int]] = []
        radii: List[int] = []
        for smoke in active_items:
            x = float(smoke.get("x", 0.0) or 0.0)
            z = float(smoke.get("z", 0.0) or 0.0)
            radius_world = float(smoke.get("radius", 0.0) or 0.0)
            px, py = _to_px(x, z, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
            if radius_world > 0.0:
                radius_px = max(8, int(radius_world / max(1e-6, world_span) * usable_span * 0.92))
            else:
                radius_px = max(10, int(usable_span * 0.02))
            px_points.append((int(px), int(py)))
            radii.append(radius_px)

        if not px_points:
            continue

        radius_px = int(_median_value(radii)) if radii else max(10, int(usable_span * 0.02))

        def _stamp_cloud(cx: float, cy: float, scale_key: int = 100) -> None:
            sprite = _smoke_cloud_sprite(radius_px, scale_key)
            if sprite is not None:
                _paste_center_rgba(img, sprite, int(round(cx)), int(round(cy)))

        if len(px_points) == 1:
            px, py = px_points[0]
            _stamp_cloud(float(px), float(py), 100)
        else:
            for idx in range(len(px_points) - 1):
                ax, ay = px_points[idx]
                bx, by = px_points[idx + 1]
                dx = float(bx - ax)
                dy = float(by - ay)
                dist = math.hypot(dx, dy)
                steps = max(1, int(math.ceil(dist / max(6.0, radius_px * 0.48))))
                for step_idx in range(steps + 1):
                    frac = float(step_idx) / float(steps)
                    scale_key = 100
                    if (idx + step_idx) % 3 == 1:
                        scale_key = 90
                    elif (idx + step_idx) % 3 == 2:
                        scale_key = 108
                    _stamp_cloud(ax + dx * frac, ay + dy * frac, scale_key)


def _detect_action_start(canonical: Dict[str, Any]) -> float:
    """Return the earliest time any entity moves significantly.

    Falls back to ``battle_start_s`` if no movement is detected.
    """
    tracks = canonical.get("tracks", {}) or {}
    earliest = None
    for track in tracks.values():
        points = track.get("points") or []
        if len(points) < 2:
            continue
        x0 = float(points[0].get("x", 0.0))
        z0 = float(points[0].get("z", 0.0))
        for p in points[1:]:
            dx = abs(float(p.get("x", 0.0)) - x0)
            dz = abs(float(p.get("z", 0.0)) - z0)
            if dx > _MOVEMENT_THRESHOLD or dz > _MOVEMENT_THRESHOLD:
                t = float(p.get("t", 0.0))
                if earliest is None or t < earliest:
                    earliest = t
                break
    if earliest is not None:
        return earliest
    return float(canonical.get("stats", {}).get("battle_start_s", 0.0))


def _effective_render_start(canonical: Dict[str, Any]) -> float:
    """Compute the replay-time at which rendering should begin."""
    battle_start = float(canonical.get("stats", {}).get("battle_start_s", 0.0))
    action_start = _detect_action_start(canonical)
    if action_start > battle_start + 10.0:
        return max(0.0, action_start - RENDER_PRESTART_LEAD_S)
    return max(0.0, battle_start - RENDER_PRESTART_LEAD_S)


def estimate_animation_frame_count(canonical: Dict[str, Any], speed: float = 3.0) -> int:
    step = max(0.05, float(speed))
    battle_end = float(canonical.get("stats", {}).get("battle_end_s", 0.0))
    render_start = _effective_render_start(canonical)
    max_clock = max(0.0, battle_end - render_start)
    if max_clock <= 0:
        tracks = canonical.get("tracks", {}) or {}
        max_clock = max(
            (float(p.get("t", 0.0)) for t in tracks.values() for p in (t.get("points", []) or [])),
            default=0.0,
        )
    return max(1, int(math.floor(max_clock / step)) + 2)


def iter_animation_frames(canonical: Dict[str, Any], canvas_size: int = 600, speed: float = 3.0, show_grid: bool = True):
    canvas_size = _native_map_size(canonical, canvas_size)
    half = _world_half(canonical)
    world_bounds = _world_bounds(canonical)
    margin = _map_margin(canonical)
    map_rect = _map_projection_rect(canonical, canvas_size, margin)
    step = max(0.05, float(speed))
    death_times = _find_death_times(canonical)
    explicit_death_times = _find_explicit_death_times(canonical)
    render_tracks = _normalize_render_tracks(canonical)
    health_timelines = _extract_health_timelines(canonical)
    player_status_timeline = _extract_player_status_timeline(canonical)
    player_track_index = _build_player_track_index(render_tracks)
    hide_player_card = bool((canonical.get("meta", {}) or {}).get("hide_player_card", False))
    layout = _render_layout(render_tracks, canvas_size, hide_player_card=hide_player_card)
    prepared_tracks = _prepare_track_render_data(render_tracks, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
    battle_end = float(canonical.get("stats", {}).get("battle_end_s", 0.0))
    if battle_end <= 0:
        battle_end = max((float(p.get("t", 0.0)) for t in render_tracks.values() for p in t.get("points", [])), default=0.0)
    render_start = _effective_render_start(canonical)
    max_clock = max(0.0, float(battle_end) - float(render_start))
    spot_timeout = max(6.0, step * 1.5)
    capture_timeline = _capture_timeline(canonical)
    smoke_timeline = _smoke_timeline(canonical)
    sensor_events = _extract_sensor_events(canonical)
    consumable_events = _extract_consumable_events(canonical)
    sensor_by_entity: Dict[int, List[Dict[str, Any]]] = {}
    for row in sensor_events:
        eid = _safe_int(row.get("entity_id"))
        if eid is None:
            continue
        sensor_by_entity.setdefault(int(eid), []).append(row)
    consumable_by_entity: Dict[int, List[Dict[str, Any]]] = {}
    for row in consumable_events:
        eid = _safe_int(row.get("entity_id"))
        if eid is None:
            continue
        consumable_by_entity.setdefault(int(eid), []).append(row)
    artillery_traces = _extract_artillery_traces(canonical)
    torpedo_tracks = _extract_torpedo_tracks(canonical)
    squadron_tracks = _extract_squadron_tracks(canonical)
    kill_feed = _extract_kill_feed(canonical)
    heading_memory: Dict[str, float] = {}
    ever_spotted_memory: Dict[str, bool] = {}
    heading_debug_filters = _heading_debug_filters()
    heading_debug_samples: List[Dict[str, Any]] = []
    ui_font_size = max(11, canvas_size // 56)
    marker_size = max(6, canvas_size // 96)
    base_frame = _build_frame_base(canonical, layout, margin, show_grid, ui_font_size, map_rect=map_rect)
    total_frames = max(1, int(math.floor(max_clock / step)) + 2)
    result_frames = max(14, min(24, total_frames))

    t = 0.0
    frame_idx = 0
    while t <= max_clock + step:
        t_replay = t + render_start
        img = base_frame.copy()
        draw = ImageDraw.Draw(img)
        capture_snapshot = _capture_snapshot_at(capture_timeline, t_replay)
        smoke_snapshot = _smoke_snapshot_at(smoke_timeline, t_replay)
        _draw_capture_overlay(img, draw, canonical, capture_snapshot, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        _draw_smoke_overlay(img, draw, smoke_snapshot, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        _draw_sensor_overlay(
            img,
            draw,
            sensor_events,
            render_tracks,
            t_replay,
            half,
            canvas_size,
            margin,
            world_bounds=world_bounds,
            map_rect=map_rect,
            spot_timeout=spot_timeout,
            death_times=death_times,
        )
        _draw_artillery_traces(img, artillery_traces, t_replay, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        _draw_torpedoes(draw, torpedo_tracks, t_replay, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)
        _draw_squadrons(img, draw, squadron_tracks, t_replay, half, canvas_size, margin, world_bounds=world_bounds, map_rect=map_rect)

        for entity_key, prepared in prepared_tracks.items():
            track = prepared["track"]
            all_points = prepared["points"]
            times = prepared["times"]
            pixels = prepared["pixels"]
            if not all_points or not times or not pixels:
                continue
            ekey = str(entity_key)
            side = _color_side(track)
            placeholder_state = _friendly_spawn_placeholder_state(track)
            idx = bisect_right(times, t_replay) - 1
            synthetic_start = False
            if idx < 0:
                if side == "enemy" and not ever_spotted_memory.get(ekey, False):
                    # Enemy ships should not render before first spot.
                    continue
                if placeholder_state is not None:
                    idx = 0
                    synthetic_start = True
                else:
                    # Show known participants from t=0 using first known position as unspotted placeholder.
                    idx = 0
                    synthetic_start = True
            death_t = death_times.get(str(entity_key))
            explicit_death_t = explicit_death_times.get(str(entity_key))
            if bool(track.get("always_unspotted", False)):
                death_t = explicit_death_t
            health = _health_state_at(health_timelines, entity_key, t_replay)
            health_sunk = health is not None and not bool(health.get("alive", True))
            if bool(track.get("always_unspotted", False)):
                sunk = death_t is not None and t_replay >= death_t
            else:
                sunk = (death_t is not None and t_replay >= death_t) or health_sunk
            if sunk and death_t is not None:
                idx = max(0, bisect_right(times, float(death_t)) - 1)
                synthetic_start = False
                placeholder_state = None
            points = all_points[max(0, idx - 9) : idx + 1]
            last_t = times[idx]
            spotted = (t_replay - last_t) <= spot_timeout and not synthetic_start and not bool(track.get("always_unspotted", False))
            # "Actively spotted" is decided only by real position packets (not by
            # minimap-vision fill points), so an ally that left spotting range is
            # rendered as a faded last-known marker rather than a solid icon.
            real_times = prepared.get("real_times") or []
            last_real_t = None
            if real_times and not synthetic_start and not bool(track.get("always_unspotted", False)):
                ridx = bisect_right(real_times, t_replay) - 1
                if ridx >= 0:
                    last_real_t = real_times[ridx]
            actively_spotted = last_real_t is not None and (t_replay - last_real_t) <= spot_timeout
            prev_heading = heading_memory.get(str(entity_key))
            if spotted:
                ever_spotted_memory[ekey] = True
            ever_spotted = ever_spotted_memory.get(ekey, False)
            if side == "enemy" and (not ever_spotted) and (not spotted):
                # Enemy ships remain hidden until they are first spotted.
                continue
            color = _status_color(side, spotted=spotted, sunk=sunk, ever_spotted=ever_spotted)
            is_local_player = _is_local_player_track(canonical, track)
            marker_color = (245, 245, 245) if is_local_player and not sunk else color
            placeholder_only = (
                placeholder_state is not None
                and side == "friendly"
                and synthetic_start
                and (not sunk)
            )
            # An ally is "known" on the team minimap when we have a recent real
            # packet OR recent decoded minimap-vision position. We keep showing
            # such allies (faded) instead of letting them vanish from the render.
            vision_hold_s = max(spot_timeout, 20.0)
            friendly_known = (
                side == "friendly"
                and (not synthetic_start)
                and (bool(track.get("has_minimap_vision", False)) or last_real_t is not None)
                and (t_replay - last_t) <= vision_hold_s
            )
            stale = (not placeholder_only) and _friendly_stale_marker(side, spotted=actively_spotted, sunk=sunk, synthetic_start=synthetic_start)
            # Out-of-range allies we still know about should keep moving on the map.
            friendly_out_of_range = stale and (not sunk) and friendly_known
            # Out-of-range allies keep their normal solid icon (no hollow/pixelated
            # "stale" style) so the marker never changes when leaving spotting range.
            draw_stale = stale and not friendly_out_of_range
            if (placeholder_only or stale) and not sunk and not friendly_out_of_range:
                # Hide unspotted friendly ships only when we have no live tracking
                # data for them (or they are a pre-spawn placeholder).
                continue
            if sunk and death_t is not None:
                exact_point = all_points[idx] if 0 <= idx < len(all_points) else points[-1]
                state = {
                    "x": float(exact_point.get("x", 0.0) or 0.0),
                    "z": float(exact_point.get("z", 0.0) or 0.0),
                    "yaw": float(exact_point.get("yaw", 0.0) or 0.0),
                }
            else:
                # Use the interpolated visual ship state so movement is
                # smooth frame-to-frame while still snapping across large
                # packet gaps.
                state = _ship_state_at(track, float(t_replay))
            poly = pixels[max(0, idx - 23) : idx + 1]
            if state is not None:
                interp_px = _to_px(
                    float(state.get("x", 0.0)),
                    float(state.get("z", 0.0)),
                    half,
                    canvas_size,
                    margin,
                    world_bounds=world_bounds,
                    map_rect=map_rect,
                )
                if not poly or poly[-1] != interp_px:
                    poly = poly + [interp_px]
            pre_heading_placeholder = placeholder_state is not None and side == "friendly" and (not sunk) and synthetic_start
            # During the WoWS countdown the replay reports yaw=0 for all
            # ships.  When every point in the current window still has
            # yaw≈0, derive heading from movement direction instead; fall
            # back to north (180°) when stationary.
            _countdown_yaw_zero = (
                not sunk
                and state is not None
                and abs(float(state.get("yaw", 0.0) or 0.0)) < 0.01
                and all(abs(float(p.get("yaw", 0.0) or 0.0)) < 0.01 for p in points)
            )
            observed_heading_deg: float | None = None
            movement_heading_deg: float | None = None
            movement_dist = 0.0
            if _countdown_yaw_zero:
                _mv_heading, _mv_dist = _movement_heading_metrics(points, window=min(6, len(points)), min_segment=0.45)
                if _mv_heading is not None and _mv_dist >= 1.0:
                    heading_deg = _mv_heading
                    if prev_heading is not None:
                        heading_deg = _lerp_angle_deg(prev_heading, _mv_heading, 0.55)
                else:
                    heading_deg = prev_heading if prev_heading is not None else 180.0
            elif pre_heading_placeholder:
                heading_deg = _yaw_to_heading_deg(float(placeholder_state.get("yaw", 0.0) or 0.0))
            elif sunk and prev_heading is not None:
                heading_deg = prev_heading
            elif state is not None:
                observed_heading_deg = _yaw_to_heading_deg(float(state.get("yaw", points[-1].get("yaw", 0.0)) or 0.0))
                movement_heading_deg, movement_dist = _movement_heading_metrics(points, window=min(6, len(points)), min_segment=0.45)
                heading_deg = _resolved_ship_heading_deg(
                    points,
                    observed_heading_deg,
                    previous_heading_deg=prev_heading,
                    allow_movement_fallback=not bool(track.get("always_unspotted", False)),
                )
            else:
                heading_deg = _yaw_to_heading_deg(points[-1].get("yaw", 0.0))
            heading_memory[str(entity_key)] = heading_deg
            if _heading_debug_match(entity_key, track, heading_debug_filters):
                heading_debug_samples.append(
                    {
                        "t": round(float(t_replay), 3),
                        "entity_key": str(entity_key),
                        "entity_id": str(track.get("entity_id") or entity_key),
                        "player_name": str(track.get("player_name") or ""),
                        "ship_name": _ship_name(track.get("ship_id")),
                        "always_unspotted": bool(track.get("always_unspotted", False)),
                        "synthetic_start": bool(synthetic_start),
                        "spotted": bool(spotted),
                        "sunk": bool(sunk),
                        "observed_heading_deg": None if observed_heading_deg is None else round(float(observed_heading_deg), 3),
                        "previous_heading_deg": None if prev_heading is None else round(float(prev_heading), 3),
                        "movement_heading_deg": None if movement_heading_deg is None else round(float(movement_heading_deg), 3),
                        "movement_dist": round(float(movement_dist), 3),
                        "resolved_heading_deg": round(float(heading_deg), 3),
                        "heading_delta_deg": (
                            None
                            if observed_heading_deg is None or movement_heading_deg is None
                            else round(abs(_angle_delta_deg(float(observed_heading_deg), float(movement_heading_deg))), 3)
                        ),
                    }
                )
            if state is not None and not poly:
                poly = [
                    _to_px(
                        float(state.get("x", 0.0)),
                        float(state.get("z", 0.0)),
                        half,
                        canvas_size,
                        margin,
                        world_bounds=world_bounds,
                        map_rect=map_rect,
                    )
                ]
            cx, cy = poly[-1]
            if placeholder_only:
                _draw_ship_marker(
                    img,
                    draw,
                    cx,
                    cy,
                    prepared["ship_type"],
                    prepared["ship_class"],
                    (245, 245, 245) if is_local_player else COLOR_FRIENDLY,
                    heading_deg,
                    _ship_name(track.get("ship_id")) or track.get("player_name"),
                    size=marker_size,
                    sunk=False,
                    stale=True,
                    consumable_kind=None,
                )
            else:
                _draw_ship_marker(
                    img,
                    draw,
                    cx,
                    cy,
                    prepared["ship_type"],
                    prepared["ship_class"],
                    marker_color,
                    heading_deg,
                    _ship_name(track.get("ship_id")) or track.get("player_name"),
                    size=marker_size,
                    sunk=sunk,
                    stale=draw_stale,
                    consumable_kind=(
                        (
                            _active_sensor_kind(
                                sensor_by_entity,
                                _safe_int(track.get("entity_id")) or _safe_int(entity_key) or 0,
                                t_replay,
                            )
                            or _active_consumable_kind(
                                consumable_by_entity,
                                _safe_int(track.get("entity_id")) or _safe_int(entity_key) or 0,
                                t_replay,
                            )
                        )
                        if not sunk
                        else None
                    ),
                )
            if health is not None and not placeholder_only:
                _draw_hp_bar(
                    draw,
                    cx,
                    cy + marker_size + 5,
                    max(20, marker_size * 4),
                    max(4, marker_size // 2),
                    float(health.get("ratio", 0.0)),
                    color,
                    sunk=sunk or (not bool(health.get("alive", True))),
                )

        battle_clock_s = _battle_clock_seconds(canonical, capture_snapshot, t_replay)
        _draw_score_overlay(img, canonical, capture_snapshot, capture_timeline, canvas_size)
        _draw_clock_overlay(img, battle_clock_s, canvas_size, ui_font_size)
        if frame_idx >= max(0, total_frames - result_frames):
            fade_frames = max(1, result_frames // 3)
            alpha = int(255 * min(1.0, float(frame_idx - (total_frames - result_frames) + 1) / float(fade_frames)))
            _draw_battle_result_overlay(img, canonical, canvas_size, alpha=alpha)
        status = _player_status_at(player_status_timeline, t_replay)
        frame_layout = layout if hide_player_card else _layout_for_player_status(layout, status)
        if not hide_player_card:
            _draw_player_status_panel(
                img,
                draw,
                canonical,
                render_tracks,
                health_timelines,
                player_status_timeline,
                t_replay,
                frame_layout,
                player_track_index=player_track_index,
            )
        _draw_kill_feed_panel(img, draw, canonical, render_tracks, kill_feed, t_replay, frame_layout)
        _draw_lineup_panel(img, draw, frame_layout, current_t=t_replay, death_times=death_times, health_timelines=health_timelines)
        yield img
        t += step
        frame_idx += 1
    _write_heading_debug(heading_debug_samples)


def render_gif_frames(canonical: Dict[str, Any], canvas_size: int = 600, speed: float = 3.0, show_grid: bool = True) -> List[Image.Image]:
    return list(iter_animation_frames(canonical, canvas_size=canvas_size, speed=speed, show_grid=show_grid))
_CONSUMABLE_ICON_CACHE: Dict[Tuple[str, int], Image.Image] = {}
_STATUS_ICON_CACHE: Dict[Tuple[str, int], Image.Image] = {}
_AIRCRAFT_PARAMS_DEBUG: Dict[str, Dict[str, Any]] = {}
