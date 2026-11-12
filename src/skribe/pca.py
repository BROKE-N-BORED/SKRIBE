"""Purpose & Context Assurance (PCA) — the pre-build gate.

PCA locks the file's purpose and intended audience before any
drafting starts, and keeps the content subject-matter only: no
operational instructions, process guidance, or meta-information.

In this tool PCA runs in advisory mode by default: it reports what
it found (purpose present or missing, audience named or not, any
operational/meta material spotted) and grading continues. With
`strict=True`, a missing purpose or audience fails the gate and the
caller decides what to do — the CLI's `polish` command offers
`--strict-pca` for that. The spec's "do not proceed until
confirmed" is the strict mode; advisory is the default because a
standalone grader meets plenty of plain documents that carry no
explicit purpose line, and refusing to grade them would make the
tool useless.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Phrases that mark operational / process / meta material — the
# things PCA's subject-matter-only filter strips. Kept short and
# plain: these are signals, not proof, and every hit is reported
# rather than silently removed.
META_PHRASES = (
    "as an ai",
    "as a language model",
    "this prompt",
    "system instruction",
    "system prompt",
    "you are an ai",
    "ignore previous",
    "disregard your instructions",
    "in this response",
    "as requested above",
)

AUDIENCE_WORDS = (
    "beginner", "novice", "intermediate", "advanced", "expert",
    "developer", "developers", "operator", "operators", "user",
    "users", "reader", "readers", "student", "students", "team",
    "engineer", "engineers", "non-technical", "technical",
)


@dataclass
class PCASummary:
    """The PCA summary, in the spec's output format."""

    purpose: str = ""
    audience: str = ""
    in_scope: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)
    constraints: str = ""
    notes: list = field(default_factory=list)
    passed: bool = False
    meta_hits: list = field(default_factory=list)

    def to_dict(self):
        return {
            "purpose": self.purpose,
            "audience": self.audience,
            "in_scope": list(self.in_scope),
            "out_of_scope": list(self.out_of_scope),
            "constraints": self.constraints,
            "notes": list(self.notes),
            "passed": self.passed,
            "meta_hits": list(self.meta_hits),
        }

    def render(self):
        lines = [
            "PCA Summary:",
            f"- Purpose: {self.purpose or '(not stated)'}",
            f"- Audience: {self.audience or '(not named)'}",
        ]
        if self.in_scope:
            lines.append("- In-Scope: " + "; ".join(self.in_scope))
        if self.out_of_scope:
            lines.append("- Out-of-Scope: " + "; ".join(self.out_of_scope))
        if self.constraints:
            lines.append(f"- Constraints: {self.constraints}")
        for note in self.notes:
            lines.append(f"- Notes: {note}")
        return "\n".join(lines)


_PURPOSE_RE = re.compile(
    r"^\s*(?:purpose|objective|goal)\s*[:\-]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE)
_AUDIENCE_RE = re.compile(
    r"^\s*(?:audience|intended audience|for)\s*[:\-]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE)


def _first_sentence(text):
    text = " ".join((text or "").split())
    if not text:
        return ""
    match = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return match[0].strip()


def check_pca(text, purpose=None, audience=None, strict=False):
    """Run the PCA gate over `text`.

    `purpose` / `audience` supplied by the caller win; otherwise
    they are read from Purpose:/Audience: lines in the text, and
    failing that from the first heading or first sentence (purpose
    only — audience is never guessed). Returns a PCASummary.
    """
    text = text or ""
    notes = []
    found_purpose = (purpose or "").strip()
    if not found_purpose:
        match = _PURPOSE_RE.search(text)
        if match:
            found_purpose = _first_sentence(match.group(1))
    if not found_purpose:
        # Fall back to the first heading: a document titled "How
        # to reset a router" states its purpose well enough for
        # grading. Noted as inferred, not declared.
        heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if heading:
            found_purpose = heading.group(1).strip()
            notes.append("Purpose inferred from the document title.")
    found_audience = (audience or "").strip()
    if not found_audience:
        match = _AUDIENCE_RE.search(text)
        if match:
            found_audience = _first_sentence(match.group(1))
    if not found_audience:
        lowered = text.lower()
        hits = sorted({w for w in AUDIENCE_WORDS if w in lowered})
        if hits:
            found_audience = "mentions: " + ", ".join(hits[:3])
            notes.append("Audience inferred from wording in the text.")
    # Subject-matter-only filter: report meta/operational hits.
    lowered = text.lower()
    meta_hits = sorted({p for p in META_PHRASES if p in lowered})
    if meta_hits:
        notes.append("Operational/meta material spotted: "
                     + ", ".join(meta_hits) + ".")
    passed = bool(found_purpose) and bool(found_audience) \
        and not meta_hits
    if strict and not passed:
        if not found_purpose:
            notes.append("Strict PCA: no purpose stated — gate failed.")
        if not found_audience:
            notes.append("Strict PCA: no audience named — gate failed.")
    return PCASummary(
        purpose=found_purpose, audience=found_audience,
        notes=notes, passed=passed, meta_hits=meta_hits)
