"""The deterministic scorer — SKRIBE's built-in grader.

No model, no key, no network: it scores a document from the text
itself, using the rubric's criteria turned into measurable checks.
Every metric returns its score plus the reasons behind it, so a
score can always be explained.

Honest limits, stated in the output: a deterministic scorer cannot
verify facts. Accuracy here is a defect check (placeholders,
unverified-claim markers, missing sources) capped at 85 — real fact
verification needs a scorer that can check claims (the prompt-based
or Decisions scorer). Domain alignment without a stated purpose is
a weak title/body check, capped at 80, and says so.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from . import rubric, scaffold as scaffold_mod
from .scores import grade_from_metrics

SCORER_NAME = "deterministic"

# Accuracy caps: the deterministic scorer cannot verify facts, so
# it never awards full marks for accuracy.
ACCURACY_CAP = 85.0
DOMAIN_NO_PURPOSE_CAP = 80.0

_URL_RE = re.compile(r"https?://[^\s)>\"]+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_PLACEHOLDERS = ("todo", "tbd", "xxx", "lorem ipsum", "to be confirmed",
                 "to be added", "placeholder", "[insert", "fill in")
_EDGE_WORDS = ("edge case", "fallback", "pitfall", "limitation",
               "exception", "if it fails", "when it fails", "failure mode",
               "workaround", "caveat")
_DEFINITION_RE = re.compile(r"\b[A-Z][A-Za-z0-9 _-]{2,40}\s+(is|are|means)\s+")
_VERSION_RE = re.compile(r"\bv?\d+\.\d+(\.\d+)?\b")
_DATE_RE = re.compile(r"\b(19|20)\d\d[-/]\d{1,2}[-/]\d{1,2}\b")


def _words(text):
    return _WORD_RE.findall(text or "")


def _sentences(text):
    text = " ".join((text or "").split())
    if not text:
        return []
    return [s for s in _SENTENCE_RE.split(text) if s.strip()]


def _syllables(word):
    """Vowel-group syllable estimate (standard heuristic)."""
    word = word.lower().strip("'-")
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    groups = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e"):
        groups -= 1
    if word.endswith("le") and len(word) > 2 and word[-3] not in "aeiouy":
        groups += 1
    return max(1, groups)


def flesch_reading_ease(text):
    """Flesch Reading Ease (0-100, higher is easier). Returns None
    when the text has no sentences or words."""
    words = _words(text)
    sentences = _sentences(text)
    if not words or not sentences:
        return None
    syllables = sum(_syllables(w) for w in words)
    asl = len(words) / len(sentences)
    asw = syllables / len(words)
    return 206.835 - 1.015 * asl - 84.6 * asw


def extract_sources(text):
    """Distinct source URLs plus reference-list entries."""
    urls = {_u.rstrip(".,;") for _u in _URL_RE.findall(text or "")}
    # Reference entries: lines in a references section that look
    # like citations (numbered, or author-year shaped).
    refs = set()
    in_refs = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,6}\s+", stripped):
            in_refs = scaffold_mod._match_section(
                stripped.lstrip("#").strip()) == "references"
            continue
        if in_refs and re.match(r"^(\d+[.)]|\[?\d+\]?|[-*])\s+\S", stripped):
            refs.add(stripped[:120])
    return urls, refs


def evs_from_text(text):
    """EVS from the sources actually present in the text.

    >= 3 distinct sources -> 1.0 (verified match); 1-2 -> 0.9;
    none -> 0.8 (partial confidence, per the v3.1 controller).
    Contradiction (0.5) is never claimed by the deterministic
    scorer — it cannot detect one.
    """
    urls, refs = extract_sources(text)
    count = len(urls) + len(refs)
    if count >= 3:
        return rubric.EVS_VERIFIED, count
    if count >= 1:
        return rubric.EVS_PARTIAL, count
    return rubric.EVS_NO_SOURCES, 0


def _score_structure(text, headings, scaffold_report):
    score = 0.0
    rationale = []
    # Metadata block (25): title + version + date + tags/keywords.
    meta_hits = 0
    head = (text or "")[:2000]
    if re.search(r"^#\s+\S", text or "", re.MULTILINE):
        meta_hits += 1
    if _VERSION_RE.search(head):
        meta_hits += 1
    if _DATE_RE.search(head):
        meta_hits += 1
    if re.search(r"(?im)^(tags|keywords|author)\s*[:\-]", head):
        meta_hits += 1
    meta_points = meta_hits * 6.25
    score += meta_points
    rationale.append(f"Metadata signals present: {meta_hits}/4 "
                     f"(title, version, date, tags/author).")
    # Heading hierarchy (25): exactly one H1, no skipped levels.
    if headings:
        h1 = sum(1 for level, _ in headings if level == 1)
        if h1 == 1:
            score += 10
            rationale.append("Exactly one top-level heading.")
        elif h1 == 0:
            rationale.append("No top-level heading.")
        else:
            score += 4
            rationale.append(f"{h1} top-level headings — one is the rule.")
        skipped = 0
        prev = 0
        for level, _ in headings:
            if prev and level > prev + 1:
                skipped += 1
            prev = level
        if skipped == 0:
            score += 15
            rationale.append("Heading levels never skip.")
        else:
            rationale.append(f"Heading levels skip {skipped} time(s).")
    else:
        rationale.append("No headings at all.")
    # Scaffold coverage (30).
    coverage_points = scaffold_report.coverage * 30
    score += coverage_points
    rationale.append(f"Scaffold sections present: "
                     f"{len(scaffold_report.present)}/7.")
    if not scaffold_report.in_order:
        score -= 5
        rationale.append("Scaffold sections out of order (-5).")
    # Section separation (20): enough headings to navigate by.
    count = len(headings)
    if count >= 5:
        score += 20
        rationale.append(f"{count} headings — well sectioned.")
    elif count >= 3:
        score += 12
        rationale.append(f"{count} headings.")
    elif count >= 1:
        score += 6
        rationale.append(f"Only {count} heading(s).")
    return max(0.0, min(100.0, score)), rationale


def _score_accuracy(text):
    score = 70.0  # neutral: no facts verified, no defects found
    rationale = ["Baseline 70: no defects found, but facts are "
                 "not verified by this scorer."]
    lowered = (text or "").lower()
    hits = sorted({p for p in _PLACEHOLDERS if p in lowered})
    if hits:
        penalty = min(30, 10 * len(hits))
        score -= penalty
        rationale.append(f"Placeholder/uncertainty markers: "
                         f"{', '.join(hits)} (-{penalty}).")
    urls, refs = extract_sources(text)
    if urls or refs:
        score += 10
        rationale.append(f"{len(urls) + len(refs)} source(s) cited (+10).")
    if _DEFINITION_RE.search(text or ""):
        score += 5
        rationale.append("Definitions present (+5).")
    if score > ACCURACY_CAP:
        score = ACCURACY_CAP
        rationale.append(f"Capped at {ACCURACY_CAP:.0f}: fact "
                         "verification needs a scorer that can check "
                         "claims.")
    return max(0.0, min(100.0, score)), rationale


def _score_utility(text):
    score = 0.0
    rationale = []
    if "```" in (text or "") or re.search(r"(?m)^\s{4}\S", text or ""):
        score += 20
        rationale.append("Code or command blocks present (+20).")
    else:
        rationale.append("No code or command blocks.")
    steps = len(re.findall(r"(?m)^\s*\d+[.)]\s+\S", text or ""))
    bullets = len(re.findall(r"(?m)^\s*[-*]\s+\S", text or ""))
    if steps >= 3:
        score += 20
        rationale.append(f"{steps} numbered steps (+20).")
    elif steps >= 1 or bullets >= 3:
        score += 12
        rationale.append("Procedures or lists present (+12).")
    else:
        rationale.append("No procedures or lists.")
    examples = len(re.findall(r"(?im)^\s*(example|e\.g\.|for instance)\b",
                              text or ""))
    if examples >= 2:
        score += 20
        rationale.append(f"{examples} examples (+20).")
    elif examples == 1:
        score += 10
        rationale.append("1 example (+10).")
    else:
        rationale.append("No examples.")
    lowered = (text or "").lower()
    gaps = [p for p in ("to be added", "to be confirmed", "coming soon")
            if p in lowered]
    if gaps:
        rationale.append(f"Open gaps named: {', '.join(gaps)}.")
    else:
        score += 20
        rationale.append("No open gaps named (+20).")
    imperatives = len(re.findall(
        r"(?im)^\s*(run|use|add|create|check|set|install|open|write|"
        r"ensure|verify|follow|see)\b", text or ""))
    if imperatives >= 5:
        score += 20
        rationale.append(f"{imperatives} direct instructions (+20).")
    elif imperatives >= 2:
        score += 10
        rationale.append(f"{imperatives} direct instructions (+10).")
    else:
        rationale.append("Few direct instructions.")
    return max(0.0, min(100.0, score)), rationale


def _score_clarity(text):
    score = 0.0
    rationale = []
    fre = flesch_reading_ease(text)
    if fre is None:
        return 0.0, ["No readable sentences found."]
    # Flesch 60-70 is the plain-language sweet spot; scale 0-40.
    if fre >= 60:
        fre_points = 40.0
    elif fre >= 30:
        fre_points = 20.0 + (fre - 30) * (20.0 / 30.0)
    elif fre >= 0:
        fre_points = fre * (20.0 / 30.0)
    else:
        fre_points = 0.0
    score += fre_points
    rationale.append(f"Reading ease {fre:.1f} "
                     f"(60-70 is plain language).")
    words = _words(text)
    sentences = _sentences(text)
    asl = len(words) / max(1, len(sentences))
    if 12 <= asl <= 22:
        score += 25
        rationale.append(f"Average sentence {asl:.1f} words — good length.")
    elif asl < 12:
        score += 15
        rationale.append(f"Average sentence {asl:.1f} words — choppy.")
    else:
        score += max(0.0, 25 - (asl - 22))
        rationale.append(f"Average sentence {asl:.1f} words — long.")
    long_words = sum(1 for w in words if len(w) > 6)
    long_ratio = long_words / max(1, len(words))
    if long_ratio <= 0.20:
        score += 20
        rationale.append("Plain vocabulary.")
    elif long_ratio <= 0.30:
        score += 12
        rationale.append(f"{long_ratio:.0%} long words — dense.")
    else:
        score += 5
        rationale.append(f"{long_ratio:.0%} long words — heavy.")
    markers = Counter(re.findall(r"(?m)^\s*([-*+])\s+\S", text or ""))
    if len(markers) <= 1:
        score += 10
        rationale.append("List markers consistent.")
    else:
        rationale.append("Mixed list markers (-10).")
    atx = len(re.findall(r"(?m)^#{1,6}\s+\S", text or ""))
    setext = len(re.findall(r"(?m)^[=-]{3,}\s*$", text or ""))
    if setext == 0 or atx == 0:
        score += 5
        rationale.append("Heading style consistent.")
    else:
        rationale.append("Mixed heading styles (-5).")
    return max(0.0, min(100.0, score)), rationale


def _score_depth(text):
    score = 0.0
    rationale = []
    word_count = len(_words(text))
    if word_count >= 2000:
        score += 30
    elif word_count >= 500:
        score += 22
    elif word_count >= 100:
        score += 12
    elif word_count >= 20:
        score += 5
    rationale.append(f"{word_count} words.")
    lowered = (text or "").lower()
    edge_hits = sorted({w for w in _EDGE_WORDS if w in lowered})
    if len(edge_hits) >= 3:
        score += 25
        rationale.append(f"Edge cases/fallbacks covered: "
                         f"{', '.join(edge_hits[:4])} (+25).")
    elif edge_hits:
        score += 12
        rationale.append(f"Some edge coverage: "
                         f"{', '.join(edge_hits)} (+12).")
    else:
        rationale.append("No edge-case or fallback coverage.")
    examples = len(re.findall(r"(?im)^\s*(example|e\.g\.|for instance)\b",
                              text or ""))
    if examples >= 2:
        score += 20
        rationale.append(f"{examples} examples (+20).")
    elif examples == 1:
        score += 10
        rationale.append("1 example (+10).")
    else:
        rationale.append("No examples.")
    xrefs = len(re.findall(r"(?im)\bsee (section|above|below|also)\b",
                           text or ""))
    links = len(re.findall(r"\[[^\]]+\]\(#[^)]+\)", text or ""))
    if xrefs + links >= 3:
        score += 15
        rationale.append("Cross-references present (+15).")
    elif xrefs + links >= 1:
        score += 7
        rationale.append("Some cross-references (+7).")
    else:
        rationale.append("No cross-references.")
    specifics = len(_VERSION_RE.findall(text or "")) \
        + len(_DATE_RE.findall(text or "")) \
        + len(re.findall(r"\b\d+(?:\.\d+)?\s*(%|MB|GB|ms|seconds?)\b",
                         text or ""))
    if specifics >= 3:
        score += 10
        rationale.append("Specific numbers/versions/dates (+10).")
    elif specifics >= 1:
        score += 5
        rationale.append("Some specifics (+5).")
    else:
        rationale.append("No specific numbers or versions.")
    return max(0.0, min(100.0, score)), rationale


_STOPWORDS = frozenset("""
a an the and or but of to in on for with by at from as is are was were be
been it its this that these those you your we our they their he she his her
""".split())


def _content_words(text):
    return {w.lower() for w in _words(text or "")
            if w.lower() not in _STOPWORDS and len(w) > 2}


def _score_domain(text, purpose=None):
    if purpose and purpose.strip():
        purpose_words = _content_words(purpose)
        body_words = _content_words(text)
        if not purpose_words:
            return 50.0, ["Purpose has no content words to match."]
        overlap = len(purpose_words & body_words) / len(purpose_words)
        score = round(overlap * 100, 2)
        rationale = [f"{len(purpose_words & body_words)}/"
                     f"{len(purpose_words)} purpose terms appear in "
                     f"the text."]
        return score, rationale
    # No purpose supplied: weak proxy — do the title's terms show
    # up in the body? Capped, and the rationale says so.
    headings = scaffold_mod.extract_headings(text)
    title = headings[0][1] if headings else ""
    title_words = _content_words(title)
    body_words = _content_words(text)
    if not title_words:
        return 50.0, ["No purpose supplied and no title to check "
                      "against — neutral score."]
    overlap = len(title_words & body_words) / len(title_words)
    score = min(DOMAIN_NO_PURPOSE_CAP, round(overlap * 100, 2))
    rationale = [f"Title terms in body: "
                 f"{len(title_words & body_words)}/{len(title_words)}.",
                 f"Capped at {DOMAIN_NO_PURPOSE_CAP:.0f}: no purpose "
                 "was supplied, so alignment is judged against the "
                 "title only."]
    return score, rationale


def score_text(text, purpose=None, audience=None):
    """Grade `text` with the deterministic scorer.

    Returns a GradeResult. Pure function of its inputs — same text
    in, same score out. `audience` is accepted for interface
    parity with the other scorers and noted, not scored.
    """
    text = text or ""
    notes = []
    if audience:
        notes.append(f"Audience: {audience}.")
    if not text.strip():
        metrics = {key: (0.0, ["Empty document."])
                   for key in rubric.METRIC_KEYS}
        return grade_from_metrics(
            {k: v[0] for k, v in metrics.items()},
            evs=rubric.EVS_NO_SOURCES, scorer=SCORER_NAME,
            rationales={k: v[1] for k, v in metrics.items()},
            notes=["Empty document — nothing to score."])
    headings = scaffold_mod.extract_headings(text)
    scaffold_report = scaffold_mod.check_scaffold(text)
    evs, source_count = evs_from_text(text)
    urls, refs = extract_sources(text)
    citations = sorted(urls)[:10]
    scores = {}
    rationales = {}
    scores["structure"], rationales["structure"] = _score_structure(
        text, headings, scaffold_report)
    scores["accuracy"], rationales["accuracy"] = _score_accuracy(text)
    scores["utility"], rationales["utility"] = _score_utility(text)
    scores["clarity"], rationales["clarity"] = _score_clarity(text)
    scores["depth"], rationales["depth"] = _score_depth(text)
    scores["domain"], rationales["domain"] = _score_domain(text, purpose)
    notes.append(f"EVS {evs} from {source_count} source(s) found "
                 "in the text.")
    return grade_from_metrics(
        scores, evs=evs, scorer=SCORER_NAME, rationales=rationales,
        citations=citations, notes=notes)
