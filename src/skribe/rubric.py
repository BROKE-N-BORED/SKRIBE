"""The FZI rubric — the six weighted metrics from the FZI Scoring
Engine Controller v3.1, aligned with the Content Quality Metrics
Rubric v3.2.0-ALPHA.

Note on the spec set: the older FCI Scoring Index describes a
five-metric scheme (Peak Performance 30%, Quality 25%, Accuracy
25%, Efficiency 10%, Detail 10%). The v3.1 controller (2025-11-08)
supersedes it with the six-metric scheme below, which is what this
tool implements. The score bands (95-100 Zenith, 90-94 Superior,
80-89 Strong, 70-79 Acceptable, below 70 Rejected) are the same in
both documents.
"""
from __future__ import annotations

# Metric key -> (display name, weight, what it measures).
# Weights sum to 1.0; the FZI controller's formula is a straight
# weighted sum, capped at 100.00.
METRICS = {
    "structure": (
        "Structure & Organization",
        0.20,
        "Metadata completeness and correct formatting; modular "
        "layout and logical section separation; explicitly defined "
        "core components; strict heading hierarchy.",
    ),
    "accuracy": (
        "Accuracy & Factual Integrity",
        0.20,
        "No false, speculative, or unverifiable claims; definitions "
        "contextually and semantically correct; logical consistency "
        "and internal coherence; the file truthfully represents its "
        "declared domain and purpose.",
    ),
    "utility": (
        "Usefulness & Utility",
        0.20,
        "Functionally complete and executable without "
        "clarification; deterministic and robust output; supports "
        "automation and high-reliability workflows.",
    ),
    "clarity": (
        "Clarity & Readability",
        0.15,
        "Clear, unambiguous phrasing; terminology appropriate to "
        "the audience level; consistent formatting for legibility.",
    ),
    "depth": (
        "Depth & Specificity",
        0.15,
        "Includes fallback logic and edge-case coverage; all "
        "abstractions reduced to operational detail; comprehensive "
        "and literal explanations.",
    ),
    "domain": (
        "Domain Alignment",
        0.10,
        "Content adheres strictly to its objective; no topic drift "
        "or irrelevant material; terminology consistent with the "
        "domain lexicon.",
    ),
}

METRIC_KEYS = tuple(METRICS.keys())

WEIGHTS = {key: METRICS[key][1] for key in METRIC_KEYS}

DISPLAY_NAMES = {key: METRICS[key][0] for key in METRIC_KEYS}

# FZI score bands, from the rubric / FCI index. (floor, label, action)
BANDS = (
    (95, "Zenith Excellence", "Deploy immediately."),
    (90, "Superior Quality", "Publish-ready."),
    (80, "Strong Performance", "Publish with minor fixes."),
    (70, "Acceptable Standard", "Requires revisions."),
    (0, "Rejected", "Major revisions required."),
)

# External Verifiability Score (EVS) — the web-validation extension
# from the v3.1 controller. Adjusted_Accuracy = Accuracy x EVS.
EVS_VERIFIED = 1.0       # verified match with >= 3 sources
EVS_PARTIAL = 0.9        # 1-2 sources found (implementation choice:
                         # the spec names only 0.8 / 0.5 / 1.0; a
                         # couple of sources sits between "none" and
                         # "verified match")
EVS_NO_SOURCES = 0.8     # no valid sources found
EVS_CONTRADICTION = 0.5  # verified contradiction detected

FZI_CAP = 100.0
