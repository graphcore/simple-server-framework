# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest

summary_report = {"name": "tests"}


def report_summary_set_name(name):
    summary_report["name"] = name


@pytest.hookimpl
def pytest_sessionstart(session):
    summary_report["report_total"] = 0
    summary_report["report_skipped"] = 0
    summary_report["report_passed"] = 0
    summary_report["tests"] = {}


@pytest.hookimpl
def pytest_report_teststatus(report, config):
    if not report.nodeid in summary_report["tests"]:
        summary_report["tests"][report.nodeid] = {
            "test": report.nodeid,
            "passed": False,
            "skipped": False,
        }
        summary_report["report_total"] += 1
    if report.outcome == "skipped":
        summary_report["tests"][report.nodeid]["skipped"] = True
        summary_report["report_skipped"] += 1
    if report.when == "call" and report.outcome == "passed":
        summary_report["tests"][report.nodeid]["passed"] = True
        summary_report["report_passed"] += 1


@pytest.hookimpl
def pytest_sessionfinish(session, exitstatus):
    print("\n--- session finish ---\n")
    print(f"exitstatus:{exitstatus}")
    print(f"summary:{summary_report}")

    def prefix_colour(result):
        if result["skipped"]:
            return '<span style="color:yellow">'
        elif result["passed"]:
            return '<span style="color:lightgreen">'
        return '<span style="color:red">'

    def postfix_colour(result):
        return "</span>"

    def colourise(s, result):
        return f"{prefix_colour(result)}{s}{postfix_colour(result)}"

    def run_string(result):
        return f"{colourise('⚠️' if result['skipped'] else '✓', result)}"

    def test_string(result):
        return f"{colourise(result['test'], result)}"

    def passed_string(result):
        return f"{colourise('' if result['skipped'] else '✅' if result['passed'] else '❌', result)}"

    report_total = summary_report["report_total"]
    report_skipped = summary_report["report_skipped"]
    report_passed = summary_report["report_passed"]
    failed = report_total - report_skipped - report_passed

    report_filename = summary_report["name"]

    with open(report_filename, "wt") as report:
        report.write('\n<div style="color:white;background-color:black;">\n\n')

        report.write("# Pytest Report\n\n")

        report.write("## Summary\n\n")

        report.write("|  |   |\n")
        report.write("| -| - |\n")
        report.write(f"| Total | {report_total} |\n")
        report.write(f"| Skipped | {report_skipped} |\n")
        report.write(f"| Passed | {report_passed} |\n")
        report.write(f"| Failed | {failed} |\n\n")

        report.write("❌\n\n" if failed else "✅\n\n")

        report.write("## Detail\n\n")

        report.write("| Test | Run | Passed |\n")
        report.write("| ---- | --- | ------ |\n")

        for _, result in summary_report["tests"].items():
            print(result)
            report.write(
                f"| {test_string(result)} | {run_string(result)} | {passed_string(result)} |\n"
            )

        report.write("\n</div>\n\n")

        print(f"Generated report in {report_filename}\n")

    print("\n----------------------\n")
