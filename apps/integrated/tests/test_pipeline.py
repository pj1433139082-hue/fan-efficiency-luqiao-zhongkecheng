"""固定输入验证真实模块衔接、时间边界、无效分支和原分配公式。夹具均为合成。"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from luqiao_fan import pipeline as p
from luqiao_fan.cli import main, load_json

ROOT = Path(__file__).resolve().parents[1]
P5, P6 = p.MACHINES


def history():
    return load_json(ROOT / "examples/history_synthetic.json")


def current():
    return load_json(ROOT / "examples/current_synthetic.json")["current"]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.curves, self.audit = p.prepare_curves(history())

    def test_independent_allocation_golden(self):
        result, detail = p.recommend(self.curves, current())
        self.assertEqual(list(result), list(p.OUTPUTS))
        self.assertEqual(result["RESULT_VALID"], 1)
        self.assertEqual(result["TARGET_FLOW"], 101)
        # 两台同压力/温度/海拔且功率60/80；平均效率权重之比(41/60):(61/80)=164:183。
        self.assertAlmostEqual(result["FAN5_FLOW"], 40 + 164 / 347, places=10)
        self.assertAlmostEqual(result["FAN6_FLOW"], 60 + 183 / 347, places=10)
        self.assertEqual(detail["recommendation"]["S"], [P5, P6])

    def test_each_minute_pairs_aggregated_flow_and_efficiency(self):
        self.assertEqual(len(self.audit), 6)
        self.assertEqual(self.curves["machines"][P5]["q_min"], 40)
        self.assertEqual(self.curves["machines"][P5]["q_max"], 42)
        self.assertEqual(self.curves["machines"][P6]["n_kept"], 3)
        self.assertTrue(all(a["n_samples"] == 4 and a["coverage_s"] == 60 for a in self.audit))

    def test_no_recalculation_during_recommend(self):
        with patch.object(p.efficiency, "compute_row", side_effect=AssertionError("online recomputed")):
            self.assertEqual(p.recommend(self.curves, current())[0]["RESULT_VALID"], 1)

    def test_module_does_not_import_generic_model(self):
        self.assertIn("fan_combination.efficiency_adapter", p.efficiency.__name__)

    def test_same_time_accepts_equivalent_utc(self):
        snap = current()
        snap[1]["observed_at"] = "2026-10-27T02:03:00Z"
        self.assertEqual(p.recommend(self.curves, snap)[0]["RESULT_VALID"], 1)

    def test_different_snapshot_times_rejected(self):
        snap = current()
        snap[1]["observed_at"] = "2026-10-27T10:03:01+08:00"
        with self.assertRaisesRegex(ValueError, "同刻"):
            p.recommend(self.curves, snap)

    def test_snapshot_before_curve_rejected(self):
        snap = current()
        for row in snap:
            row["observed_at"] = "2026-10-27T10:02:59+08:00"
        with self.assertRaisesRegex(ValueError, "未来"):
            p.recommend(self.curves, snap)

    def test_unavailable_flow_still_in_target(self):
        snap = current()
        snap[0]["eligible"] = False
        result, detail = p.recommend(self.curves, snap)
        self.assertEqual(result, p.blank_result())
        self.assertEqual(detail["target"], 101)
        self.assertEqual(detail["status"], "NO_FEASIBLE")
        self.assertIsNone(detail["recommendation"])

    def test_single_fan_fewer_units_preferred(self):
        snap = current()
        snap[0].update(inlet_flow=0, run_flag=0)
        snap[1]["inlet_flow"] = 60
        result, detail = p.recommend(self.curves, snap)
        self.assertEqual((result["FAN5_FLOW"], result["FAN6_FLOW"]), (0, 60))
        self.assertEqual(detail["recommendation"]["S"], [P6])

    def test_current_stop_positive_flow_invalid(self):
        snap = current()
        snap[0]["run_flag"] = 0
        result, detail = p.recommend(self.curves, snap)
        self.assertEqual(result["RESULT_VALID"], 0)
        self.assertEqual(detail["status"], "CURRENT_FLOW_RUN_CONFLICT")

    def test_current_missing_not_zero_filled(self):
        snap = current()
        snap[0]["inlet_flow"] = None
        self.assertEqual(p.recommend(self.curves, snap)[0], p.blank_result())

    def test_current_quality_invalid(self):
        snap = current()
        snap[1]["raw_quality_ok"] = False
        self.assertEqual(p.recommend(self.curves, snap)[0]["RESULT_VALID"], 0)

    def test_current_duplicate_machine_rejected(self):
        snap = current()
        snap[1] = deepcopy(snap[0])
        with self.assertRaises(ValueError):
            p.recommend(self.curves, snap)

    def test_invalid_tolerance_not_silently_applied(self):
        with self.assertRaises(ValueError):
            p.recommend(self.curves, current(), 8)

    def test_other_plant_curve_rejected(self):
        bundle = deepcopy(self.curves)
        bundle["model_id"] = "taierzhuang"
        with self.assertRaises(ValueError):
            p.recommend(bundle, current())

    def test_nan_curve_rejected(self):
        self.curves["machines"][P5]["q_max"] = float("nan")
        with self.assertRaises(ValueError):
            p.recommend(self.curves, current())

    def test_no_history_does_not_borrow_curve(self):
        request = history()
        request["samples"] = [r for r in request["samples"] if r["point_id"] == P6]
        bundle, _ = p.prepare_curves(request)
        self.assertEqual(bundle["machines"][P5]["status"], "INSUFFICIENT_POINTS")
        self.assertEqual(bundle["machines"][P5]["n_kept"], 0)

    def test_no_history_anywhere(self):
        request = history()
        request["samples"] = []
        bundle, _ = p.prepare_curves(request)
        result, detail = p.recommend(bundle, current())
        self.assertEqual(result, p.blank_result())
        self.assertEqual(detail["status"], "NO_AVAILABLE_UNITS")

    def test_less_than_three_points_remains_usable_original_rule(self):
        request = history()
        request["samples"] = [r for r in request["samples"] if "10:00:" in r["observed_at"]]
        bundle, _ = p.prepare_curves(request)
        self.assertEqual(bundle["machines"][P5]["n_kept"], 1)
        self.assertTrue(bundle["machines"][P5]["sample_count_lt3"])

    def test_raw_duplicate_rejected(self):
        request = history()
        request["samples"].append(deepcopy(request["samples"][0]))
        with self.assertRaisesRegex(ValueError, "重复"):
            p.prepare_curves(request)

    def test_raw_current_point_cannot_enter_history(self):
        request = history()
        request["samples"][0]["observed_at"] = request["history_end"]
        with self.assertRaisesRegex(ValueError, "窗口"):
            p.prepare_curves(request)

    def test_other_phase_rejected(self):
        request = history()
        request["samples"][0]["point_id"] = "PS1061-BE_GFJF_0001-C_003_0002"
        with self.assertRaises(ValueError):
            p.prepare_curves(request)

    def test_elevation_not_silently_defaulted(self):
        request = history()
        del request["samples"][0]["elevation"]
        with self.assertRaises(KeyError):
            p.prepare_curves(request)

    def test_cleaning_gap_not_target_tolerance_default(self):
        request = history()
        request["cleaning_gap_pct"] = None
        with self.assertRaises(ValueError):
            p.prepare_curves(request)

    def test_unknown_time_zone_rejected(self):
        request = history()
        request["samples"][0]["observed_at"] = "2026-10-27T10:00:00"
        with self.assertRaises(ValueError):
            p.prepare_curves(request)

    def test_coverage_gap_is_not_forward_filled(self):
        request = history()
        request["samples"] = [r for r in request["samples"] if r["point_id"] == P5 and
                               r["observed_at"] == "2026-10-27T10:00:00+08:00"]
        _, audit = p.prepare_curves(request)
        first = next(a for a in audit if a["point_id"] == P5)
        self.assertEqual(first["quality"], "NO_SAMPLE")
        self.assertEqual(first["coverage_s"], 15)

    def test_raw_bad_quality_excludes_whole_row(self):
        request = history()
        for row in request["samples"]:
            row["raw_quality_ok"] = False
        bundle, _ = p.prepare_curves(request)
        self.assertTrue(all(c["n_kept"] == 0 for c in bundle["machines"].values()))

    def test_refuses_existing_output_before_computation(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "occupied"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("unchanged", encoding="utf-8")
            with patch("luqiao_fan.cli.prepare_curves", side_effect=AssertionError("should not run")):
                code = main(["prepare", "--input", "does-not-exist", "--output", str(target)])
            self.assertEqual(code, 1)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")


if __name__ == "__main__":
    unittest.main()

