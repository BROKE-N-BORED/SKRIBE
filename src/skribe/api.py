"""The library API — grade, polish, verify from code.

    from skribe import grade, polish, verify

    result = grade(open("guide.md").read())
    print(result.fzi, result.band)

    polished = polish(text)  # mechanical revision, deterministic
    report = verify(text)

Scorers are swappable: pass `scorer="deterministic"` (default, no
model or key), `scorer="decisions"` (needs a Gemini API key), or a
`chat` function for the prompt-based scorer. The loop is
PCA gate -> scaffold -> grade -> revise -> verify -> trace log,
following the spec's pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import decisions as decisions_mod
from . import deterministic as deterministic_mod
from . import loop as loop_mod
from . import pca as pca_mod
from . import prompt as prompt_mod
from . import revise as revise_mod
from . import scaffold as scaffold_mod
from . import verification as verify_mod
from .scores import GradeResult
from .trace import Trace


@dataclass
class PolishResult:
    """What a polish run finished with."""

    text: str
    initial_fzi: float
    final_fzi: float
    cycles_run: int
    exit_reason: str
    verification: object = None  # VerificationReport
    history: list = field(default_factory=list)
    trace: object = None  # Trace

    def to_dict(self):
        data = {
            "initial_fzi": round(self.initial_fzi, 2),
            "final_fzi": round(self.final_fzi, 2),
            "cycles_run": self.cycles_run,
            "exit_reason": self.exit_reason,
            "history": [c.to_dict() for c in self.history],
            "verification": self.verification.to_dict()
            if self.verification else None,
        }
        return data


def _make_score_fn(scorer, chat=None, api_key=None, client=None,
                   purpose=None, audience=None):
    """Build a score_fn(text) -> GradeResult for the named scorer."""
    if scorer == "deterministic" or scorer is None:
        def score_fn(text):
            return deterministic_mod.score_text(
                text, purpose=purpose, audience=audience)
        return score_fn
    if scorer == "prompt":
        if not callable(chat):
            raise ValueError(
                "prompt scorer needs a chat function")
        def score_fn(text):
            return prompt_mod.score_text(
                text, chat, purpose=purpose, audience=audience)
        return score_fn
    if scorer == "decisions":
        if client is None and not api_key:
            raise ValueError(
                "decisions scorer needs a Gemini API key")
        def score_fn(text):
            return decisions_mod.score_text(
                text, api_key, purpose=purpose, audience=audience,
                client=client)
        return score_fn
    raise ValueError(f"unknown scorer: {scorer!r} "
                     "(deterministic, prompt, decisions)")


def grade(text, scorer="deterministic", chat=None, api_key=None,
          client=None, purpose=None, audience=None, trace=None):
    """Score `text`. Returns a GradeResult (fzi, per-metric
    breakdown with rationales, band, EVS, citations, notes)."""
    trace = trace or Trace()
    trace.log("Grade requested", where="api.grade",
              how=f"scorer={scorer}",
              why="score one document against the FZI rubric")
    pca = pca_mod.check_pca(text, purpose=purpose, audience=audience)
    trace.log(f"PCA gate: {'pass' if pca.passed else 'advisory'}",
              where="api.grade", how="pca.check_pca",
              why="purpose/audience lock precedes scoring")
    score_fn = _make_score_fn(scorer, chat=chat, api_key=api_key,
                              client=client, purpose=purpose,
                              audience=audience)
    result = score_fn(text)
    if pca.passed:
        result.notes.append("PCA: pass.")
    elif pca.notes:
        result.notes.append("PCA advisory: " + "; ".join(pca.notes))
    else:
        result.notes.append(
            "PCA advisory: purpose or audience not stated.")
    trace.log(f"Graded: FZI {result.fzi:.2f} ({result.band})",
              where="api.grade", how=f"scorer={scorer}",
              why="score recorded")
    return result


def polish(text, scorer="deterministic", chat=None, api_key=None,
           client=None, reviser=None, config=None, purpose=None,
           audience=None, strict_pca=False, trace=None):
    """Grade -> revise loop. Returns a PolishResult holding the
    BEST version seen. `reviser` is any function (text, grade) ->
    new text; the default is the deterministic mechanical reviser.
    With `strict_pca`, a failed PCA gate raises ValueError instead
    of polishing."""
    trace = trace or Trace()
    trace.log("Polish requested", where="api.polish",
              how=f"scorer={scorer}",
              why="improve one document through the grade/revise loop")
    pca = pca_mod.check_pca(text, purpose=purpose, audience=audience,
                            strict=strict_pca)
    if strict_pca and not pca.passed:
        raise ValueError("PCA gate failed: "
                         + "; ".join(pca.notes))
    score_fn = _make_score_fn(scorer, chat=chat, api_key=api_key,
                              client=client, purpose=purpose,
                              audience=audience)
    revise_fn = reviser or revise_mod.revise
    result = loop_mod.run_loop(text, score_fn, revise_fn,
                               config=config, trace=trace)
    verification = verify_mod.verify_text(result.text)
    trace.log(f"Polish done: FZI {result.initial_fzi:.2f} -> "
              f"{result.final_fzi:.2f} ({result.exit_reason}); "
              f"verification {'pass' if verification.passed else 'fail'}",
              where="api.polish", how="loop + verify",
              why="final state recorded")
    return PolishResult(
        text=result.text, initial_fzi=result.initial_fzi,
        final_fzi=result.final_fzi, cycles_run=result.cycles_run,
        exit_reason=result.exit_reason, verification=verification,
        history=result.history, trace=trace)


def verify(text, trace=None):
    """Run the output-verification checks over `text`. Returns a
    VerificationReport."""
    trace = trace or Trace()
    report = verify_mod.verify_text(text)
    trace.log(f"Verification: {'pass' if report.passed else 'fail'}",
              where="api.verify", how="verify.verify_text",
              why="final file integrity before shipping")
    return report


def scaffold_check(text):
    """Check `text` against the seven-section knowledge-file
    scaffold. Returns a ScaffoldReport."""
    return scaffold_mod.check_scaffold(text)


def pca_check(text, purpose=None, audience=None, strict=False):
    """Run the PCA gate over `text`. Returns a PCASummary."""
    return pca_mod.check_pca(text, purpose=purpose,
                             audience=audience, strict=strict)
