"""Tests for the Decisions scorer — fake transport only, no network.

The fake urlopen returns canned Decisions API responses, so these
tests prove the request shape, the score mapping, and the error
handling without ever touching the network.
"""
import json
import unittest
import urllib.error

from skribe import decisions as dec
from skribe import rubric
from skribe.prompt import ScorerError


class FakeResponse:
    def __init__(self, payload):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self._raw = payload.encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _score_answer(score, key="score"):
    return {
        "type": "score",
        "score": score,
        "legend": {"0": "Broken", "1": "Weak", "2": "Adequate",
                   "3": "Good", "4": "Excellent"},
        "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0,
                          "3": 0.0, "4": 1.0},
        "confidence": 0.9,
    }


def _fake_urlopen_factory(payload, capture=None):
    def fake_urlopen(request, timeout=None):
        if capture is not None:
            capture["url"] = request.full_url
            capture["method"] = request.get_method()
            capture["headers"] = dict(request.header_items())
            capture["body"] = json.loads(
                request.data.decode("utf-8"))
        return FakeResponse(payload)
    return fake_urlopen


class ScoreMappingTests(unittest.TestCase):
    def _client_for_score(self, score):
        payload = {"answers": {"score": _score_answer(score)},
                   "usage": {"total_input_tokens": 123}}
        return dec.DecisionsClient(
            api_key="test-key",
            urlopen=_fake_urlopen_factory(payload))

    def test_score_zero_maps_to_fzi_zero(self):
        result = self._client_for_score(0).score_text(
            "text", dec.FZI_RUBRIC_LEVELS, "q")
        self.assertEqual(result.fzi, 0)

    def test_score_four_maps_to_fzi_100(self):
        result = self._client_for_score(4).score_text(
            "text", dec.FZI_RUBRIC_LEVELS, "q")
        self.assertEqual(result.fzi, 100)

    def test_score_two_maps_to_fzi_50(self):
        result = self._client_for_score(2).score_text(
            "text", dec.FZI_RUBRIC_LEVELS, "q")
        self.assertEqual(result.fzi, 50)

    def test_fractional_score_maps_continuously(self):
        # 3.5 / 4 * 100 = 87.5 -> 88 (round-half-even: 87.5 -> 88).
        result = self._client_for_score(3.5).score_text(
            "text", dec.FZI_RUBRIC_LEVELS, "q")
        self.assertEqual(result.fzi, 88)

    def test_probabilities_legend_confidence_tokens_kept(self):
        result = self._client_for_score(4).score_text(
            "text", dec.FZI_RUBRIC_LEVELS, "q")
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.input_tokens, 123)
        self.assertEqual(result.legend["4"], "Excellent")
        self.assertEqual(result.probabilities["4"], 1.0)


class RequestShapeTests(unittest.TestCase):
    def test_request_shape(self):
        capture = {}
        payload = {"answers": {"skribe_fzi": _score_answer(3)}}
        client = dec.DecisionsClient(
            api_key="secret-key",
            urlopen=_fake_urlopen_factory(payload, capture))
        dec.score_fzi(client, "hello document")
        self.assertEqual(
            capture["url"],
            "https://generativelanguage.googleapis.com/v1beta/decisions")
        self.assertEqual(capture["method"], "POST")
        self.assertEqual(capture["headers"]["X-goog-api-key"],
                         "secret-key")
        body = capture["body"]
        self.assertEqual(body["model"], "gemini-decision-1")
        self.assertEqual(body["input"], "hello document")
        question = body["questions"]["skribe_fzi"]
        self.assertEqual(question["type"], "score")
        self.assertEqual(len(question["criteria"]), 5)
        self.assertIn("SKRIBE", question["instructions"])

    def test_long_input_truncated_with_note(self):
        capture = {}
        payload = {"answers": {"skribe_fzi": _score_answer(3)}}
        client = dec.DecisionsClient(
            api_key="k", urlopen=_fake_urlopen_factory(payload, capture))
        dec.score_fzi(client, "x" * 150_000)
        sent = capture["body"]["input"]
        self.assertLess(len(sent), 150_000)
        self.assertIn("truncated", sent)
        self.assertTrue(sent.startswith("x" * 100))

    def test_missing_key_raises(self):
        client = dec.DecisionsClient(
            api_key="", urlopen=_fake_urlopen_factory({}))
        with self.assertRaises(ScorerError):
            client.score_text("t", dec.FZI_RUBRIC_LEVELS, "q")


class ErrorHandlingTests(unittest.TestCase):
    def _client(self, payload):
        return dec.DecisionsClient(
            api_key="k", urlopen=_fake_urlopen_factory(payload))

    def test_missing_answer_raises(self):
        with self.assertRaises(ScorerError):
            self._client({"answers": {}}).score_text(
                "t", dec.FZI_RUBRIC_LEVELS, "q")

    def test_non_score_answer_raises(self):
        payload = {"answers": {"score": {"type": "choice",
                                         "choice": "a"}}}
        with self.assertRaises(ScorerError):
            self._client(payload).score_text(
                "t", dec.FZI_RUBRIC_LEVELS, "q")

    def test_non_numeric_score_raises(self):
        payload = {"answers": {"score": {"type": "score",
                                         "score": "high"}}}
        with self.assertRaises(ScorerError):
            self._client(payload).score_text(
                "t", dec.FZI_RUBRIC_LEVELS, "q")

    def test_non_json_body_raises(self):
        client = dec.DecisionsClient(
            api_key="k",
            urlopen=_fake_urlopen_factory("not json at all"))
        with self.assertRaises(ScorerError):
            client.score_text("t", dec.FZI_RUBRIC_LEVELS, "q")

    def test_http_error_raises_scorer_error(self):
        def failing_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", {}, None)

        client = dec.DecisionsClient(api_key="k",
                                     urlopen=failing_urlopen)
        with self.assertRaises(ScorerError) as ctx:
            client.score_text("t", dec.FZI_RUBRIC_LEVELS, "q")
        self.assertIn("429", str(ctx.exception))

    def test_bad_rubric_raises_value_error(self):
        client = self._client({})
        with self.assertRaises(ValueError):
            client.score_text("t", ["only one"], "q")
        with self.assertRaises(ValueError):
            client.score_text("t", ["ok", "  "], "q")


class ScoreMetricsTests(unittest.TestCase):
    def test_six_questions_one_request(self):
        capture = {}
        answers = {key: _score_answer(3) for key in rubric.METRIC_KEYS}
        payload = {"answers": answers}
        client = dec.DecisionsClient(
            api_key="k", urlopen=_fake_urlopen_factory(payload, capture))
        result = dec.score_metrics(client, "some document")
        # Six questions sent in one request.
        self.assertEqual(len(capture["body"]["questions"]), 6)
        self.assertEqual(set(capture["body"]["questions"]),
                         set(rubric.METRIC_KEYS))
        # Each metric scored 3/4 = 75; EVS 0.8 pulls accuracy to 60:
        # FZI = 75*.2 + 60*.2 + 75*.2 + 75*.15 + 75*.15 + 75*.1 = 72.
        self.assertEqual(result.fzi, 72.0)
        self.assertEqual(result.scorer, "decisions")
        self.assertEqual(result.metrics["structure"].score, 75)
        self.assertEqual(result.evs, 0.8)


if __name__ == "__main__":
    unittest.main()
