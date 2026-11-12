"""SKRIBE — score and polish written work with the FZI rubric.

    from skribe import grade, polish, verify

    result = grade(text)          # GradeResult: fzi, metrics, band
    polished = polish(text)       # PolishResult: best text + scores
    report = verify(text)         # VerificationReport: pass/fail checks

The built-in deterministic scorer needs no model and no key. Swap
scorers with grade(..., scorer="decisions", api_key=...) or pass a
chat function for the prompt-based scorer.
"""
from __future__ import annotations

from .api import grade, pca_check, polish, scaffold_check, verify
from .loop import LoopConfig
from .scores import GradeResult
from .trace import Trace

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "grade",
    "polish",
    "verify",
    "pca_check",
    "scaffold_check",
    "LoopConfig",
    "GradeResult",
    "Trace",
]
