"""The deterministic reviser — mechanical polish, no model.

It fixes what can be fixed safely without understanding the text:
heading hierarchy, list-marker consistency, blank-line runs,
trailing whitespace, and a missing metadata block. It never rewrites
sentences, never invents content, and never removes text — every
change is structural or cosmetic, so a revision cannot make the
document worse in meaning (the loop's degradation check is still
the backstop).

Deep revision (rewriting for clarity, adding missing depth, fixing
facts) needs a reviser that understands the text — pass one to
`skribe.polish` in the library, or use the MCP server with an agent
in the loop.
"""
from __future__ import annotations

import datetime
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_RE = re.compile(r"^(\s*)[-*+]\s+")
_VERSION_RE = re.compile(r"\bv?\d+\.\d+(\.\d+)?\b")
_DATE_RE = re.compile(r"\b(19|20)\d\d[-/]\d{1,2}[-/]\d{1,2}\b")


def _fix_headings(lines):
    """One H1; levels never skip. Extra H1s become H2; a jump like
    H1 -> H3 is pulled back to H1 -> H2."""
    out = []
    seen_h1 = False
    prev_level = 0
    changed = False
    for line in lines:
        match = _HEADING_RE.match(line)
        if not match:
            out.append(line)
            continue
        level = len(match.group(1))
        text = match.group(2)
        new_level = level
        if level == 1:
            if seen_h1:
                new_level = 2
            seen_h1 = True
        elif prev_level and level > prev_level + 1:
            new_level = prev_level + 1
        if new_level != level:
            changed = True
            line = "#" * new_level + " " + text
        prev_level = new_level
        out.append(line)
    return out, changed


def _fix_lists(lines):
    """One list marker style: the most common marker wins."""
    markers = [m.group(0).strip() for line in lines
               for m in [_LIST_RE.match(line)] if m]
    if not markers:
        return lines, False
    winner = max(set(markers), key=markers.count)
    out = []
    changed = False
    for line in lines:
        match = _LIST_RE.match(line)
        if match and match.group(0).strip() != winner:
            changed = True
            line = match.group(1) + winner + " " + line[match.end():]
        out.append(line)
    return out, changed


def _fix_spacing(lines):
    """Strip trailing whitespace; collapse 3+ blank lines to 2."""
    out = []
    changed = False
    blanks = 0
    for line in lines:
        stripped = line.rstrip()
        if stripped != line:
            changed = True
        if not stripped:
            blanks += 1
            if blanks > 2:
                changed = True
                continue
        else:
            blanks = 0
        out.append(stripped)
    return out, changed


def _add_metadata(lines):
    """Add a minimal metadata block when the document has a title
    but no version/date/tags at all. Returns (lines, changed)."""
    head = "\n".join(lines[:20])
    if _VERSION_RE.search(head) or _DATE_RE.search(head):
        return lines, False
    title_idx = None
    title = ""
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            title_idx = i
            title = match.group(2)
            break
    if title_idx is None:
        return lines, False
    today = datetime.date.today().isoformat()
    block = [
        "",
        f"version: 1.0",
        f"date: {today}",
        f"description: {title}",
    ]
    return lines[:title_idx + 1] + block + lines[title_idx + 1:], True


def revise(text, grade=None):
    """One mechanical revision pass. `grade` (the current
    GradeResult) is accepted for interface parity with model
    revisers; the mechanical pass does not need it. Returns the
    revised text — identical input when nothing applies."""
    if not (text or "").strip():
        return text
    lines = (text or "").split("\n")
    lines, _ = _fix_headings(lines)
    lines, _ = _fix_lists(lines)
    lines, _ = _fix_spacing(lines)
    lines, _ = _add_metadata(lines)
    revised = "\n".join(lines)
    if not revised.endswith("\n") and text.endswith("\n"):
        revised += "\n"
    return revised


def describe_changes(before, after):
    """Plain-words list of what a revision pass changed."""
    if before == after:
        return ["No changes — nothing mechanical left to fix."]
    changes = []
    before_lines = before.split("\n")
    after_lines = after.split("\n")
    if [l for l in before_lines if _HEADING_RE.match(l)] != \
            [l for l in after_lines if _HEADING_RE.match(l)]:
        changes.append("Heading hierarchy repaired.")
    before_markers = {_LIST_RE.match(l).group(0).strip()
                      for l in before_lines if _LIST_RE.match(l)}
    after_markers = {_LIST_RE.match(l).group(0).strip()
                     for l in after_lines if _LIST_RE.match(l)}
    if before_markers != after_markers:
        changes.append("List markers made consistent.")
    if len(after_lines) != len(before_lines):
        changes.append("Blank lines / metadata adjusted.")
    if not changes:
        changes.append("Whitespace and formatting tidied.")
    return changes
