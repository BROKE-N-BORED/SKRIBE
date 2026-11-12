"""Knowledge File Structure — the universal scaffold from
KnowledgeFileStructure v1.1.

Every knowledge file follows seven sections, in order: METADATA,
CONTEXT, CORE CONTENT, IMPLEMENTATION, TESTS AND VERIFICATION,
LINKS AND REFERENCES, REVISION HISTORY. This module checks a
document against that scaffold: which sections are present, whether
they appear in order, and what is missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Section key -> heading patterns that count as that section.
# Matching is deliberately loose: a heading that names the section
# (or a close synonym) counts, whatever its level.
SECTIONS = (
    ("metadata", ("metadata", "meta data", "file info", "document info")),
    ("context", ("context", "purpose", "objective", "overview", "about")),
    ("core", ("core content", "content", "definitions", "concepts",
              "core concepts", "background")),
    ("implementation", ("implementation", "instructions", "usage",
                        "how to", "procedure", "procedures", "method",
                        "methods", "guide")),
    ("tests", ("tests", "test", "verification", "validation",
               "testing", "test cases")),
    ("references", ("references", "links", "sources", "citations",
                    "further reading", "see also")),
    ("history", ("revision history", "history", "changelog",
                 "change log", "revisions")),
)

SECTION_NAMES = {
    "metadata": "Metadata",
    "context": "Context",
    "core": "Core Content",
    "implementation": "Implementation",
    "tests": "Tests and Verification",
    "references": "Links and References",
    "history": "Revision History",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class ScaffoldReport:
    """What the scaffold check found."""

    present: list  # section keys found, in document order
    missing: list  # section keys not found
    in_order: bool
    headings: list = field(default_factory=list)  # (level, text)
    notes: list = field(default_factory=list)

    @property
    def coverage(self):
        """Fraction of scaffold sections present (0.0-1.0)."""
        return len(self.present) / len(SECTIONS)

    def to_dict(self):
        return {
            "present": [SECTION_NAMES[k] for k in self.present],
            "missing": [SECTION_NAMES[k] for k in self.missing],
            "in_order": self.in_order,
            "coverage": round(self.coverage, 2),
            "notes": list(self.notes),
        }


def extract_headings(text):
    """(level, text) for every ATX heading in the document."""
    return [(len(m.group(1)), m.group(2).strip())
            for m in _HEADING_RE.finditer(text or "")]


def _match_section(heading_text):
    lowered = heading_text.strip().lower()
    for key, patterns in SECTIONS:
        for pattern in patterns:
            # Exact, leading, or "before a colon" match:
            # "Tests and Verification" hits "tests", "Core
            # Content" hits "core content", "Metadata:" hits
            # "metadata".
            if (lowered == pattern
                    or lowered.startswith(pattern + " ")
                    or pattern in lowered.split(":")[0]):
                return key
    return None


def check_scaffold(text):
    """Check `text` against the seven-section scaffold."""
    headings = extract_headings(text)
    found = []  # (section key, heading index)
    seen = set()
    for index, (_level, heading) in enumerate(headings):
        key = _match_section(heading)
        if key and key not in seen:
            seen.add(key)
            found.append((key, index))
    order = [key for key, _ in SECTIONS]
    present = [key for key, _ in found]
    missing = [key for key in order if key not in seen]
    # In order: the found sections appear in scaffold order.
    positions = [order.index(key) for key in present]
    in_order = positions == sorted(positions)
    notes = []
    if missing:
        names = ", ".join(SECTION_NAMES[k] for k in missing)
        notes.append(f"Missing scaffold sections: {names}.")
    if not in_order:
        notes.append("Scaffold sections appear out of order.")
    if not headings:
        notes.append("No headings found — the document has no "
                     "section structure to check.")
    return ScaffoldReport(present=present, missing=missing,
                          in_order=in_order, headings=headings,
                          notes=notes)
