"""Record per-job pytest results and publish a compact workflow summary."""

from __future__ import print_function

import argparse
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


COUNT_FIELDS = ("total", "successful", "failed", "skipped")


def _integer_attribute(elements, name):
    values = [element.attrib[name] for element in elements if name in element.attrib]
    if not values:
        return None
    return sum(int(value) for value in values)


def _float_attribute(elements, name):
    values = [element.attrib[name] for element in elements if name in element.attrib]
    if not values:
        return None
    return sum(float(value) for value in values)


def parse_junit(path):
    """Return pytest/JUnit test counts from *path*."""
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    testcases = list(root.iter("testcase"))

    total = _integer_attribute(suites, "tests")
    failures = _integer_attribute(suites, "failures")
    errors = _integer_attribute(suites, "errors")
    skipped = _integer_attribute(suites, "skipped")
    duration = _float_attribute(suites, "time")

    if total is None:
        total = len(testcases)
    if failures is None:
        failures = sum(1 for case in testcases if case.find("failure") is not None)
    if errors is None:
        errors = sum(1 for case in testcases if case.find("error") is not None)
    if skipped is None:
        skipped = sum(1 for case in testcases if case.find("skipped") is not None)

    # A collection/setup error can be represented without a testcase and with
    # tests="0". Count that error in the reported total rather than displaying
    # more failed tests than total tests.
    total = max(total, failures + errors + skipped)
    failed = failures + errors
    successful = max(total - failed - skipped, 0)
    return {
        "total": total,
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "duration_seconds": duration,
    }


def _escape_workflow_message(message):
    return (message.replace("%", "%25")
            .replace("\r", "%0D")
            .replace("\n", "%0A"))


def _status_for_outcome(outcome):
    return {
        "success": "passed",
        "failure": "failed",
        "cancelled": "cancelled",
        "skipped": "not-run",
    }.get(outcome, "unknown")


def record_result(args):
    result = {
        "label": args.label,
        "outcome": args.outcome,
        "status": _status_for_outcome(args.outcome),
    }
    try:
        result.update(parse_junit(Path(args.xml)))
    except (OSError, ET.ParseError, ValueError) as error:
        result.update({field: None for field in COUNT_FIELDS})
        result["errors"] = None
        result["duration_seconds"] = None
        result["report_error"] = str(error)

    output_path = Path(args.json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    if args.outcome == "failure":
        if result["total"] is None:
            message = "%s: test step failed; no readable JUnit report was produced" % args.label
        else:
            message = ("%s: %d successful, %d failed, %d skipped (%d total)"
                       % (args.label, result["successful"], result["failed"],
                          result["skipped"], result["total"]))
        print("::error title=Tests failed::%s" % _escape_workflow_message(message))
    return 0


def _display_count(value):
    return "—" if value is None else str(value)


def _display_duration(value):
    return "—" if value is None else "%.1fs" % value


def _display_status(status):
    return {
        "passed": "✅ Passed",
        "failed": "❌ Failed",
        "cancelled": "⚪ Cancelled",
        "not-run": "⏭️ Not run",
        "unknown": "⚠️ Unknown",
    }.get(status, "⚠️ Unknown")


def _aggregate_status(results):
    statuses = {result.get("status") for result in results}
    if "failed" in statuses:
        return "❌ Failed"
    if "cancelled" in statuses:
        return "⚪ Cancelled"
    if statuses.intersection({"not-run", "unknown"}):
        return "⚠️ Incomplete"
    return "✅ Passed"


def _markdown_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_aggregate(args):
    results = []
    for path in sorted(Path(args.results_dir).rglob("test-result.json")):
        try:
            results.append(json.loads(path.read_text()))
        except (OSError, ValueError) as error:
            results.append({
                "label": str(path),
                "status": "unknown",
                "total": None,
                "successful": None,
                "failed": None,
                "skipped": None,
                "duration_seconds": None,
                "report_error": str(error),
            })

    lines = ["## Wheel test results", ""]
    if not results:
        lines.append("No test result records were produced.")
    else:
        lines.extend([
            "| Test job | Result | Successful | Failed | Skipped | Total | Duration |",
            "|---|---|---:|---:|---:|---:|---:|",
        ])
        for result in results:
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s |" % (
                    _markdown_cell(result.get("label", "unknown")),
                    _display_status(result.get("status")),
                    _display_count(result.get("successful")),
                    _display_count(result.get("failed")),
                    _display_count(result.get("skipped")),
                    _display_count(result.get("total")),
                    _display_duration(result.get("duration_seconds")),
                )
            )

        complete_results = [result for result in results
                            if all(result.get(field) is not None for field in COUNT_FIELDS)]
        if complete_results:
            lines.append(
                "| **Total** | **%s** | **%d** | **%d** | **%d** | **%d** | — |" % (
                    _aggregate_status(results),
                    sum(result["successful"] for result in complete_results),
                    sum(result["failed"] for result in complete_results),
                    sum(result["skipped"] for result in complete_results),
                    sum(result["total"] for result in complete_results),
                )
            )
        lines.extend([
            "",
            "Failed includes pytest assertion failures and test errors.",
        ])
        if len(complete_results) != len(results):
            lines.append("Rows without a readable JUnit report are omitted from the totals.")

    summary_path = Path(args.summary_file)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a") as summary:
        summary.write("\n".join(lines) + "\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    record = subparsers.add_parser("record", help="record one matrix job result")
    record.add_argument("--xml", required=True, help="pytest JUnit XML path")
    record.add_argument("--json", required=True, help="per-job JSON output path")
    record.add_argument("--label", required=True, help="human-readable matrix job label")
    record.add_argument("--outcome", required=True, help="test step outcome")

    aggregate = subparsers.add_parser("aggregate", help="write the final Markdown summary")
    aggregate.add_argument("--results-dir", required=True, help="downloaded result artifact directory")
    aggregate.add_argument("--summary-file", default=None,
                           help="summary output path (defaults to GITHUB_STEP_SUMMARY)")

    args = parser.parse_args(argv)
    if args.command == "record":
        return record_result(args)
    if args.command == "aggregate":
        args.summary_file = args.summary_file or os.environ.get("GITHUB_STEP_SUMMARY")
        if not args.summary_file:
            parser.error("aggregate requires --summary-file or GITHUB_STEP_SUMMARY")
        return write_aggregate(args)
    parser.error("a command is required")


if __name__ == "__main__":
    sys.exit(main())
