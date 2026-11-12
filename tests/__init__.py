"""Make the src layout importable for the test run.

The package lives under src/, so a bare checkout cannot `import
skribe` until it is installed. This insert lets `python -m unittest
discover -s tests` work straight from a clone, with no install step.
(Lead fix, 2026-11-12: the naive discover run failed with 8 import
errors before this file existed.)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
