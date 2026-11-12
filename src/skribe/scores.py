"""FZI math — the weighted composite, EVS adjustment, cap, and bands.

This module is the one place the scoring formula lives. Every scorer
(deterministic, prompt-based, Decisions) produces per-metric scores
and the FZI comes out of here, so the number means the same thing no
matter which scorer produced it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import rubric


@dataclass
class MetricScore:
    """One metric's score (0-100) plus the reasons behind it."""

    key: str
    score: float
    rationale: list = field(default_factory=list)

    @property
    def name(self):
        return rubric.DISPLAY_NAMES[self.key]

    @property
    def weight(self):
        return rubric.WEIGHTS[self.key]

    def to_dict(self):
        return {
            "metric": self.key,
            "name": self.name,
            "weight": self.weight,
            "score": round(self.score, 2),
            "rationale": list(self.rationale),
        }


@dataclass
class GradeResult:
    """The full result of grading one document."""

    fzi: float
    metrics: dict  # key -> MetricScore
    evs: float
    scorer: str
    band: str = ""
    band_action: str = ""
    citations: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def __post_init__(self):
        if not self.band:
            self.band, self.band_action = band_for(self.fzi)

    def to_dict(self):
        return {
            "fzi": round(self.fzi, 2),
            "band": self.band,
            "band_action": self.band_action,
            "scorer": self.scorer,
            "evs": self.evs,
            "citations": list(self.citations),
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "notes": list(self.notes),
        }


def clamp_score(value):
    """A metric score is always 0-100."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    return max(0.0, min(100.0, value))


def band_for(fzi):
    """The rubric's score band for an FZI value."""
    fzi = clamp_score(fzi)
    for floor, label, action in rubric.BANDS:
        if fzi >= floor:
            return label, action
    return rubric.BANDS[-1][1], rubric.BANDS[-1][2]


def compute_fzi(metric_scores, evs=1.0):
    """The FZI formula from the v3.1 controller.

    FZI = (Structure x 0.20) + (Adjusted_Accuracy x 0.20)
        + (Utility x 0.20) + (Clarity x 0.15) + (Depth x 0.15)
        + (Domain x 0.10)

    Adjusted_Accuracy = Accuracy x EVS. Final score capped at
    100.00. Missing metrics count as 0 (a scorer that cannot judge
    a metric says so in its rationale rather than leaving it out).
    Returns (fzi, adjusted_accuracy).
    """
    try:
        evs = max(0.0, min(1.0, float(evs)))
    except (TypeError, ValueError):
        evs = 1.0
    scores = {}
    for key in rubric.METRIC_KEYS:
        scores[key] = clamp_score(metric_scores.get(key, 0.0))
    adjusted_accuracy = scores["accuracy"] * evs
    fzi = (
        scores["structure"] * rubric.WEIGHTS["structure"]
        + adjusted_accuracy * rubric.WEIGHTS["accuracy"]
        + scores["utility"] * rubric.WEIGHTS["utility"]
        + scores["clarity"] * rubric.WEIGHTS["clarity"]
        + scores["depth"] * rubric.WEIGHTS["depth"]
        + scores["domain"] * rubric.WEIGHTS["domain"]
    )
    return min(rubric.FZI_CAP, round(fzi, 2)), round(adjusted_accuracy, 2)


def grade_from_metrics(metric_scores, evs=1.0, scorer="unknown",
                       rationales=None, citations=None, notes=None):
    """Build a GradeResult from raw per-metric scores (0-100)."""
    rationales = rationales or {}
    fzi, adjusted = compute_fzi(metric_scores, evs)
    metrics = {}
    for key in rubric.METRIC_KEYS:
        score = clamp_score(metric_scores.get(key, 0.0))
        rationale = list(rationales.get(key, []))
        if key == "accuracy" and evs != 1.0:
            rationale.append(
                f"Adjusted by EVS {evs}: {score:.2f} -> "
                f"{adjusted:.2f}.")
        metrics[key] = MetricScore(key=key, score=score,
                                   rationale=rationale)
    band, action = band_for(fzi)
    return GradeResult(
        fzi=fzi, metrics=metrics, evs=evs, scorer=scorer,
        band=band, band_action=action,
        citations=list(citations or []), notes=list(notes or []))
