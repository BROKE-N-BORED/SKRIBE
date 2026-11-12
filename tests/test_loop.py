"""Tests for the recursion / flow-control loop."""
import unittest

from skribe.loop import (EXIT_DEGRADED, EXIT_DIMINISHING,
                         EXIT_MAX_CYCLES, EXIT_NO_CHANGE, EXIT_TARGET,
                         LoopConfig, run_loop)
from skribe.scores import grade_from_metrics


class _FakeGrade:
    def __init__(self, fzi):
        self.fzi = fzi


def _score_fn_from_scores(scores):
    """A score function returning preset FZIs in order."""
    state = {"i": 0}

    def score_fn(_text):
        value = scores[min(state["i"], len(scores) - 1)]
        state["i"] += 1
        return _FakeGrade(value)

    return score_fn


def _revise_fn_factory(outputs):
    """A reviser returning preset texts in order."""
    state = {"i": 0}

    def revise_fn(_text, _grade):
        value = outputs[min(state["i"], len(outputs) - 1)]
        state["i"] += 1
        return value

    return revise_fn


class LoopTests(unittest.TestCase):
    def test_already_at_target_finalizes_without_cycles(self):
        result = run_loop(
            "text", _score_fn_from_scores([95]),
            _revise_fn_factory(["changed"]),
            LoopConfig(target_fzi=90))
        self.assertEqual(result.cycles_run, 0)
        self.assertEqual(result.exit_reason, EXIT_TARGET)
        self.assertEqual(result.text, "text")
        self.assertEqual(result.final_fzi, 95)

    def test_gain_at_or_below_one_finalizes(self):
        # 50 -> 51 is a gain of exactly +1: finalize.
        result = run_loop(
            "v0", _score_fn_from_scores([50, 51]),
            _revise_fn_factory(["v1"]),
            LoopConfig(target_fzi=90, min_gain=1.0))
        self.assertEqual(result.exit_reason, EXIT_DIMINISHING)
        self.assertEqual(result.cycles_run, 1)
        self.assertEqual(result.final_fzi, 51)

    def test_gain_above_one_continues(self):
        # 50 -> 60 -> 61: first gain +10 continues, second +1 stops.
        result = run_loop(
            "v0", _score_fn_from_scores([50, 60, 61]),
            _revise_fn_factory(["v1", "v2"]),
            LoopConfig(target_fzi=90, min_gain=1.0))
        self.assertEqual(result.cycles_run, 2)
        self.assertEqual(result.exit_reason, EXIT_DIMINISHING)
        self.assertEqual(result.final_fzi, 61)

    def test_target_reached_mid_loop(self):
        result = run_loop(
            "v0", _score_fn_from_scores([50, 92]),
            _revise_fn_factory(["v1"]),
            LoopConfig(target_fzi=90, min_gain=1.0))
        self.assertEqual(result.exit_reason, EXIT_TARGET)
        self.assertEqual(result.final_fzi, 92)
        self.assertEqual(result.text, "v1")

    def test_max_cycles_caps_the_loop(self):
        scores = [50, 60, 70, 80, 85, 88]
        outputs = [f"v{i}" for i in range(1, 7)]
        result = run_loop(
            "v0", _score_fn_from_scores(scores),
            _revise_fn_factory(outputs),
            LoopConfig(target_fzi=95, min_gain=1.0, max_cycles=3))
        self.assertEqual(result.cycles_run, 3)
        self.assertEqual(result.exit_reason, EXIT_MAX_CYCLES)
        self.assertEqual(result.final_fzi, 80)

    def test_degradation_keeps_the_best_version(self):
        # 50 -> 70 -> 65: the third version is worse; keep v1.
        result = run_loop(
            "v0", _score_fn_from_scores([50, 70, 65]),
            _revise_fn_factory(["v1", "v2"]),
            LoopConfig(target_fzi=90, min_gain=1.0))
        self.assertEqual(result.exit_reason, EXIT_DEGRADED)
        self.assertEqual(result.text, "v1")
        self.assertEqual(result.final_fzi, 70)
        self.assertEqual(result.best_fzi, 70)

    def test_no_change_finalizes(self):
        result = run_loop(
            "v0", _score_fn_from_scores([50]),
            _revise_fn_factory(["v0"]),
            LoopConfig(target_fzi=90))
        self.assertEqual(result.exit_reason, EXIT_NO_CHANGE)
        self.assertEqual(result.cycles_run, 0)

    def test_history_records_every_cycle(self):
        result = run_loop(
            "v0", _score_fn_from_scores([50, 60, 61]),
            _revise_fn_factory(["v1", "v2"]),
            LoopConfig(target_fzi=90, min_gain=1.0))
        self.assertEqual(len(result.history), 2)
        self.assertEqual(result.history[0].gain, 10)
        self.assertEqual(result.history[1].gain, 1)
        self.assertEqual(result.history[0].fzi_before, 50)
        self.assertEqual(result.history[0].fzi_after, 60)


class LoopConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = LoopConfig()
        self.assertEqual(config.target_fzi, 90.0)
        self.assertEqual(config.min_gain, 1.0)
        self.assertEqual(config.max_cycles, 5)

    def test_target_clamped(self):
        self.assertEqual(LoopConfig(target_fzi=110).target_fzi, 100.0)
        self.assertEqual(LoopConfig(target_fzi=-5).target_fzi, 0.0)

    def test_max_cycles_at_least_one(self):
        self.assertEqual(LoopConfig(max_cycles=0).max_cycles, 1)


if __name__ == "__main__":
    unittest.main()
