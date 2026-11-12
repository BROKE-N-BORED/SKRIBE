"""Tests for the prompt-based scorer (fake chat functions)."""
import json
import unittest

from skribe import prompt as prompt_mod
from skribe.prompt import ScorerError


def _reply(scores=None, evs=0.9, rationale=None):
    scores = scores or {k: 80 for k in
                        ("structure", "accuracy", "utility",
                         "clarity", "depth", "domain")}
    return json.dumps({"metrics": scores, "evs": evs,
                       "rationale": rationale or {}})


class ParseReplyTests(unittest.TestCase):
    def test_plain_json_parses(self):
        scores, _, evs = prompt_mod.parse_reply(_reply())
        self.assertEqual(scores["structure"], 80)
        self.assertEqual(evs, 0.9)

    def test_fenced_json_parses(self):
        reply = "Here is the grade:\n```json\n" + _reply() + "\n```"
        scores, _, _ = prompt_mod.parse_reply(reply)
        self.assertEqual(scores["depth"], 80)

    def test_scores_clamped(self):
        reply = _reply(scores={k: 500 for k in
                               ("structure", "accuracy", "utility",
                                "clarity", "depth", "domain")})
        scores, _, _ = prompt_mod.parse_reply(reply)
        self.assertEqual(scores["structure"], 100.0)

    def test_missing_metric_raises(self):
        reply = json.dumps({"metrics": {"structure": 80}})
        with self.assertRaises(ScorerError):
            prompt_mod.parse_reply(reply)

    def test_non_numeric_score_raises(self):
        reply = json.dumps({"metrics": {
            k: ("high" if k == "structure" else 80)
            for k in ("structure", "accuracy", "utility",
                      "clarity", "depth", "domain")}})
        with self.assertRaises(ScorerError):
            prompt_mod.parse_reply(reply)

    def test_gibberish_raises(self):
        with self.assertRaises(ScorerError):
            prompt_mod.parse_reply("I really liked this document!")
        with self.assertRaises(ScorerError):
            prompt_mod.parse_reply("")

    def test_evs_defaults_to_08_when_absent(self):
        reply = json.dumps({"metrics": {k: 80 for k in
                                        ("structure", "accuracy",
                                         "utility", "clarity", "depth",
                                         "domain")}})
        _, _, evs = prompt_mod.parse_reply(reply)
        self.assertEqual(evs, 0.8)


class ScoreTextTests(unittest.TestCase):
    def test_fake_chat_grades(self):
        def chat(prompt):
            self.assertIn("SKRIBE rubric", prompt)
            self.assertIn("grade me", prompt)
            return _reply()
        result = prompt_mod.score_text("grade me", chat)
        self.assertEqual(result.scorer, "prompt")
        # All 80s, EVS 0.9: accuracy 72; FZI = 16+14.4+16+12+12+8 = 78.4
        self.assertEqual(result.fzi, 78.4)

    def test_purpose_folded_into_prompt(self):
        seen = {}

        def chat(prompt):
            seen["prompt"] = prompt
            return _reply()
        prompt_mod.score_text("text", chat, purpose="teach backups")
        self.assertIn("teach backups", seen["prompt"])

    def test_non_callable_chat_raises(self):
        with self.assertRaises(ScorerError):
            prompt_mod.score_text("text", None)


if __name__ == "__main__":
    unittest.main()
