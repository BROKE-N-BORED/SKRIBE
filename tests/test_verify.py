"""Tests for output verification + the scaffold check."""
import unittest

from skribe import scaffold as scaffold_mod
from skribe import verification as verify_mod

FULL_DOC = """# A complete knowledge file

version: 1.0
date: 2026-11-12

## Metadata

Title, id, version, and tags live here.

## Context

Purpose and audience live here.

## Core Content

Definitions and concepts live here.

## Implementation

Steps and code live here.

## Tests and Verification

Test cases live here.

## Links and References

Sources live here.

## Revision History

- v1.0 - 2026-11-12 - Author - First version.
"""

OUT_OF_ORDER_DOC = """# Title

version: 1.0

## Implementation

Steps here.

## Metadata

Meta here.
"""


class ScaffoldTests(unittest.TestCase):
    def test_full_doc_passes(self):
        report = scaffold_mod.check_scaffold(FULL_DOC)
        self.assertEqual(report.missing, [])
        self.assertTrue(report.in_order)
        self.assertEqual(report.coverage, 1.0)

    def test_missing_sections_listed(self):
        report = scaffold_mod.check_scaffold("# Title\n\nText.\n")
        self.assertEqual(len(report.missing), 7)
        self.assertEqual(report.coverage, 0.0)

    def test_out_of_order_detected(self):
        report = scaffold_mod.check_scaffold(OUT_OF_ORDER_DOC)
        self.assertFalse(report.in_order)

    def test_heading_extraction(self):
        headings = scaffold_mod.extract_headings(
            "# One\n\n## Two\n\n### Three\n")
        self.assertEqual(headings, [(1, "One"), (2, "Two"),
                                    (3, "Three")])


class VerifyTests(unittest.TestCase):
    def test_full_doc_passes(self):
        report = verify_mod.verify_text(FULL_DOC)
        self.assertTrue(report.passed)
        self.assertEqual(report.failures, [])

    def test_empty_doc_fails(self):
        report = verify_mod.verify_text("")
        self.assertFalse(report.passed)
        failed = {c.name for c in report.failures}
        self.assertIn("scaffold", failed)
        self.assertIn("metadata", failed)

    def test_duplicate_headings_fail(self):
        text = "# Title\n\n## Setup\n\nText.\n\n## Setup\n\nMore.\n"
        report = verify_mod.verify_text(text)
        failed = {c.name for c in report.failures}
        self.assertIn("unique sections", failed)

    def test_empty_section_fails(self):
        text = "# Title\n\n## Empty\n\n## Next\n\nText.\n"
        report = verify_mod.verify_text(text)
        failed = {c.name for c in report.failures}
        self.assertIn("complete sections", failed)

    def test_placeholders_fail(self):
        text = "# Title\n\nTODO fill this in.\n"
        report = verify_mod.verify_text(text)
        failed = {c.name for c in report.failures}
        self.assertIn("no placeholders", failed)

    def test_oversize_fails_without_trimming(self):
        report = verify_mod.verify_text(
            "small", size_bytes=verify_mod.MAX_FILE_BYTES + 1)
        failed = {c.name for c in report.failures}
        self.assertIn("size", failed)

    def test_report_renders(self):
        report = verify_mod.verify_text(FULL_DOC)
        rendered = report.render()
        self.assertIn("PASS", rendered)
        self.assertIn("scaffold", rendered)


if __name__ == "__main__":
    unittest.main()
