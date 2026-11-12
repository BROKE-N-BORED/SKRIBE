"""Tests for the library API: grade, polish, verify, PCA."""
import unittest

from skribe import api as api_mod
from skribe import grade, pca_check, polish, scaffold_check, verify
from skribe.loop import LoopConfig

DOC = """# Backing up files

This guide shows how to back up a home folder with rsync.

### Why back up

Drives fail. A backup saves your files.

### Steps

* Plug in a drive.
- Run rsync.
* Check the copy.
"""

GOOD_DOC = """# Backing up a home folder

version: 1.0
date: 2026-11-12

## Purpose

Teach a beginner to back up a Linux home folder with rsync.

## Procedure

1. Plug in the drive.
2. Run the command.
3. Check the copy.

## Example

```
rsync -av /home/you/ /media/you/drive/backups/
```

## Edge cases

If the drive fills up, the backup fails. A fallback is to split
the backup. One pitfall is the missing trailing slash.

## References

- https://example.org/a
- https://example.org/b
- https://example.org/c

## Revision history

- v1.0 - 2026-11-12 - Author - First version.
"""


class GradeApiTests(unittest.TestCase):
    def test_grade_returns_result(self):
        result = grade(DOC)
        self.assertGreater(result.fzi, 0)
        self.assertLessEqual(result.fzi, 100)
        self.assertEqual(len(result.metrics), 6)
        self.assertIn(result.band, ("Zenith Excellence",
                                    "Superior Quality",
                                    "Strong Performance",
                                    "Acceptable Standard",
                                    "Rejected"))

    def test_good_doc_beats_rough_doc(self):
        self.assertGreater(grade(GOOD_DOC).fzi, grade(DOC).fzi)

    def test_unknown_scorer_raises(self):
        with self.assertRaises(ValueError):
            grade(DOC, scorer="nope")

    def test_prompt_scorer_needs_chat(self):
        with self.assertRaises(ValueError):
            grade(DOC, scorer="prompt")

    def test_decisions_scorer_needs_key(self):
        with self.assertRaises(ValueError):
            grade(DOC, scorer="decisions")

    def test_grade_with_fake_prompt_scorer(self):
        import json

        def chat(prompt):
            return json.dumps({
                "metrics": {k: 90 for k in
                            ("structure", "accuracy", "utility",
                             "clarity", "depth", "domain")},
                "evs": 1.0})
        result = grade(DOC, scorer="prompt", chat=chat)
        self.assertEqual(result.fzi, 90.0)
        self.assertEqual(result.scorer, "prompt")


class PolishApiTests(unittest.TestCase):
    def test_polish_improves_a_rough_doc(self):
        result = polish(DOC)
        self.assertGreaterEqual(result.final_fzi, result.initial_fzi)
        self.assertGreater(result.final_fzi, result.initial_fzi)
        # Heading levels fixed, list markers unified.
        self.assertIn("## Why back up", result.text)
        self.assertNotIn("### Why back up", result.text)

    def test_polish_already_good_doc_runs_few_cycles(self):
        result = polish(GOOD_DOC, config=LoopConfig(target_fzi=90))
        self.assertLessEqual(result.cycles_run, 5)
        self.assertGreaterEqual(result.final_fzi, result.initial_fzi)

    def test_polish_verifies_the_result(self):
        result = polish(DOC)
        self.assertIsNotNone(result.verification)

    def test_polish_with_model_reviser(self):
        def reviser(text, grade_result):
            return text + "\n## References\n\n- https://example.org/a\n"
        result = polish(DOC, reviser=reviser,
                        config=LoopConfig(target_fzi=99, max_cycles=1))
        self.assertIn("References", result.text)

    def test_strict_pca_blocks_purposeless_doc(self):
        with self.assertRaises(ValueError):
            polish("just some words, no title, no purpose",
                   strict_pca=True)


class VerifyApiTests(unittest.TestCase):
    def test_verify_reports(self):
        report = verify(DOC)
        self.assertFalse(report.passed)
        self.assertTrue(report.checks)


class PcaTests(unittest.TestCase):
    def test_purpose_and_audience_from_args(self):
        summary = pca_check(DOC, purpose="Teach backups",
                            audience="beginners")
        self.assertEqual(summary.purpose, "Teach backups")
        self.assertEqual(summary.audience, "beginners")
        self.assertTrue(summary.passed)

    def test_purpose_read_from_text(self):
        text = "Purpose: Teach backups.\n\nSome content here.\n"
        summary = pca_check(text)
        self.assertEqual(summary.purpose, "Teach backups.")

    def test_meta_phrases_flagged(self):
        summary = pca_check("As an AI, I will explain backups.\n")
        self.assertIn("as an ai", summary.meta_hits)
        self.assertFalse(summary.passed)

    def test_pca_summary_renders(self):
        summary = pca_check(DOC, purpose="Teach backups",
                            audience="beginners")
        rendered = summary.render()
        self.assertIn("Purpose: Teach backups", rendered)
        self.assertIn("Audience: beginners", rendered)


class ScaffoldApiTests(unittest.TestCase):
    def test_scaffold_check_exposed(self):
        report = scaffold_check(GOOD_DOC)
        self.assertGreater(report.coverage, 0.5)


if __name__ == "__main__":
    unittest.main()
