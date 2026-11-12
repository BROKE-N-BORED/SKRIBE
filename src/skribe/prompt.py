"""The prompt-based scorer — grade with any chat model.

The caller supplies a `chat` function (prompt -> reply text): an
Ollama call, a provider call, a local model, anything. SKRIBE sends
one structured prompt asking for per-metric scores as JSON, parses
the reply, and runs the same FZI math as every other scorer.

The reply must be a JSON object with a `metrics` object keyed by
the six metric names (structure, accuracy, utility, clarity,
depth, domain), each 0-100, plus optional `rationale` strings and
an optional `evs` (0-1). A code fence around the JSON is fine.
Anything unparseable raises ScorerError — the caller decides
whether to fall back to the deterministic scorer.
"""
from __future__ import annotations

import json
import re

from . import rubric
from .scores import grade_from_metrics

SCORER_NAME = "prompt"

PROMPT_TEMPLATE = """Grade the document below against the SKRIBE rubric. Score each
metric 0-100 and give one short reason per metric.

Metrics:
- structure: Structure & Organization (20%) — {structure}
- accuracy: Accuracy & Factual Integrity (20%) — {accuracy}
- utility: Usefulness & Utility (20%) — {utility}
- clarity: Clarity & Readability (15%) — {clarity}
- depth: Depth & Specificity (15%) — {depth}
- domain: Domain Alignment (10%) — {domain}

Also give an `evs` (External Verifiability Score, 0-1): 1.0 if the
document's factual claims check out against 3 or more sources you
know, 0.8 if no sources are cited or checkable, 0.5 if you spot a
contradiction with known facts.

Reply with ONLY a JSON object, no other text:
{{"metrics": {{"structure": 0, "accuracy": 0, "utility": 0, "clarity": 0, "depth": 0, "domain": 0}}, "rationale": {{"structure": "...", "accuracy": "...", "utility": "...", "clarity": "...", "depth": "...", "domain": "..."}}, "evs": 0.8}}

Document:
---
{document}
---
"""


class ScorerError(Exception):
    """The scorer could not produce a grade."""


def build_prompt(text, purpose=None):
    criteria = {key: rubric.METRICS[key][2] for key in rubric.METRIC_KEYS}
    document = text or ""
    if purpose:
        document = (f"Stated purpose of this document: {purpose}\n\n"
                    + document)
    return PROMPT_TEMPLATE.format(document=document, **criteria)


def _extract_json(reply):
    text = (reply or "").strip()
    if not text:
        raise ScorerError("empty reply from the model")
    # Prefer a fenced JSON block; otherwise the whole reply.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text,
                       re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else text
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # Last resort: the first {...} span in the reply.
        span = re.search(r"\{.*\}", text, re.DOTALL)
        if not span:
            raise ScorerError(
                "the model did not return a JSON object")
        try:
            data = json.loads(span.group(0))
        except json.JSONDecodeError as exc:
            raise ScorerError(
                f"the model's JSON could not be parsed: {exc}")
    if not isinstance(data, dict):
        raise ScorerError("the model's reply was not a JSON object")
    return data


def parse_reply(reply):
    """Parse a model's grading reply into (scores, rationales, evs)."""
    data = _extract_json(reply)
    raw_metrics = data.get("metrics")
    if not isinstance(raw_metrics, dict):
        raise ScorerError("the model's reply has no 'metrics' object")
    scores = {}
    for key in rubric.METRIC_KEYS:
        value = raw_metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ScorerError(
                f"the model's reply has no numeric score for "
                f"'{key}'")
        scores[key] = max(0.0, min(100.0, float(value)))
    raw_rationale = data.get("rationale") or {}
    rationales = {}
    for key in rubric.METRIC_KEYS:
        reason = raw_rationale.get(key) if isinstance(raw_rationale, dict) else None
        rationales[key] = [str(reason)] if reason else []
    evs = data.get("evs", rubric.EVS_NO_SOURCES)
    if isinstance(evs, bool) or not isinstance(evs, (int, float)):
        evs = rubric.EVS_NO_SOURCES
    evs = max(0.0, min(1.0, float(evs)))
    return scores, rationales, evs


def score_text(text, chat, purpose=None, audience=None):
    """Grade `text` by asking a chat function.

    `chat` is any callable taking a prompt string and returning the
    model's reply text. Raises ScorerError on a bad reply.
    """
    if not callable(chat):
        raise ScorerError("prompt scorer needs a chat function")
    prompt = build_prompt(text, purpose)
    reply = chat(prompt)
    scores, rationales, evs = parse_reply(reply)
    notes = ["Scored by a chat model through the prompt interface."]
    if audience:
        notes.append(f"Audience: {audience}.")
    return grade_from_metrics(
        scores, evs=evs, scorer=SCORER_NAME, rationales=rationales,
        notes=notes)
