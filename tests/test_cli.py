"""End-to-end CLI tests — subprocess runs against the source tree."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SAMPLE = ROOT / "examples" / "sample.md"

ENV = dict(os.environ, PYTHONPATH=str(SRC))


def run_cli(*args, input_text=None):
    return subprocess.run(
        [sys.executable, "-m", "skribe", *args],
        capture_output=True, text=True, input=input_text,
        env=ENV, cwd=ROOT, timeout=60)


class CliGradeTests(unittest.TestCase):
    def test_grade_sample(self):
        proc = run_cli("grade", str(SAMPLE))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("FZI:", proc.stdout)
        self.assertIn("Structure & Organization", proc.stdout)
        self.assertIn("Scorer: deterministic", proc.stdout)

    def test_grade_json(self):
        proc = run_cli("grade", str(SAMPLE), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("fzi", data)
        self.assertEqual(len(data["metrics"]), 6)
        self.assertEqual(data["scorer"], "deterministic")

    def test_grade_stdin(self):
        proc = run_cli("grade", "-", input_text="# Title\n\nText.\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("FZI:", proc.stdout)

    def test_grade_missing_file_fails(self):
        proc = run_cli("grade", "no-such-file.md")
        self.assertNotEqual(proc.returncode, 0)

    def test_grade_with_purpose(self):
        proc = run_cli("grade", str(SAMPLE), "--purpose",
                       "Teach backups with rsync")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("FZI:", proc.stdout)

    def test_decisions_without_key_fails_cleanly(self):
        env = dict(ENV)
        env.pop("GEMINI_API_KEY", None)
        proc = subprocess.run(
            [sys.executable, "-m", "skribe", "grade", str(SAMPLE),
             "--scorer", "decisions"],
            capture_output=True, text=True, env=env, cwd=ROOT,
            timeout=60)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("API key", proc.stderr)


class CliPolishTests(unittest.TestCase):
    def test_polish_to_stdout(self):
        proc = run_cli("polish", str(SAMPLE))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("FZI:", proc.stdout)
        self.assertIn("->", proc.stdout)
        # The polished text follows the summary.
        self.assertIn("How to back up a Linux home folder",
                      proc.stdout)

    def test_polish_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "polished.md")
            proc = run_cli("polish", str(SAMPLE), "-o", out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.isfile(out))
            text = Path(out).read_text()
            self.assertIn("version: 1.0", text)
            self.assertIn("## Why back up", text)

    def test_polish_json(self):
        proc = run_cli("polish", str(SAMPLE), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertIn("initial_fzi", data)
        self.assertIn("final_fzi", data)
        self.assertIn("exit_reason", data)
        self.assertGreaterEqual(data["final_fzi"],
                                data["initial_fzi"])


class CliVerifyTests(unittest.TestCase):
    def test_verify_sample_fails_on_scaffold(self):
        # The sample lacks the 7-section scaffold: exit 1, honestly.
        proc = run_cli("verify", str(SAMPLE))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL", proc.stdout)

    def test_verify_json(self):
        proc = run_cli("verify", str(SAMPLE), "--json")
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertFalse(data["passed"])
        self.assertIn("checks", data)

    def test_verify_good_doc_passes(self):
        full = """# A complete knowledge file

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
        with tempfile.NamedTemporaryFile(
                "w", suffix=".md", delete=False) as handle:
            handle.write(full)
            path = handle.name
        try:
            proc = run_cli("verify", path)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("PASS", proc.stdout)
        finally:
            os.unlink(path)


class CliMiscTests(unittest.TestCase):
    def test_version(self):
        proc = run_cli("--version")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("0.1.0", proc.stdout)

    def test_no_command_fails(self):
        proc = run_cli()
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
