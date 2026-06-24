import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main as cli_main
from api import setup_api, wows_api
from tools import update_wows_version


class MainCliTests(unittest.TestCase):
    def test_comprehensive_module_imports_from_package(self):
        module = importlib.import_module("tools.dev_tools.comprehensive_replay_analysis")
        self.assertTrue(hasattr(module, "ComprehensiveReplayAnalyzer"))

    def test_run_analyze_uses_packaged_analyzer(self):
        calls = {}

        class FakeAnalyzer:
            def __init__(self, replay_path: str):
                calls["path"] = replay_path

            def analyze_complete(self):
                return {"ok": True}

            def save_all_analysis(self):
                calls["saved"] = True

            def print_summary(self):
                calls["printed"] = True

        with patch("tools.dev_tools.comprehensive_replay_analysis.ComprehensiveReplayAnalyzer", FakeAnalyzer):
            rc = cli_main._run_analyze(["sample.json"])

        self.assertEqual(rc, 0)
        self.assertEqual(calls["path"], "sample.json")
        self.assertTrue(calls["saved"])
        self.assertTrue(calls["printed"])

    def test_run_setup_defaults_to_setup_subcommand(self):
        seen_argv: list[list[str]] = []

        def fake_setup_main() -> None:
            seen_argv.append(sys.argv[:])

        with patch("api.setup_api.main", side_effect=fake_setup_main):
            rc = cli_main._run_setup([])

        self.assertEqual(rc, 0)
        self.assertEqual(seen_argv, [["setup_api.py", "setup"]])

    def test_run_setup_preserves_explicit_subcommand(self):
        seen_argv: list[list[str]] = []

        def fake_setup_main() -> None:
            seen_argv.append(sys.argv[:])

        with patch("api.setup_api.main", side_effect=fake_setup_main):
            rc = cli_main._run_setup(["cache"])

        self.assertEqual(rc, 0)
        self.assertEqual(seen_argv, [["setup_api.py", "cache"]])


class SetupApiTests(unittest.TestCase):
    def test_setup_credentials_saves_entered_app_id_and_default_realm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "wws_api_config.json"
            fake_api = Mock()
            fake_api.get_all_ships.return_value = {"1": {"name": "Test Ship"}}

            with patch.object(setup_api, "CONFIG_FILE", config_path), \
                patch("builtins.input", side_effect=["my-app-id", ""]), \
                patch("api.setup_api.load_credentials", return_value=object()), \
                patch("api.setup_api.WoWSAPI", return_value=fake_api):
                result = setup_api.setup_credentials()

            self.assertTrue(result)
            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["app_id"], "my-app-id")
            self.assertEqual(written["realm"], "na")

    def test_create_ship_cache_interactive_uses_repo_root_cache_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "ships_cache.json"
            fake_api = object()

            with patch.object(setup_api, "SHIP_CACHE_FILE", cache_path), \
                patch("api.setup_api.load_credentials", return_value=object()), \
                patch("api.setup_api.WoWSAPI", return_value=fake_api), \
                patch("api.setup_api.create_ship_cache", return_value={"1": {"name": "Test Ship"}}) as create_cache:
                result = setup_api.create_ship_cache_interactive()

            self.assertTrue(result)
            create_cache.assert_called_once_with(fake_api, str(cache_path))

    def test_load_credentials_reads_repo_root_config_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "wws_api_config.json"
            config_path.write_text(
                json.dumps({"app_id": "root-app-id", "realm": "eu"}),
                encoding="utf-8",
            )

            with patch.object(wows_api, "CONFIG_FILE", config_path), \
                patch.dict("os.environ", {}, clear=True):
                creds = wows_api.load_credentials()

        self.assertIsNotNone(creds)
        self.assertEqual(creds.app_id, "root-app-id")
        self.assertEqual(creds.realm, "eu")


class UpdateWowsVersionGuardTests(unittest.TestCase):
    def test_packet_shape_delta_ignores_count_only_changes(self):
        baseline = {
            "render_packet_raw_lengths": {
                "Position": {"min": 24, "max": 24, "values": [24], "common": [[24, 100]]}
            }
        }
        candidate = {
            "render_packet_raw_lengths": {
                "Position": {"min": 24, "max": 24, "values": [24], "common": [[24, 250]]}
            }
        }

        delta = update_wows_version._packet_shape_delta(baseline, candidate)

        self.assertEqual({}, delta)

    def test_packet_shape_delta_flags_render_packet_layout_changes(self):
        baseline = {"render_packet_raw_lengths": {"PlayerPosition": {"min": 28, "max": 28, "values": [28]}}}
        candidate = {"render_packet_raw_lengths": {"PlayerPosition": {"min": 32, "max": 32, "values": [32]}}}

        delta = update_wows_version._packet_shape_delta(baseline, candidate)

        self.assertIn("PlayerPosition", delta)

    def test_quality_delta_flags_large_track_loss(self):
        baseline = {"track_count": 24, "point_count": 5000, "tracks_with_points": 24}
        candidate = {"track_count": 8, "point_count": 900, "tracks_with_points": 8}

        delta = update_wows_version._quality_delta(baseline, candidate)

        self.assertIn("track_count", delta)
        self.assertIn("point_count", delta)

    def test_player_field_warnings_flag_shifted_player_info_values(self):
        info = {
            "players": {
                1: {
                    "id": "not-an-id",
                    "name": 1234,
                    "shipId": {"wrong": "slot"},
                    "teamId": 1,
                    "shipComponents": [],
                }
            }
        }

        warnings = update_wows_version._player_field_warnings(info)

        self.assertGreaterEqual(len(warnings), 3)

    def test_static_map_delta_flags_player_field_map_changes(self):
        baseline = {"player_info_maps": {"players": {"1": "id", "2": "name"}}}
        candidate = {"player_info_maps": {"players": {"1": "id", "2": "shipId"}}}

        delta = update_wows_version._static_map_delta(baseline, candidate)

        self.assertIn("player_info_maps", delta)

    def test_render_feature_coverage_reports_not_observed_optional_features(self):
        canonical = {
            "meta": {"mapDisplayName": "Test Map", "control_points": [{"id": 1}]},
            "entities": {"1": {"ship_build": {"components": {}}}},
            "tracks": {
                "1": {
                    "team": "player",
                    "ship_id": 1,
                    "player_name": "Tester",
                    "points": [{"t": 0, "x": 0, "y": 0, "z": 0, "yaw": 0}],
                },
                "2": {
                    "team": "enemy",
                    "ship_id": 2,
                    "player_name": "Enemy",
                    "points": [{"t": 0, "x": 10, "y": 0, "z": 10, "yaw": 0}],
                },
                "3": {
                    "team": "ally",
                    "ship_id": 3,
                    "player_name": "Ally",
                    "points": [{"t": 0, "x": -10, "y": 0, "z": -10, "yaw": 0}],
                },
            },
            "events": {"health": [{}], "player_status": [{}], "kills": [{}], "captures": [{}]},
            "stats": {"battle_end_s": 100, "team_scores_final": {"0": 500}},
        }
        quality = update_wows_version._canonical_quality_summary(canonical)

        coverage = update_wows_version._render_feature_coverage(canonical, quality)

        self.assertEqual("ok", coverage["features"]["ship_movement"]["status"])
        self.assertIn("sensor_overlay", coverage["not_observed"])
