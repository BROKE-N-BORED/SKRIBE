"""Tests for the deterministic scorer."""
import unittest

from skribe import deterministic as det
from skribe import rubric

GOOD_DOC = """# Backing up a home folder

version: 1.0
date: 2026-11-12
tags: backup, linux, rsync
author: Test Author

## Purpose

This guide teaches a beginner how to back up a Linux home folder
with rsync. It covers picking a drive, running the backup, and
checking the result.

## Definitions

A backup is a copy of your files kept somewhere else. rsync is a
tool that copies files and keeps two folders in sync.

## Procedure

1. Plug in the external drive.
2. Run the backup command below.
3. Check that a few files open correctly from the backup.

## Example

Run this command to copy your home folder:

```
rsync -av /home/you/ /media/you/drive/backups/home/
```

For instance, a 40 GB home folder takes about 20 minutes on USB 3.

## Edge cases

If the drive fills up, the backup fails partway through. Watch the
free space. A fallback is to back up in two parts. One pitfall is
forgetting the trailing slash, which changes what rsync copies.

## References

- https://rsync.samba.org/documentation.html
- https://wiki.archlinux.org/title/rsync
- https://example.org/backup-guide

## Revision history

- v1.0 - 2026-11-12 - Test Author - First version.
"""

BAD_DOC = """stuff about backups

TODO add the real content later. lorem ipsum dolor sit amet.
TBD whether this even works.
"""

FLAT_DOC = "One short paragraph with no headings at all."


class DeterministicTests(unittest.TestCase):
    def test_good_doc_beats_bad_doc(self):
        good = det.score_text(GOOD_DOC)
        bad = det.score_text(BAD_DOC)
        self.assertGreater(good.fzi, bad.fzi)
        self.assertGreater(good.fzi, 60)
        self.assertLess(bad.fzi, 40)

    def test_same_input_same_output(self):
        first = det.score_text(GOOD_DOC)
        second = det.score_text(GOOD_DOC)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_empty_text_scores_zero(self):
        result = det.score_text("")
        self.assertEqual(result.fzi, 0.0)
        result = det.score_text("   \n  ")
        self.assertEqual(result.fzi, 0.0)

    def test_scorer_name(self):
        self.assertEqual(det.score_text(GOOD_DOC).scorer,
                         "deterministic")


class StructureTests(unittest.TestCase):
    def test_skipped_heading_levels_lose_points(self):
        skipped = "# Title\n\n### Deep\n\nText here.\n"
        clean = "# Title\n\n## Section\n\nText here.\n"
        self.assertGreater(
            det.score_text(clean).metrics["structure"].score,
            det.score_text(skipped).metrics["structure"].score)

    def test_two_h1s_lose_points(self):
        two = "# One\n\nText.\n\n# Two\n\nMore text.\n"
        one = "# One\n\nText.\n\n## Two\n\nMore text.\n"
        self.assertGreater(
            det.score_text(one).metrics["structure"].score,
            det.score_text(two).metrics["structure"].score)

    def test_metadata_signals_raise_structure(self):
        bare = "# Title\n\n## Section\n\nText.\n"
        meta = ("# Title\n\nversion: 1.0\ndate: 2026-11-12\n"
                "tags: a, b\n\n## Section\n\nText.\n")
        self.assertGreater(
            det.score_text(meta).metrics["structure"].score,
            det.score_text(bare).metrics["structure"].score)


class AccuracyTests(unittest.TestCase):
    def test_placeholders_lower_accuracy(self):
        clean = "# Guide\n\nThis is a plain guide with real content.\n"
        dirty = "# Guide\n\nTODO write this. TBD later.\n"
        self.assertGreater(
            det.score_text(clean).metrics["accuracy"].score,
            det.score_text(dirty).metrics["accuracy"].score)

    def test_accuracy_capped_at_85(self):
        result = det.score_text(GOOD_DOC)
        self.assertLessEqual(result.metrics["accuracy"].score, 85.0)


class EvsTests(unittest.TestCase):
    def test_three_sources_give_evs_1(self):
        evs, count = det.evs_from_text(GOOD_DOC)
        self.assertEqual(evs, rubric.EVS_VERIFIED)
        self.assertGreaterEqual(count, 3)

    def test_no_sources_give_evs_08(self):
        evs, count = det.evs_from_text(FLAT_DOC)
        self.assertEqual(evs, rubric.EVS_NO_SOURCES)
        self.assertEqual(count, 0)

    def test_one_source_gives_evs_09(self):
        text = "See https://example.org/one for details.\n"
        evs, count = det.evs_from_text(text)
        self.assertEqual(evs, rubric.EVS_PARTIAL)
        self.assertEqual(count, 1)


class ClarityTests(unittest.TestCase):
    def test_flesch_reading_ease_plain_text(self):
        fre = det.flesch_reading_ease(
            "The cat sat on the mat. It was a warm day. "
            "The dog ran fast.")
        self.assertGreater(fre, 70)

    def test_flesch_none_on_empty(self):
        self.assertIsNone(det.flesch_reading_ease(""))
        self.assertIsNone(det.flesch_reading_ease("   "))

    def test_long_sentences_lose_clarity(self):
        short = ("Short text. Clear words. Easy to read. " * 10).strip()
        long = ("This extraordinarily long and convoluted sentence "
                "continues without pause through numerous subordinate "
                "clauses and unnecessary qualifications that obscure "
                "the central point considerably. " * 5).strip()
        self.assertGreater(
            det.score_text(short).metrics["clarity"].score,
            det.score_text(long).metrics["clarity"].score)


class DepthTests(unittest.TestCase):
    def test_longer_doc_scores_deeper(self):
        short = "# T\n\nA few words here.\n"
        long = "# T\n\n" + ("This is a detailed paragraph about the "
                            "topic with real substance. " * 60)
        self.assertGreater(
            det.score_text(long).metrics["depth"].score,
            det.score_text(short).metrics["depth"].score)

    def test_edge_case_words_raise_depth(self):
        plain = "# T\n\n" + ("Plain content paragraph. " * 40)
        edgy = ("# T\n\n" + ("Plain content paragraph. " * 40)
                + "\nEdge case: if it fails, use the fallback. "
                "One pitfall is the timeout limitation.")
        self.assertGreater(
            det.score_text(edgy).metrics["depth"].score,
            det.score_text(plain).metrics["depth"].score)


class DomainTests(unittest.TestCase):
    def test_purpose_overlap(self):
        text = "# Backing up files\n\nUse rsync to copy your home " \
               "folder to a backup drive every week.\n"
        matching = det.score_text(
            text, purpose="back up home folder with rsync")
        other = det.score_text(
            text, purpose="bake sourdough bread at home")
        self.assertGreater(matching.metrics["domain"].score,
                           other.metrics["domain"].score)

    def test_no_purpose_caps_at_80(self):
        result = det.score_text(GOOD_DOC)
        self.assertLessEqual(result.metrics["domain"].score, 80.0)


if __name__ == "__main__":
    unittest.main()
