# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os
import pytest
from ssf import cli as ssf_cli
from ssf.results import *

from test_bash_cli import example_simple_expected_endpoints
from utils import get_stdout_stderr

# We don't need much here since this won't be the primary entry-point.
# Just check it can work for some small subset of tests.


@pytest.mark.fast
def test_python_cli(capfd):
    for f in example_simple_expected_endpoints:
        if os.path.isfile(f):
            os.remove(f)

    result = ssf_cli.run(
        ["--config", "examples/simple/ssf_config.yaml", "init", "build"]
    )
    stdout, stderr = get_stdout_stderr(capfd)

    assert result == RESULT_OK
    for f in example_simple_expected_endpoints:
        assert os.path.isfile(f)
