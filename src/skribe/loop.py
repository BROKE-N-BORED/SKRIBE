"""Recursion control + flow control — the polish loop.

The spec's loop (Recursion_Control_Logic + FlowControl_Override):
score, enhance while the score is below target, finalize when the
score stops improving or an enhancement would degrade it. Two
things in the spec need reconciling for a real tool:

1. The spec loops "while FZI < 110" — but FZI is capped at 100, so
   110 is unreachable and the loop would never end on its own. The
   110 is an overshoot: "keep going until it cannot get better."
   This tool replaces it with a configurable target (default 90,
   the floor of the Superior Quality / publish-ready band) plus
   the gain and cycle caps below.
2. The spec's own stop rules are the real exit: "gain <= +1 ->
   finalize" and "score drops -> finalize". Those are kept exactly,
   plus a max-cycles cap so a stubborn document cannot loop
   forever.

Flow-control separation (from FlowControl_Override): the scorer
only scores, the reviser only revises, and THIS module makes every
loop/finalize decision. No other module finalizes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_TARGET_FZI = 90.0
DEFAULT_MIN_GAIN = 1.0
DEFAULT_MAX_CYCLES = 5

EXIT_TARGET = "target reached"
EXIT_DIMINISHING = "diminishing returns (gain <= +1)"
EXIT_DEGRADED = "revision degraded the score — kept the best version"
EXIT_MAX_CYCLES = "max cycles reached"
EXIT_NO_CHANGE = "revision changed nothing"


@dataclass
class LoopConfig:
    """The loop's caps, all overridable by the caller."""

    target_fzi: float = DEFAULT_TARGET_FZI
    min_gain: float = DEFAULT_MIN_GAIN
    max_cycles: int = DEFAULT_MAX_CYCLES

    def __post_init__(self):
        self.target_fzi = max(0.0, min(100.0, float(self.target_fzi)))
        self.min_gain = max(0.0, float(self.min_gain))
        self.max_cycles = max(1, int(self.max_cycles))


@dataclass
class CycleRecord:
    cycle: int
    fzi_before: float
    fzi_after: float
    gain: float
    decision: str

    def to_dict(self):
        return {
            "cycle": self.cycle,
            "fzi_before": round(self.fzi_before, 2),
            "fzi_after": round(self.fzi_after, 2),
            "gain": round(self.gain, 2),
            "decision": self.decision,
        }


@dataclass
class LoopResult:
    """What the loop finished with."""

    text: str
    initial_fzi: float
    final_fzi: float
    cycles_run: int
    exit_reason: str
    history: list = field(default_factory=list)  # CycleRecord
    best_fzi: float = 0.0

    def to_dict(self):
        return {
            "initial_fzi": round(self.initial_fzi, 2),
            "final_fzi": round(self.final_fzi, 2),
            "best_fzi": round(self.best_fzi, 2),
            "cycles_run": self.cycles_run,
            "exit_reason": self.exit_reason,
            "history": [c.to_dict() for c in self.history],
        }


def run_loop(text, score_fn, revise_fn, config=None, trace=None):
    """Run the grade -> revise loop.

    `score_fn(text)` returns a GradeResult (or anything with an
    `.fzi` attribute). `revise_fn(text, grade)` returns revised
    text. Returns a LoopResult holding the BEST version seen — a
    degrading revision never ships.
    """
    config = config or LoopConfig()
    first = score_fn(text)
    initial_fzi = first.fzi
    best_text = text
    best_fzi = initial_fzi
    current_text = text
    current_fzi = initial_fzi
    last_grade = first
    history = []
    if trace is not None:
        trace.log(f"Initial score: FZI {initial_fzi:.2f}",
                  where="loop", how="score_fn",
                  why="baseline before any revision")
    if initial_fzi >= config.target_fzi:
        return LoopResult(
            text=text, initial_fzi=initial_fzi, final_fzi=initial_fzi,
            cycles_run=0, exit_reason=EXIT_TARGET, history=history,
            best_fzi=initial_fzi)
    exit_reason = EXIT_MAX_CYCLES
    for cycle in range(1, config.max_cycles + 1):
        revised = revise_fn(current_text, last_grade)
        if revised == current_text:
            exit_reason = EXIT_NO_CHANGE
            if trace is not None:
                trace.log(f"Cycle {cycle}: revision changed nothing",
                          where="loop", how="revise_fn",
                          why="no further mechanical improvement")
            break
        grade = score_fn(revised)
        gain = grade.fzi - current_fzi
        if grade.fzi < current_fzi:
            # Degradation: keep the best version, finalize.
            record = CycleRecord(cycle, current_fzi, grade.fzi, gain,
                                 EXIT_DEGRADED)
            history.append(record)
            exit_reason = EXIT_DEGRADED
            if trace is not None:
                trace.log(
                    f"Cycle {cycle}: FZI {current_fzi:.2f} -> "
                    f"{grade.fzi:.2f} (gain {gain:+.2f}) — degraded",
                    where="loop", how="score_fn",
                    why="revision lowered the score; best kept")
            break
        record = CycleRecord(cycle, current_fzi, grade.fzi, gain, "")
        if grade.fzi > best_fzi:
            best_fzi = grade.fzi
            best_text = revised
        current_text = revised
        current_fzi = grade.fzi
        last_grade = grade
        if grade.fzi >= config.target_fzi:
            record.decision = EXIT_TARGET
            exit_reason = EXIT_TARGET
        elif gain <= config.min_gain:
            record.decision = EXIT_DIMINISHING
            exit_reason = EXIT_DIMINISHING
        else:
            record.decision = "continue"
        history.append(record)
        if trace is not None:
            trace.log(
                f"Cycle {cycle}: FZI {record.fzi_before:.2f} -> "
                f"{record.fzi_after:.2f} (gain {gain:+.2f}) — "
                f"{record.decision}",
                where="loop", how="score_fn + revise_fn",
                why="loop decision per the flow-control rules")
        if record.decision != "continue":
            break
    return LoopResult(
        text=best_text, initial_fzi=initial_fzi,
        final_fzi=best_fzi, cycles_run=len(history),
        exit_reason=exit_reason, history=history, best_fzi=best_fzi)
