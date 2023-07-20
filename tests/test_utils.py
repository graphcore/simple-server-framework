# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import sys
from utils import run_subprocess, get_stdout_stderr


@pytest.mark.fast
def test_run_subprocess():

    result, stdout, stderr = run_subprocess(["echo", "bob"])
    assert result == 0
    assert "bob" in stdout[0]

    result, stdout, stderr = run_subprocess(["cat", "bob"])
    assert result != 0
    assert "bob" in stderr[0]

    slit = """hello
goodbye"""
    result, stdout, stderr = run_subprocess(["cat"], slit.encode())
    assert result == 0
    assert stdout[0] == "hello"
    assert stdout[1] == "goodbye"


@pytest.mark.fast
def test_get_stdout_stderr(capfd):
    print("hello")
    print("goodbye")
    sys.stderr.write("No errors here")

    stdout, stderr = get_stdout_stderr(capfd)
    assert stdout[0] == "hello"
    assert stdout[1] == "goodbye"
    assert stderr[0] == "No errors here"
