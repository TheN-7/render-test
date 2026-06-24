import sys
import unittest
from pathlib import Path
import math
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.replay_extract import extract_replay, _normalize_chat_feed, _normalize_torpedo_points
from core.replay_unpack_adapter import TrackPoint, _sanitize_track, read_replay, decode_packets, _looks_serialized_chat_blob, _resolve_public_info_player_row, _live_damage_stat_totals
from core.replay_schema import validate_extraction, to_legacy_schema
from minimap_render_v2 import PLAYBACK_DURATION_SCALE, _resolve_speed, auto_output_duration_s, internal_target_duration_s, speed_for_output_duration
from renderers.minimap_renderer import RIBBON_ID_TO_ASSET, _battle_result_text, _friendly_stale_marker, _health_state_at, _load_ribbon_icon, _load_space_bin_world_bounds, _map_assets_root, _map_cache_dir, _native_map_size, _overview_half_extent, _world_bounds, _normalize_render_tracks, _render_layout, _layout_for_player_status, _find_death_times, _split_lineups, LINEUP_CLASS_ORDER, _ship_type, _ship_state_at, _infer_unknown_squadron_type, _team_aircraft_capabilities, _extract_torpedo_tracks, _load_aircraft_module_params, _refine_squadron_types
from bot import _layout_covers_skills, _layout_for_ship_type, _load_commander_skill_icon, _select_ship_class_skills
from core.ship_build_display import (
    build_consumable_entries,
    build_module_entries,
    find_module_icon_path,
    find_modernization_icon_path,
    load_consumable_tile_icon,
    load_module_tile_icon,
    parse_mounted_upgrades,
)
from core.consumable_resolver import parse_mounted_consumable_ids
from tools.update_aircraft_params import _build_by_cv


ROOT = Path(__file__).resolve().parent.parent
SAMPLES = sorted(ROOT.glob("*.wowsreplay"))
SAMPLE = SAMPLES[0] if SAMPLES else None


class ReplayPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SAMPLE is None:
            raise unittest.SkipTest("No .wowsreplay sample found in repository root")

    def test_replay_reader_smoke(self):
        ctx = read_replay(str(SAMPLE))
        self.assertEqual(ctx.game, "wows")
        self.assertGreater(len(ctx.decrypted_data), 1000)
        self.assertIn("vehicles", ctx.engine_data)

    def test_packet_mapping_smoke(self):
        ctx = read_replay(str(SAMPLE))
        packets = decode_packets(ctx)
        names = {p.packet_name for p in packets}
        self.assertIn("Position", names)
        self.assertTrue("PlayerPosition" in names or "TYPE_43" in names or "TYPE_37" in names)

    def test_canonical_schema_validation(self):
        data = extract_replay(str(SAMPLE))
        result = validate_extraction(data)
        self.assertTrue(result.ok, msg="; ".join(result.errors))

    def test_legacy_adapter(self):
        canonical = extract_replay(str(SAMPLE))
        legacy = to_legacy_schema(canonical)
        self.assertIn("positions", legacy)
        self.assertIn("deaths", legacy)
        self.assertIn("battle_end", legacy)

    def test_integration_non_empty(self):
        data = extract_replay(str(SAMPLE))
        self.assertGreater(len(data.get("tracks", {})), 0)
        self.assertGreater(len(data.get("events", {}).get("deaths", [])), 0)
        self.assertGreater(len(data.get("diagnostics", {}).get("packet_counts", {})), 0)

    def test_battle_overlay_fields(self):
        data = extract_replay(str(SAMPLE))
        meta = data.get("meta", {}) or {}
        events = data.get("events", {}) or {}
        stats = data.get("stats", {}) or {}

        self.assertIsInstance(meta.get("control_points", []), list)
        self.assertIsInstance(events.get("captures", []), list)
        self.assertIsInstance(events.get("kills", []), list)
        self.assertIsInstance(events.get("health", []), list)
        self.assertIsInstance(events.get("player_status", []), list)
        self.assertIsInstance(stats.get("team_scores_final", {}), dict)
        self.assertIn("team_win_score", stats)

        captures = events.get("captures", [])
        if captures:
            snap = captures[0]
            self.assertIn("time_s", snap)
            self.assertIn("caps", snap)
            self.assertIn("team_scores", snap)

        health = events.get("health", [])
        if health:
            snap = health[0]
            self.assertIn("time_s", snap)
            self.assertIn("entities", snap)
            self.assertIsInstance(snap.get("entities"), dict)

        player_status = events.get("player_status", [])
        if player_status:
            snap = player_status[0]
            self.assertIn("time_s", snap)
            self.assertIn("damage_total", snap)
            self.assertIn("ribbons", snap)
            self.assertIn("ship_entity_key", snap)

    def test_arms_race_buffs_spawn_before_center_cap_becomes_visible(self):
        arms_race_sample = ROOT / "20260331_010819_PFSS710-Surcouf_16_OC_bees_to_honey.wowsreplay"
        if not arms_race_sample.exists():
            raise unittest.SkipTest("Arms Race sample replay not found in repository root")

        data = extract_replay(str(arms_race_sample))
        self.assertEqual("armsrace", str((data.get("meta", {}) or {}).get("scenario") or "").lower())

        captures = list((data.get("events", {}) or {}).get("captures", []))
        self.assertGreater(len(captures), 0)

        first = captures[0]
        first_caps = list(first.get("caps", []))
        self.assertEqual(1, len(first_caps))
        self.assertEqual(9, int(first_caps[0].get("zone_type", -1)))
        self.assertFalse(bool(first_caps[0].get("is_visible", True)))
        self.assertFalse(bool(first_caps[0].get("is_enabled", True)))

        buffs_before_center = None
        center_visible_later = None
        for snap in captures:
            caps = list(snap.get("caps", []))
            buffs = [c for c in caps if int(c.get("zone_type", -1)) == 6 and not bool(c.get("is_control_point", False))]
            center_caps = [c for c in caps if bool(c.get("is_control_point", False))]
            if buffs_before_center is None and buffs and not any(bool(c.get("is_visible", False)) or bool(c.get("is_enabled", False)) for c in center_caps):
                buffs_before_center = snap
            if center_visible_later is None and any(bool(c.get("is_visible", False)) and bool(c.get("is_enabled", False)) for c in center_caps):
                center_visible_later = snap
                break

        self.assertIsNotNone(buffs_before_center)
        self.assertIsNotNone(center_visible_later)
        self.assertLess(float(buffs_before_center.get("time_s", 0.0)), float(center_visible_later.get("time_s", 0.0)))

        def _snapshot_at(target: float) -> dict:
            last = captures[0]
            for snap in captures:
                if float(snap.get("time_s", 0.0)) <= float(target):
                    last = snap
                else:
                    break
            return last

        early_wave = _snapshot_at(170.0)
        after_pickups = _snapshot_at(245.0)
        later_wave = _snapshot_at(530.0)

        early_buffs = [c for c in early_wave.get("caps", []) if int(c.get("zone_type", -1)) == 6 and not bool(c.get("is_control_point", False))]
        picked_remaining = [c for c in after_pickups.get("caps", []) if int(c.get("zone_type", -1)) == 6 and not bool(c.get("is_control_point", False))]
        later_buffs = [c for c in later_wave.get("caps", []) if int(c.get("zone_type", -1)) == 6 and not bool(c.get("is_control_point", False))]

        self.assertGreater(len(early_buffs), len(picked_remaining))
        self.assertGreater(len(later_buffs), 0)

        early_zone_param_ids = {int(c.get("zone_params_id", -1)) for c in early_buffs}
        self.assertTrue(all(pid > 0 for pid in early_zone_param_ids))
        self.assertIn(4292757424, early_zone_param_ids)  # PCOD002_Regeneration
        self.assertIn(4251862960, early_zone_param_ids)  # PCOD041_AR_AddHeath
        self.assertIn(4291708848, early_zone_param_ids)  # PCOD003_ShotDelay

    def test_account_team_alignment(self):
        data = extract_replay(str(SAMPLE))
        meta = data.get("meta", {}) or {}
        entities = data.get("entities", {}) or {}

        relation_by_account = {}
        for v in meta.get("vehicles", []) or []:
            account_id = v.get("id")
            relation = v.get("relation")
            if account_id is None or relation is None:
                continue
            relation_by_account[int(account_id)] = int(relation)

        self.assertGreater(len(relation_by_account), 0)

        mapped_accounts = []
        for entity in entities.values():
            account_id = entity.get("account_entity_id")
            if account_id is None:
                continue
            account_id = int(account_id)
            relation = relation_by_account.get(account_id)
            if relation is None:
                continue
            expected_team = "player" if relation == 0 else ("ally" if relation == 1 else "enemy")
            self.assertEqual(entity.get("team"), expected_team)
            mapped_accounts.append(account_id)

        self.assertGreater(len(mapped_accounts), 0)
        self.assertEqual(len(mapped_accounts), len(set(mapped_accounts)))

    def test_local_player_track_has_no_impossible_jumps(self):
        data = extract_replay(str(SAMPLE))
        player_name = str((data.get("meta", {}) or {}).get("playerName") or "").strip()
        self.assertTrue(player_name)

        player_track = None
        for track in (data.get("tracks", {}) or {}).values():
            if str(track.get("player_name") or "").strip() == player_name:
                player_track = track
                break

        self.assertIsNotNone(player_track)
        points = list((player_track or {}).get("points", []))
        self.assertGreater(len(points), 0)

        bad_jumps = []
        for a, b in zip(points, points[1:]):
            dt = float(b.get("t", 0.0)) - float(a.get("t", 0.0))
            if dt <= 0.0:
                continue
            dist = math.hypot(float(b.get("x", 0.0)) - float(a.get("x", 0.0)), float(b.get("z", 0.0)) - float(a.get("z", 0.0)))
            if dist > 35.0:
                bad_jumps.append((a.get("t"), b.get("t"), dist))

        self.assertEqual([], bad_jumps[:5], msg=f"unexpected local-player jumps: {bad_jumps[:5]}")

    def test_track_sanitizer_keeps_continuity_for_duplicate_timestamps(self):
        points = [
            TrackPoint(t=1.0, x=10.0, y=0.0, z=10.0, yaw=0.0),
            TrackPoint(t=2.0, x=20.0, y=0.0, z=20.0, yaw=0.0),
            TrackPoint(t=2.0, x=520.0, y=0.0, z=520.0, yaw=0.0),
            TrackPoint(t=3.0, x=30.0, y=0.0, z=30.0, yaw=0.0),
        ]

        sanitized = _sanitize_track(points)

        self.assertEqual(3, len(sanitized))
        self.assertEqual([1.0, 2.0, 3.0], [p.t for p in sanitized])
        self.assertAlmostEqual(20.0, sanitized[1].x)
        self.assertAlmostEqual(20.0, sanitized[1].z)

    def test_track_sanitizer_prefers_dominant_first_duplicate_sample(self):
        points = [
            TrackPoint(t=0.0, x=-440.0, y=0.0, z=500.0, yaw=math.pi),
            TrackPoint(t=0.0, x=-440.0, y=0.0, z=500.0, yaw=math.pi),
            TrackPoint(t=0.0, x=615.0, y=0.0, z=400.0, yaw=math.pi),
            TrackPoint(t=0.1, x=-440.0, y=0.0, z=500.0, yaw=math.pi),
        ]

        sanitized = _sanitize_track(points)

        self.assertEqual(2, len(sanitized))
        self.assertAlmostEqual(-440.0, sanitized[0].x)
        self.assertAlmostEqual(500.0, sanitized[0].z)

    def test_public_info_row_falls_back_to_player_name(self):
        public_info = {
            "552902982": [None, "Florindi_1", None, None],
            "940975572": {"unexpected": "shape"},
        }

        key, row = _resolve_public_info_player_row(public_info, 940975572, "Florindi_1")

        self.assertEqual("552902982", key)
        self.assertEqual("Florindi_1", row[1])

    def test_live_damage_stat_totals_sum_spotting_and_potential(self):
        totals = _live_damage_stat_totals(
            {
                (2, 3): 274000.0,
                (1, 3): 235800.0,
                (1, 2): 4323.0,
                (2, 2): 940.5,
                (1, 0): 29637.0,
            }
        )

        self.assertAlmostEqual(509800.0, totals["potential_damage"])
        self.assertAlmostEqual(5263.5, totals["spotting_damage"])

    def test_space_bin_bounds_parse_for_haven(self):
        bounds = _load_space_bin_world_bounds("50_Gold_harbor")
        self.assertIsNotNone(bounds)
        min_x, max_x, min_z, max_z = bounds or (0.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(-835.3986, min_x, places=2)
        self.assertAlmostEqual(796.2786, max_x, places=2)
        self.assertAlmostEqual(-835.3986, min_z, places=2)
        self.assertAlmostEqual(796.2786, max_z, places=2)

    def test_overview_half_extent_for_haven(self):
        half = _overview_half_extent("50_Gold_harbor")
        self.assertIsNotNone(half)
        self.assertAlmostEqual(700.0, half or 0.0, places=3)

    def test_world_bounds_prefer_overview_size(self):
        data = extract_replay(str(SAMPLE))
        bounds = _world_bounds(data)
        self.assertEqual((-700.0, 700.0, -700.0, 700.0), tuple(float(v) for v in bounds))

    def test_player_layout_expands_for_extra_ribbon_rows(self):
        data = extract_replay(str(SAMPLE))
        render_tracks = _normalize_render_tracks(data)
        base_layout = _render_layout(render_tracks, 512)
        status = {
            "ribbons": {"15": 12, "14": 9, "17": 8, "8": 6, "3": 5, "0": 4, "1": 3, "6": 2},
        }
        dynamic_layout = _layout_for_player_status(base_layout, status)
        self.assertGreater(dynamic_layout["player_rect"][3], base_layout["player_rect"][3])
        self.assertGreater(dynamic_layout["feed_rect"][1], base_layout["feed_rect"][1])

    def test_find_death_times_uses_health_timeline(self):
        canonical = {
            "entities": {"42": {"death_time": None}},
            "events": {
                "deaths": [],
                "health": [
                    {"time_s": 10.0, "entities": {"42": {"hp": 1000, "alive": True}}},
                    {"time_s": 12.5, "entities": {"42": {"hp": 0, "alive": False}}},
                ],
            },
        }
        deaths = _find_death_times(canonical)
        self.assertEqual(12.5, deaths.get("42"))

    def test_ship_state_holds_position_across_large_gaps(self):
        track = {
            "points": [
                {"t": 10.0, "x": 100.0, "z": 200.0, "yaw": 1.0},
                {"t": 440.0, "x": 300.0, "z": 400.0, "yaw": 2.0},
            ]
        }

        state = _ship_state_at(track, 200.0)

        self.assertIsNotNone(state)
        self.assertAlmostEqual(100.0, state["x"])
        self.assertAlmostEqual(200.0, state["z"])
        self.assertAlmostEqual(1.0, state["yaw"])

    def test_health_state_exposes_restorable_and_regenerated_hp(self):
        timelines = {
            "7": {
                "times": [10.0, 20.0],
                "hp": [30000, 32000],
                "alive": [True, True],
                "fire": [False, False],
                "flood": [False, False],
                "restorable_hp": [12500, 11200],
                "regenerated_hp": [0, 1300],
                "max_hp": 50000,
            }
        }

        state = _health_state_at(timelines, "7", 20.0)

        self.assertIsNotNone(state)
        self.assertEqual(11200, state["restorable_hp"])
        self.assertEqual(1300, state["regenerated_hp"])

    def test_normalize_torpedo_points_preserves_packet_direction(self):
        rows = _normalize_torpedo_points(
            [
                {
                    "owner_entity_id": 42,
                    "torpedo_id": 7,
                    "time_s": 12.5,
                    "x": 100.0,
                    "z": 200.0,
                    "dir_x": 0.8,
                    "dir_z": 0.6,
                    "params_id": 999,
                    "salvo_id": 3,
                }
            ],
            {"42": "ally"},
        )

        self.assertEqual(1, len(rows))
        self.assertAlmostEqual(0.8, rows[0]["dir_x"])
        self.assertAlmostEqual(0.6, rows[0]["dir_z"])
        self.assertEqual(999, rows[0]["params_id"])
        self.assertEqual(3, rows[0]["salvo_id"])

    def test_extract_torpedo_tracks_prefers_packet_direction_for_single_point_tracks(self):
        canonical = {
            "events": {
                "torpedoes": [
                    {"owner_entity_key": "42", "torpedo_id": 1, "time_s": 10.0, "x": 5.0, "z": 0.0, "dir_x": 1.0, "dir_z": 0.0, "team_side": "friendly"},
                    {"owner_entity_key": "42", "torpedo_id": 2, "time_s": 10.2, "x": 0.0, "z": 5.0, "dir_x": 0.0, "dir_z": 1.0, "team_side": "friendly"},
                ]
            },
            "tracks": {
                "42": {
                    "points": [
                        {"t": 10.0, "x": 0.0, "z": 0.0, "yaw": 0.0},
                    ]
                }
            },
        }

        tracks = _extract_torpedo_tracks(canonical)

        self.assertEqual((1.0, 0.0), tracks["42:1"]["dir"])
        self.assertEqual((0.0, 1.0), tracks["42:2"]["dir"])

    def test_chat_blob_filter_ignores_serialized_payloads(self):
        blob = "\x02}q\x01(U\rplayerClanTagq\x02X\x03\x00\x00\x00R7Sq\x03U\nplayerNameq\x04U\x14PermanentBrainDamageq\x05U\x0bprebattleIdq\x06J\x1f\\\x1b8U\x0eplayerAvatarIdq\x07J^\x14\x00U\rpreBattleSignq\x08K\x00U\x04typeq\tK\x05u."
        self.assertTrue(_looks_serialized_chat_blob(blob))

        rows = _normalize_chat_feed(
            [
                {"time_s": 1.0, "sender": "Khitan", "message": "RPF: WNW~NW"},
                {"time_s": 2.0, "sender": "id_0", "message": blob},
            ]
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("Khitan", rows[0]["sender"])
        self.assertEqual("RPF: WNW~NW", rows[0]["message"])

    def test_friendly_stale_marker_only_marks_alive_hidden_friendlies(self):
        self.assertTrue(_friendly_stale_marker("friendly", spotted=False, sunk=False))
        self.assertFalse(_friendly_stale_marker("friendly", spotted=True, sunk=False))
        self.assertFalse(_friendly_stale_marker("friendly", spotted=False, sunk=True))
        self.assertFalse(_friendly_stale_marker("friendly", spotted=False, sunk=False, synthetic_start=True))
        self.assertFalse(_friendly_stale_marker("enemy", spotted=False, sunk=False))

    @patch("renderers.minimap_renderer._aircraft_param_meta")
    def test_infer_unknown_surface_dive_squadron_prefers_asw_family(self, mock_meta):
        mock_meta.return_value = {"species": "dive", "nation": "usa"}
        inferred = _infer_unknown_squadron_type(
            {"params_id": 42},
            {
                "carrier_attack_types": [],
                "surface_attack_types": ["asw", "airdrop_he"],
                "all_attack_types": ["asw", "airdrop_he"],
                "support_types": ["fighter"],
                "fallback_types": ["asw", "airdrop_he", "fighter"],
                "has_cv_attack": False,
                "has_surface_attack": True,
                "has_support": True,
            },
        )
        self.assertEqual("asw", inferred)

    @patch("renderers.minimap_renderer._aircraft_param_meta")
    def test_infer_unknown_cv_torpedo_squadron_uses_carrier_attack_types(self, mock_meta):
        mock_meta.return_value = {"species": "torpedo", "nation": "japan"}
        inferred = _infer_unknown_squadron_type(
            {"params_id": 84},
            {
                "carrier_attack_types": ["rocket", "torpedo"],
                "surface_attack_types": ["asw"],
                "all_attack_types": ["rocket", "torpedo", "asw"],
                "support_types": ["fighter"],
                "fallback_types": ["rocket", "torpedo", "asw", "fighter"],
                "has_cv_attack": True,
                "has_surface_attack": True,
                "has_support": True,
            },
        )
        self.assertEqual("torpedo", inferred)

    @patch("renderers.minimap_renderer._ship_aircraft_support")
    @patch("renderers.minimap_renderer._ship_type")
    def test_team_aircraft_capabilities_split_carrier_and_surface_attack(self, mock_ship_type, mock_support):
        def _ship_type_lookup(ship_id):
            return {100: "AirCarrier", 200: "Cruiser", 300: "Battleship"}.get(int(ship_id), "")

        def _support_lookup(ship_id):
            return {
                100: {"attack_types": ["rocket", "torpedo"], "render_support_types": ["fighter"]},
                200: {"attack_types": ["asw"], "render_support_types": []},
                300: {"attack_types": ["airdrop_he"], "render_support_types": []},
            }.get(int(ship_id), {})

        mock_ship_type.side_effect = _ship_type_lookup
        mock_support.side_effect = _support_lookup

        caps = _team_aircraft_capabilities(
            {
                "entities": {
                    "1": {"team": "ally", "ship_id": 100},
                    "2": {"team": "ally", "ship_id": 200},
                    "3": {"team": "enemy", "ship_id": 300},
                }
            },
            "friendly",
        )

        self.assertEqual(["rocket", "torpedo"], caps["carrier_attack_types"])
        self.assertEqual(["asw"], caps["surface_attack_types"])
        self.assertEqual(["fighter"], caps["support_types"])

    @patch("renderers.minimap_renderer._load_ship_cache")
    def test_aircraft_module_params_preserve_cv_fighter_bucket_as_rocket(self, mock_cache):
        mock_cache.return_value = {
            "4179605200": {
                "type": "AirCarrier",
                "modules": {
                    "fighter": {"ids": ["3346771664"], "names": ["A8M Rikufu"]},
                },
                "modules_tree": {
                    "3346771664": {"type": "Fighter", "name": "A8M Rikufu"},
                },
            }
        }
        _load_aircraft_module_params.cache_clear()
        try:
            mapping = _load_aircraft_module_params()
        finally:
            _load_aircraft_module_params.cache_clear()
        self.assertEqual("rocket", mapping.get("3346771664"))

    def test_build_by_cv_maps_cv_fighter_bucket_to_rocket_attack(self):
        payload = _build_by_cv(
            {
                "4179605200": {
                    "name": "Hakuryu",
                    "nation": "japan",
                    "tier": 10,
                    "type": "AirCarrier",
                    "modules": {
                        "fighter": {"ids": ["3346771664"], "name": "A8M Rikufu"},
                        "dive_bomber": {"ids": ["3347984080"], "name": "A7M Reppu"},
                        "torpedo_bomber": {"ids": ["3348049616"], "name": "C6N Saiun"},
                    },
                    "modules_tree": {
                        "3346771664": {"type": "Fighter", "name": "A8M Rikufu"},
                        "3347984080": {"type": "DiveBomber", "name": "A7M Reppu"},
                        "3348049616": {"type": "TorpedoBomber", "name": "C6N Saiun"},
                    },
                }
            }
        )
        planes = ((payload.get("4179605200") or {}).get("planes") or [])
        by_id = {str(row.get("id")): str(row.get("normalized_type") or "") for row in planes}
        self.assertEqual("rocket", by_id.get("3346771664"))
        self.assertEqual("bomber", by_id.get("3347984080"))
        self.assertEqual("torpedo", by_id.get("3348049616"))

    @patch("renderers.minimap_renderer._aircraft_param_meta")
    def test_refine_squadron_types_promotes_mobile_fighter_species_to_rocket(self, mock_meta):
        mock_meta.side_effect = lambda pid: {"species": "Fighter" if int(pid) in (1001, 1002) else ""}
        tracks = {
            "a": {"team_side": "friendly", "params_id": 1001, "type": "fighter", "mapped_type": "fighter", "points": [{"t": 0.0, "x": 0.0, "z": 0.0}, {"t": 20.0, "x": 420.0, "z": 0.0}]},
            "b": {"team_side": "friendly", "params_id": 1002, "type": "fighter", "mapped_type": "fighter", "points": [{"t": 0.0, "x": 0.0, "z": 0.0}, {"t": 20.0, "x": 80.0, "z": 0.0}]},
        }
        caps = {
            "friendly": {
                "carrier_attack_types": ["rocket", "torpedo", "bomber"],
                "support_types": ["fighter"],
            }
        }
        _refine_squadron_types({}, tracks, caps)
        self.assertEqual("rocket", tracks["a"]["type"])
        self.assertEqual("fighter", tracks["b"]["type"])

    @patch("renderers.minimap_renderer._aircraft_param_meta")
    def test_refine_squadron_types_maps_bomber_species_to_torpedo_when_dive_exists(self, mock_meta):
        def _meta(pid):
            if int(pid) == 2001:
                return {"species": "Bomber"}
            if int(pid) == 2002:
                return {"species": "Dive"}
            return {}
        mock_meta.side_effect = _meta
        tracks = {
            "torp_like": {"team_side": "friendly", "params_id": 2001, "type": "bomber", "mapped_type": "bomber", "points": [{"t": 0.0, "x": 0.0, "z": 0.0}, {"t": 10.0, "x": 120.0, "z": 0.0}]},
            "dive_like": {"team_side": "friendly", "params_id": 2002, "type": "bomber", "mapped_type": "bomber", "points": [{"t": 0.0, "x": 0.0, "z": 0.0}, {"t": 10.0, "x": 160.0, "z": 0.0}]},
        }
        caps = {
            "friendly": {
                "carrier_attack_types": ["rocket", "torpedo", "bomber"],
                "support_types": ["fighter"],
            }
        }
        _refine_squadron_types({}, tracks, caps)
        self.assertEqual("torpedo", tracks["torp_like"]["type"])
        self.assertEqual("bomber", tracks["dive_like"]["type"])

    def test_vermont_replay_consumables_resolve(self):
        sample = ROOT / "20260226_004059_PASB110-Vermont_44_Path_warrior.wowsreplay"
        if not sample.exists():
            raise unittest.SkipTest("Vermont sample replay not found in repository root")

        data = extract_replay(str(sample))
        player = next((row for row in data["entities"].values() if str(row.get("team") or "").lower() == "player"), None)
        self.assertIsNotNone(player)
        build = (player or {}).get("ship_build", {}) or {}
        consumables = build_consumable_entries(build, ship_id=(player or {}).get("ship_id"))
        kinds = {row["kind"] for row in consumables}
        self.assertIn("dcp", kinds)
        self.assertIn("heal", kinds)
        self.assertGreater(len(parse_mounted_consumable_ids(build.get("config_dump_hex"))), 0)
        for row in consumables:
            self.assertIsNotNone(load_consumable_tile_icon(row, 32), f"Missing consumable icon for {row['kind']}")

    def test_ship_build_module_icons_resolve(self):
        stock, fitted = build_module_entries(
            {
                "hull": "Hakuryu_Hull",
                "engine": "Hakuryu_Engine",
                "flightControl": "A1_FlightControl",
                "fighter": "A1_Fighter",
                "diveBomber": "A2_DiveBomber",
                "airDefense": "A2_AirDefense",
                "atba": "A2_ATBA",
            },
            ship_type="Aircraft Carrier",
        )
        self.assertEqual(["hull", "engine"], [row["key"] for row in stock])
        self.assertIn("flightControl", [row["key"] for row in fitted])
        for row in stock + fitted:
            self.assertIsNotNone(
                load_module_tile_icon(row, 32),
                f"Module icon missing for {row['key']}",
            )

    def test_modernization_icon_index_has_flight_control(self):
        path = find_modernization_icon_path("icon_modernization_PCM009_FlightControl_Mod_I.png")
        self.assertIsNotNone(path)
        self.assertTrue(find_module_icon_path("Hull").is_file())

    def test_hakuryu_replay_exposes_captain_skills_and_ship_build(self):
        sample = ROOT / "20260522_000107_PJSA110-Hakuryu_51_Greece.wowsreplay"
        if not sample.exists():
            raise unittest.SkipTest("Hakuryu sample replay not found in repository root")

        data = extract_replay(str(sample))
        entities = data.get("entities", {}) or {}
        hakuryu = next(
            (row for row in entities.values() if str(row.get("player_name") or "") == "Florindi_1"),
            None,
        )

        self.assertIsNotNone(hakuryu)
        captain = (hakuryu or {}).get("captain_skills", {}) or {}
        learned = captain.get("learned_skills", {}) or {}
        self.assertIn("AirCarrier", learned)
        self.assertIn("PlanesSpeed", learned["AirCarrier"])
        self.assertIn("PlanesReload", learned["AirCarrier"])

        build = (hakuryu or {}).get("ship_build", {}) or {}
        components = build.get("components", {}) or {}
        self.assertEqual("A1_Fighter", components.get("fighter"))
        self.assertEqual("A2_TorpedoBomber", components.get("torpedoBomber"))
        self.assertEqual("A2_DiveBomber", components.get("diveBomber"))
        self.assertEqual("A1_FlightControl", components.get("flightControl"))
        self.assertTrue(build.get("config_dump_hex"))

        stock, fitted = build_module_entries(components, ship_type="Aircraft Carrier")
        self.assertGreater(len(stock), 0)
        self.assertGreater(len(fitted), 0)
        for row in stock + fitted:
            self.assertIsNotNone(load_module_tile_icon(row, 32), f"Missing build icon for {row['key']}")
        upgrades = parse_mounted_upgrades(str(build.get("config_dump_hex") or ""))
        for upgrade in upgrades:
            self.assertTrue(find_modernization_icon_path(upgrade["icon"]).is_file())

    def test_hakuryu_skill_icons_resolve_for_replay(self):
        sample = ROOT / "20260522_000107_PJSA110-Hakuryu_51_Greece.wowsreplay"
        if not sample.exists():
            raise unittest.SkipTest("Hakuryu sample replay not found in repository root")

        data = extract_replay(str(sample))
        entities = data.get("entities", {}) or {}
        hakuryu = next(
            (row for row in entities.values() if str(row.get("player_name") or "") == "Florindi_1"),
            None,
        )

        self.assertIsNotNone(hakuryu)
        captain = (hakuryu or {}).get("captain_skills", {}) or {}
        learned = captain.get("learned_skills", {}) or {}
        for skills in learned.values():
            for skill in skills:
                self.assertIsNotNone(_load_commander_skill_icon(skill, 32), f"Icon missing for skill {skill}")

    def test_hakuryu_aircraft_carrier_layout_covers_all_replay_skills(self):
        sample = ROOT / "20260522_000107_PJSA110-Hakuryu_51_Greece.wowsreplay"
        if not sample.exists():
            raise unittest.SkipTest("Hakuryu sample replay not found in repository root")

        data = extract_replay(str(sample))
        entities = data.get("entities", {}) or {}
        hakuryu = next(
            (row for row in entities.values() if str(row.get("player_name") or "") == "Florindi_1"),
            None,
        )

        self.assertIsNotNone(hakuryu)
        captain = (hakuryu or {}).get("captain_skills", {}) or {}
        selected_type, skills = _select_ship_class_skills(captain, "Aircraft Carrier")
        self.assertEqual("AirCarrier", selected_type)
        layout = _layout_for_ship_type(selected_type)
        self.assertTrue(layout)
        self.assertTrue(_layout_covers_skills(skills, layout))

    def test_surcouf_submarine_layout_covers_all_replay_skills(self):
        sample = ROOT / "20260522_003146_PFSS710-Surcouf_15_NE_north.wowsreplay"
        if not sample.exists():
            raise unittest.SkipTest("Surcouf sample replay not found in repository root")

        data = extract_replay(str(sample))
        entities = data.get("entities", {}) or {}
        surcouf = next(
            (row for row in entities.values() if str(row.get("player_name") or "") == "Florindi_1"),
            None,
        )

        self.assertIsNotNone(surcouf)
        captain = (surcouf or {}).get("captain_skills", {}) or {}
        selected_type, skills = _select_ship_class_skills(captain, "Submarine")
        self.assertEqual("Submarine", selected_type)
        self.assertIn("SubmarineSpeed", skills)
        layout = _layout_for_ship_type(selected_type)
        self.assertTrue(layout)
        self.assertTrue(_layout_covers_skills(skills, layout))

    def test_bungo_battleship_layout_covers_all_replay_skills(self):
        sample = ROOT / "20260519_214531_PJSB210-Bungo_44_Path_warrior.wowsreplay"
        if not sample.exists():
            raise unittest.SkipTest("Bungo sample replay not found in repository root")

        data = extract_replay(str(sample))
        entities = data.get("entities", {}) or {}
        bungo = next(
            (row for row in entities.values() if str(row.get("player_name") or "") == "Florindi_1"),
            None,
        )

        self.assertIsNotNone(bungo)
        captain = (bungo or {}).get("captain_skills", {}) or {}
        selected_type, skills = _select_ship_class_skills(captain, "Battleship")
        self.assertEqual("Battleship", selected_type)
        self.assertIn("DefenceCritFireFlooding", skills)
        self.assertIn("TriggerSpeedBb", skills)
        layout = _layout_for_ship_type(selected_type)
        self.assertTrue(layout)
        self.assertTrue(_layout_covers_skills(skills, layout))

    def test_lineup_is_sorted_by_ship_class(self):
        data = extract_replay(str(SAMPLE))
        render_tracks = _normalize_render_tracks(data)
        friendly, enemy = _split_lineups(render_tracks)
        for lineup in (friendly, enemy):
            ranks = [LINEUP_CLASS_ORDER.get(_ship_type(item.get("ship_id")), 99) for item in lineup]
            self.assertEqual(ranks, sorted(ranks))

    def test_shell_hit_ribbon_ids_map_to_distinct_subribbons(self):
        self.assertEqual("subribbons/subribbon_main_caliber_over_penetration.png", RIBBON_ID_TO_ASSET[14])
        self.assertEqual("subribbons/subribbon_main_caliber_penetration.png", RIBBON_ID_TO_ASSET[15])
        self.assertEqual("subribbons/subribbon_main_caliber_no_penetration.png", RIBBON_ID_TO_ASSET[16])
        self.assertEqual("subribbons/subribbon_main_caliber_ricochet.png", RIBBON_ID_TO_ASSET[17])
        self.assertEqual("subribbons/subribbon_bulge.png", RIBBON_ID_TO_ASSET[28])

    def test_shell_hit_subribbons_load_as_wide_icons(self):
        for rid in (14, 15, 16, 17, 28):
            icon = _load_ribbon_icon(rid, 34)
            self.assertIsNotNone(icon, msg=f"missing ribbon icon for {rid}")
            self.assertGreater(icon.width, icon.height, msg=f"expected wide subribbon for {rid}")

    def test_resolve_speed_applies_playback_scale(self):
        canonical = {"stats": {"battle_end_s": 100.0}}
        resolved = _resolve_speed(canonical, fps=10, speed=3.0, target_duration_s=20.0)
        expected = 100.0 / float(max(1, int(round(20.0 * PLAYBACK_DURATION_SCALE * 10)) - 1))
        self.assertAlmostEqual(expected, resolved, places=6)

    def test_battle_result_text_uses_local_team_score(self):
        canonical = {
            "meta": {"local_team_id": 1, "enemy_team_id": 0},
            "stats": {"team_scores_final": {"0": 720, "1": 1000}, "team_win_score": 1000},
        }
        self.assertEqual(("VICTORY", (112, 235, 126)), _battle_result_text(canonical))

    def test_native_map_size_respects_requested_floor(self):
        data = extract_replay(str(SAMPLE))
        self.assertEqual(1024, _native_map_size(data, 1024))

    def test_map_roots_use_gui_spaces_and_dedicated_cache(self):
        self.assertEqual((ROOT / "gui" / "spaces").resolve(), _map_assets_root().resolve())
        self.assertEqual((ROOT / "content" / "wg_map_cache").resolve(), _map_cache_dir().resolve())

    def test_auto_output_duration_stays_within_55_to_85_seconds(self):
        self.assertAlmostEqual(55.0, auto_output_duration_s({"stats": {"battle_end_s": 0.0}}), places=3)
        self.assertAlmostEqual(70.0, auto_output_duration_s({"stats": {"battle_end_s": 600.0}}), places=3)
        self.assertAlmostEqual(85.0, auto_output_duration_s({"stats": {"battle_end_s": 1200.0}}), places=3)
        self.assertAlmostEqual(85.0, auto_output_duration_s({"stats": {"battle_end_s": 1800.0}}), places=3)

    def test_internal_target_duration_converts_output_seconds(self):
        self.assertAlmostEqual(55.0 / PLAYBACK_DURATION_SCALE, internal_target_duration_s(55.0), places=6)

    def test_speed_for_output_duration_matches_resolve_speed(self):
        battle_seconds = 710.083
        output_duration = 51.83
        expected = _resolve_speed({"stats": {"battle_end_s": battle_seconds}}, 25, 3.0, internal_target_duration_s(output_duration))
        self.assertAlmostEqual(expected, speed_for_output_duration(battle_seconds, 25, output_duration), places=6)


if __name__ == "__main__":
    unittest.main()
