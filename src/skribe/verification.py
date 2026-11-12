"""Output Verification Module — the final pass before a file ships.

Checks, from Output_Verification_Module v1.0 + KnowledgeFileStructure
v1.1:
- Size: the spec caps a file at 512 MB. Over that, this module
  REPORTS the overage — it does not auto-trim, because trimming
  deletes the reader's content. (A future `--trim` can add the
  spec's redundant-first trimming as an explicit, opt-in step.)
- Scaffold compliance: all seven sections present, in order.
- Sections scoped, unique, complete: no duplicate headings, no
  empty sections, no placeholder markers left behind.
- Metadata present: title + version or date.

Every check reports pass/fail with a plain-words detail line.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import scaffold as scaffold_mod

MAX_FILE_BYTES = 512 * 1024 * 1024  # 512 MB, per the spec

_PLACEHOLDERS = ("todo", "tbd", "xxx", "lorem ipsum",
                 "to be confirmed", "to be added", "placeholder")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str

    def to_dict(self):
        return {"check": self.name, "passed": self.passed,
                "detail": self.detail}


@dataclass
class VerificationReport:
    passed: bool
    checks: list = field(default_factory=list)  # Check
    size_bytes: int = 0

    @property
    def failures(self):
        return [c for c in self.checks if not c.passed]

    def to_dict(self):
        return {
            "passed": self.passed,
            "size_bytes": self.size_bytes,
            "checks": [c.to_dict() for c in self.checks],
        }

    def render(self):
        lines = [f"Verification: {'PASS' if self.passed else 'FAIL'} "
                 f"({self.size_bytes} bytes)"]
        for check in self.checks:
            mark = "ok  " if check.passed else "FAIL"
            lines.append(f"  [{mark}] {check.name}: {check.detail}")
        return "\n".join(lines)


def verify_text(text, size_bytes=None):
    """Run the output-verification checks over `text`."""
    text = text or ""
    if size_bytes is None:
        size_bytes = len(text.encode("utf-8"))
    checks = []
    # Size.
    if size_bytes <= MAX_FILE_BYTES:
        checks.append(Check("size", True,
                            f"{size_bytes} bytes, under the 512 MB cap."))
    else:
        over = size_bytes - MAX_FILE_BYTES
        checks.append(Check(
            "size", False,
            f"{size_bytes} bytes — {over} bytes over the 512 MB cap. "
            "Trim redundant content; this tool does not auto-trim."))
    # Scaffold compliance.
    report = scaffold_mod.check_scaffold(text)
    if not report.missing and report.in_order:
        checks.append(Check("scaffold", True,
                            "All 7 sections present, in order."))
    else:
        detail = "; ".join(report.notes) if report.notes \
            else "Scaffold incomplete."
        checks.append(Check("scaffold", False, detail))
    # Unique headings.
    headings = scaffold_mod.extract_headings(text)
    lowered = [h[1].lower() for h in headings]
    dupes = sorted({h for h in lowered if lowered.count(h) > 1})
    if dupes:
        checks.append(Check("unique sections", False,
                            "Duplicate headings: "
                            + ", ".join(dupes[:5]) + "."))
    else:
        checks.append(Check("unique sections", True,
                            f"{len(headings)} headings, no duplicates."))
    # No empty sections: a heading followed by another heading with
    # nothing between (ignoring blank lines).
    lines = text.split("\n")
    empty = []
    for i, line in enumerate(lines):
        match = scaffold_mod._HEADING_RE.match(line)
        if not match:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or scaffold_mod._HEADING_RE.match(lines[j]):
            empty.append(match.group(2).strip())
    if empty:
        checks.append(Check("complete sections", False,
                            "Empty sections: "
                            + ", ".join(empty[:5]) + "."))
    else:
        checks.append(Check("complete sections", True,
                            "No empty sections."))
    # No placeholders left.
    lowered_text = text.lower()
    hits = sorted({p for p in _PLACEHOLDERS if p in lowered_text})
    if hits:
        checks.append(Check("no placeholders", False,
                            "Placeholder markers left: "
                            + ", ".join(hits) + "."))
    else:
        checks.append(Check("no placeholders", True,
                            "No placeholder markers."))
    # Metadata present.
    import re as _re
    has_title = bool(_re.search(r"(?m)^#\s+\S", text))
    has_version = bool(_re.search(r"\bv?\d+\.\d+(\.\d+)?\b",
                                  text[:2000]))
    has_date = bool(_re.search(r"\b(19|20)\d\d[-/]\d{1,2}[-/]\d{1,2}\b",
                               text[:2000]))
    if has_title and (has_version or has_date):
        checks.append(Check("metadata", True,
                            "Title plus version/date present."))
    else:
        missing = []
        if not has_title:
            missing.append("title")
        if not has_version and not has_date:
            missing.append("version/date")
        checks.append(Check("metadata", False,
                            "Missing metadata: "
                            + ", ".join(missing) + "."))
    passed = all(c.passed for c in checks)
    return VerificationReport(passed=passed, checks=checks,
                              size_bytes=size_bytes)
