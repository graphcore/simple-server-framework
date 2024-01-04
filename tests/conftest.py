# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
from utils import print_header_separator

# Use tests report_summary hooks to generate a pytest.tests.report.md
from report_summary import *

report_summary_set_name("pytest.tests.report.md")


@pytest.fixture(scope="function", autouse=True)
def test_log_bracket(request):
    def bracket_begin():
        print_header_separator(f"Begin test {request.node.nodeid}")

    def bracket_end():
        print_header_separator(f"End test {request.node.nodeid}")

    bracket_begin()
    request.addfinalizer(bracket_end)


def pytest_addoption(parser):
    parser.addoption(
        "--port",
        action="store",
        default=8200,
        help="Port on which test server will start",
    )


def pytest_configure(config):
    pytest.server_port = config.getoption("--port")


@pytest.fixture
def port(request):
    return request.config.getoption("--port")
