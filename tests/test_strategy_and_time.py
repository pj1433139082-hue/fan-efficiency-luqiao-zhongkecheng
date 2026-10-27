from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/integrated"))
sys.path.insert(0, str(ROOT / "apps/platform_adapter"))
from fan_combination.contract import MACHINES
from fan_combination.strategy import prepare_curves_from_points, recommend
from fan_combination.time_input import optional_time
from luqiao_fan.pipeline import prepare_curves
from platform2622 import main as platform_main


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class IndependentStrategyTests(unittest.TestCase):
    def setUp(self):
        self.request = load("apps/strategy_only/examples/efficiency_points_synthetic.json")
        self.current = load("apps/strategy_only/examples/current_synthetic.json")["current"]

    def test_raw_and_efficiency_result_routes_equal(self):
        c1, _ = prepare_curves(load("apps/integrated/examples/history_synthetic.json"))
        c2, _ = prepare_curves_from_points(self.request)
        self.assertEqual(c1["machines"], c2["machines"])
        self.assertEqual(recommend(c1, self.current)[0], recommend(c2, self.current)[0])

    def test_reject_percent_mistaken_for_fraction(self):
        self.request["efficiency_points"][0]["eta_excel"] = 65
        with self.assertRaises(ValueError):
            prepare_curves_from_points(self.request)

    def test_reject_duplicate_points(self):
        self.request["efficiency_points"].append(deepcopy(self.request["efficiency_points"][0]))
        with self.assertRaises(ValueError):
            prepare_curves_from_points(self.request)

    def test_reject_cross_phase(self):
        self.request["efficiency_points"][0]["point_id"] = "other-phase"
        with self.assertRaises(ValueError):
            prepare_curves_from_points(self.request)

    def test_reject_current_point_in_history(self):
        self.request["efficiency_points"][0]["observed_at"] = self.request["history_end"]
        with self.assertRaises(ValueError):
            prepare_curves_from_points(self.request)

    def test_invalid_upstream_points_do_not_become_curves(self):
        for p in self.request["efficiency_points"]:
            p["quality"] = "STOPPED"
        curves, _ = prepare_curves_from_points(self.request)
        self.assertTrue(all(c["n_kept"] == 0 for c in curves["machines"].values()))
        self.assertEqual(recommend(curves, self.current)[0]["RESULT_VALID"], 0)

    def test_standalone_cli_works_without_site_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            hist, result = Path(directory) / "history", Path(directory) / "result"
            commands = [["prepare", "--input", str(ROOT / "apps/strategy_only/examples/efficiency_points_synthetic.json"), "--output", str(hist)],
                ["recommend", "--curves", str(hist / "curves.json"), "--input", str(ROOT / "apps/strategy_only/examples/current_synthetic.json"), "--output", str(result)]]
            for args in commands:
                run = subprocess.run([sys.executable, "-I", "-S", "-B", "-X", "utf8", str(ROOT / "apps/strategy_only/run.py"), *args], capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(run.returncode, 0, run.stderr)
            value = json.loads((result / "numeric_result.json").read_text(encoding="utf-8"))
            self.assertEqual(value["RESULT_VALID"], 1)
            self.assertAlmostEqual(value["FAN5_FLOW"], 40 + 164 / 347)


class OptionalTimeTests(unittest.TestCase):
    def test_absent_forms(self):
        for value in (None, "", " ", [], float("nan")):
            with self.subTest(value=value):
                self.assertIsNone(optional_time(value))

    def test_nonempty_containers_and_numbers_rejected(self):
        for value in ([[]], ["2026-10-27T10:03:00+08:00"], {}, 0, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "as_of"):
                    optional_time(value)

    def test_iso_time_preserved(self):
        self.assertEqual(optional_time("2026-10-27T10:03:00+08:00"), "2026-10-27T10:03:00+08:00")

    def test_platform_empty_array_has_same_result_as_omission(self):
        import pandas as pd
        req = load("apps/platform_adapter/examples/request.json")
        curves = load("apps/platform_adapter/examples/curves_synthetic.json")
        current = load("apps/integrated/examples/current_synthetic.json")["current"]
        stamp = "2026-10-27T10:03:00+08:00"
        records = []
        for item in current:
            for signal, value in (("V_IF", item["inlet_flow"]), ("S_RUN", 1), ("A_FLT", 0), ("A_SAG", 0)):
                records.append({"data_time": stamp, "column": item["point_id"] + "|" + signal, "value": value, "status": "0"})
        class FixedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat("2026-10-27T10:03:01+08:00").astimezone(tz)
        with patch.object(platform_main, "datetime", FixedClock), patch.object(platform_main, "IotClient") as client:
            client.return_value.fetch.return_value = (pd.DataFrame(records), [])
            baseline = platform_main.online_feature_engineering(pd.DataFrame([req]), {"curves": curves})
            for value in (None, "", " ", []):
                actual = platform_main.online_feature_engineering(pd.DataFrame([{**req, "as_of": value}]), {"curves": curves})
                pd.testing.assert_frame_equal(baseline, actual)
        self.assertEqual(baseline.iloc[0]["RESULT_VALID"], 1)

    def test_required_point_array_still_cannot_be_empty(self):
        import pandas as pd
        req = load("apps/platform_adapter/examples/request.json")
        curves = load("apps/platform_adapter/examples/curves_synthetic.json")
        with patch.object(platform_main, "IotClient") as client:
            with self.assertRaisesRegex(ValueError, "V_IF"):
                platform_main.online_feature_engineering(pd.DataFrame([{**req, "V_IF": [], "as_of": []}]), {"curves": curves})
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()

