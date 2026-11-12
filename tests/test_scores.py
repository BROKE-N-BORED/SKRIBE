"""Tests for the FZI math: weights, EVS, cap, bands."""
import unittest

from skribe import rubric
from skribe.scores import band_for, clamp_score, compute_fzi, grade_from_metrics


class WeightsTests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        total = sum(rubric.WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0)

    def test_weights_match_the_v31_controller(self):
        self.assertEqual(rubric.WEIGHTS["structure"], 0.20)
        self.assertEqual(rubric.WEIGHTS["accuracy"], 0.20)
        self.assertEqual(rubric.WEIGHTS["utility"], 0.20)
        self.assertEqual(rubric.WEIGHTS["clarity"], 0.15)
        self.assertEqual(rubric.WEIGHTS["depth"], 0.15)
        self.assertEqual(rubric.WEIGHTS["domain"], 0.10)

    def test_all_six_metrics_present(self):
        self.assertEqual(set(rubric.METRIC_KEYS),
                         {"structure", "accuracy", "utility",
                          "clarity", "depth", "domain"})


class ComputeFziTests(unittest.TestCase):
    def _all(self, value):
        return {k: value for k in rubric.METRIC_KEYS}

    def test_perfect_scores_give_100(self):
        fzi, _ = compute_fzi(self._all(100))
        self.assertEqual(fzi, 100.0)

    def test_zero_scores_give_zero(self):
        fzi, _ = compute_fzi(self._all(0))
        self.assertEqual(fzi, 0.0)

    def test_half_scores_give_50(self):
        fzi, _ = compute_fzi(self._all(50))
        self.assertEqual(fzi, 50.0)

    def test_weighted_mix(self):
        # Only structure at 100: 100 x 0.20 = 20.
        scores = self._all(0)
        scores["structure"] = 100
        fzi, _ = compute_fzi(scores)
        self.assertEqual(fzi, 20.0)
        # Only domain at 100: 100 x 0.10 = 10.
        scores = self._all(0)
        scores["domain"] = 100
        fzi, _ = compute_fzi(scores)
        self.assertEqual(fzi, 10.0)

    def test_missing_metric_counts_as_zero(self):
        fzi, _ = compute_fzi({"structure": 100})
        self.assertEqual(fzi, 20.0)

    def test_scores_clamped_to_0_100(self):
        fzi, _ = compute_fzi(self._all(500))
        self.assertEqual(fzi, 100.0)
        fzi, _ = compute_fzi(self._all(-50))
        self.assertEqual(fzi, 0.0)


class EvsTests(unittest.TestCase):
    def _all(self, value):
        return {k: value for k in rubric.METRIC_KEYS}

    def test_evs_1_leaves_accuracy_alone(self):
        fzi, adjusted = compute_fzi(self._all(100), evs=1.0)
        self.assertEqual(adjusted, 100.0)
        self.assertEqual(fzi, 100.0)

    def test_evs_08_no_sources(self):
        # Accuracy 100 x 0.8 = 80; FZI = 80 + 80 x 0.20 = 96.
        fzi, adjusted = compute_fzi(self._all(100), evs=0.8)
        self.assertEqual(adjusted, 80.0)
        self.assertEqual(fzi, 96.0)

    def test_evs_05_contradiction(self):
        # Accuracy 100 x 0.5 = 50; FZI = 80 + 50 x 0.20 = 90.
        fzi, adjusted = compute_fzi(self._all(100), evs=0.5)
        self.assertEqual(adjusted, 50.0)
        self.assertEqual(fzi, 90.0)

    def test_evs_applies_only_to_accuracy(self):
        scores = self._all(0)
        scores["accuracy"] = 100
        fzi, _ = compute_fzi(scores, evs=0.8)
        # 80 x 0.20 = 16.
        self.assertEqual(fzi, 16.0)

    def test_evs_clamped(self):
        fzi, adjusted = compute_fzi(self._all(100), evs=5.0)
        self.assertEqual(adjusted, 100.0)
        fzi, adjusted = compute_fzi(self._all(100), evs=-1.0)
        self.assertEqual(adjusted, 0.0)


class BandTests(unittest.TestCase):
    def test_bands_at_boundaries(self):
        self.assertEqual(band_for(100)[0], "Zenith Excellence")
        self.assertEqual(band_for(95)[0], "Zenith Excellence")
        self.assertEqual(band_for(94.99)[0], "Superior Quality")
        self.assertEqual(band_for(90)[0], "Superior Quality")
        self.assertEqual(band_for(89.99)[0], "Strong Performance")
        self.assertEqual(band_for(80)[0], "Strong Performance")
        self.assertEqual(band_for(79.99)[0], "Acceptable Standard")
        self.assertEqual(band_for(70)[0], "Acceptable Standard")
        self.assertEqual(band_for(69.99)[0], "Rejected")
        self.assertEqual(band_for(0)[0], "Rejected")


class ClampTests(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp_score(150), 100.0)
        self.assertEqual(clamp_score(-5), 0.0)
        self.assertEqual(clamp_score(42.5), 42.5)
        self.assertEqual(clamp_score(float("nan")), 0.0)
        self.assertEqual(clamp_score("nope"), 0.0)
        self.assertEqual(clamp_score(None), 0.0)


class GradeFromMetricsTests(unittest.TestCase):
    def test_result_shape(self):
        result = grade_from_metrics(
            {k: 80 for k in rubric.METRIC_KEYS},
            evs=1.0, scorer="test",
            rationales={"structure": ["reason here"]})
        self.assertEqual(result.fzi, 80.0)
        self.assertEqual(result.band, "Strong Performance")
        self.assertEqual(result.scorer, "test")
        self.assertEqual(result.metrics["structure"].rationale,
                         ["reason here"])
        data = result.to_dict()
        self.assertEqual(data["fzi"], 80.0)
        self.assertEqual(data["metrics"]["structure"]["score"], 80.0)
        self.assertEqual(data["metrics"]["structure"]["weight"], 0.20)

    def test_accuracy_rationale_names_the_evs_adjustment(self):
        result = grade_from_metrics(
            {k: 100 for k in rubric.METRIC_KEYS}, evs=0.8,
            scorer="test")
        rationale = " ".join(result.metrics["accuracy"].rationale)
        self.assertIn("EVS 0.8", rationale)
        self.assertIn("80.00", rationale)


if __name__ == "__main__":
    unittest.main()
