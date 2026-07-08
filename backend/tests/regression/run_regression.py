"""
AuditOS Regression Harness
==========================
Runs all deterministic regression test suites and prints a colored summary.

Usage:
    python backend/tests/regression/run_regression.py
    python backend/tests/regression/run_regression.py --suite gst_math
    python backend/tests/regression/run_regression.py --suite itc_rules
    python backend/tests/regression/run_regression.py --suite gstr2b
    python backend/tests/regression/run_regression.py --suite reconciliation
    python backend/tests/regression/run_regression.py --suite validation
    python backend/tests/regression/run_regression.py --fail-fast
    python backend/tests/regression/run_regression.py -v        # verbose test names

Exit code:
    0  — all suites passed
    1  — one or more suites had failures or errors
"""
import sys
import os
import time
import unittest
import argparse
import io

# Force UTF-8 output on Windows so box-drawing / unicode chars don't crash cp1252
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # Python < 3.7 fallback

# Ensure project root is on sys.path when invoked from anywhere
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "../../.."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── ANSI colors (disabled when stdout is not a TTY) ──────────────────────────

def _has_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_C = {
    "reset":  "\033[0m"  if _has_color() else "",
    "bold":   "\033[1m"  if _has_color() else "",
    "red":    "\033[91m" if _has_color() else "",
    "green":  "\033[92m" if _has_color() else "",
    "yellow": "\033[93m" if _has_color() else "",
    "cyan":   "\033[96m" if _has_color() else "",
    "dim":    "\033[2m"  if _has_color() else "",
}


def _c(color: str, text: str) -> str:
    return f"{_C[color]}{text}{_C['reset']}"


# ── Suite registry ────────────────────────────────────────────────────────────

SUITES = {
    "gst_math": {
        "label": "GST Tax Mathematics (TaxMathematicsEngine)",
        "module": "backend.tests.regression.test_gst_math",
    },
    "reconciliation": {
        "label": "Financial Reconciliation Engine (8-stage)",
        "module": "backend.tests.regression.test_reconciliation_regression",
    },
    "validation": {
        "label": "Validation Engine + All 5 Packs",
        "module": "backend.tests.regression.test_validation_regression",
    },
    "itc_rules": {
        "label": "ITC Eligibility — Section 17(5) Hard Blocks",
        "module": "backend.tests.regression.test_itc_rules_regression",
    },
    "gstr2b": {
        "label": "GSTR-2B Reconciliation Engine",
        "module": "backend.tests.regression.test_gstr2b_regression",
    },
    "sales_line_items": {
        "label": "Sales Line-Item Extraction (deterministic, OneStack template)",
        "module": "backend.tests.regression.test_sales_line_item_extraction",
    },
    "credit_notes": {
        "label": "Credit Note Extraction (deterministic, OneStack template)",
        "module": "backend.tests.regression.test_credit_note_extraction",
    },
    "client_sheet": {
        "label": "Client Sheet Parser (OneStack masterdata schema)",
        "module": "backend.tests.regression.test_client_sheet_parser",
    },
}


# ── Test runner ───────────────────────────────────────────────────────────────

def _run_suite(name: str, module_path: str, verbose: bool) -> dict:
    """Load and run a single test module. Returns result dict."""
    import importlib

    t_start = time.monotonic()
    try:
        mod = importlib.import_module(module_path)
    except Exception as exc:
        elapsed = time.monotonic() - t_start
        return {
            "name": name,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "elapsed": elapsed,
            "import_error": str(exc),
            "output": "",
        }

    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(mod)

    buf = io.StringIO()
    runner = unittest.TextTestRunner(
        stream=buf,
        verbosity=2 if verbose else 1,
        failfast=False,
    )
    result = runner.run(suite)
    elapsed = time.monotonic() - t_start

    return {
        "name": name,
        "passed":  result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        "failed":  len(result.failures),
        "errors":  len(result.errors),
        "skipped": len(result.skipped),
        "elapsed": elapsed,
        "import_error": None,
        "output": buf.getvalue(),
        "failures": result.failures,
        "test_errors": result.errors,
    }


# ── Formatting helpers ────────────────────────────────────────────────────────

def _suite_header(label: str) -> str:
    width = 72
    pad = max(0, width - len(label) - 4)
    return f"{_c('cyan', '┌─')} {_c('bold', label)} {_c('dim', '─' * pad + '┐')}"


def _suite_footer(r: dict) -> str:
    ok    = r["passed"]
    fail  = r["failed"] + r["errors"]
    skip  = r["skipped"]
    ms    = r["elapsed"] * 1000

    status = _c("green", f"PASS  {ok} passed") if fail == 0 else _c("red", f"FAIL  {ok} passed, {fail} failed")
    skip_s = f"  {_c('yellow', str(skip) + ' skipped')}" if skip else ""
    return f"{_c('dim', '└─')} {status}{skip_s}  {_c('dim', f'{ms:.0f}ms')}"


def _print_failures(r: dict) -> None:
    for label, tb in r.get("failures", []):
        print(f"\n  {_c('red', '✗')} {label}")
        for line in tb.strip().splitlines():
            print(f"    {_c('dim', line)}")
    for label, tb in r.get("test_errors", []):
        print(f"\n  {_c('red', '⚠')} ERROR — {label}")
        for line in tb.strip().splitlines():
            print(f"    {_c('dim', line)}")


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="AuditOS Regression Harness")
    parser.add_argument("--suite",     choices=list(SUITES.keys()),
                        help="Run a single suite instead of all")
    parser.add_argument("--fail-fast", action="store_true",
                        help="Stop after first suite with failures")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show individual test names")
    args = parser.parse_args()

    suites_to_run = (
        {args.suite: SUITES[args.suite]} if args.suite else SUITES
    )

    print()
    print(_c("bold", "━" * 72))
    print(_c("bold", "  AuditOS Regression Harness"))
    print(_c("dim",  f"  {len(suites_to_run)} suite(s) · deterministic layer only · no LLM calls"))
    print(_c("bold", "━" * 72))
    print()

    all_results = []
    overall_start = time.monotonic()

    for name, meta in suites_to_run.items():
        print(_suite_header(meta["label"]))

        r = _run_suite(name, meta["module"], args.verbose)
        all_results.append(r)

        if r["import_error"]:
            print(f"  {_c('red', 'IMPORT ERROR')} — {r['import_error']}")
        elif args.verbose:
            # Print buffered unittest output indented
            for line in r["output"].splitlines():
                print(f"  {_c('dim', line)}")

        if r["failed"] or r["errors"]:
            _print_failures(r)

        print(_suite_footer(r))
        print()

        if args.fail_fast and (r["failed"] or r["errors"] or r["import_error"]):
            print(_c("yellow", "  ── Stopped early (--fail-fast) ──"))
            break

    # ── Overall summary ───────────────────────────────────────────────────────

    total_elapsed = time.monotonic() - overall_start
    total_passed  = sum(r["passed"]  for r in all_results)
    total_failed  = sum(r["failed"]  for r in all_results)
    total_errors  = sum(r["errors"]  for r in all_results) + sum(1 for r in all_results if r["import_error"])
    total_skipped = sum(r["skipped"] for r in all_results)
    total_tests   = total_passed + total_failed + total_errors + total_skipped

    print(_c("bold", "━" * 72))
    print(_c("bold", "  SUMMARY"))
    print(_c("bold", "━" * 72))
    print()

    col_w = max(len(SUITES[k]["label"]) for k in SUITES) + 2
    for r in all_results:
        meta_label = SUITES[r["name"]]["label"]
        fail_total = r["failed"] + r["errors"] + (1 if r["import_error"] else 0)
        if fail_total == 0:
            status = _c("green", "✓ PASS")
        else:
            status = _c("red",   "✗ FAIL")
        ms = r["elapsed"] * 1000
        print(f"  {status}  {meta_label:<{col_w}}  {_c('dim', f'{ms:>6.0f}ms')}")

    print()
    total_status = "ALL PASSED" if (total_failed + total_errors) == 0 else "FAILURES DETECTED"
    color = "green" if (total_failed + total_errors) == 0 else "red"
    print(f"  {_c(color, _c('bold', total_status))}")
    print(f"  {_c('dim', f'{total_tests} tests · {total_passed} passed · {total_failed + total_errors} failed · {total_skipped} skipped · {total_elapsed*1000:.0f}ms total')}")
    print()

    return 0 if (total_failed + total_errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
