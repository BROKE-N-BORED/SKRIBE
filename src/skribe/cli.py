"""SKRIBE command line.

    skribe grade <file> [--scorer deterministic|decisions] [--json]
    skribe polish <file> [-o OUT] [--max-cycles N] [--target N]
    skribe verify <file> [--json]
    skribe mcp            (MCP server on stdio, for agents)

The built-in deterministic scorer needs no model and no key. The
Decisions scorer needs a Gemini API key: pass --api-key, or set
GEMINI_API_KEY in the environment. The key is never printed, logged,
or stored — it goes only in the request header.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, api as api_mod
from .loop import LoopConfig
from .prompt import ScorerError
from .trace import Trace


def _read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _print_grade(result, as_json):
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return
    print(f"FZI: {result.fzi:.2f} — {result.band}")
    print(f"  {result.band_action}")
    print(f"  Scorer: {result.scorer}  EVS: {result.evs}")
    for key in ("structure", "accuracy", "utility", "clarity",
                "depth", "domain"):
        metric = result.metrics[key]
        print(f"  {metric.name} ({metric.weight:.0%}): "
              f"{metric.score:.2f}")
        for reason in metric.rationale:
            print(f"      - {reason}")
    if result.citations:
        print(f"  Citations: {len(result.citations)} source(s)")
    for note in result.notes:
        print(f"  Note: {note}")


def _cmd_grade(args):
    text = _read(args.file)
    trace = Trace() if args.trace else None
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
    try:
        result = api_mod.grade(
            text, scorer=args.scorer, api_key=api_key or None,
            purpose=args.purpose, audience=args.audience, trace=trace)
    except (ScorerError, ValueError) as exc:
        print(f"grade failed: {exc}", file=sys.stderr)
        return 2
    _print_grade(result, args.json)
    if trace is not None:
        print(trace.render())
    return 0


def _cmd_polish(args):
    text = _read(args.file)
    trace = Trace() if args.trace else None
    config = LoopConfig(target_fzi=args.target,
                        min_gain=args.min_gain,
                        max_cycles=args.max_cycles)
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
    try:
        result = api_mod.polish(
            text, scorer=args.scorer, api_key=api_key or None,
            config=config, purpose=args.purpose,
            audience=args.audience, strict_pca=args.strict_pca,
            trace=trace)
    except (ScorerError, ValueError) as exc:
        print(f"polish failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"FZI: {result.initial_fzi:.2f} -> "
              f"{result.final_fzi:.2f} "
              f"({result.cycles_run} cycle(s), {result.exit_reason})")
        print(f"Verification: "
              f"{'PASS' if result.verification.passed else 'FAIL'}")
        for check in result.verification.failures:
            print(f"  FAIL {check.name}: {check.detail}")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(result.text)
        if not args.json:
            print(f"Wrote {args.output}")
    elif not args.json:
        print()
        print(result.text)
    if trace is not None:
        print(trace.render())
    return 0


def _cmd_verify(args):
    text = _read(args.file)
    trace = Trace() if args.trace else None
    report = api_mod.verify(text, trace=trace)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.render())
    if trace is not None:
        print(trace.render())
    return 0 if report.passed else 1


def _cmd_mcp(_args):
    from . import mcp_server
    return mcp_server.serve()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skribe",
        description="SKRIBE — score and polish written work with "
                    "the FZI rubric.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    grade = sub.add_parser("grade", help="Score a document.")
    grade.add_argument("file", help="File to grade ('-' for stdin).")
    grade.add_argument("--scorer", default="deterministic",
                       choices=["deterministic", "decisions"],
                       help="Scorer to use (default: deterministic).")
    grade.add_argument("--api-key", default="",
                       help="Gemini API key for the Decisions "
                            "scorer (or set GEMINI_API_KEY).")
    grade.add_argument("--purpose", default=None,
                       help="Stated purpose of the document.")
    grade.add_argument("--audience", default=None,
                       help="Intended audience.")
    grade.add_argument("--json", action="store_true",
                       help="Print the result as JSON.")
    grade.add_argument("--trace", action="store_true",
                       help="Print the trace log.")
    grade.set_defaults(func=_cmd_grade)

    polish = sub.add_parser("polish",
                            help="Grade and revise a document.")
    polish.add_argument("file", help="File to polish ('-' for stdin).")
    polish.add_argument("-o", "--output", default=None,
                        help="Write the polished file here "
                             "(default: print to stdout).")
    polish.add_argument("--scorer", default="deterministic",
                        choices=["deterministic", "decisions"],
                        help="Scorer to use (default: deterministic).")
    polish.add_argument("--api-key", default="",
                        help="Gemini API key for the Decisions "
                             "scorer (or set GEMINI_API_KEY).")
    polish.add_argument("--purpose", default=None)
    polish.add_argument("--audience", default=None)
    polish.add_argument("--target", type=float, default=90.0,
                        help="Stop when FZI reaches this (default: 90).")
    polish.add_argument("--min-gain", type=float, default=1.0,
                        help="Stop when a cycle gains this or less "
                             "(default: 1).")
    polish.add_argument("--max-cycles", type=int, default=5,
                        help="Most revision cycles to run (default: 5).")
    polish.add_argument("--strict-pca", action="store_true",
                        help="Refuse to polish when the PCA gate fails.")
    polish.add_argument("--json", action="store_true",
                        help="Print the result as JSON (not the text).")
    polish.add_argument("--trace", action="store_true",
                        help="Print the trace log.")
    polish.set_defaults(func=_cmd_polish)

    verify = sub.add_parser("verify",
                            help="Run the output-verification checks.")
    verify.add_argument("file", help="File to verify ('-' for stdin).")
    verify.add_argument("--json", action="store_true",
                        help="Print the report as JSON.")
    verify.add_argument("--trace", action="store_true",
                        help="Print the trace log.")
    verify.set_defaults(func=_cmd_verify)

    mcp = sub.add_parser("mcp",
                         help="Run the MCP server on stdio.")
    mcp.set_defaults(func=_cmd_mcp)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"skribe: {exc}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print("skribe: that file is not UTF-8 text",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
