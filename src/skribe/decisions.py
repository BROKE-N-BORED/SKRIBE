"""The Gemini Decisions API scorer.

Google's Decisions API answers closed-set questions instead of
generating text: one shared input plus typed questions, back as
calibrated probabilities in ~150-250 ms, zero output tokens. Model
gemini-decision-1, endpoint POST /v1beta/decisions on the Gemini
Developer API. Raw urllib, no SDK, no retries — a failed call
raises and the caller falls back to local grading.

This module follows the same interface shape as the Decisions
client in Code Forge (score_text / score_fzi, five rubric levels,
FZI = score x 25 over the levels) but is written standalone for
this package — it shares no code with Forge.

Two entry points:
- score_fzi(client, text): one score question, one overall FZI.
  The shape Forge's SKRIBE lane uses.
- score_metrics(client, text): one score question PER metric (six
  questions, one request, one shared input) — the full per-metric
  breakdown, with the FZI computed by the standard weighted formula
  in skribe.scores.

Free tier (Google AI Studio): 200 requests/min, 50,000 tokens/min,
10,000 requests/day. A grading pass is one request per document.
Free-tier data may be used by Google to improve its products.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import rubric
from .prompt import ScorerError
from .scores import grade_from_metrics

SCORER_NAME = "decisions"

DECISION_MODEL = "gemini-decision-1"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# The FZI rubric as Decisions levels — five, lowest first. Five
# because the API recommends 2-10 levels and five maps cleanly onto
# FZI: the weighted score runs 0-4, so FZI = score * 25, with the
# weighted average giving continuous values between the steps.
FZI_RUBRIC_LEVELS = [
    "Broken or unusable: the file does not do what it was written "
    "to do, or misses the point entirely.",
    "Weak: the file does what it was written to do only partly; "
    "major gaps, errors, or confusion remain.",
    "Adequate: the file does what it was written to do, with minor "
    "gaps or rough edges.",
    "Good: the file does what it was written to do well; clear and "
    "complete, only small polish missing.",
    "Excellent: the file does what it was written to do thoroughly "
    "and well; nothing material left to fix.",
]

FZI_QUESTION = ("Grade this file the way SKRIBE would: does it do "
                "what it was written to do, completely and "
                "correctly? Score it against the rubric levels.")

FZI_QUESTION_KEY = "skribe_fzi"

# One document's contents per request, capped so a single request
# stays near half the free tier's 50,000-token-per-minute budget
# (~4 chars per token). Documents past the cap are scored on their
# head, with the truncation named in the input itself.
MAX_INPUT_CHARS = 100_000

_USER_AGENT = "SKRIBE/0.1.0 (standalone scorer)"


def _metric_levels(metric_key):
    """Five rubric levels for one metric, lowest first."""
    name = rubric.DISPLAY_NAMES[metric_key]
    criteria = rubric.METRICS[metric_key][2]
    return [
        f"Broken on {name}: fails this outright. ({criteria})",
        f"Weak on {name}: major gaps or errors remain. ({criteria})",
        f"Adequate on {name}: meets the bar with minor gaps. "
        f"({criteria})",
        f"Good on {name}: strong, only small polish missing. "
        f"({criteria})",
        f"Excellent on {name}: thoroughly and well done. ({criteria})",
    ]


def _metric_question(metric_key):
    return (f"Score this file on {rubric.DISPLAY_NAMES[metric_key]} "
            f"only: {rubric.METRICS[metric_key][2]}")


def _truncate(text):
    content = str(text or "")
    if len(content) > MAX_INPUT_CHARS:
        content = (content[:MAX_INPUT_CHARS]
                   + "\n\n[SKRIBE NOTE: file truncated to its first "
                   f"{MAX_INPUT_CHARS} characters for scoring.]")
    return content


def _short_json(data, limit=2000):
    """A scrubbed, truncated rendering of a response body for error
    messages — enough to diagnose, never a dump."""
    try:
        text = json.dumps(data)
    except Exception:
        text = str(data)
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


class ScoreResult:
    """One scored question: the 0-100 value, plus the raw numbers
    behind it (probabilities keyed by level index as a string,
    legend mapping those indices back to their level descriptions,
    confidence 0-1, and the request's input tokens when the usage
    block carried them)."""

    def __init__(self, fzi, score, probabilities, legend, confidence,
                 input_tokens=None):
        self.fzi = fzi
        self.score = score
        self.probabilities = probabilities
        self.legend = legend
        self.confidence = confidence
        self.input_tokens = input_tokens


class DecisionsClient:
    """Minimal client for the Decisions endpoint: POST JSON, parse
    JSON, validate the answers. `urlopen` is injectable so tests
    run against a fake transport with no network."""

    def __init__(self, api_key="", urlopen=None, timeout=30,
                 base_url=None):
        self.api_key = api_key or ""
        self._urlopen = urlopen or urllib.request.urlopen
        self.timeout = timeout
        self.base_url = str(base_url or BASE_URL).rstrip("/")

    def _headers(self):
        return {"x-goog-api-key": self.api_key,
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json"}

    def _post(self, body):
        if not self.api_key:
            raise ScorerError("Decisions scorer needs a Gemini API key")
        req = urllib.request.Request(
            self.base_url + "/decisions",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(), method="POST")
        try:
            with self._urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:
                detail = ""
            raise ScorerError(
                f"Decisions API refused the request (HTTP "
                f"{exc.code}){': ' + detail if detail else ''}")
        except urllib.error.URLError as exc:
            raise ScorerError(
                f"Decisions API unreachable: {exc.reason}")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ScorerError(
                "Decisions API returned a body that is not JSON")
        if not isinstance(data, dict):
            raise ScorerError(
                "Decisions API returned a JSON value that is not "
                "an object")
        return data

    @staticmethod
    def _answer_to_result(data, question_key, level_count):
        answers = data.get("answers")
        if not isinstance(answers, dict) or question_key not in answers:
            raise ScorerError(
                "Decisions API returned no answer for the score "
                f"question '{question_key}'",
            )
        answer = answers[question_key]
        if not isinstance(answer, dict) or answer.get("type") != "score":
            raise ScorerError(
                "Decisions API returned an answer that is not a "
                "score")
        score = answer.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ScorerError(
                "Decisions API returned a score that is not a number")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict):
            probabilities = {}
        legend = answer.get("legend")
        if not isinstance(legend, dict):
            legend = {}
        confidence = answer.get("confidence")
        if isinstance(confidence, bool) or not isinstance(
                confidence, (int, float)):
            confidence = None
        # The score is the probability-weighted average of the
        # 0-based level indices; normalize by the top index (the
        # docs' own recipe) and scale to 0-100.
        value = int(round(score / (level_count - 1) * 100))
        value = max(0, min(100, value))
        usage = data.get("usage")
        input_tokens = None
        if isinstance(usage, dict):
            tokens = usage.get("total_input_tokens")
            if isinstance(tokens, int) and not isinstance(tokens, bool):
                input_tokens = tokens
        return ScoreResult(value, score, probabilities, legend,
                           confidence, input_tokens)

    def score_text(self, text, rubric_levels, question,
                   question_key="score"):
        """One Decisions request: score `text` against
        `rubric_levels` (level descriptions, lowest first). Returns
        a ScoreResult. Raises ScorerError on any API failure (HTTP
        refusal, bad JSON, missing or malformed answer); ValueError
        on a bad rubric (a programming error, not an API failure).
        No retries — the caller falls back to local grading."""
        levels = [str(level).strip() for level in (rubric_levels or [])]
        if len(levels) < 2:
            raise ValueError(
                "a score question needs at least 2 rubric levels")
        if any(not level for level in levels):
            raise ValueError(
                "rubric levels must be non-empty descriptions")
        body = {
            "model": DECISION_MODEL,
            "input": str(text or ""),
            "questions": {
                question_key: {
                    "type": "score",
                    "instructions": str(question),
                    "criteria": levels,
                },
            },
        }
        data = self._post(body)
        return self._answer_to_result(data, question_key, len(levels))

    def score_questions(self, text, questions):
        """One Decisions request with several score questions:
        `questions` maps a key to (rubric_levels, question). Returns
        {key: ScoreResult}. One request, one shared input."""
        body_questions = {}
        counts = {}
        for key, (levels, question) in questions.items():
            cleaned = [str(level).strip() for level in (levels or [])]
            if len(cleaned) < 2 or any(not level for level in cleaned):
                raise ValueError(
                    f"question '{key}' needs at least 2 non-empty "
                    "rubric levels")
            body_questions[key] = {
                "type": "score",
                "instructions": str(question),
                "criteria": cleaned,
            }
            counts[key] = len(cleaned)
        body = {
            "model": DECISION_MODEL,
            "input": str(text or ""),
            "questions": body_questions,
        }
        data = self._post(body)
        return {key: self._answer_to_result(data, key, counts[key])
                for key in questions}


def score_fzi(client, text):
    """One document's overall FZI through a Decisions client: the
    document's text against the FZI rubric. The single-question
    shape Forge's SKRIBE lane uses."""
    return client.score_text(_truncate(text), FZI_RUBRIC_LEVELS,
                             FZI_QUESTION, FZI_QUESTION_KEY)


def score_metrics(client, text, purpose=None):
    """Grade `text` with one score question per metric (six
    questions, one request). Returns a GradeResult with the full
    per-metric breakdown and the FZI from the standard weighted
    formula. EVS is 0.8 (no sources checked — the Decisions scorer
    judges the text, it does not browse), unless the caller passes
    a purpose, which is folded into the input."""
    content = _truncate(text)
    if purpose:
        content = (f"Stated purpose of this document: {purpose}\n\n"
                   + content)
    questions = {key: (_metric_levels(key), _metric_question(key))
                 for key in rubric.METRIC_KEYS}
    results = client.score_questions(content, questions)
    scores = {key: results[key].fzi for key in rubric.METRIC_KEYS}
    rationales = {}
    for key in rubric.METRIC_KEYS:
        result = results[key]
        reason = f"Decisions score {result.score:.2f}/4"
        if result.confidence is not None:
            reason += f", confidence {result.confidence:.2f}"
        rationales[key] = [reason + "."]
    return grade_from_metrics(
        scores, evs=rubric.EVS_NO_SOURCES, scorer=SCORER_NAME,
        rationales=rationales,
        notes=["Scored by the Decisions API (one score question "
               "per metric). EVS 0.8: no sources were checked."])


def score_text(text, api_key, purpose=None, audience=None, client=None):
    """Grade `text` with the Decisions scorer. `api_key` is the
    Gemini API key; pass a prebuilt `client` to reuse one (tests
    pass a client on a fake transport)."""
    client = client or DecisionsClient(api_key=api_key)
    result = score_metrics(client, text, purpose)
    if audience:
        result.notes.append(f"Audience: {audience}.")
    return result
