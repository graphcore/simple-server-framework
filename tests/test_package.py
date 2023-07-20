# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
from utils import run_subprocess
from ssf.results import *


@pytest.mark.slow
def test_package_with_req_file():
    result, stdout, stderr = run_subprocess(
        [
            "gc-ssf",
            "--config",
            "tests/app_usecases/req_file.yaml",
            "init",
            "build",
            "package",
        ]
    )
    assert result == RESULT_OK


@pytest.mark.slow
def test_package_with_req_list():
    result, stdout, stderr = run_subprocess(
        [
            "gc-ssf",
            "--config",
            "tests/app_usecases/req_list.yaml",
            "init",
            "build",
            "package",
        ]
    )
    assert result == RESULT_OK


@pytest.mark.fast
def test_self_package():
    result, stdout, stderr = run_subprocess(
        [
            "gc-ssf",
            "package",
        ]
    )
    assert result == RESULT_OK
