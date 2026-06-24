from __future__ import annotations

import asyncio
import collections
import contextlib
import copy
import io
import json
import logging
import os
import re
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any


import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont

WOWS_BG = (10, 17, 28)
WOWS_PANEL = (20, 28, 40)
WOWS_PANEL_ALT = (25, 34, 49)
WOWS_PANEL_INNER = (13, 18, 26)
WOWS_OUTLINE = (86, 114, 149)
WOWS_OUTLINE_SOFT = (58, 72, 88)
WOWS_OUTLINE_INNER = (44, 54, 66)
WOWS_TEXT = (238, 244, 250)
WOWS_TEXT_SUB = (173, 185, 199)
WOWS_TEXT_DIM = (130, 141, 155)
WOWS_ACCENT = (124, 179, 232)
WOWS_FRIENDLY = (93, 214, 105)
WOWS_ENEMY = (234, 92, 92)
WOWS_HP = (126, 232, 140)
WOWS_GOLD = (246, 214, 104)

ROOT = Path(__file__).resolve().parent
WOWS_GUI_DIR = ROOT / "gui"
WOWS_FONT_BOLD_PATH = WOWS_GUI_DIR / "fonts" / "WarHeliosCondCBold (1).ttf"
WOWS_FONT_PATH = WOWS_GUI_DIR / "fonts" / "WarHeliosCondC (1).ttf"
WOWS_LOGO_WG_PATH = WOWS_GUI_DIR / "logos" / "logo_wg.png"
WOWS_PANEL_TEXTURE_PATH = WOWS_GUI_DIR / "panel_background" / "dock_menu_bg.png"

from core.minimap_data import load_canonical_data
from core.ship_build_display import (
    build_consumable_entries,
    build_module_entries,
    load_consumable_tile_icon,
    load_module_tile_icon,
    load_upgrade_tile_icon,
    parse_mounted_upgrades,
)
from minimap_render_v2 import auto_output_duration_s, internal_target_duration_s, render_minimap as _render_minimap_impl, QUALITY_SCALE

LOG = logging.getLogger("render_bot")
CONFIG_PATH = Path(__file__).resolve().with_name("bot_config.json")
DEFAULT_FILE_LIMIT = 10 * 1024 * 1024
MAX_REPLAY_BYTES = 64 * 1024 * 1024
DEFAULT_RENDER_SIZE = 1024
DEFAULT_RENDER_FPS = 30
DUAL_RENDER_SIZE = 720
DISCORD_BOOSTED_FILE_LIMIT = 50 * 1024 * 1024
DISCORD_SAFE_RENDER_SIZE = 720
DISCORD_BOOSTED_RENDER_SIZE = 900
DISCORD_HQ_RENDER_SIZE = 1080
DISCORD_SAFE_DUAL_RENDER_SIZE = 720
DISCORD_BOOSTED_DUAL_RENDER_SIZE = 900
DISCORD_HQ_DUAL_RENDER_SIZE = 900
DISCORD_SAFE_RENDER_FPS = 30
DISCORD_BOOSTED_RENDER_FPS = 30
DISCORD_HQ_RENDER_FPS = 30
DISCORD_SAFE_RENDER_QUALITY = 0.9
DISCORD_BOOSTED_RENDER_QUALITY = 1.1
DISCORD_HQ_RENDER_QUALITY = 1.3
DISCORD_SAFE_RENDER_PRESET = "faster"
DISCORD_BOOSTED_RENDER_PRESET = "fast"
DISCORD_HQ_RENDER_PRESET = "fast"
DISCORD_SAFE_RENDER_CRF = "24"
DISCORD_BOOSTED_RENDER_CRF = "21"
DISCORD_HQ_RENDER_CRF = "19"
MAX_ENCODER_THREADS = 16
MAX_RENDER_QUEUE = 10
RENDER_QUEUE_TIMEOUT_S = 600
RENDER_QUEUE_CONDITION: asyncio.Condition | None = None
RENDER_QUEUE_LOOP: asyncio.AbstractEventLoop | None = None
RENDER_QUEUE: collections.deque[int] = collections.deque()
ACTIVE_RENDER_TICKET: int | None = None
NEXT_RENDER_TICKET = 1
_CURRENT_DISCORD_UPLOAD_LIMIT = DEFAULT_FILE_LIMIT


def render_minimap(*args: Any, **kwargs: Any):
    size_value = int(kwargs.get("size", DEFAULT_RENDER_SIZE) or DEFAULT_RENDER_SIZE)
    dual = size_value == DUAL_RENDER_SIZE
    file_limit = max(DEFAULT_FILE_LIMIT, int(_CURRENT_DISCORD_UPLOAD_LIMIT or DEFAULT_FILE_LIMIT))
    attempts = _discord_render_attempts(
        None,
        dual=dual,
        threads=kwargs.get("mp4_threads"),
        file_limit=file_limit,
    )
    last_result = None
    for attempt_index, attempt in enumerate(attempts):
        trial_kwargs = dict(kwargs)
        trial_kwargs["size"] = attempt["size"]
        trial_kwargs["quality"] = attempt["quality"]
        trial_kwargs["fps"] = attempt["fps"]
        trial_kwargs["mp4_preset"] = attempt["preset"]
        trial_kwargs["mp4_crf"] = attempt["crf"]
        if attempt.get("threads") is not None:
            trial_kwargs["mp4_threads"] = attempt["threads"]
        else:
            trial_kwargs.pop("mp4_threads", None)

        out_mp4 = trial_kwargs.get("out_mp4")
        second_last_frame = trial_kwargs.get("capture_second_last_frame")
        result = _render_minimap_impl(*args, **trial_kwargs)
        last_result = result

        if not out_mp4:
            return result

        out_path = Path(out_mp4)
        try:
            rendered_size = out_path.stat().st_size
        except OSError:
            return result

        if rendered_size <= file_limit or attempt_index + 1 >= len(attempts):
            return result

        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        if second_last_frame:
            try:
                Path(second_last_frame).unlink(missing_ok=True)
            except OSError:
                pass

    return last_result
_SHIP_CACHE_DATA: dict[str, dict[str, Any]] | None = None
_SHIP_GAMEPARAMS_DATA: dict[str, dict[str, Any]] | None = None
_CAPTAIN_SKILL_LAYOUT_DATA: dict[str, Any] | None = None


def _load_bot_config() -> dict[str, Any]:
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing bot config file: {CONFIG_PATH.name}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {CONFIG_PATH.name}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"{CONFIG_PATH.name} must contain a JSON object")
    return data


def _load_bot_token() -> str:
    data = _load_bot_config()

    token = str(data.get("token", "") or "").strip()
    if not token:
        raise SystemExit(f"`token` is missing in {CONFIG_PATH.name}")
    return token


def _discord_upload_limit(interaction: discord.Interaction) -> int:
    guild = getattr(interaction, "guild", None)
    if guild is None:
        return DEFAULT_FILE_LIMIT
    try:
        guild_limit = int(getattr(guild, "filesize_limit", DEFAULT_FILE_LIMIT) or DEFAULT_FILE_LIMIT)
    except Exception:
        guild_limit = DEFAULT_FILE_LIMIT
    return max(DEFAULT_FILE_LIMIT, max(1, guild_limit))


def _discord_render_attempts(
    interaction: discord.Interaction | None,
    *,
    dual: bool,
    threads: int | None = None,
    file_limit: int | None = None,
) -> list[dict[str, Any]]:
    if file_limit is None:
        if interaction is None:
            file_limit = DEFAULT_FILE_LIMIT
        else:
            file_limit = _discord_upload_limit(interaction)
    file_limit = max(DEFAULT_FILE_LIMIT, max(1, int(file_limit)))
    try:
        effective_threads = min(MAX_ENCODER_THREADS, max(1, int(threads))) if threads is not None else None
    except Exception:
        effective_threads = None
    if effective_threads is None:
        cpu_count = os.cpu_count() or 2
        effective_threads = min(MAX_ENCODER_THREADS, max(1, cpu_count))

    if file_limit > DISCORD_BOOSTED_FILE_LIMIT:
        plans = [
            {
                "profile": "discord_hq",
                "size": DISCORD_HQ_DUAL_RENDER_SIZE if dual else DISCORD_HQ_RENDER_SIZE,
                "quality": DISCORD_HQ_RENDER_QUALITY,
                "fps": DISCORD_HQ_RENDER_FPS,
                "preset": DISCORD_HQ_RENDER_PRESET,
                "crf": DISCORD_HQ_RENDER_CRF,
            },
            {
                "profile": "discord_boosted",
                "size": DISCORD_BOOSTED_DUAL_RENDER_SIZE if dual else DISCORD_BOOSTED_RENDER_SIZE,
                "quality": DISCORD_BOOSTED_RENDER_QUALITY,
                "fps": DISCORD_BOOSTED_RENDER_FPS,
                "preset": DISCORD_BOOSTED_RENDER_PRESET,
                "crf": DISCORD_BOOSTED_RENDER_CRF,
            },
            {
                "profile": "discord_safe",
                "size": DISCORD_SAFE_DUAL_RENDER_SIZE if dual else DISCORD_SAFE_RENDER_SIZE,
                "quality": DISCORD_SAFE_RENDER_QUALITY,
                "fps": DISCORD_SAFE_RENDER_FPS,
                "preset": DISCORD_SAFE_RENDER_PRESET,
                "crf": DISCORD_SAFE_RENDER_CRF,
            },
        ]
    elif file_limit > DEFAULT_FILE_LIMIT:
        plans = [
            {
                "profile": "discord_boosted",
                "size": DISCORD_BOOSTED_DUAL_RENDER_SIZE if dual else DISCORD_BOOSTED_RENDER_SIZE,
                "quality": DISCORD_BOOSTED_RENDER_QUALITY,
                "fps": DISCORD_BOOSTED_RENDER_FPS,
                "preset": DISCORD_BOOSTED_RENDER_PRESET,
                "crf": DISCORD_BOOSTED_RENDER_CRF,
            },
            {
                "profile": "discord_safe",
                "size": DISCORD_SAFE_DUAL_RENDER_SIZE if dual else DISCORD_SAFE_RENDER_SIZE,
                "quality": DISCORD_SAFE_RENDER_QUALITY,
                "fps": DISCORD_SAFE_RENDER_FPS,
                "preset": DISCORD_SAFE_RENDER_PRESET,
                "crf": DISCORD_SAFE_RENDER_CRF,
            },
        ]
    else:
        plans = [
            {
                "profile": "discord_safe",
                "size": DISCORD_SAFE_DUAL_RENDER_SIZE if dual else DISCORD_SAFE_RENDER_SIZE,
                "quality": DISCORD_SAFE_RENDER_QUALITY,
                "fps": DISCORD_SAFE_RENDER_FPS,
                "preset": DISCORD_SAFE_RENDER_PRESET,
                "crf": DISCORD_SAFE_RENDER_CRF,
            },
        ]

    for plan in plans:
        plan["threads"] = effective_threads
    return plans


def render_minimap(*args: Any, **kwargs: Any) -> Any:
    out_mp4 = kwargs.get("out_mp4")
    if not out_mp4:
        return _render_minimap_impl(*args, **kwargs)

    try:
        file_limit = int(_CURRENT_DISCORD_UPLOAD_LIMIT)
    except Exception:
        file_limit = DEFAULT_FILE_LIMIT
    file_limit = max(DEFAULT_FILE_LIMIT, max(1, file_limit))

    try:
        size_hint = int(kwargs.get("size", DEFAULT_RENDER_SIZE) or DEFAULT_RENDER_SIZE)
    except Exception:
        size_hint = DEFAULT_RENDER_SIZE
    dual = size_hint <= DUAL_RENDER_SIZE

    attempts = _discord_render_attempts(
        None,
        dual=dual,
        threads=kwargs.get("mp4_threads"),
        file_limit=file_limit,
    )
    if dual:
        attempts.extend(
            [
                {"profile": "discord_emergency", "size": 560, "quality": 0.88, "fps": 24, "preset": "slow", "crf": "24", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 480, "quality": 0.78, "fps": 24, "preset": "slow", "crf": "26", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 420, "quality": 0.68, "fps": 20, "preset": "slow", "crf": "28", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 360, "quality": 0.60, "fps": 20, "preset": "slow", "crf": "30", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 320, "quality": 0.54, "fps": 15, "preset": "slow", "crf": "32", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 280, "quality": 0.50, "fps": 15, "preset": "slow", "crf": "34", "threads": kwargs.get("mp4_threads")},
            ]
        )
    else:
        attempts.extend(
            [
                {"profile": "discord_emergency", "size": 640, "quality": 0.90, "fps": 24, "preset": "slow", "crf": "24", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 540, "quality": 0.80, "fps": 24, "preset": "slow", "crf": "26", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 480, "quality": 0.70, "fps": 20, "preset": "slow", "crf": "28", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 400, "quality": 0.62, "fps": 20, "preset": "slow", "crf": "30", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 320, "quality": 0.54, "fps": 15, "preset": "slow", "crf": "32", "threads": kwargs.get("mp4_threads")},
                {"profile": "discord_emergency", "size": 280, "quality": 0.50, "fps": 15, "preset": "slow", "crf": "34", "threads": kwargs.get("mp4_threads")},
            ]
        )

    out_path = Path(str(out_mp4))
    capture_path = kwargs.get("capture_second_last_frame")
    last_result: Any = None
    hard_limit = DEFAULT_FILE_LIMIT

    for attempt_index, attempt in enumerate(attempts, start=1):
        attempt_kwargs = dict(kwargs)
        attempt_kwargs["size"] = int(attempt["size"])
        attempt_kwargs["fps"] = int(attempt["fps"])
        attempt_kwargs["quality"] = float(attempt["quality"])
        attempt_kwargs["mp4_preset"] = str(attempt["preset"])
        attempt_kwargs["mp4_crf"] = str(attempt["crf"])
        attempt_kwargs["mp4_threads"] = attempt.get("threads")
        last_result = _render_minimap_impl(*args, **attempt_kwargs)
        try:
            file_size = out_path.stat().st_size
        except FileNotFoundError:
            file_size = 0
        if file_size <= hard_limit or attempt_index >= len(attempts):
            return last_result
        with contextlib.suppress(FileNotFoundError):
            out_path.unlink()
        if capture_path:
            with contextlib.suppress(FileNotFoundError):
                Path(str(capture_path)).unlink()

    return last_result


def _discord_render_settings(interaction: discord.Interaction, *, dual: bool) -> dict[str, Any]:
    base = _render_settings()
    file_limit = _discord_upload_limit(interaction)
    if file_limit > DISCORD_BOOSTED_FILE_LIMIT:
        profile = "discord_hq"
        size = DISCORD_HQ_DUAL_RENDER_SIZE if dual else DISCORD_HQ_RENDER_SIZE
        quality = DISCORD_HQ_RENDER_QUALITY
        fps = DISCORD_HQ_RENDER_FPS
        preset = DISCORD_HQ_RENDER_PRESET
        crf = DISCORD_HQ_RENDER_CRF
    elif file_limit > DEFAULT_FILE_LIMIT:
        profile = "discord_boosted"
        size = DISCORD_BOOSTED_DUAL_RENDER_SIZE if dual else DISCORD_BOOSTED_RENDER_SIZE
        quality = DISCORD_BOOSTED_RENDER_QUALITY
        fps = DISCORD_BOOSTED_RENDER_FPS
        preset = DISCORD_BOOSTED_RENDER_PRESET
        crf = DISCORD_BOOSTED_RENDER_CRF
    else:
        profile = "discord_safe"
        size = DISCORD_SAFE_DUAL_RENDER_SIZE if dual else DISCORD_SAFE_RENDER_SIZE
        quality = DISCORD_SAFE_RENDER_QUALITY
        fps = DISCORD_SAFE_RENDER_FPS
        preset = DISCORD_SAFE_RENDER_PRESET
        crf = DISCORD_SAFE_RENDER_CRF
    settings = {
        "profile": profile,
        "file_limit": file_limit,
        "size": size,
        "quality": quality,
        "fps": fps,
        "preset": preset,
        "crf": crf,
        "threads": base.get("threads"),
    }
    if settings.get("threads") is not None:
        try:
            settings["threads"] = min(MAX_ENCODER_THREADS, max(1, int(settings["threads"])))
        except Exception:
            settings["threads"] = None
    if settings["threads"] is None:
        cpu_count = os.cpu_count() or 2
        settings["threads"] = min(MAX_ENCODER_THREADS, max(1, cpu_count))
    return settings


def _render_settings() -> dict[str, Any]:
    data = _load_bot_config()
    profile = str(data.get("render_profile", "hosted") or "").strip().lower()
    cpu_count = os.cpu_count() or 2
    settings = {
        "profile": profile,
        "quality": float(data.get("render_quality", QUALITY_SCALE)),
        "preset": str(data.get("render_preset", "slow")),
        "crf": str(data.get("render_crf", "17")),
        "fps": int(data.get("render_fps", DEFAULT_RENDER_FPS)),
        "threads": data.get("render_threads"),
    }
    if profile == "hosted":
        if "render_quality" not in data:
            settings["quality"] = 1.0
        if "render_preset" not in data:
            settings["preset"] = "fast"
        if "render_crf" not in data:
            settings["crf"] = "19"
        if "render_fps" not in data:
            settings["fps"] = DEFAULT_RENDER_FPS
        if "render_threads" not in data:
            settings["threads"] = min(MAX_ENCODER_THREADS, max(1, cpu_count))
    elif "render_threads" not in data:
        settings["threads"] = min(MAX_ENCODER_THREADS, max(1, cpu_count))
    if settings.get("threads") is not None:
        try:
            settings["threads"] = min(MAX_ENCODER_THREADS, max(1, int(settings["threads"])))
        except Exception:
            settings["threads"] = None
    return settings


def _safe_name(filename: str) -> str:
    name = Path(str(filename or "battle.wowsreplay")).name
    return name or "battle.wowsreplay"


def _is_replay_attachment(attachment: discord.Attachment) -> bool:
    return Path(attachment.filename or "").suffix.lower() == ".wowsreplay"


def _load_ship_cache() -> dict[str, dict[str, Any]]:
    global _SHIP_CACHE_DATA
    if _SHIP_CACHE_DATA is not None:
        return _SHIP_CACHE_DATA
    cache_path = Path(__file__).resolve().with_name("ships_cache.json")
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        _SHIP_CACHE_DATA = data if isinstance(data, dict) else {}
    except Exception:
        _SHIP_CACHE_DATA = {}
    return _SHIP_CACHE_DATA


def _load_ship_gameparams_cache() -> dict[str, dict[str, Any]]:
    global _SHIP_GAMEPARAMS_DATA
    if _SHIP_GAMEPARAMS_DATA is not None:
        return _SHIP_GAMEPARAMS_DATA
    cache_path = Path(__file__).resolve().parent / "content" / "ships_gameparams.json"
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        _SHIP_GAMEPARAMS_DATA = data if isinstance(data, dict) else {}
    except Exception:
        _SHIP_GAMEPARAMS_DATA = {}
    return _SHIP_GAMEPARAMS_DATA


def _load_captain_skill_layout() -> dict[str, Any]:
    global _CAPTAIN_SKILL_LAYOUT_DATA
    if _CAPTAIN_SKILL_LAYOUT_DATA is not None:
        return _CAPTAIN_SKILL_LAYOUT_DATA
    path = Path(__file__).resolve().parent / "content" / "captain_skill_layout.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _CAPTAIN_SKILL_LAYOUT_DATA = data if isinstance(data, dict) else {}
    except Exception:
        _CAPTAIN_SKILL_LAYOUT_DATA = {}
    return _CAPTAIN_SKILL_LAYOUT_DATA


def _ship_entry_by_id(ship_id: Any) -> dict[str, Any]:
    try:
        key = str(int(ship_id))
    except (TypeError, ValueError):
        return {}
    for source in (_load_ship_cache(), _load_ship_gameparams_cache()):
        entry = source.get(key)
        if isinstance(entry, dict):
            return entry
    return {}


def _resolve_ship_name(canonical: dict[str, Any]) -> str:
    meta = canonical.get("meta", {}) or {}
    vehicles = meta.get("vehicles", []) or []
    player_name = str(meta.get("playerName") or "").strip()
    ship_id = None
    if isinstance(vehicles, list):
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            if str(vehicle.get("name") or "").strip() == player_name:
                ship_id = vehicle.get("shipId")
                break
    try:
        key = str(int(ship_id))
    except (TypeError, ValueError):
        key = ""
    if key:
        ship_name = str(_ship_entry_by_id(key).get("name") or "").strip()
        if ship_name:
            return ship_name
    return str(meta.get("playerVehicle") or "").strip() or "Unknown ship"


def _resolve_ship_type(entity: dict[str, Any]) -> str:
    ship_type = str(entity.get("type") or entity.get("species") or "").strip()
    if ship_type:
        return ship_type
    entry = _ship_entry_by_id(entity.get("ship_id"))
    return str(entry.get("type") or entry.get("species") or "").strip()


def _result_embed(filename: str, output_length_label: str, canonical: dict[str, Any]) -> discord.Embed:
    meta = canonical.get("meta", {}) or {}
    map_name = str(meta.get("map_name_resolved") or meta.get("mapDisplayName") or meta.get("mapId") or "Unknown map")
    player_name = str(meta.get("playerName") or "Unknown player")
    ship_name = _resolve_ship_name(canonical)

    embed = discord.Embed(title="Render Complete", color=discord.Color.green())
    embed.add_field(name="Replay", value=filename, inline=False)
    embed.add_field(name="Map", value=map_name, inline=True)
    embed.add_field(name="Player", value=player_name, inline=True)
    embed.add_field(name="Ship", value=ship_name, inline=True)
    embed.add_field(name="Output Length", value=output_length_label, inline=True)
    return embed


def _local_entity_from_canonical(canonical: dict[str, Any]) -> dict[str, Any] | None:
    entities = canonical.get("entities", {}) or {}
    if not isinstance(entities, dict):
        return None
    for row in entities.values():
        if isinstance(row, dict) and str(row.get("team") or "").lower() == "player":
            return row
    return None


def _log_render_start(canonical: dict[str, Any], interaction: discord.Interaction) -> None:
    meta = canonical.get("meta", {}) or {}
    player = str(meta.get("playerName") or "Unknown")
    guild = str(getattr(interaction.guild, "name", "DM") or "DM")
    LOG.info("Render: player=%s, discord_server=%s", player, guild)


def _ship_code_from_canonical(canonical: dict[str, Any]) -> str:
    meta = canonical.get("meta", {}) or {}
    vehicle = str(meta.get("playerVehicle") or "").strip()
    if vehicle:
        return vehicle.split("-", 1)[0].strip()
    return ""


def _pretty_token(value: str) -> str:
    text = str(value or "").replace("_", " ").strip()
    if not text:
        return ""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    replacements = {
        "Aa": "AA",
        "Ap": "AP",
        "Asw": "ASW",
        "Atba": "Secondaries",
        "Bb": "BB",
        "Ca": "CA",
        "Cv": "CV",
        "Dd": "DD",
        "He": "HE",
        "Hp": "HP",
        "Sap": "SAP",
        "Uw": "UW",
    }
    words = []
    for word in text.split():
        words.append(replacements.get(word, word))
    return " ".join(words)


def _friendly_component_name(name: str) -> str:
    return _pretty_token(name).replace("Atba", "Secondaries")


def _friendly_component_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[A-Z]_", "", text)
    text = re.sub(r"TypeDefault$", "", text)
    text = re.sub(r"Default$", "", text)
    text = re.sub(r"Type$", "", text)
    text = re.sub(r"\bGunDefault$", "Gun", text)
    text = re.sub(r"\bGunsDefault$", "Guns", text)
    text = _pretty_token(text)
    return re.sub(r"\s+", " ", text).strip()


def _ordered_build_components(components: dict[str, Any]) -> list[tuple[str, str]]:
    priority = [
        "hull",
        "engine",
        "artillery",
        "torpedoes",
        "fireControl",
        "airDefense",
        "flightControl",
        "fighter",
        "diveBomber",
        "torpedoBomber",
        "skipBomber",
        "airArmament",
        "airSupport",
        "radars",
        "depthCharges",
        "pinger",
        "wcs",
        "directors",
        "finders",
        "atba",
    ]
    hidden = {
        "aiParams",
        "airshipPlane",
        "auxiliaryPlane",
        "axisLaser",
        "cameras",
        "chargeLasers",
        "impulseLasers",
        "innateSkills",
        "missiles",
        "phaserLasers",
        "scout",
        "specials",
        "underwaterCamera",
        "waves",
    }
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in priority:
        if key in components and key not in hidden:
            ordered.append((_friendly_component_name(key), _friendly_component_value(components[key])))
            seen.add(key)
    for key in sorted(components):
        if key in seen or key in hidden:
            continue
        ordered.append((_friendly_component_name(key), _friendly_component_value(components[key])))
    return ordered


def _normalize_ship_type_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
    aliases = {
        "aircraftcarrier": "aircarrier",
        "carrier": "aircarrier",
        "cv": "aircarrier",
        "sub": "submarine",
    }
    return aliases.get(text, text)


def _select_ship_class_skills(captain: dict[str, Any], ship_type: str) -> tuple[str, list[str]]:
    learned = captain.get("learned_skills", {}) if isinstance(captain, dict) else {}
    if not isinstance(learned, dict):
        return "", []
    target = _normalize_ship_type_key(ship_type)
    non_empty: list[tuple[str, list[str]]] = []
    for label, skills in learned.items():
        skill_list = [str(skill) for skill in skills if skill]
        if not skill_list:
            continue
        label_text = str(label or "").strip()
        non_empty.append((label_text, skill_list))
        if target and _normalize_ship_type_key(label_text) == target:
            return label_text, skill_list
    if len(non_empty) == 1:
        return non_empty[0]
    return non_empty[0] if non_empty else ("", [])


def _layout_for_ship_type(ship_type: str) -> list[list[str | None]]:
    data = _load_captain_skill_layout()
    if not isinstance(data, dict):
        return []
    target = _normalize_ship_type_key(ship_type)
    for label, payload in data.items():
        if _normalize_ship_type_key(label) != target or not isinstance(payload, dict):
            continue
        rows = payload.get("rows")
        if not isinstance(rows, list):
            continue
        normalized_rows: list[list[str | None]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            normalized_rows.append([str(item) if item else None for item in row])
        return normalized_rows
    return []


def _captain_points_for_layout(learned_skills: list[str], rows: list[list[str | None]]) -> int:
    learned = {str(skill) for skill in learned_skills if skill}
    total = 0
    for row_idx, row in enumerate(rows, start=1):
        for skill in row:
            if skill and skill in learned:
                total += row_idx
    return total


def _layout_covers_skills(learned_skills: list[str], rows: list[list[str | None]]) -> bool:
    if not learned_skills:
        return True
    layout_skills = {
        str(skill)
        for row in rows
        for skill in row
        if skill
    }
    return all(str(skill) in layout_skills for skill in learned_skills if skill)


def _load_bot_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred = [
        WOWS_FONT_BOLD_PATH if bold else WOWS_FONT_PATH,
        WOWS_FONT_PATH if bold else WOWS_FONT_BOLD_PATH,
        "C:/Windows/Fonts/seguisb.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in preferred:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _load_rgba_asset(path: Path) -> Image.Image | None:
    if not path.is_file():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _tint_rgba_asset(img: Image.Image | None, color: tuple[int, int, int]) -> Image.Image | None:
    if img is None:
        return None
    asset = img.convert("RGBA")
    tinted = Image.new("RGBA", asset.size, color + (0,))
    tinted.putalpha(asset.getchannel("A"))
    return tinted


def _load_build_ship_art(ship_code: str, max_w: int, max_h: int) -> Image.Image | None:
    if not ship_code:
        return None
    candidates = [
        ROOT / "gui" / "ship_previews" / f"{ship_code}.png",
        ROOT / "gui" / "ship_previews" / "medium" / f"{ship_code}.png",
        ROOT / "gui" / "ships_silhouettes" / f"{ship_code}.png",
        ROOT / "gui" / "ship_icons" / f"{ship_code}.png",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            img = Image.open(path).convert("RGBA")
        except Exception:
            continue
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        return img
    return None


def _skill_icon_slug(skill_name: str) -> str:
    text = str(skill_name or "").strip()
    if not text:
        return ""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", text)
    text = text.replace(" ", "_").replace("-", "_").replace(".", "_")
    text = re.sub(r"__+", "_", text)
    return text.strip("_").lower()


def _find_commander_skill_icon_path(skill_name: str) -> Path | None:
    icon_root = Path(__file__).resolve().parent / "gui" / "crew_commander" / "skills"
    if not icon_root.is_dir():
        return None

    slug = _skill_icon_slug(skill_name)
    if slug:
        candidate = icon_root / f"{slug}.png"
        if candidate.is_file():
            return candidate

    normalized = re.sub(r"[^a-z0-9]+", "_", str(skill_name or "").strip().lower()).strip("_")
    if normalized:
        candidate = icon_root / f"{normalized}.png"
        if candidate.is_file():
            return candidate

    alias_map = {
        "triggerplanestorpedouwreducedspeed": "planes_torpedo_uw_reduced",
    }
    requested_key = re.sub(r"[^a-z0-9]", "", str(skill_name or "").strip().lower())
    if requested_key:
        alias = alias_map.get(requested_key)
        if alias:
            candidate = icon_root / f"{alias}.png"
            if candidate.is_file():
                return candidate
    if requested_key:
        for candidate in sorted(icon_root.glob("*.png")):
            candidate_key = re.sub(r"[^a-z0-9]", "", candidate.stem.lower())
            if candidate_key == requested_key:
                return candidate
        for candidate in sorted(icon_root.glob("*.png")):
            candidate_key = re.sub(r"[^a-z0-9]", "", candidate.stem.lower())
            if candidate_key.endswith(requested_key) or requested_key.endswith(candidate_key):
                return candidate
    return None


def _load_commander_skill_icon(skill_name: str, size: int) -> Image.Image | None:
    path = _find_commander_skill_icon_path(skill_name)
    if path is None:
        return None
    try:
        icon = Image.open(path).convert("RGBA")
    except Exception:
        return None
    icon.thumbnail((size, size), Image.Resampling.LANCZOS)
    return icon


def _build_card_payload(canonical: dict[str, Any]) -> dict[str, Any] | None:
    entity = _local_entity_from_canonical(canonical)
    if not isinstance(entity, dict):
        return None
    captain = entity.get("captain_skills")
    build = entity.get("ship_build")
    if not isinstance(captain, dict) and not isinstance(build, dict):
        return None
    return {
        "player_name": str(entity.get("player_name") or (canonical.get("meta", {}) or {}).get("playerName") or "").strip(),
        "ship_name": _resolve_ship_name(canonical),
        "ship_code": _ship_code_from_canonical(canonical),
        "ship_type": _resolve_ship_type(entity),
        "ship_id": entity.get("ship_id"),
        "captain_skills": captain if isinstance(captain, dict) else {},
        "ship_build": build if isinstance(build, dict) else {},
    }


def _draw_wrapped_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x: int,
    y: int,
    width: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_gap: int = 6,
    max_height: int | None = None,
    align: str = "left",
) -> int:
    words = text.split()
    if not words:
        return y
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        trial_w, _ = _measure_text(draw, trial, font)
        if trial_w <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    _, line_h = _measure_text(draw, "Ag", font)
    step = line_h + line_gap
    # Cap line count to whatever fits in ``max_height`` so trailing words can't
    # spill below the parent tile.
    if max_height is not None and step > 0:
        max_lines = max(1, (max_height + line_gap) // step)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
    for line in lines:
        lx = x
        if align in ("center", "centre"):
            lw, _ = _measure_text(draw, line, font)
            lx = x + max(0, (width - lw) // 2)
        draw.text((lx, y), line, font=font, fill=fill)
        y += step
    return y


def _draw_module_tile(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    entry: dict[str, Any],
    icon_size: int,
    label_font: ImageFont.ImageFont,
    caption_font: ImageFont.ImageFont,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=WOWS_PANEL, outline=WOWS_OUTLINE, width=2)
    draw.rounded_rectangle((x + 4, y + 4, x + w - 4, y + h - 4), radius=10, outline=WOWS_OUTLINE_SOFT, width=1)

    icon = load_module_tile_icon(entry, icon_size)
    if icon is not None:
        px = x + (w - icon.width) // 2
        py = y + 8
        img.paste(icon, (px, py), icon)
    else:
        short = "".join(word[:1] for word in str(entry.get("slot_label") or "?").split()[:2]).upper() or "?"
        fw, fh = _measure_text(draw, short, label_font)
        draw.text((x + (w - fw) // 2, y + 16), short, font=label_font, fill=WOWS_TEXT)

    caption = str(entry.get("variant") or entry.get("slot_label") or "").strip()
    if caption:
        caption_top = y + h - 60
        max_caption_height = max(0, (y + h) - caption_top - 6)
        _draw_wrapped_lines(
            draw,
            caption,
            x=x + 6,
            y=caption_top,
            width=w - 12,
            font=caption_font,
            fill=WOWS_TEXT_SUB,
            line_gap=0,
            max_height=max_caption_height,
            align="center",
        )


def _draw_upgrade_tile(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    upgrade: dict[str, Any],
    icon_size: int,
    caption_font: ImageFont.ImageFont,
    slot_font: ImageFont.ImageFont | None = None,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=14, fill=WOWS_PANEL, outline=WOWS_OUTLINE, width=2)

    if slot_font is not None:
        slot_label = upgrade.get("slot_position")
        if slot_label is not None:
            slot_text = f"Slot {slot_label}"
            sw, sh = _measure_text(draw, slot_text, slot_font)
            draw.rounded_rectangle(
                (x + 8, y + 8, x + 8 + sw + 14, y + 8 + sh + 6),
                radius=6,
                fill=WOWS_PANEL_ALT,
            )
            draw.text((x + 15, y + 11), slot_text, font=slot_font, fill=WOWS_TEXT)

    # Caption is drawn just below the icon and stays clipped inside the tile
    # to prevent trailing digits from spilling underneath the box.
    icon = load_upgrade_tile_icon(upgrade, icon_size)
    icon_top = y + 14
    if icon is not None:
        px = x + (w - icon.width) // 2
        img.paste(icon, (px, icon_top), icon)
        caption_top = icon_top + icon.height + 10
    else:
        caption_top = icon_top + icon_size + 10

    caption = str(upgrade.get("label") or upgrade.get("code") or "").strip()
    if caption:
        max_caption_height = max(0, (y + h) - caption_top - 12)
        _draw_wrapped_lines(
            draw,
            caption,
            x=x + 10,
            y=caption_top,
            width=w - 20,
            font=caption_font,
            fill=WOWS_TEXT_SUB,
            line_gap=4,
            max_height=max_caption_height,
            align="center",
        )


def _draw_module_grid(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    entries: list[dict[str, Any]],
    box: tuple[int, int, int, int],
    start_y: int,
    label_font: ImageFont.ImageFont,
    caption_font: ImageFont.ImageFont,
) -> int:
    if not entries:
        return start_y
    tile_w = 118
    tile_h = 118
    gap_x = 12
    gap_y = 12
    cols = max(1, (box[2] - box[0] - 56) // (tile_w + gap_x))
    x0 = box[0] + 28
    y = start_y
    for idx, entry in enumerate(entries):
        row = idx // cols
        col = idx % cols
        tile_x = x0 + col * (tile_w + gap_x)
        tile_y = y + row * (tile_h + gap_y)
        if tile_y + tile_h > box[3] - 20:
            break
        _draw_module_tile(
            img,
            draw,
            x=tile_x,
            y=tile_y,
            w=tile_w,
            h=tile_h,
            entry=entry,
            icon_size=52,
            label_font=label_font,
            caption_font=caption_font,
        )
    rows_used = (len(entries) + cols - 1) // cols
    return y + rows_used * (tile_h + gap_y)


def _draw_consumable_tile(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    entry: dict[str, Any],
    icon_size: int,
    label_font: ImageFont.ImageFont,
    caption_font: ImageFont.ImageFont,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=WOWS_PANEL, outline=WOWS_OUTLINE, width=2)
    draw.rounded_rectangle((x + 4, y + 4, x + w - 4, y + h - 4), radius=10, outline=WOWS_OUTLINE_SOFT, width=1)

    icon = load_consumable_tile_icon(entry, icon_size)
    if icon is not None:
        px = x + (w - icon.width) // 2
        py = y + 8
        img.paste(icon, (px, py), icon)
    else:
        short = "".join(word[:1] for word in str(entry.get("label") or "?").split()[:2]).upper() or "?"
        fw, fh = _measure_text(draw, short, label_font)
        draw.text((x + (w - fw) // 2, y + 16), short, font=label_font, fill=WOWS_TEXT)

    caption = str(entry.get("label") or "").strip()
    if caption:
        caption_top = y + h - 60
        max_caption_height = max(0, (y + h) - caption_top - 6)
        _draw_wrapped_lines(
            draw,
            caption,
            x=x + 6,
            y=caption_top,
            width=w - 12,
            font=caption_font,
            fill=WOWS_TEXT_SUB,
            line_gap=0,
            max_height=max_caption_height,
            align="center",
        )


def _draw_consumable_grid(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    entries: list[dict[str, Any]],
    box: tuple[int, int, int, int],
    start_y: int,
    label_font: ImageFont.ImageFont,
    caption_font: ImageFont.ImageFont,
) -> int:
    if not entries:
        return start_y
    tile_w = 118
    tile_h = 118
    gap_x = 12
    gap_y = 12
    cols = max(1, (box[2] - box[0] - 56) // (tile_w + gap_x))
    x0 = box[0] + 28
    y = start_y
    for idx, entry in enumerate(entries):
        row = idx // cols
        col = idx % cols
        tile_x = x0 + col * (tile_w + gap_x)
        tile_y = y + row * (tile_h + gap_y)
        if tile_y + tile_h > box[3] - 20:
            break
        _draw_consumable_tile(
            img,
            draw,
            x=tile_x,
            y=tile_y,
            w=tile_w,
            h=tile_h,
            entry=entry,
            icon_size=52,
            label_font=label_font,
            caption_font=caption_font,
        )
    rows_used = (len(entries) + cols - 1) // cols
    return y + rows_used * (tile_h + gap_y)


def _draw_skill_tile(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    skill_name: str,
    icon_size: int,
    active: bool = True,
) -> None:
    outer_fill = WOWS_PANEL if active else WOWS_PANEL_INNER
    outer_outline = WOWS_TEXT if active else WOWS_OUTLINE_SOFT
    inner_outline = WOWS_OUTLINE_SOFT if active else WOWS_OUTLINE_INNER
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=outer_fill, outline=outer_outline, width=2)
    draw.rounded_rectangle((x + 4, y + 4, x + w - 4, y + h - 4), radius=10, outline=inner_outline, width=1)

    icon = _load_commander_skill_icon(skill_name, icon_size)
    if icon is not None:
        if not active:
            alpha = icon.getchannel("A").point(lambda value: int(value * 0.28))
            icon = icon.copy()
            icon.putalpha(alpha)
        px = x + (w - icon.width) // 2
        py = y + (h - icon.height) // 2
        img.paste(icon, (px, py), icon)
    else:
        fallback_font = _load_bot_font(max(20, icon_size // 2), bold=True)
        fw, fh = _measure_text(draw, "?", fallback_font)
        fill = WOWS_TEXT if active else WOWS_TEXT_DIM
        draw.text((x + (w - fw) // 2, y + (h - fh) // 2), "?", font=fallback_font, fill=fill)


def _render_build_card_image(payload: dict[str, Any]) -> Image.Image:
    width = 1480

    player_name = str(payload.get("player_name") or "Unknown player")
    ship_name = str(payload.get("ship_name") or "Unknown ship")
    ship_code = str(payload.get("ship_code") or "").strip()
    ship_type = str(payload.get("ship_type") or "").strip()
    captain = payload.get("captain_skills", {}) or {}
    build = payload.get("ship_build", {}) or {}

    # Pre-compute right-panel data so the card height can adapt.
    components = build.get("components", {}) if isinstance(build, dict) else {}
    ship_id = payload.get("ship_id")
    stock_modules, fitted_modules = (
        build_module_entries(components, ship_type=ship_type, ship_id=ship_id)
        if isinstance(components, dict)
        else ([], [])
    )
    all_modules = stock_modules + fitted_modules
    upgrades = parse_mounted_upgrades(
        str(build.get("config_dump_hex") or "") if isinstance(build, dict) else ""
    )
    consumables = build_consumable_entries(
        build if isinstance(build, dict) else None, ship_id=ship_id
    )

    # Tile dimensions used by the module/consumable grids.
    _tile_w = 118
    _tile_h = 118
    _gap_x = 12
    _gap_y = 12
    _right_inner = (width - 56) - 730 - 56
    _cols = max(1, _right_inner // (_tile_w + _gap_x))

    # Estimate the vertical space the right panel needs.
    panels_top = 250
    right_content_h = 78  # "Ship Build" heading offset
    if all_modules:
        right_content_h += 36  # "Stock modules" heading
        _mod_rows = (len(all_modules) + _cols - 1) // _cols
        right_content_h += _mod_rows * (_tile_h + _gap_y)
        right_content_h += 12  # inter-section gap
    if consumables:
        right_content_h += 36  # "Consumables" heading
        _cons_rows = (len(consumables) + _cols - 1) // _cols
        right_content_h += _cons_rows * (_tile_h + _gap_y)
    if not all_modules and not consumables and not upgrades:
        right_content_h += 40  # fallback text
    right_content_h += 22  # bottom padding

    panel_height = max(510, right_content_h)
    panels_bottom = panels_top + panel_height

    upgrades_gap = 16
    upgrades_h = 216
    if upgrades:
        height = panels_bottom + upgrades_gap + upgrades_h + 48
    else:
        height = panels_bottom + 48
    height = max(1040, height)

    img = Image.new("RGB", (width, height), WOWS_BG)
    header_texture = _load_rgba_asset(WOWS_PANEL_TEXTURE_PATH)
    if header_texture is not None:
        header_box = (48, 48, width - 48, 214)
        header_w = header_box[2] - header_box[0]
        header_h = header_box[3] - header_box[1]
        texture = header_texture.resize((header_w, header_h), Image.Resampling.LANCZOS)
        texture = texture.copy()
        texture.putalpha(texture.getchannel("A").point(lambda a: int(a * 0.28)))
        img.paste(texture, (header_box[0], header_box[1]), texture)

    logo = _tint_rgba_asset(_load_rgba_asset(WOWS_LOGO_WG_PATH), WOWS_TEXT)
    if logo is not None:
        logo = logo.copy()
        logo.thumbnail((260, 84), Image.Resampling.LANCZOS)
        logo.putalpha(logo.getchannel("A").point(lambda a: int(a * 0.52)))

    draw = ImageDraw.Draw(img)

    title_font = _load_bot_font(44, bold=True)
    header_font = _load_bot_font(28, bold=True)
    body_font = _load_bot_font(24)
    small_font = _load_bot_font(20)
    skill_heading_font = _load_bot_font(22, bold=True)
    micro_font = _load_bot_font(16)
    tiny_font = _load_bot_font(15)

    draw.rounded_rectangle((28, 28, width - 28, height - 28), radius=28, fill=WOWS_PANEL, outline=WOWS_OUTLINE, width=2)
    draw.rounded_rectangle((48, 48, width - 48, 214), radius=24, fill=WOWS_PANEL_ALT)

    if logo is not None:
        logo_wm = logo.copy()
        logo_wm.thumbnail((180, 56), Image.Resampling.LANCZOS)
        logo_wm.putalpha(logo_wm.getchannel("A").point(lambda a: int(a * 0.18)))
        watermark_x = width - 58 - logo_wm.width
        watermark_y = height - 58 - logo_wm.height
        img.paste(logo_wm, (watermark_x, watermark_y), logo_wm)

    draw.text((84, 76), "Captain & Ship Build", font=title_font, fill=WOWS_TEXT)
    draw.text((86, 134), f"{player_name}  |  {ship_name}", font=header_font, fill=WOWS_ACCENT)
    if ship_code:
        draw.text((86, 174), ship_code, font=small_font, fill=WOWS_TEXT_DIM)

    art = _load_build_ship_art(ship_code, 360, 140)
    if art is not None:
        art_x = width - 86 - art.width
        art_y = 74 + max(0, (128 - art.height) // 2)
        img.paste(art, (art_x, art_y), art)

    left_box = (56, panels_top, 690, panels_bottom)
    right_box = (730, panels_top, width - 56, panels_bottom)
    upgrades_box = (56, panels_bottom + upgrades_gap, width - 56, panels_bottom + upgrades_gap + upgrades_h)
    for box in (left_box, right_box):
        draw.rounded_rectangle(box, radius=22, fill=WOWS_PANEL_ALT, outline=WOWS_OUTLINE_SOFT, width=2)

    draw.text((left_box[0] + 28, left_box[1] + 22), "Skills & Talents", font=header_font, fill=WOWS_TEXT)
    draw.text((right_box[0] + 28, right_box[1] + 22), "Ship Build", font=header_font, fill=WOWS_TEXT)

    grid_panel = (left_box[0] + 20, left_box[1] + 66, left_box[2] - 20, left_box[3] - 22)
    draw.rounded_rectangle(grid_panel, radius=18, fill=WOWS_PANEL_INNER, outline=WOWS_OUTLINE_SOFT, width=1)

    y_left = left_box[1] + 84
    selected_type, skills = _select_ship_class_skills(captain, ship_type)
    skill_layout = _layout_for_ship_type(selected_type or ship_type)
    if skills and skill_layout and _layout_covers_skills(skills, skill_layout):
        draw.text((left_box[0] + 34, y_left), _pretty_token(selected_type or ship_type or "Captain"), font=skill_heading_font, fill=WOWS_TEXT_SUB)
        spent_points = _captain_points_for_layout(skills, skill_layout)
        draw.text((left_box[0] + 34, y_left + 28), f"Captain points: {spent_points}/21", font=micro_font, fill=WOWS_TEXT_DIM)
        y_left += 62
        tile_w = 84
        tile_h = 84
        gap_x = 14
        gap_y = 14
        start_x = left_box[0] + 34
        learned_set = {str(skill) for skill in skills if skill}
        for row_idx, row_skills in enumerate(skill_layout):
            for col_idx, slot_skill in enumerate(row_skills):
                if not slot_skill:
                    continue
                active = slot_skill in learned_set
                tile_x = start_x + col_idx * (tile_w + gap_x)
                tile_y = y_left + row_idx * (tile_h + gap_y)
                _draw_skill_tile(
                    img,
                    draw,
                    x=tile_x,
                    y=tile_y,
                    w=tile_w,
                    h=tile_h,
                    skill_name=slot_skill,
                    icon_size=40,
                    active=active,
                )
    elif skills:
        draw.text((left_box[0] + 34, y_left), _pretty_token(selected_type or ship_type or "Captain"), font=skill_heading_font, fill=WOWS_TEXT_SUB)
        generic_caption = "Replay-confirmed commander skills for this ship class"
        if skill_layout:
            generic_caption = "Replay-confirmed commander skills. Layout fallback used because one or more mapped slots did not match replay data."
        draw.text((left_box[0] + 34, y_left + 28), generic_caption, font=micro_font, fill=WOWS_TEXT_DIM)
        y_left += 58
        cols = 5
        tile_w = 78
        tile_h = 78
        gap_x = 14
        gap_y = 14
        start_x = left_box[0] + 34
        for idx, skill in enumerate(skills):
            row = idx // cols
            col = idx % cols
            tile_x = start_x + col * (tile_w + gap_x)
            tile_y = y_left + row * (tile_h + gap_y)
            _draw_skill_tile(
                img,
                draw,
                x=tile_x,
                y=tile_y,
                w=tile_w,
                h=tile_h,
                skill_name=skill,
                icon_size=40,
            )
    else:
        draw.text((left_box[0] + 34, y_left), "No captain skill data found in this replay.", font=body_font, fill=WOWS_TEXT_DIM)

    y_right = right_box[1] + 78

    if all_modules:
        draw.text((right_box[0] + 28, y_right), "Stock modules", font=skill_heading_font, fill=WOWS_TEXT_SUB)
        y_right += 36
        y_right = _draw_module_grid(
            img,
            draw,
            entries=all_modules,
            box=right_box,
            start_y=y_right,
            label_font=small_font,
            caption_font=tiny_font,
        )
        y_right += 12

    if consumables:
        draw.text((right_box[0] + 28, y_right), "Consumables", font=skill_heading_font, fill=WOWS_TEXT_SUB)
        y_right += 36
        y_right = _draw_consumable_grid(
            img,
            draw,
            entries=consumables,
            box=right_box,
            start_y=y_right,
            label_font=small_font,
            caption_font=tiny_font,
        )
    elif not all_modules and not upgrades:
        draw.text((right_box[0] + 28, y_right), "No ship build data found in this replay.", font=body_font, fill=WOWS_TEXT_DIM)

    if upgrades:
        # Full-width band along the bottom of the card -- gives each tile
        # enough room to fit the longest modernization names without text
        # spilling outside the box.
        draw.rounded_rectangle(upgrades_box, radius=22, fill=WOWS_PANEL_ALT, outline=WOWS_OUTLINE_SOFT, width=2)
        draw.text((upgrades_box[0] + 28, upgrades_box[1] + 18), "Mounted upgrades", font=header_font, fill=WOWS_TEXT)

        count = max(1, len(upgrades))
        gap_x = 14
        row_inner = upgrades_box[2] - upgrades_box[0] - 56
        tile_w = max(140, (row_inner - gap_x * (count - 1)) // count)
        tile_h = upgrades_box[3] - upgrades_box[1] - 78
        x0 = upgrades_box[0] + 28
        y0 = upgrades_box[1] + 66
        upgrade_caption_font = _load_bot_font(18, bold=True)
        for idx, upgrade in enumerate(upgrades):
            tile_x = x0 + idx * (tile_w + gap_x)
            _draw_upgrade_tile(
                img,
                draw,
                x=tile_x,
                y=y0,
                w=tile_w,
                h=tile_h,
                upgrade=upgrade,
                icon_size=72,
                caption_font=upgrade_caption_font,
                slot_font=None,
            )

    return img


def _dual_result_embed(
    filename_a: str,
    filename_b: str,
    output_length_label: str,
    canonical_a: dict[str, Any],
    canonical_b: dict[str, Any],
) -> discord.Embed:
    meta_a = canonical_a.get("meta", {}) or {}
    meta_b = canonical_b.get("meta", {}) or {}
    map_name = str(
        meta_a.get("map_name_resolved")
        or meta_a.get("mapDisplayName")
        or meta_b.get("map_name_resolved")
        or meta_b.get("mapDisplayName")
        or "Unknown map"
    )
    player_a = str(meta_a.get("playerName") or "Unknown player")
    player_b = str(meta_b.get("playerName") or "Unknown player")
    ship_a = _resolve_ship_name(canonical_a)
    ship_b = _resolve_ship_name(canonical_b)

    embed = discord.Embed(title="Merged Dual Render Complete", color=discord.Color.green())
    embed.add_field(name="Map", value=map_name, inline=False)
    embed.add_field(name="View A", value=f"{player_a}\n{ship_a}", inline=True)
    embed.add_field(name="View B", value=f"{player_b}\n{ship_b}", inline=True)
    embed.add_field(name="Output Length", value=output_length_label, inline=True)
    embed.add_field(name="Replay A", value=filename_a, inline=False)
    embed.add_field(name="Replay B", value=filename_b, inline=False)
    return embed


class RenderResultView(discord.ui.View):
    def __init__(
        self,
        frame_path: Path | None,
        build_payload: dict[str, Any] | None,
        owner_id: int,
        *,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.frame_path = Path(frame_path) if frame_path is not None else None
        self.build_payload = build_payload or None
        self.owner_id = int(owner_id)
        self.message: discord.Message | None = None
        if self.frame_path is None or not self.frame_path.is_file():
            self.send_second_last_frame.disabled = True
        if self.build_payload is None:
            self.send_build_card.disabled = True

    def _cleanup_file(self) -> None:
        if self.frame_path is None:
            return
        with contextlib.suppress(FileNotFoundError):
            self.frame_path.unlink()

    async def _refresh_view(self) -> None:
        if self.message is not None:
            with contextlib.suppress(Exception):
                await self.message.edit(view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        await self._refresh_view()
        self._cleanup_file()
        self.build_payload = None

    async def _consume_button(self, button: discord.ui.Button) -> None:
        button.disabled = True
        await self._refresh_view()
        if all(getattr(child, "disabled", False) for child in self.children):
            self.stop()

    @discord.ui.button(label="Battle Results", style=discord.ButtonStyle.secondary)
    async def send_second_last_frame(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This button is only for the user who requested the render.", ephemeral=True)
            return
        if self.frame_path is None or not self.frame_path.is_file():
            await self._consume_button(button)
            await interaction.response.send_message("The saved frame is no longer available.", ephemeral=True)
            self._cleanup_file()
            return

        with self.frame_path.open("rb") as fp:
            discord_file = discord.File(fp, filename=self.frame_path.name or "second_last_frame.png")
            await interaction.response.send_message(
                content=f"{interaction.user.mention} battle results",
                file=discord_file,
                allowed_mentions=discord.AllowedMentions(users=True),
            )

        await self._consume_button(button)
        self._cleanup_file()

    @discord.ui.button(label="Captain & Build", style=discord.ButtonStyle.secondary)
    async def send_build_card(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This button is only for the user who requested the render.", ephemeral=True)
            return
        if not self.build_payload:
            await self._consume_button(button)
            await interaction.response.send_message("No ship build data is available for this replay.", ephemeral=True)
            return

        # The first call may decode the 16 MB GameParams pickle, which takes
        # several seconds -- well past Discord's 3-second response window.
        # Defer immediately so the interaction token stays alive while the
        # image is built, then post the result via followup.
        try:
            await interaction.response.defer(thinking=True)
        except discord.HTTPException:
            LOG.exception("Build-card defer failed")
            return

        try:
            image = await asyncio.to_thread(_render_build_card_image, self.build_payload)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)
            filename = f"{str(self.build_payload.get('ship_name') or 'ship').strip().replace(' ', '_').lower()}_build.png"
            discord_file = discord.File(buffer, filename=filename)
            await interaction.followup.send(
                content=f"{interaction.user.mention} captain and ship build",
                file=discord_file,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except Exception:
            LOG.exception("Failed to render build card")
            with contextlib.suppress(discord.HTTPException):
                await interaction.followup.send("Failed to build the captain/loadout image.", ephemeral=True)
            return

        await self._consume_button(button)


def _progress_bar(current: int, total: int, width: int = 12) -> str:
    total = max(1, int(total))
    current = max(0, min(int(current), total))
    filled = max(0, min(width, int(round((current / total) * width))))
    return "#" * filled + "-" * (width - filled)


def _queue_embed(label: str, queue_position: int, queued_at: float, *, is_dual: bool, active_running: bool, queue_depth: int = 0) -> discord.Embed:
    title = "Dual Render Queued" if is_dual else "Render Queued"
    pos = max(1, int(queue_position))
    if pos == 1 and active_running:
        status = "You're next — waiting for the current render to finish"
    elif active_running:
        status = f"{pos - 1} render(s) ahead of you"
    else:
        status = "Starting soon"
    elapsed = max(0, int(time.monotonic() - queued_at))
    embed = discord.Embed(title=title, color=discord.Color.orange())
    embed.add_field(name="Replay", value=label, inline=False)
    depth = max(pos, int(queue_depth))
    position_label = f"#{pos} of {depth}" if depth > 1 else f"#{pos}"
    embed.add_field(name="Queue Position", value=position_label, inline=True)
    embed.add_field(name="Queued", value=f"{elapsed}s", inline=True)
    embed.add_field(name="Status", value=status, inline=False)
    return embed


class QueueFullError(Exception):
    """Raised when the render queue has reached its maximum depth."""


def _render_queue_condition() -> asyncio.Condition:
    global ACTIVE_RENDER_TICKET, RENDER_QUEUE_CONDITION, RENDER_QUEUE_LOOP
    loop = asyncio.get_running_loop()
    if RENDER_QUEUE_CONDITION is None or RENDER_QUEUE_LOOP is not loop:
        if RENDER_QUEUE_LOOP is not None and RENDER_QUEUE_LOOP is not loop:
            RENDER_QUEUE.clear()
            ACTIVE_RENDER_TICKET = None
        RENDER_QUEUE_CONDITION = asyncio.Condition()
        RENDER_QUEUE_LOOP = loop
    return RENDER_QUEUE_CONDITION


async def _enqueue_render_ticket() -> int:
    global NEXT_RENDER_TICKET
    condition = _render_queue_condition()
    async with condition:
        if len(RENDER_QUEUE) >= MAX_RENDER_QUEUE:
            raise QueueFullError(
                f"The render queue is full ({MAX_RENDER_QUEUE} pending). Please try again later."
            )
        ticket_id = NEXT_RENDER_TICKET
        NEXT_RENDER_TICKET += 1
        RENDER_QUEUE.append(ticket_id)
        condition.notify_all()
        return ticket_id


async def _queue_snapshot(ticket_id: int) -> tuple[int, bool, bool, int]:
    """Return (position, is_active, is_running, queue_depth)."""
    condition = _render_queue_condition()
    async with condition:
        is_active = ACTIVE_RENDER_TICKET == ticket_id
        is_running = ACTIVE_RENDER_TICKET is not None
        depth = len(RENDER_QUEUE)
        if is_active:
            return 0, True, is_running, depth
        try:
            position = list(RENDER_QUEUE).index(ticket_id) + 1
        except ValueError:
            position = 0
        return position, False, is_running, depth


async def _acquire_render_turn(ticket_id: int) -> None:
    global ACTIVE_RENDER_TICKET
    deadline = time.monotonic() + RENDER_QUEUE_TIMEOUT_S
    condition = _render_queue_condition()
    async with condition:
        while ACTIVE_RENDER_TICKET is not None or not RENDER_QUEUE or RENDER_QUEUE[0] != ticket_id:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                with contextlib.suppress(ValueError):
                    RENDER_QUEUE.remove(ticket_id)
                condition.notify_all()
                raise asyncio.TimeoutError("Render queue wait timed out")
            try:
                await asyncio.wait_for(
                    condition.wait(), timeout=remaining,
                )
            except asyncio.TimeoutError:
                with contextlib.suppress(ValueError):
                    RENDER_QUEUE.remove(ticket_id)
                condition.notify_all()
                raise asyncio.TimeoutError("Render queue wait timed out")
        ACTIVE_RENDER_TICKET = ticket_id
        RENDER_QUEUE.popleft()
        condition.notify_all()


async def _release_render_turn(ticket_id: int) -> None:
    global ACTIVE_RENDER_TICKET
    condition = _render_queue_condition()
    async with condition:
        if ACTIVE_RENDER_TICKET == ticket_id:
            ACTIVE_RENDER_TICKET = None
        else:
            with contextlib.suppress(ValueError):
                RENDER_QUEUE.remove(ticket_id)
        condition.notify_all()


async def _queue_status_updater(
    interaction: discord.Interaction,
    label: str,
    ticket_id: int,
    queued_at: float,
    *,
    is_dual: bool,
) -> None:
    last_sent: tuple[int, bool, int] | None = None
    while True:
        position, is_active, is_running, depth = await _queue_snapshot(ticket_id)
        if is_active or position <= 0:
            return
        snapshot = (position, is_running, depth)
        if snapshot != last_sent:
            try:
                await interaction.edit_original_response(
                    embed=_queue_embed(label, position, queued_at, is_dual=is_dual, active_running=is_running, queue_depth=depth),
                    attachments=[],
                    content=None,
                )
            except Exception:
                LOG.exception("Failed to update queue message")
                return
            last_sent = snapshot
        await asyncio.sleep(2.0)


async def _enter_render_queue(interaction: discord.Interaction, label: str, *, is_dual: bool) -> int:
    ticket_id = await _enqueue_render_ticket()
    queued_at = time.monotonic()
    position, _, is_running, depth = await _queue_snapshot(ticket_id)
    await interaction.edit_original_response(
        embed=_queue_embed(label, position or 1, queued_at, is_dual=is_dual, active_running=is_running, queue_depth=depth),
        attachments=[],
        content=None,
    )

    updater = asyncio.create_task(_queue_status_updater(interaction, label, ticket_id, queued_at, is_dual=is_dual))
    try:
        await _acquire_render_turn(ticket_id)
    finally:
        updater.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await updater
    return ticket_id

def _render_progress_embed(filename: str, output_length_label: str, stage: str, current: int, total: int, started_at: float) -> discord.Embed:
    pct = int(round((max(0, current) / max(1, total)) * 100))
    if stage == "loading":
        title = "Rendering Replay"
        status = "Loading replay data"
    elif stage == "rendering_a":
        title = "Rendering Dual Replay"
        status = "Rendering view A"
    elif stage == "encoding_a":
        title = "Rendering Dual Replay"
        status = "Encoding view A"
    elif stage == "rendering_b":
        title = "Rendering Dual Replay"
        status = "Rendering view B"
    elif stage == "encoding_b":
        title = "Rendering Dual Replay"
        status = "Encoding view B"
    elif stage == "stacking":
        title = "Rendering Dual Replay"
        status = "Combining both views"
    elif stage == "encoding":
        title = "Rendering Replay"
        status = "Encoding MP4 frames"
    elif stage == "done":
        title = "Render Complete"
        status = "Upload ready"
    else:
        title = "Rendering Replay"
        status = "Preparing render"

    elapsed = max(0, int(time.monotonic() - started_at))
    embed = discord.Embed(title=title, color=discord.Color.blurple())
    embed.add_field(name="Replay", value=filename, inline=False)
    embed.add_field(name="Output Length", value=output_length_label, inline=True)
    embed.add_field(name="Elapsed", value=f"{elapsed}s", inline=True)
    embed.add_field(name="Status", value=status, inline=False)
    embed.add_field(name="Progress", value=f"`{_progress_bar(current, total)}` {pct}%", inline=False)
    return embed


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> "datetime | None":
    """Normalize a replay meta ``dateTime`` to a timezone-aware ``datetime``.

    WoWS clients serialize the battle start time in several shapes: integer
    epoch seconds, float epoch seconds, ISO-8601 strings with or without
    fractional seconds, and with or without a trailing ``Z``. This helper
    accepts all of them so :func:`_battle_identity_error` can do a
    tolerance-based comparison instead of brittle string equality.
    Returns ``None`` if the value is empty or unparseable.
    """
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    # Last resort: numeric epoch encoded as a string.
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _battle_identity_error(canonical_a: dict[str, Any], canonical_b: dict[str, Any]) -> str | None:
    meta_a = canonical_a.get("meta", {}) or {}
    meta_b = canonical_b.get("meta", {}) or {}

    arena_a = _safe_int(meta_a.get("battle_arena_id"))
    arena_b = _safe_int(meta_b.get("battle_arena_id"))
    # If both arena IDs are present and equal, the replays are definitively
    # from the same battle regardless of any dateTime drift. WoWS assigns
    # one arena per match and it is identical across every player's replay
    # of that match, so this is a stronger identity signal than dateTime.
    if arena_a is not None and arena_b is not None and arena_a == arena_b:
        return None
    if arena_a is not None and arena_b is not None and arena_a != arena_b:
        return "The replays are from different battles."

    map_a = str(meta_a.get("mapDisplayName") or meta_a.get("mapName") or meta_a.get("mapId") or "").strip()
    map_b = str(meta_b.get("mapDisplayName") or meta_b.get("mapName") or meta_b.get("mapId") or "").strip()
    if map_a and map_b and map_a != map_b:
        return "The replays are on different maps."

    dt_a = meta_a.get("dateTime")
    dt_b = meta_b.get("dateTime")
    if dt_a and dt_b:
        parsed_a = _parse_dt(dt_a)
        parsed_b = _parse_dt(dt_b)
        if parsed_a is not None and parsed_b is not None:
            # Truncate to whole seconds to ignore sub-second capture jitter
            # (e.g. "...:43" vs "...:43.500") and allow a small tolerance
            # for clients that captured the start packet a few seconds
            # apart. Beyond 5s is treated as a different battle.
            delta = abs(
                (parsed_a.replace(microsecond=0) - parsed_b.replace(microsecond=0)).total_seconds()
            )
            if delta > 5:
                return "The replays have different battle start times."
        else:
            # Couldn't parse one or both - fall back to strict string compare
            # so we don't silently accept malformed input.
            s_a = str(dt_a).strip()
            s_b = str(dt_b).strip()
            if s_a and s_b and s_a != s_b:
                return "The replays have different battle start times."

    team_a = _safe_int(meta_a.get("local_team_id"))
    team_b = _safe_int(meta_b.get("local_team_id"))
    if team_a is not None and team_b is not None and team_a == team_b:
        return "Both replays appear to be from the same team."

    return None


def _dual_output_filename(stem_a: str, stem_b: str) -> str:
    safe_a = stem_a[:48].strip() or "view_a"
    safe_b = stem_b[:48].strip() or "view_b"
    return f"{safe_a}__{safe_b}_dual_minimap.mp4"


def _norm_player_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _source_team_side(canonical: dict[str, Any], entity_key: Any, track: dict[str, Any] | None = None) -> str:
    def _side(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in ("ally", "player", "friendly", "green"):
            return "friendly"
        if text in ("enemy", "foe", "red"):
            return "enemy"
        return "unknown"

    track = track if isinstance(track, dict) else {}
    side = _side(track.get("team_side") or track.get("team"))
    if side != "unknown":
        return side
    entities = canonical.get("entities", {}) or {}
    entity = entities.get(str(entity_key), {}) if isinstance(entities, dict) else {}
    if isinstance(entity, dict):
        side = _side(entity.get("team_side") or entity.get("team"))
        if side != "unknown":
            return side
    return "unknown"


def _entity_identity(canonical: dict[str, Any], entity_key: Any, track: dict[str, Any] | None = None) -> dict[str, str]:
    track = track if isinstance(track, dict) else {}
    entities = canonical.get("entities", {}) or {}
    entity = entities.get(str(entity_key), {}) if isinstance(entities, dict) else {}
    if not isinstance(entity, dict):
        entity = {}
    player_name = str(track.get("player_name") or entity.get("player_name") or "").strip()
    account_id = str(entity.get("account_entity_id") or track.get("account_entity_id") or "").strip()
    ship_id = str(track.get("ship_id") or entity.get("ship_id") or "").strip()
    return {
        "account": account_id,
        "name": _norm_player_key(player_name),
        "ship": ship_id,
    }


def _merge_dual_canonical(canonical_a: dict[str, Any], canonical_b: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(canonical_a)
    meta = copy.deepcopy(canonical_a.get("meta", {}) or {})
    meta["hide_player_card"] = True
    meta["merged_dual_render"] = True

    merged_tracks: dict[str, dict[str, Any]] = {}
    merged_entities: dict[str, dict[str, Any]] = {}
    merged_vehicles: list[dict[str, Any]] = []
    direct_maps: dict[str, dict[str, str]] = {"a": {}, "b": {}}
    identity_maps: dict[str, dict[tuple[str, str], str]] = {"a": {}, "b": {}}

    def _new_entity_id(prefix: str, raw_key: Any, raw_entity_id: Any) -> int:
        base = _safe_int(raw_entity_id)
        if base is None:
            base = _safe_int(raw_key)
        if base is None:
            base = abs(hash((prefix, str(raw_key)))) % 900000
        return int(base) if prefix == "a" else int(base) + 1_000_000

    def _remember_identity(prefix: str, canonical: dict[str, Any], old_key: Any, track: dict[str, Any], new_key: str) -> None:
        ident = _entity_identity(canonical, old_key, track)
        for kind in ("account", "name"):
            value = ident.get(kind, "")
            if value:
                identity_maps[prefix][(kind, value)] = new_key

    def _add_vehicles(prefix: str, canonical: dict[str, Any], desired_relation: int) -> None:
        vehicles = (canonical.get("meta", {}) or {}).get("vehicles", []) or []
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                continue
            relation = _safe_int(vehicle.get("relation"))
            if relation == 2:
                continue
            row = copy.deepcopy(vehicle)
            row["relation"] = int(desired_relation)
            row["merged_view"] = prefix
            merged_vehicles.append(row)

    def _copy_side(prefix: str, canonical: dict[str, Any], desired_side: str, desired_relation: int) -> None:
        _add_vehicles(prefix, canonical, desired_relation)
        tracks = canonical.get("tracks", {}) or {}
        entities = canonical.get("entities", {}) or {}
        for old_key, track_raw in tracks.items():
            if not isinstance(track_raw, dict):
                continue
            if _source_team_side(canonical, old_key, track_raw) != "friendly":
                continue
            old_key_s = str(old_key)
            entity_raw = entities.get(old_key_s, {}) if isinstance(entities, dict) else {}
            if not isinstance(entity_raw, dict):
                entity_raw = {}
            new_id = _new_entity_id(prefix, old_key, track_raw.get("entity_id") or entity_raw.get("entity_id"))
            new_key = str(new_id)
            direct_maps[prefix][old_key_s] = new_key

            track = copy.deepcopy(track_raw)
            track["entity_id"] = new_id
            track["team"] = desired_side
            track["team_side"] = desired_side
            track["team_label_side"] = desired_side
            merged_tracks[new_key] = track

            entity = copy.deepcopy(entity_raw)
            entity["entity_id"] = new_id
            entity["team"] = desired_side
            entity["team_side"] = desired_side
            entity.setdefault("player_name", track.get("player_name", ""))
            entity.setdefault("ship_id", track.get("ship_id"))
            merged_entities[new_key] = entity
            _remember_identity(prefix, canonical, old_key_s, track_raw, new_key)

    _copy_side("a", canonical_a, "friendly", 0)
    _copy_side("b", canonical_b, "enemy", 2)

    def _resolve_ref(prefix: str, canonical: dict[str, Any], old_key: Any) -> str:
        old_key_s = str(old_key or "")
        if old_key_s in direct_maps[prefix]:
            return direct_maps[prefix][old_key_s]
        tracks = canonical.get("tracks", {}) or {}
        track = tracks.get(old_key_s, {}) if isinstance(tracks, dict) else {}
        ident = _entity_identity(canonical, old_key_s, track if isinstance(track, dict) else {})
        other_prefix = "b" if prefix == "a" else "a"
        for kind in ("account", "name"):
            value = ident.get(kind, "")
            if value:
                mapped = identity_maps[other_prefix].get((kind, value))
                if mapped:
                    return mapped
        return "-1"

    def _remap_entity_id(prefix: str, canonical: dict[str, Any], old_id: Any) -> int | None:
        mapped = _resolve_ref(prefix, canonical, old_id)
        return _safe_int(mapped)

    def _dedupe_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
        seen: set[tuple[Any, ...]] = set()
        out: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda item: float(item.get("time_s", item.get("start_time", 0.0)) or 0.0)):
            key = tuple(row.get(field) for field in key_fields)
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    def _copy_actor_events(prefix: str, canonical: dict[str, Any], event_name: str) -> list[dict[str, Any]]:
        rows = ((canonical.get("events", {}) or {}).get(event_name, []) or [])
        copied: list[dict[str, Any]] = []
        for row_raw in rows:
            if not isinstance(row_raw, dict):
                continue
            row = copy.deepcopy(row_raw)
            old_entity_id = row.get("entity_id")
            new_entity_id = _remap_entity_id(prefix, canonical, old_entity_id)
            if new_entity_id is None:
                continue
            row["entity_id"] = new_entity_id
            row["team_side"] = "friendly" if prefix == "a" else "enemy"
            copied.append(row)
        return copied

    def _copy_torpedoes(prefix: str, canonical: dict[str, Any]) -> list[dict[str, Any]]:
        rows = ((canonical.get("events", {}) or {}).get("torpedoes", []) or [])
        copied: list[dict[str, Any]] = []
        for row_raw in rows:
            if not isinstance(row_raw, dict):
                continue
            row = copy.deepcopy(row_raw)
            owner = _resolve_ref(prefix, canonical, row.get("owner_entity_key"))
            if owner == "-1":
                continue
            row["owner_entity_key"] = owner
            row["team_side"] = "friendly" if prefix == "a" else "enemy"
            copied.append(row)
        return copied

    def _copy_squadrons(prefix: str, canonical: dict[str, Any]) -> list[dict[str, Any]]:
        rows = ((canonical.get("events", {}) or {}).get("squadrons", []) or [])
        copied: list[dict[str, Any]] = []
        offset = 0 if prefix == "a" else 1_000_000
        for row_raw in rows:
            if not isinstance(row_raw, dict):
                continue
            side = _source_team_side(canonical, row_raw.get("entity_id", ""), {"team": row_raw.get("team_side")})
            if side not in ("friendly", "unknown"):
                continue
            row = copy.deepcopy(row_raw)
            squadron_id = _safe_int(row.get("squadron_id"))
            if squadron_id is not None:
                row["squadron_id"] = squadron_id + offset
            row["team_side"] = "friendly" if prefix == "a" else "enemy"
            copied.append(row)
        return copied

    def _copy_health(prefix: str, canonical: dict[str, Any]) -> list[dict[str, Any]]:
        rows = ((canonical.get("events", {}) or {}).get("health", []) or [])
        copied: list[dict[str, Any]] = []
        for row_raw in rows:
            if not isinstance(row_raw, dict):
                continue
            entities_raw = row_raw.get("entities", {})
            if not isinstance(entities_raw, dict):
                continue
            entities_new: dict[str, Any] = {}
            for old_key, state in entities_raw.items():
                new_key = _resolve_ref(prefix, canonical, old_key)
                if new_key != "-1":
                    entities_new[new_key] = copy.deepcopy(state)
            if entities_new:
                row = copy.deepcopy(row_raw)
                row["entities"] = entities_new
                copied.append(row)
        return copied

    def _copy_deaths(prefix: str, canonical: dict[str, Any]) -> list[dict[str, Any]]:
        rows = ((canonical.get("events", {}) or {}).get("deaths", []) or [])
        copied: list[dict[str, Any]] = []
        for row_raw in rows:
            if not isinstance(row_raw, dict):
                continue
            new_key = _resolve_ref(prefix, canonical, row_raw.get("entity_key"))
            if new_key == "-1":
                continue
            row = copy.deepcopy(row_raw)
            row["entity_key"] = new_key
            copied.append(row)
        return copied

    def _copy_kills(prefix: str, canonical: dict[str, Any]) -> list[dict[str, Any]]:
        rows = ((canonical.get("events", {}) or {}).get("kills", []) or [])
        copied: list[dict[str, Any]] = []
        for row_raw in rows:
            if not isinstance(row_raw, dict):
                continue
            killer = _resolve_ref(prefix, canonical, row_raw.get("killer_entity_key"))
            victim = _resolve_ref(prefix, canonical, row_raw.get("victim_entity_key"))
            if victim == "-1":
                continue
            row = copy.deepcopy(row_raw)
            row["killer_entity_key"] = killer
            row["victim_entity_key"] = victim
            copied.append(row)
        return copied

    events_a = canonical_a.get("events", {}) or {}
    merged_events = copy.deepcopy(events_a)
    merged_events["deaths"] = _dedupe_rows(_copy_deaths("a", canonical_a) + _copy_deaths("b", canonical_b), ("entity_key", "time_s"))
    merged_events["kills"] = _dedupe_rows(
        _copy_kills("a", canonical_a) + _copy_kills("b", canonical_b),
        ("time_s", "killer_entity_key", "victim_entity_key", "reason_code", "weapon_kind"),
    )
    merged_events["chat"] = _dedupe_rows(
        copy.deepcopy((canonical_a.get("events", {}) or {}).get("chat", []) or [])
        + copy.deepcopy((canonical_b.get("events", {}) or {}).get("chat", []) or []),
        ("time_s", "sender", "message"),
    )
    merged_events["health"] = _copy_health("a", canonical_a) + _copy_health("b", canonical_b)
    merged_events["sensors"] = _copy_actor_events("a", canonical_a, "sensors") + _copy_actor_events("b", canonical_b, "sensors")
    merged_events["consumables"] = _copy_actor_events("a", canonical_a, "consumables") + _copy_actor_events("b", canonical_b, "consumables")
    merged_events["smokes"] = _copy_actor_events("a", canonical_a, "smokes") + _copy_actor_events("b", canonical_b, "smokes")
    merged_events["torpedoes"] = _copy_torpedoes("a", canonical_a) + _copy_torpedoes("b", canonical_b)
    merged_events["squadrons"] = _copy_squadrons("a", canonical_a) + _copy_squadrons("b", canonical_b)
    merged_events["player_status"] = []

    meta["vehicles"] = merged_vehicles
    merged["meta"] = meta
    merged["tracks"] = merged_tracks
    merged["entities"] = merged_entities
    merged["events"] = merged_events
    merged.setdefault("diagnostics", {})
    if isinstance(merged["diagnostics"], dict):
        merged["diagnostics"]["merged_dual_render"] = {
            "team_a_tracks": sum(1 for track in merged_tracks.values() if track.get("team_side") == "friendly"),
            "team_b_tracks": sum(1 for track in merged_tracks.values() if track.get("team_side") == "enemy"),
        }
    stats = copy.deepcopy(merged.get("stats", {}) or {})
    stats["tracked_entities"] = len(merged_tracks)
    stats["track_points"] = sum(len(track.get("points", []) or []) for track in merged_tracks.values())
    stats["kills"] = len(merged_events.get("kills", []) or [])
    stats["chat_messages"] = len(merged_events.get("chat", []) or [])
    merged["stats"] = stats
    return merged


class RenderBot(discord.AutoShardedClient):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        if self.shard_id not in (None, 0):
            return
        # Only pre-warm the lightweight modernizations cache (~64 KB).
        # GameParams (~16 MB compressed → ~1 GB in memory) is loaded lazily
        # on the first "Captain & Build" press to keep idle RAM low.
        try:
            from core.modernization_resolver import _load_modernizations_cache

            await asyncio.to_thread(_load_modernizations_cache)
            LOG.info("Modernizations cache warmed")
        except Exception:
            LOG.exception("Failed to warm modernizations cache")
        synced = await self.tree.sync()
        LOG.info("Synced %s global command(s)", len(synced))


bot = RenderBot()




@bot.tree.command(name="render", description="Render a minimap MP4 from a WoWS replay upload")
@app_commands.describe(
    replay="Upload a .wowsreplay file",
)
async def render_command(
    interaction: discord.Interaction,
    replay: discord.Attachment,
) -> None:
    if not _is_replay_attachment(replay):
        await interaction.response.send_message("Upload a `.wowsreplay` file.", ephemeral=True)
        return

    if replay.size and replay.size > MAX_REPLAY_BYTES:
        await interaction.response.send_message(
            f"Replay is too large ({replay.size / (1024 * 1024):.1f} MB). Limit is {MAX_REPLAY_BYTES / (1024 * 1024):.0f} MB.",
            ephemeral=True,
        )
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.NotFound:
        LOG.warning("Interaction expired before render could defer")
        return
    except discord.HTTPException:
        LOG.exception("Failed to defer render interaction")
        return

    filename = _safe_name(replay.filename)
    stem = Path(filename).stem
    ticket_id: int | None = None

    try:
        try:
            ticket_id = await _enter_render_queue(interaction, filename, is_dual=False)
        except QueueFullError as exc:
            await interaction.edit_original_response(embed=None, content=str(exc), attachments=[])
            return
        except asyncio.TimeoutError:
            await interaction.edit_original_response(
                embed=None, content="Your render timed out waiting in the queue. Please try again later.", attachments=[],
            )
            return

        started_at = time.monotonic()
        global _CURRENT_DISCORD_UPLOAD_LIMIT
        _CURRENT_DISCORD_UPLOAD_LIMIT = _discord_upload_limit(interaction)
        base_settings = _render_settings()
        settings = _discord_render_settings(interaction, dual=False)
        try:
            replay_bytes = await replay.read()
        except Exception as exc:
            LOG.exception("Failed to read replay attachment")
            await interaction.edit_original_response(
                embed=None,
                content=f"Failed to download the replay: {exc}",
                attachments=[],
            )
            return

        progress_state = {"stage": "loading", "current": 0, "total": 1}
        progress_lock = asyncio.Lock()
        output_length_label = "auto"

        async def _set_progress(stage: str, current: int, total: int) -> None:
            async with progress_lock:
                progress_state["stage"] = stage
                progress_state["current"] = max(0, int(current))
                progress_state["total"] = max(1, int(total))

        loop = asyncio.get_running_loop()

        def _progress_callback(stage: str, current: int, total: int) -> None:
            asyncio.run_coroutine_threadsafe(_set_progress(stage, current, total), loop)

        await interaction.edit_original_response(
            embed=_render_progress_embed(filename, output_length_label, "loading", 0, 1, started_at),
            attachments=[],
            content=None,
        )

        async def _progress_updater() -> None:
            last_sent: tuple[str, int, int] | None = None
            while True:
                async with progress_lock:
                    stage = str(progress_state["stage"])
                    current = int(progress_state["current"])
                    total = int(progress_state["total"])
                snapshot = (stage, current, total)
                if snapshot != last_sent:
                    try:
                        await interaction.edit_original_response(
                            embed=_render_progress_embed(filename, output_length_label, stage, current, total, started_at),
                            attachments=[],
                            content=None,
                        )
                    except Exception:
                        LOG.exception("Failed to update render progress message")
                        return
                    last_sent = snapshot
                if stage == "done":
                    return
                await asyncio.sleep(1.0)

        progress_task = asyncio.create_task(_progress_updater())

        try:
            with tempfile.TemporaryDirectory(prefix="render_bot_") as tmpdir:
                tmp = Path(tmpdir)
                replay_path = tmp / filename
                replay_path.write_bytes(replay_bytes)
                canonical = await asyncio.to_thread(load_canonical_data, str(replay_path))
                _log_render_start(canonical, interaction)
                output_length_s = auto_output_duration_s(canonical)
                output_length_label = f"{int(round(output_length_s))}s"
                target_dur = internal_target_duration_s(output_length_s)

                out_mp4 = tmp / f"{stem}_minimap.mp4"
                cleanup_paths = [out_mp4]
                frame_fd, frame_temp = tempfile.mkstemp(prefix="render_second_last_", suffix=".png")
                os.close(frame_fd)
                second_last_frame_path = Path(frame_temp)
                keep_second_last_frame = False
                build_payload = _build_card_payload(canonical)
                render_attempts = _discord_render_attempts(
                    interaction,
                    dual=False,
                    threads=base_settings.get("threads"),
                )

                try:
                    result = await asyncio.to_thread(
                        render_minimap,
                        str(replay_path),
                        canonical=canonical,
                        out_mp4=str(out_mp4),
                        size=int(settings["size"]),
                        fps=int(settings["fps"]),
                        target_duration_s=target_dur,
                        quality=float(settings["quality"]),
                        mp4_preset=str(settings["preset"]),
                        mp4_crf=str(settings["crf"]),
                        mp4_threads=settings.get("threads"),
                        show_labels=True,
                        show_grid=True,
                        progress=_progress_callback,
                        capture_second_last_frame=str(second_last_frame_path),
                    )
                    await _set_progress("done", 1, 1)
                    await progress_task

                    file_limit = _discord_upload_limit(interaction)
                    file_size = out_mp4.stat().st_size
                    if file_size > file_limit:
                        await interaction.edit_original_response(
                            embed=None,
                            content=(
                                f"Render finished, but the MP4 is {file_size / (1024 * 1024):.1f} MB and exceeds this Discord "
                                f"upload limit of {file_limit / (1024 * 1024):.1f} MB."
                            ),
                            attachments=[],
                        )
                        return

                    with out_mp4.open("rb") as fp:
                        discord_file = discord.File(fp, filename=out_mp4.name)
                        await interaction.delete_original_response()
                        view = None
                        if second_last_frame_path.is_file() or build_payload is not None:
                            view = RenderResultView(
                                second_last_frame_path if second_last_frame_path.is_file() else None,
                                build_payload,
                                interaction.user.id,
                            )
                        sent_message = await interaction.followup.send(
                            content=f"{interaction.user.mention}",
                            embed=_result_embed(filename, output_length_label, result.get("canonical", {}) or {}),
                            file=discord_file,
                            view=view,
                            wait=True,
                            allowed_mentions=discord.AllowedMentions(users=True),
                        )
                        if view is not None:
                            view.message = sent_message
                            keep_second_last_frame = True
                finally:
                    for path in cleanup_paths:
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                        except Exception:
                            LOG.exception("Failed to delete render output %s", path)
                    if not keep_second_last_frame:
                        with contextlib.suppress(FileNotFoundError):
                            second_last_frame_path.unlink()
        except Exception as exc:
            LOG.exception("Render failed")
            if not progress_task.done():
                progress_task.cancel()
            await interaction.edit_original_response(
                embed=None,
                content=f"Render failed: {exc}",
                attachments=[],
            )
    finally:
        if ticket_id is not None:
            await _release_render_turn(ticket_id)


@bot.tree.command(name="render_dual", description="Merge two same-battle WoWS replays into one synchronized minimap MP4")
@app_commands.describe(
    replay_a="First .wowsreplay file",
    replay_b="Second .wowsreplay file from the other team",
)
async def render_dual_command(
    interaction: discord.Interaction,
    replay_a: discord.Attachment,
    replay_b: discord.Attachment,
) -> None:
    if not _is_replay_attachment(replay_a) or not _is_replay_attachment(replay_b):
        await interaction.response.send_message("Upload two `.wowsreplay` files.", ephemeral=True)
        return

    for attachment in (replay_a, replay_b):
        if attachment.size and attachment.size > MAX_REPLAY_BYTES:
            await interaction.response.send_message(
                f"`{attachment.filename}` is too large ({attachment.size / (1024 * 1024):.1f} MB). "
                f"Limit is {MAX_REPLAY_BYTES / (1024 * 1024):.0f} MB.",
                ephemeral=True,
            )
            return

    try:
        await interaction.response.defer(thinking=True)
    except discord.NotFound:
        LOG.warning("Interaction expired before dual render could defer")
        return
    except discord.HTTPException:
        LOG.exception("Failed to defer dual render interaction")
        return

    filename_a = _safe_name(replay_a.filename)
    filename_b = _safe_name(replay_b.filename)
    stem_a = Path(filename_a).stem
    stem_b = Path(filename_b).stem
    label = f"{filename_a}\n{filename_b}"
    ticket_id: int | None = None

    try:
        try:
            ticket_id = await _enter_render_queue(interaction, label, is_dual=True)
        except QueueFullError as exc:
            await interaction.edit_original_response(embed=None, content=str(exc), attachments=[])
            return
        except asyncio.TimeoutError:
            await interaction.edit_original_response(
                embed=None, content="Your render timed out waiting in the queue. Please try again later.", attachments=[],
            )
            return
        started_at = time.monotonic()
        global _CURRENT_DISCORD_UPLOAD_LIMIT
        _CURRENT_DISCORD_UPLOAD_LIMIT = _discord_upload_limit(interaction)
        settings = _discord_render_settings(interaction, dual=False)
        try:
            replay_a_bytes = await replay_a.read()
            replay_b_bytes = await replay_b.read()
        except Exception as exc:
            LOG.exception("Failed to read dual replay attachments")
            await interaction.edit_original_response(
                embed=None,
                content=f"Failed to download the replays: {exc}",
                attachments=[],
            )
            return

        progress_state = {"stage": "loading", "current": 0, "total": 1}
        progress_lock = asyncio.Lock()
        output_length_label = "auto"

        async def _set_progress(stage: str, current: int, total: int) -> None:
            async with progress_lock:
                progress_state["stage"] = stage
                progress_state["current"] = max(0, int(current))
                progress_state["total"] = max(1, int(total))

        loop = asyncio.get_running_loop()

        def _progress_callback(stage: str, current: int, total: int) -> None:
            asyncio.run_coroutine_threadsafe(_set_progress(stage, current, total), loop)

        await interaction.edit_original_response(
            embed=_render_progress_embed(label, output_length_label, "loading", 0, 1, started_at),
            attachments=[],
            content=None,
        )

        async def _progress_updater() -> None:
            last_sent: tuple[str, int, int] | None = None
            while True:
                async with progress_lock:
                    stage = str(progress_state["stage"])
                    current = int(progress_state["current"])
                    total = int(progress_state["total"])
                snapshot = (stage, current, total)
                if snapshot != last_sent:
                    try:
                        await interaction.edit_original_response(
                            embed=_render_progress_embed(label, output_length_label, stage, current, total, started_at),
                            attachments=[],
                            content=None,
                        )
                    except Exception:
                        LOG.exception("Failed to update dual render progress message")
                        return
                    last_sent = snapshot
                if stage == "done":
                    return
                await asyncio.sleep(1.0)

        progress_task = asyncio.create_task(_progress_updater())

        try:
            with tempfile.TemporaryDirectory(prefix="render_dual_bot_") as tmpdir:
                tmp = Path(tmpdir)
                replay_a_path = tmp / filename_a
                replay_b_path = tmp / filename_b
                replay_a_path.write_bytes(replay_a_bytes)
                replay_b_path.write_bytes(replay_b_bytes)

                canonical_a = await asyncio.to_thread(load_canonical_data, str(replay_a_path))
                canonical_b = await asyncio.to_thread(load_canonical_data, str(replay_b_path))
                _log_render_start(canonical_a, interaction)
                _log_render_start(canonical_b, interaction)

                identity_error = _battle_identity_error(canonical_a, canonical_b)
                if identity_error:
                    if not progress_task.done():
                        progress_task.cancel()
                    await interaction.edit_original_response(embed=None, content=identity_error, attachments=[])
                    return

                merged_canonical = _merge_dual_canonical(canonical_a, canonical_b)
                output_length_s = auto_output_duration_s(merged_canonical)
                output_length_label = f"{int(round(output_length_s))}s"
                target_dur = internal_target_duration_s(output_length_s)

                out_mp4 = tmp / _dual_output_filename(stem_a, stem_b)
                cleanup_paths = [out_mp4]

                try:
                    result = await asyncio.to_thread(
                        render_minimap,
                        str(replay_a_path),
                        canonical=merged_canonical,
                        out_mp4=str(out_mp4),
                        size=int(settings["size"]),
                        fps=int(settings["fps"]),
                        target_duration_s=target_dur,
                        quality=float(settings["quality"]),
                        mp4_preset=str(settings["preset"]),
                        mp4_crf=str(settings["crf"]),
                        mp4_threads=settings.get("threads"),
                        show_labels=True,
                        show_grid=True,
                        progress=_progress_callback,
                    )
                    await _set_progress("done", 1, 1)
                    await progress_task

                    file_limit = _discord_upload_limit(interaction)
                    file_size = out_mp4.stat().st_size
                    if file_size > file_limit:
                        await interaction.edit_original_response(
                            embed=None,
                            content=(
                                f"Dual render finished, but the MP4 is {file_size / (1024 * 1024):.1f} MB and exceeds this Discord "
                                f"upload limit of {file_limit / (1024 * 1024):.1f} MB."
                            ),
                            attachments=[],
                        )
                        return

                    with out_mp4.open("rb") as fp:
                        discord_file = discord.File(fp, filename=out_mp4.name)
                        await interaction.delete_original_response()
                        await interaction.followup.send(
                            content=f"{interaction.user.mention}",
                            embed=_dual_result_embed(filename_a, filename_b, output_length_label, result.get("canonical", {}) or merged_canonical, canonical_b),
                            file=discord_file,
                            allowed_mentions=discord.AllowedMentions(users=True),
                        )
                finally:
                    for path in cleanup_paths:
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                        except Exception:
                            LOG.exception("Failed to delete render output %s", path)
        except Exception as exc:
            LOG.exception("Dual render failed")
            if not progress_task.done():
                progress_task.cancel()
            await interaction.edit_original_response(
                embed=None,
                content=f"Dual render failed: {exc}",
                attachments=[],
            )
    finally:
        if ticket_id is not None:
            await _release_render_turn(ticket_id)






@bot.tree.command(name="help", description="Show how to use /render and /render_dual")
async def help_command(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="🎬 Render Bot — Help",
        description=(
            "I turn World of Warships replay files (`.wowsreplay`) into minimap videos. "
            "There are two render commands — pick whichever matches what you have."
        ),
        color=0x2B6CB0,
    )

    embed.add_field(
        name="📥 /render — single replay",
        value=(
            "Use this when you have **one** `.wowsreplay` file and want a minimap video of that match.\n\n"
            "**How to use:**\n"
            "1. Type `/render` in chat and press the slash command.\n"
            "2. Discord will open a file picker for the `replay` option.\n"
            "3. Select the `.wowsreplay` file from your computer and submit.\n"
            "4. Wait — the bot will queue your job and post a progress message.\n"
            "5. When it's done, the same message is edited with the finished `.mp4` attached.\n\n"
            "**Notes:**\n"
            "• File must end in `.wowsreplay` (not `.zip`/`.rar`/etc.).\n"
            f"• Max size: **{MAX_REPLAY_BYTES / (1024 * 1024):.0f} MB**.\n"
            "• One render runs at a time per server — your job is queued behind anyone else's.\n"
            "• The bot picks a quality profile automatically based on this server's upload limit."
        ),
        inline=False,
    )

    embed.add_field(
        name="🎞️ /render_dual — two replays, merged view",
        value=(
            "Use this when you have **two** replays from the **same match** (one from each team) "
            "and want one synchronized minimap with Team A from replay A and Team B from replay B.\n\n"
            "**How to use:**\n"
            "1. Type `/render_dual` and pick the command.\n"
            "2. Attach **both** `.wowsreplay` files in the `replay_a` and `replay_b` slots.\n"
            "   The order doesn't matter — the bot figures out which is which from the replays themselves.\n"
            "3. Submit and wait — the bot validates that the two files are from the same match, then renders.\n"
            "4. When finished, the message is edited with the finished merged `.mp4`.\n\n"
            "**Important:**\n"
            "• Both files must be from the **same battle** (same map, same start time, same arena).\n"
            "   If the bot rejects them with a mismatch error, double-check the filenames "
            "and timestamps.\n"
            "• The two replays are placed side-by-side with a shared timer so you can "
            "compare team movements at any instant.\n"
            "• Upload limit applies to the *combined* output — the bot downgrades quality if needed."
        ),
        inline=False,
    )

    embed.add_field(
        name="❓ Common questions",
        value=(
            "**\"Replays are from different battles\" / \"different battle start times\"**\n"
            "The two files in `/render_dual` must be from the same match. "
            "Each WoWS match has a unique arena ID and a shared start time — the bot checks both. "
            "If the timestamps look the same to you but the bot still complains, "
            "make sure you grabbed the right files.\n\n"
            "**\"Render failed\" / \"error parsing replay\"**\n"
            "The most common cause is a replay from a WoWS version the bot doesn't know yet. "
            "(it appears in the replay file name).\n\n"
            "**Queue / how long?**\n"
            "Renders are sequential per server same with the quality and a normal render takes 30-60s\n\n"
            "**Privacy**\n"
            "Replays are processed in memory and your files are not stored."
        ),
        inline=False,
    )

    embed.set_footer(text="Render Bot • Minimap videos from WoWS replays")

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready() -> None:
    if bot.user is None:
        return
    LOG.info(
        "Logged in as %s (%s) shard=%s/%s",
        bot.user.name,
        bot.user.id,
        bot.shard_id if bot.shard_id is not None else "-",
        bot.shard_count if bot.shard_count is not None else "-",
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = _load_bot_token()
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
