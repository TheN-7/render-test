from __future__ import annotations

import argparse
import importlib
import json
import math
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List
from io import BytesIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.replay_extract import extract_replay
from core.replay_schema import validate_extraction
from core.replay_unpack_adapter import ReplayDecodeError, WowsReplayPlayer, decode_packets, read_replay
from replay_unpack.core.network.net_packet import NetPacket  # type: ignore
from replay_unpack.clients.wows.network.packets import (  # type: ignore
    PACKETS_MAPPING,
    PACKETS_MAPPING_12_6,
    PlayerPosition,
)


VERSIONS_DIR = ROOT / "vendor" / "replay_unpack" / "clients" / "wows" / "versions"
DEFAULT_REPORT_ROOT = ROOT / "replay_debug" / "version_updates"

RENDER_PACKET_NAMES = {
    "Position",
    "PlayerPosition",
    "EntityCreate",
    "EntityMethod",
    "EntityProperty",
    "NestedProperty",
    "BattleStats",
    "Map",
    "Version",
    "EntityEnter",
    "EntityLeave",
}

RENDER_CRITICAL_PACKET_NAMES = {
    "Position",
    "PlayerPosition",
    "EntityCreate",
    "EntityMethod",
    "BattleStats",
}

FIXED_LAYOUT_PACKET_NAMES = {
    "Position",
    "PlayerPosition",
}

CANONICAL_SHAPE_KEYS = (
    "tracks",
    "entities",
    "deaths",
    "kills",
    "captures",
    "health",
    "player_status",
    "torpedoes",
    "artillery",
)


def _version_candidates(version_parts: List[str]) -> List[str]:
    clean = [str(part).strip() for part in version_parts if str(part).strip()]
    candidates: List[str] = []
    if len(clean) >= 4:
        candidates.append("_".join(clean[:4]))
    if len(clean) >= 3:
        short = "_".join(clean[:3])
        if short not in candidates:
            candidates.append(short)
    return candidates


def _target_version_dir_name(version_parts: List[str]) -> str:
    candidates = _version_candidates(version_parts)
    if not candidates:
        raise ReplayDecodeError("Replay version is missing or malformed")
    return candidates[-1]


def _packet_mapping(version_parts: List[str]) -> Dict[int, Any]:
    major_minor_patch = tuple(int(x) for x in (version_parts + ["0", "0", "0"])[:3])
    if major_minor_patch >= (12, 6, 0):
        mapping = dict(PACKETS_MAPPING_12_6)
    else:
        mapping = dict(PACKETS_MAPPING)

    if major_minor_patch >= (15, 1, 0):
        mapping[0x2C] = PlayerPosition
    return mapping


def _dump_raw_packets(replay_path: str, output_path: Path, filter_names: set[str] | None = None) -> None:
    context = read_replay(replay_path)
    mapping = _packet_mapping(context.version)
    data = context.decrypted_data
    stream = BytesIO(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        while stream.tell() < len(data):
            packet = NetPacket(stream)
            packet_cls = mapping.get(packet.type)
            packet_name = packet_cls.__name__ if packet_cls else f"TYPE_{packet.type}"
            if filter_names and packet_name not in filter_names:
                continue
            raw_bytes = packet.raw_data
            if isinstance(raw_bytes, BytesIO):
                raw_bytes = raw_bytes.getvalue()
            handle.write(
                json.dumps(
                    {
                        "time": round(float(packet.time), 6),
                        "packet_type": hex(int(packet.type)),
                        "packet_name": packet_name,
                        "raw_len": len(raw_bytes),
                        "raw_hex": raw_bytes.hex(),
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )


def _existing_version_dir(version_parts: List[str]) -> Path | None:
    for candidate in _version_candidates(version_parts):
        path = VERSIONS_DIR / candidate
        if path.is_dir():
            return path
    return None


def _version_static_map(version_parts: List[str]) -> Dict[str, Any]:
    version_dir = _existing_version_dir(version_parts)
    result: Dict[str, Any] = {
        "supported": version_dir is not None,
        "version_dir": str(version_dir or ""),
        "player_info_maps": {},
        "render_packet_types": {},
        "fixed_packet_layouts": {},
    }
    if version_dir is not None:
        module_name = f"replay_unpack.clients.wows.versions.{version_dir.name}.constants"
        try:
            constants = importlib.import_module(module_name)
            result["player_info_maps"] = {
                "players": _stringify_map(getattr(constants, "id_property_map", {}) or {}),
                "bots": _stringify_map(getattr(constants, "id_property_map_bots", {}) or {}),
                "observers": _stringify_map(getattr(constants, "id_property_map_observer", {}) or {}),
            }
        except Exception as exc:
            result["player_info_map_error"] = f"{type(exc).__name__}: {exc}"

    mapping = _packet_mapping(version_parts)
    render_packet_types: Dict[str, List[str]] = {}
    fixed_layouts: Dict[str, List[str]] = {}
    for packet_type, packet_cls in sorted(mapping.items(), key=lambda item: int(item[0])):
        packet_name = getattr(packet_cls, "__name__", f"TYPE_{packet_type}")
        if packet_name not in RENDER_PACKET_NAMES:
            continue
        render_packet_types.setdefault(packet_name, []).append(hex(int(packet_type)))
        if packet_name in FIXED_LAYOUT_PACKET_NAMES:
            slots = getattr(packet_cls, "__slots__", None)
            fixed_layouts[packet_name] = [str(slot) for slot in slots] if slots else []
    result["render_packet_types"] = render_packet_types
    result["fixed_packet_layouts"] = fixed_layouts
    return result


def _stringify_map(mapping: Dict[Any, Any]) -> Dict[str, str]:
    return {str(key): str(value) for key, value in sorted(mapping.items(), key=lambda item: int(item[0]))}


def _packet_summary(replay_path: str) -> Dict[str, Any]:
    context = read_replay(replay_path)
    packets = decode_packets(context)
    type_counts = Counter(int(packet.packet_type) for packet in packets)
    name_counts = Counter(str(packet.packet_name) for packet in packets)
    unknown_types = sorted({int(packet.packet_type) for packet in packets if str(packet.packet_name).startswith("TYPE_")})
    raw_lengths: Dict[str, Counter[int]] = {}
    decoded_warnings: List[str] = []

    for packet in packets:
        packet_name = str(packet.packet_name)
        if packet_name in RENDER_CRITICAL_PACKET_NAMES:
            raw_lengths.setdefault(packet_name, Counter())[int(getattr(packet, "raw_len", 0) or 0)] += 1
            decoded_warnings.extend(_packet_value_warnings(packet))

    return {
        "version": ".".join(context.version),
        "packet_count": len(packets),
        "packet_types": {hex(packet_type): count for packet_type, count in sorted(type_counts.items())},
        "packet_names": dict(sorted(name_counts.items())),
        "unknown_packet_types": [hex(packet_type) for packet_type in unknown_types],
        "render_packet_raw_lengths": {
            name: {
                "min": min(lengths),
                "max": max(lengths),
                "values": sorted(lengths),
                "common": [[length, count] for length, count in lengths.most_common(5)],
            }
            for name, lengths in sorted(raw_lengths.items())
            if lengths
        },
        "decoded_value_warnings": decoded_warnings[:50],
    }


def _packet_value_warnings(packet: Any) -> List[str]:
    packet_name = str(getattr(packet, "packet_name", "") or "")
    packet_obj = getattr(packet, "packet_obj", None)
    warnings: List[str] = []
    if packet_obj is None:
        return warnings

    for attr in ("entityId", "entityID", "entityId1", "entityId2", "objectID"):
        if not hasattr(packet_obj, attr):
            continue
        value = _safe_int(getattr(packet_obj, attr, None))
        if value is None:
            warnings.append(f"{packet_name}.{attr} is not int-like at {float(packet.time):.3f}s")
        elif abs(value) > 10_000_000:
            warnings.append(f"{packet_name}.{attr} looks out of range ({value}) at {float(packet.time):.3f}s")

    pos = getattr(packet_obj, "position", None)
    if pos is not None:
        coords = [getattr(pos, axis, None) for axis in ("x", "y", "z")]
        if not all(_finite_number(value) for value in coords):
            warnings.append(f"{packet_name}.position has non-finite coordinate at {float(packet.time):.3f}s")
        elif max(abs(float(value)) for value in coords) > 1_000_000.0:
            warnings.append(f"{packet_name}.position looks out of map range at {float(packet.time):.3f}s")

    for attr in ("yaw", "pitch", "roll"):
        if hasattr(packet_obj, attr) and not _finite_number(getattr(packet_obj, attr, None)):
            warnings.append(f"{packet_name}.{attr} is non-finite at {float(packet.time):.3f}s")

    return warnings


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _strict_player_check(replay_path: str) -> Dict[str, Any]:
    context = read_replay(replay_path)
    player = WowsReplayPlayer(context.version)
    try:
        player.play(context.decrypted_data, strict_mode=True)
        info = player.get_info() or {}
        players = info.get("players", {}) if isinstance(info, dict) else {}
        player_count = len(players) if isinstance(players, dict) else len(players or [])
        return {
            "ok": True,
            "player_count": player_count,
            "unknown_player_fields": _unknown_player_fields_summary(info),
            "player_field_warnings": _player_field_warnings(info),
        }
    except Exception as exc:
        result: Dict[str, Any] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            relaxed_player = WowsReplayPlayer(context.version)
            relaxed_player.play(context.decrypted_data, strict_mode=False)
            relaxed_info = relaxed_player.get_info() or {}
            relaxed_players = relaxed_info.get("players", {}) if isinstance(relaxed_info, dict) else {}
            relaxed_count = len(relaxed_players) if isinstance(relaxed_players, dict) else len(relaxed_players or [])
            result["relaxed_player_count"] = relaxed_count
            result["unknown_player_fields"] = _unknown_player_fields_summary(relaxed_info)
            result["player_field_warnings"] = _player_field_warnings(relaxed_info)
        except Exception as relaxed_exc:
            result["relaxed_error"] = f"{type(relaxed_exc).__name__}: {relaxed_exc}"
        return result


def _json_safe_preview(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _json_safe_preview(v) for k, v in list(value.items())[:5]}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_preview(v) for v in list(value)[:5]]
    return repr(value)


def _unknown_player_fields_summary(info: Dict[str, Any]) -> Dict[str, Any]:
    players = info.get("players", {}) if isinstance(info, dict) else {}
    if not isinstance(players, dict):
        return {}

    summary: Dict[str, Dict[str, Any]] = {}
    for player_id, player in players.items():
        if not isinstance(player, dict):
            continue
        player_name = str(player.get("name") or player.get("nickName") or player_id)
        for key, value in player.items():
            if not (isinstance(key, str) and key.startswith("unknown_")):
                continue
            row = summary.setdefault(
                key,
                {
                    "field_id": int(key.split("_", 1)[1]),
                    "players": [],
                    "sample_values": [],
                    "count": 0,
                },
            )
            row["count"] += 1
            if len(row["players"]) < 5 and player_name not in row["players"]:
                row["players"].append(player_name)
            preview = _json_safe_preview(value)
            if len(row["sample_values"]) < 5 and preview not in row["sample_values"]:
                row["sample_values"].append(preview)

    return dict(sorted(summary.items(), key=lambda item: item[1]["field_id"]))


def _player_field_warnings(info: Dict[str, Any]) -> List[str]:
    players = info.get("players", {}) if isinstance(info, dict) else {}
    if not isinstance(players, dict):
        return ["players info is not a dict"]

    warnings: List[str] = []
    for player_id, player in list(players.items())[:64]:
        if not isinstance(player, dict):
            warnings.append(f"player {player_id} row is not a dict")
            continue
        label = str(player.get("name") or player_id)
        expected_ints = ("id", "shipId", "teamId")
        for key in expected_ints:
            if key in player and _safe_int(player.get(key)) is None:
                warnings.append(f"player {label} field {key} is not int-like")
        if "name" in player and not isinstance(player.get("name"), str):
            warnings.append(f"player {player_id} field name is not a string")
        if "shipComponents" in player and not isinstance(player.get("shipComponents"), dict):
            warnings.append(f"player {label} field shipComponents is not a dict")
        if "crewParams" in player and not isinstance(player.get("crewParams"), list):
            warnings.append(f"player {label} field crewParams is not a list")
        if "isAlive" in player and not isinstance(player.get("isAlive"), bool):
            warnings.append(f"player {label} field isAlive is not a bool")
        if len(warnings) >= 50:
            break
    return warnings


def _extraction_summary(replay_path: str) -> Dict[str, Any]:
    try:
        canonical = extract_replay(replay_path)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    validation = validate_extraction(canonical)
    events = canonical.get("events", {}) or {}
    diagnostics = canonical.get("diagnostics", {}) or {}

    quality = _canonical_quality_summary(canonical)
    feature_coverage = _render_feature_coverage(canonical, quality)
    return {
        "ok": True,
        "canonical": canonical,
        "validation_ok": bool(validation.ok),
        "validation_errors": list(validation.errors),
        "quality": quality,
        "feature_coverage": feature_coverage,
        "shape": {
            "tracks": len(canonical.get("tracks", {}) or {}),
            "entities": len(canonical.get("entities", {}) or {}),
            "deaths": len(events.get("deaths", []) or []),
            "kills": len(events.get("kills", []) or []),
            "captures": len(events.get("captures", []) or []),
            "health": len(events.get("health", []) or []),
            "player_status": len(events.get("player_status", []) or []),
            "chat": len(events.get("chat", []) or []),
            "torpedoes": len(events.get("torpedoes", []) or []),
            "artillery": len(events.get("artillery", []) or []),
            "packet_counts": len(diagnostics.get("packet_counts", {}) or {}),
        },
    }


def _render_feature_coverage(canonical: Dict[str, Any], quality: Dict[str, Any]) -> Dict[str, Any]:
    meta = canonical.get("meta", {}) or {}
    events = canonical.get("events", {}) or {}
    stats = canonical.get("stats", {}) or {}
    entities = canonical.get("entities", {}) or {}
    tracks = canonical.get("tracks", {}) or {}

    def _list_count(key: str) -> int:
        value = events.get(key, [])
        return len(value) if isinstance(value, list) else 0

    def _status(ok: bool, *, observed: bool = True, warnings: List[str] | None = None, counts: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not observed:
            state = "not_observed"
        elif ok and not warnings:
            state = "ok"
        elif ok:
            state = "warn"
        else:
            state = "missing"
        return {
            "status": state,
            "counts": counts or {},
            "warnings": warnings or [],
        }

    roster_warnings: List[str] = []
    if len(entities) != len(tracks):
        roster_warnings.append("entity/track counts differ")
    if quality.get("tracks_with_ship_id") != quality.get("track_count"):
        roster_warnings.append("some tracks are missing ship_id")
    if quality.get("tracks_with_player_name") != quality.get("track_count"):
        roster_warnings.append("some tracks are missing player_name")

    team_counts = quality.get("team_counts", {}) or {}
    team_warnings: List[str] = []
    if not team_counts.get("player"):
        team_warnings.append("no local player track")
    if not team_counts.get("enemy"):
        team_warnings.append("no enemy tracks")
    if not team_counts.get("ally"):
        team_warnings.append("no ally tracks")

    movement_warnings: List[str] = []
    if quality.get("invalid_points"):
        movement_warnings.append("invalid track points")
    if quality.get("impossible_jumps"):
        movement_warnings.append("suspicious movement jumps")

    score_warnings: List[str] = []
    if not stats.get("team_scores_final"):
        score_warnings.append("missing final team scores")
    if meta.get("local_team_id") is None or meta.get("enemy_team_id") is None:
        score_warnings.append("missing local/enemy team ids")

    build_entities = [
        entity
        for entity in entities.values()
        if isinstance(entity, dict) and (entity.get("captain_skills") or entity.get("ship_build"))
    ]

    features = {
        "map_background": _status(
            bool(meta.get("mapDisplayName") or meta.get("map_name_resolved") or meta.get("mapId")),
            counts={"control_points_meta": len(meta.get("control_points", []) or [])},
        ),
        "ship_roster_and_lineups": _status(
            bool(tracks) and not roster_warnings,
            warnings=roster_warnings,
            counts={
                "entities": len(entities),
                "tracks": len(tracks),
                "tracks_with_ship_id": quality.get("tracks_with_ship_id"),
                "tracks_with_player_name": quality.get("tracks_with_player_name"),
            },
        ),
        "team_classification": _status(bool(team_counts) and not team_warnings, warnings=team_warnings, counts=dict(team_counts)),
        "ship_movement": _status(
            bool(tracks) and quality.get("tracks_with_points") == quality.get("track_count") and not movement_warnings,
            warnings=movement_warnings,
            counts={
                "tracks_with_points": quality.get("tracks_with_points"),
                "point_count": quality.get("point_count"),
                "max_abs_coordinate": quality.get("max_abs_coordinate"),
            },
        ),
        "health_bars_and_status": _status(_list_count("health") > 0, counts={"health": _list_count("health")}),
        "player_status_panel": _status(_list_count("player_status") > 0, counts={"player_status": _list_count("player_status")}),
        "kills_deaths_feed": _status(
            _list_count("kills") > 0 or _list_count("deaths") > 0,
            counts={"kills": _list_count("kills"), "deaths": _list_count("deaths")},
        ),
        "score_and_battle_result": _status(bool(stats.get("team_scores_final")) and not score_warnings, warnings=score_warnings, counts={"team_scores_final": stats.get("team_scores_final")}),
        "capture_zones": _status(_list_count("captures") > 0 or bool(meta.get("control_points")), counts={"captures": _list_count("captures")}),
        "smoke_overlay": _status(True, observed=_list_count("smokes") > 0 or _list_count("smoke_puffs") > 0, counts={"smokes": _list_count("smokes"), "smoke_puffs": _list_count("smoke_puffs")}),
        "sensor_overlay": _status(True, observed=_list_count("sensors") > 0, counts={"sensors": _list_count("sensors")}),
        "consumable_overlay": _status(True, observed=_list_count("consumables") > 0, counts={"consumables": _list_count("consumables")}),
        "torpedo_tracks": _status(True, observed=_list_count("torpedoes") > 0, counts={"torpedoes": _list_count("torpedoes")}),
        "squadron_tracks": _status(True, observed=_list_count("squadrons") > 0, counts={"squadrons": _list_count("squadrons")}),
        "artillery_traces": _status(True, observed=_list_count("fires") > 0, counts={"fires": _list_count("fires")}),
        "chat_feed": _status(True, observed=_list_count("chat") > 0, counts={"chat": _list_count("chat")}),
        "minimap_vision": _status(
            True,
            observed=bool(meta.get("minimap_vision_initial") or meta.get("minimap_vision_timeline")),
            counts={
                "initial_entries": len(meta.get("minimap_vision_initial", {}) or {}),
                "timeline_entries": len(meta.get("minimap_vision_timeline", []) or []),
            },
        ),
        "captain_and_build_card": _status(True, observed=bool(build_entities), counts={"entities_with_build_data": len(build_entities)}),
    }

    required_missing = [
        name
        for name, row in features.items()
        if name in {
            "map_background",
            "ship_roster_and_lineups",
            "team_classification",
            "ship_movement",
            "health_bars_and_status",
            "player_status_panel",
            "kills_deaths_feed",
            "score_and_battle_result",
            "capture_zones",
        }
        and row.get("status") in {"missing", "warn"}
    ]
    not_observed = [name for name, row in features.items() if row.get("status") == "not_observed"]
    return {
        "features": features,
        "required_missing_or_warn": required_missing,
        "not_observed": not_observed,
    }


def _canonical_quality_summary(canonical: Dict[str, Any]) -> Dict[str, Any]:
    tracks = canonical.get("tracks", {}) or {}
    entities = canonical.get("entities", {}) or {}
    stats = canonical.get("stats", {}) or {}
    events = canonical.get("events", {}) or {}
    warnings: List[str] = []

    point_count = 0
    invalid_points = 0
    max_abs_coordinate = 0.0
    impossible_jumps = 0
    tracks_with_points = 0
    tracks_with_ship_id = 0
    tracks_with_player_name = 0
    team_counts = Counter()

    for entity_key, track in tracks.items():
        if not isinstance(track, dict):
            warnings.append(f"track {entity_key} is not an object")
            continue
        points = list(track.get("points", []) or [])
        if points:
            tracks_with_points += 1
        if track.get("ship_id") is not None:
            tracks_with_ship_id += 1
        if str(track.get("player_name") or "").strip():
            tracks_with_player_name += 1
        team_counts[str(track.get("team") or "unknown")] += 1

        previous: Dict[str, Any] | None = None
        for point in points:
            point_count += 1
            values = [point.get("t"), point.get("x"), point.get("y", 0.0), point.get("z"), point.get("yaw", 0.0)]
            if not all(_finite_number(value) for value in values):
                invalid_points += 1
                continue
            max_abs_coordinate = max(max_abs_coordinate, abs(float(point.get("x", 0.0))), abs(float(point.get("z", 0.0))))
            if previous is not None and _finite_number(previous.get("t")):
                dt = max(1e-6, float(point.get("t", 0.0)) - float(previous.get("t", 0.0)))
                dist = math.hypot(float(point.get("x", 0.0)) - float(previous.get("x", 0.0)), float(point.get("z", 0.0)) - float(previous.get("z", 0.0)))
                if dt > 0.0 and dist / dt > 350.0:
                    impossible_jumps += 1
            previous = point

    if not tracks:
        warnings.append("no tracks extracted")
    if tracks and not tracks_with_points:
        warnings.append("tracks exist but contain no points")
    if invalid_points:
        warnings.append(f"{invalid_points} track point(s) contain non-finite values")
    if max_abs_coordinate > 1_000_000.0:
        warnings.append("track coordinates exceed expected world range")
    if impossible_jumps:
        warnings.append(f"{impossible_jumps} suspicious position jump(s) detected")
    if tracks and tracks_with_ship_id == 0:
        warnings.append("no track has a ship_id")
    if tracks and tracks_with_player_name == 0:
        warnings.append("no track has a player_name")
    if not events.get("health"):
        warnings.append("no health timeline extracted")
    if not stats.get("battle_end_s"):
        warnings.append("missing battle_end_s")

    return {
        "track_count": len(tracks),
        "entity_count": len(entities),
        "point_count": point_count,
        "tracks_with_points": tracks_with_points,
        "tracks_with_ship_id": tracks_with_ship_id,
        "tracks_with_player_name": tracks_with_player_name,
        "team_counts": dict(sorted(team_counts.items())),
        "invalid_points": invalid_points,
        "max_abs_coordinate": round(max_abs_coordinate, 3),
        "impossible_jumps": impossible_jumps,
        "battle_end_s": stats.get("battle_end_s"),
        "warnings": warnings,
    }


def _compare_summaries(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    base_unknown = set(baseline.get("packet_summary", {}).get("unknown_packet_types", []) or [])
    cand_unknown = set(candidate.get("packet_summary", {}).get("unknown_packet_types", []) or [])
    base_types = set((baseline.get("packet_summary", {}) or {}).get("packet_types", {}).keys())
    cand_types = set((candidate.get("packet_summary", {}) or {}).get("packet_types", {}).keys())

    base_extract = baseline.get("extract", {}) or {}
    cand_extract = candidate.get("extract", {}) or {}
    base_shape = base_extract.get("shape", {}) if base_extract.get("ok") else {}
    cand_shape = cand_extract.get("shape", {}) if cand_extract.get("ok") else {}
    shape_delta = {}
    for key in CANONICAL_SHAPE_KEYS:
        if base_shape.get(key) != cand_shape.get(key):
            shape_delta[key] = {"baseline": base_shape.get(key), "candidate": cand_shape.get(key)}

    packet_shape_delta = _packet_shape_delta(
        baseline.get("packet_summary", {}) or {},
        candidate.get("packet_summary", {}) or {},
    )
    static_map_delta = _static_map_delta(baseline.get("version_map", {}) or {}, candidate.get("version_map", {}) or {})
    quality_delta = _quality_delta(base_extract.get("quality", {}) or {}, cand_extract.get("quality", {}) or {})
    candidate_feature_coverage = (cand_extract.get("feature_coverage", {}) or {})
    required_feature_warnings = candidate_feature_coverage.get("required_missing_or_warn", []) or []

    manual_review_reasons: List[str] = []
    if not candidate.get("strict_play", {}).get("ok"):
        manual_review_reasons.append("strict replay player check failed")
    if not candidate.get("extract", {}).get("ok"):
        manual_review_reasons.append("canonical extraction failed")
    if candidate.get("extract", {}).get("ok") and not candidate.get("extract", {}).get("validation_ok"):
        manual_review_reasons.append("canonical validation failed")
    if cand_unknown - base_unknown:
        manual_review_reasons.append("new unknown packet types detected")
    if candidate.get("strict_play", {}).get("player_field_warnings"):
        manual_review_reasons.append("player info field values look suspicious")
    if candidate.get("packet_summary", {}).get("decoded_value_warnings"):
        manual_review_reasons.append("render-critical packet values look suspicious")
    if packet_shape_delta:
        manual_review_reasons.append("render-critical packet raw shapes changed")
    if static_map_delta.get("player_info_maps"):
        manual_review_reasons.append("version player-info field map changed")
    if static_map_delta.get("fixed_packet_layouts") or static_map_delta.get("render_packet_types"):
        manual_review_reasons.append("version packet map changed")
    if (cand_extract.get("quality", {}) or {}).get("warnings"):
        manual_review_reasons.append("canonical render-quality warnings detected")
    if quality_delta:
        manual_review_reasons.append("canonical render-quality metrics changed significantly")
    if required_feature_warnings:
        manual_review_reasons.append("required render feature coverage is missing or suspicious")
    # New packet types alone are not a blocker if they are known and parsing succeeds.
    # They are still recorded in the report for manual inspection.

    return {
        "new_unknown_packet_types": sorted(cand_unknown - base_unknown),
        "packet_types_only_in_candidate": sorted(cand_types - base_types),
        "packet_types_only_in_baseline": sorted(base_types - cand_types),
        "shape_delta": shape_delta,
        "packet_shape_delta": packet_shape_delta,
        "static_map_delta": static_map_delta,
        "quality_delta": quality_delta,
        "candidate_feature_coverage": candidate_feature_coverage,
        "manual_review_needed": bool(manual_review_reasons),
        "manual_review_reasons": manual_review_reasons,
    }


def _static_map_delta(baseline_map: Dict[str, Any], candidate_map: Dict[str, Any]) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    for section in ("player_info_maps", "render_packet_types", "fixed_packet_layouts"):
        base_section = baseline_map.get(section, {}) or {}
        cand_section = candidate_map.get(section, {}) or {}
        section_delta: Dict[str, Any] = {}
        for key in sorted(set(base_section) | set(cand_section)):
            if base_section.get(key) != cand_section.get(key):
                section_delta[key] = {"baseline": base_section.get(key), "candidate": cand_section.get(key)}
        if section_delta:
            delta[section] = section_delta
    return delta


def _packet_shape_delta(baseline_packet_summary: Dict[str, Any], candidate_packet_summary: Dict[str, Any]) -> Dict[str, Any]:
    base_lengths = baseline_packet_summary.get("render_packet_raw_lengths", {}) or {}
    cand_lengths = candidate_packet_summary.get("render_packet_raw_lengths", {}) or {}
    delta: Dict[str, Any] = {}
    for packet_name in sorted(FIXED_LAYOUT_PACKET_NAMES):
        base = base_lengths.get(packet_name)
        cand = cand_lengths.get(packet_name)
        base_shape = None if not isinstance(base, dict) else {key: base.get(key) for key in ("min", "max", "values")}
        cand_shape = None if not isinstance(cand, dict) else {key: cand.get(key) for key in ("min", "max", "values")}
        if base_shape != cand_shape:
            delta[packet_name] = {"baseline": base_shape, "candidate": cand_shape}
    return delta


def _quality_delta(baseline_quality: Dict[str, Any], candidate_quality: Dict[str, Any]) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    for key in ("track_count", "point_count", "tracks_with_points", "tracks_with_ship_id", "tracks_with_player_name"):
        base_value = _safe_int(baseline_quality.get(key))
        cand_value = _safe_int(candidate_quality.get(key))
        if base_value is None or cand_value is None:
            continue
        if base_value <= 0 and cand_value <= 0:
            continue
        if base_value <= 0 or cand_value <= 0:
            delta[key] = {"baseline": base_value, "candidate": cand_value}
            continue
        ratio = cand_value / float(base_value)
        if ratio < 0.5 or ratio > 2.0:
            delta[key] = {"baseline": base_value, "candidate": cand_value, "ratio": round(ratio, 3)}

    for key in ("invalid_points", "impossible_jumps"):
        cand_value = _safe_int(candidate_quality.get(key)) or 0
        base_value = _safe_int(baseline_quality.get(key)) or 0
        if cand_value > base_value:
            delta[key] = {"baseline": base_value, "candidate": cand_value}
    return delta


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_report_markdown(path: Path, report: Dict[str, Any]) -> None:
    baseline = report.get("baseline", {}) or {}
    candidate = report.get("candidate", {}) or {}
    scaffold = report.get("scaffold", {}) or {}
    comparison = report.get("comparison", {}) or {}

    lines = [
        "# WoWS Version Update Report",
        "",
        f"- Baseline replay: `{baseline.get('path', '')}`",
        f"- Candidate replay: `{candidate.get('path', '')}`",
        f"- Baseline version: `{baseline.get('version', '')}`",
        f"- Candidate version: `{candidate.get('version', '')}`",
        f"- Scaffold created: `{scaffold.get('created', False)}`",
        f"- Target version folder: `{scaffold.get('target_dir', '')}`",
        f"- Manual review needed: `{comparison.get('manual_review_needed', False)}`",
        "",
        "## Manual Review Reasons",
    ]
    reasons = comparison.get("manual_review_reasons", []) or []
    if reasons:
        lines.extend([f"- {reason}" for reason in reasons])
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## New Unknown Packet Types",
        ]
    )
    unknowns = comparison.get("new_unknown_packet_types", []) or []
    if unknowns:
        lines.extend([f"- `{value}`" for value in unknowns])
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Unknown Player Fields",
        ]
    )
    strict_play = candidate.get("strict_play", {}) or {}
    unknown_player_fields = strict_play.get("unknown_player_fields", {}) or {}
    if unknown_player_fields:
        for field_name, row in unknown_player_fields.items():
            lines.append(
                f"- `{field_name}` (id `{row.get('field_id')}`), "
                f"seen `{row.get('count', 0)}` time(s), "
                f"players: `{', '.join(row.get('players', []) or [])}`"
            )
            sample_values = row.get("sample_values", []) or []
            if sample_values:
                lines.append(f"  - sample values: `{json.dumps(sample_values, ensure_ascii=False)}`")
    else:
        lines.append("- none detected")

    player_field_warnings = strict_play.get("player_field_warnings", []) or []
    if player_field_warnings:
        lines.extend(["", "## Player Field Warnings"])
        lines.extend([f"- {warning}" for warning in player_field_warnings])

    lines.extend(
        [
            "",
            "## Render-Critical Packet Shape Changes",
        ]
    )
    packet_shape_delta = comparison.get("packet_shape_delta", {}) or {}
    if packet_shape_delta:
        for packet_name, row in packet_shape_delta.items():
            lines.append(f"- `{packet_name}`: `{json.dumps(row, sort_keys=True)}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Version Map Changes"])
    static_map_delta = comparison.get("static_map_delta", {}) or {}
    if static_map_delta:
        for section, rows in static_map_delta.items():
            lines.append(f"- `{section}` changed")
            for key, row in (rows or {}).items():
                lines.append(f"  - `{key}`: `{json.dumps(row, sort_keys=True)}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Canonical Quality Warnings",
        ]
    )
    quality = ((candidate.get("extract", {}) or {}).get("quality", {}) or {})
    quality_warnings = quality.get("warnings", []) or []
    if quality_warnings:
        lines.extend([f"- {warning}" for warning in quality_warnings])
    else:
        lines.append("- none")

    lines.extend(["", "## Render Feature Coverage"])
    feature_coverage = ((candidate.get("extract", {}) or {}).get("feature_coverage", {}) or {})
    features = feature_coverage.get("features", {}) or {}
    if features:
        for name, row in features.items():
            status = row.get("status", "unknown")
            counts = row.get("counts", {}) or {}
            warnings = row.get("warnings", []) or []
            lines.append(f"- `{name}`: `{status}` counts=`{json.dumps(counts, sort_keys=True)}`")
            for warning in warnings:
                lines.append(f"  - {warning}")
    else:
        lines.append("- none")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_side_report(replay_path: Path) -> Dict[str, Any]:
    context = read_replay(str(replay_path))
    return {
        "path": str(replay_path),
        "version": ".".join(context.version),
        "supported_dir": str(_existing_version_dir(context.version) or ""),
        "version_map": _version_static_map(context.version),
        "packet_summary": _packet_summary(str(replay_path)),
        "strict_play": _strict_player_check(str(replay_path)),
        "extract": _extraction_summary(str(replay_path)),
    }


def _scaffold_candidate_version(baseline_version_dir: Path, candidate_version_parts: List[str], apply: bool) -> Dict[str, Any]:
    target_name = _target_version_dir_name(candidate_version_parts)
    target_dir = VERSIONS_DIR / target_name
    already_exists = target_dir.is_dir()
    created = False

    if apply and not already_exists and baseline_version_dir.resolve() != target_dir.resolve():
        shutil.copytree(baseline_version_dir, target_dir)
        created = True

    return {
        "created": created,
        "already_exists": already_exists,
        "source_dir": str(baseline_version_dir),
        "target_dir": str(target_dir),
    }


def build_report(baseline_replay: Path, candidate_replay: Path, apply: bool) -> Dict[str, Any]:
    baseline_context = read_replay(str(baseline_replay))
    candidate_context = read_replay(str(candidate_replay))

    baseline_version_dir = _existing_version_dir(baseline_context.version)
    if baseline_version_dir is None:
        raise RuntimeError(
            f"Baseline replay version {'.'.join(baseline_context.version)} is not supported locally, "
            "so there is nothing safe to copy from."
        )

    scaffold = _scaffold_candidate_version(baseline_version_dir, candidate_context.version, apply)
    baseline = _build_side_report(baseline_replay)
    candidate = _build_side_report(candidate_replay)

    report = {
        "baseline": baseline,
        "candidate": candidate,
        "scaffold": scaffold,
        "comparison": _compare_summaries(baseline, candidate),
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold and compare WoWS replay support between a known-good version and a newer replay version.",
    )
    parser.add_argument("baseline_replay", help="Replay from the last known working WoWS version")
    parser.add_argument("candidate_replay", help="Replay from the newer WoWS version to evaluate")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_REPORT_ROOT),
        help="Directory where reports and extracted canonicals will be written",
    )
    parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Do not create the new vendor version folder; only report what would happen",
    )
    parser.add_argument(
        "--skip-canonical-dump",
        action="store_true",
        help="Do not write baseline/candidate canonical JSON files when extraction succeeds",
    )
    parser.add_argument(
        "--dump-raw-packets",
        action="store_true",
        help="Write raw packet dumps (.jsonl) for baseline and candidate replays",
    )
    parser.add_argument(
        "--dump-render-packets",
        action="store_true",
        help="Write filtered raw packet dumps (.jsonl) with only render-relevant packet types",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Exit non-zero when the comparison says manual review is needed",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_replay = Path(args.baseline_replay).expanduser().resolve()
    candidate_replay = Path(args.candidate_replay).expanduser().resolve()
    report_root = Path(args.output_dir).expanduser().resolve()

    report = build_report(baseline_replay, candidate_replay, apply=not args.no_apply)

    candidate_version = report.get("candidate", {}).get("version", "unknown").replace(".", "_")
    output_dir = report_root / candidate_version
    _write_json(output_dir / "baseline_report.json", report.get("baseline", {}) or {})
    _write_json(output_dir / "candidate_report.json", report.get("candidate", {}) or {})
    _write_json(output_dir / "comparison_report.json", report)
    _write_report_markdown(output_dir / "comparison_report.md", report)

    if not args.skip_canonical_dump:
        baseline_extract = (report.get("baseline", {}) or {}).get("extract", {}) or {}
        candidate_extract = (report.get("candidate", {}) or {}).get("extract", {}) or {}
        if baseline_extract.get("ok") and isinstance(baseline_extract.get("canonical"), dict):
            _write_json(output_dir / "baseline_canonical.json", baseline_extract["canonical"])
        if candidate_extract.get("ok") and isinstance(candidate_extract.get("canonical"), dict):
            _write_json(output_dir / "candidate_canonical.json", candidate_extract["canonical"])

    if args.dump_raw_packets or args.dump_render_packets:
        filters = RENDER_PACKET_NAMES if args.dump_render_packets else None
        _dump_raw_packets(str(baseline_replay), output_dir / "baseline_raw_packets.jsonl", filters)
        _dump_raw_packets(str(candidate_replay), output_dir / "candidate_raw_packets.jsonl", filters)

    comparison = report.get("comparison", {}) or {}
    print(f"Baseline version:  {report['baseline']['version']}")
    print(f"Candidate version: {report['candidate']['version']}")
    print(f"Target folder:     {report['scaffold']['target_dir']}")
    print(f"Folder created:    {report['scaffold']['created']}")
    print(f"Manual review:     {comparison.get('manual_review_needed', False)}")
    if comparison.get("manual_review_reasons"):
        print("Reasons:")
        for reason in comparison["manual_review_reasons"]:
            print(f"  - {reason}")
    print(f"Report written to: {output_dir}")
    if args.fail_on_review and comparison.get("manual_review_needed", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
