# SKRIBE

Score and polish written work with the FZI rubric — from the terminal, from code, or from an agent.

SKRIBE grades a document on six measures (structure, accuracy, usefulness, clarity, depth, domain fit), combines them into one score from 0 to 100 called the FZI, and can revise a document in a loop until it stops improving. The built-in scorer needs no model and no key: it works entirely from the text. If you have a model or a key, you can swap in a smarter scorer.

## Install

```bash
pip install .
```

That is the whole install. SKRIBE uses only the Python standard library, so there is nothing else to fetch. Python 3.10 or newer.

Or clone the repo and run it without installing:

```bash
git clone https://github.com/BROKE-N-BORED/SKRIBE
cd SKRIBE
PYTHONPATH=src python -m skribe grade examples/sample.md
```

## The three commands

### `skribe grade` — score a document

```bash
skribe grade guide.md
```

Prints the FZI, the score band, and every metric with its reasons:

```
FZI: 57.41 — Rejected
  Major revisions required.
  Scorer: deterministic  EVS: 0.8
  Structure & Organization (20%): 40.54
      - Metadata signals present: 1/4 (title, version, date, tags/author).
      - Exactly one top-level heading.
      - Heading levels skip 1 time(s).
      ...
```

Score bands: 95–100 Zenith Excellence, 90–94 Superior Quality, 80–89 Strong Performance, 70–79 Acceptable Standard, below 70 Rejected.

Options: `--purpose "..."` and `--audience "..."` tell the grader what the document is for; `--json` prints the result as JSON; `--trace` prints the trace log; `-` reads from stdin instead of a file.

### `skribe polish` — grade and revise

```bash
skribe polish guide.md -o guide-polished.md
```

Runs the grade → revise loop: score the document, revise it, score again, and stop when the score reaches the target (default 90), when a cycle gains 1 point or less, when a revision would make things worse (the best version is kept), or when the cycle cap is hit (default 5). Without `-o`, the polished text prints to stdout.

The built-in reviser fixes structure and formatting only — heading levels, list markers, spacing, a missing metadata block. It never rewrites sentences or invents content. For deep revision, pass a reviser of your own through the library (see below).

Options: `--target`, `--min-gain`, `--max-cycles` set the loop caps; `--strict-pca` refuses to polish a document with no stated purpose or audience.

### `skribe verify` — check a finished file

```bash
skribe verify guide.md
```

Runs the output checks: under the 512 MB size cap, all seven scaffold sections present and in order, no duplicate or empty sections, no placeholder markers left, metadata present. Exit code 0 when everything passes, 1 when anything fails.

## From code

```python
from skribe import grade, polish, verify

result = grade(open("guide.md").read())
print(result.fzi, result.band)          # 57.41 Rejected
print(result.metrics["clarity"].score)  # per-metric scores + reasons

polished = polish(open("guide.md").read())
open("guide-polished.md", "w").write(polished.text)

report = verify(open("guide.md").read())
print(report.passed)                    # True / False
```

`grade()` returns a `GradeResult` (fzi, metrics, band, evs, citations, notes). `polish()` returns a `PolishResult` (text, initial/final FZI, cycles, exit reason, verification report, per-cycle history). `verify()` returns a `VerificationReport` (pass/fail per check).

## Scorers

Three scorers, one scoring formula — the FZI means the same thing whichever scorer produced it.

- **deterministic** (default): scores from the text itself. No model, no key, no network. Honest about its limits: it cannot verify facts, so accuracy is a defect check capped at 85, and domain fit without a stated purpose is judged against the title only, capped at 80. Both caps are named in the output.
- **prompt**: grade with any chat model. Pass a `chat` function (prompt → reply) and SKRIBE asks it for per-metric scores as JSON:
  ```python
  result = grade(text, scorer="prompt", chat=my_chat_fn)
  ```
- **decisions**: grade with the Gemini Decisions API — one request, one score question per metric, calibrated probabilities back, zero generated text. Needs a Gemini API key:
  ```bash
  skribe grade guide.md --scorer decisions --api-key "$GEMINI_API_KEY"
  ```
  or set `GEMINI_API_KEY` in the environment. The key goes only in the request header — never printed, logged, or stored. The Decisions free tier covers grading easily (200 requests/minute); a grading pass is one request per document. Note: free-tier data may be used by Google to improve its products.

## From an agent (MCP server)

```bash
skribe mcp
```

Serves SKRIBE over stdio as an MCP server with three tools: `skribe_grade`, `skribe_polish`, `skribe_verify`. Point any MCP client at the command and agents can grade, polish, and verify documents the same way the CLI does.

## How the score works

FZI = (Structure × 0.20) + (Accuracy × 0.20) + (Utility × 0.20) + (Clarity × 0.15) + (Depth × 0.15) + (Domain × 0.10), capped at 100. Accuracy is adjusted by the External Verifiability Score (EVS): 1.0 when 3 or more sources are cited, 0.9 for one or two, 0.8 when none are found, 0.5 when a contradiction is detected.

The loop is: PCA gate (purpose and audience) → scaffold → grade → revise → verify → trace log. The scorer only scores; the reviser only revises; the loop controller makes every continue/finalize decision.

Two notes on the spec this tool is built from:

- The spec set contains two scoring schemes. The older FCI document uses five metrics; the newer FZI controller v3.1 uses the six above. This tool implements the six-metric v3.1 scheme. The score bands are identical in both.
- The spec's loop condition ("while FZI < 110") can never end on its own, because FZI is capped at 100. This tool treats 110 as "above the cap" and loops against a configurable target (default 90) plus the spec's own stop rules: gain of 1 or less finalizes, and any degrading revision finalizes with the best version kept.

## Running the tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

The package lives under `src/`, so a bare clone needs `PYTHONPATH=src` for the test run (or `pip install -e .` first). 127 tests.

## License

MIT. See LICENSE.
