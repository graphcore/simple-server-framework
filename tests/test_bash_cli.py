# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os
import pytest
from utils import run_subprocess
from ssf.results import *


# TODO:
# Add more Bash CLI tests

example_simple_expected_endpoints = [
    "ssf-simple-test-endpoint-0-fastapi.py",
    "ssf-simple-test-endpoint-1-fastapi.py",
]


@pytest.mark.fast
def test_example_simple_build():
    for f in example_simple_expected_endpoints:
        if os.path.isfile(f):
            os.remove(f)

    result, stdout, stderr = run_subprocess(
        ["gc-ssf", "--config", "examples/simple/ssf_config.yaml", "build"]
    )
    assert result == RESULT_OK
    for f in example_simple_expected_endpoints:
        assert os.path.isfile(f)


@pytest.mark.fast
def test_example_simple_init():
    for f in example_simple_expected_endpoints:
        with open(f, mode="a"):
            pass
        assert os.path.isfile(f)
    result, stdout, stderr = run_subprocess(
        ["gc-ssf", "--config", "examples/simple/ssf_config.yaml", "init"]
    )
    assert result == RESULT_OK
    for f in example_simple_expected_endpoints:
        assert not os.path.isfile(f)
