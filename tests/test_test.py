# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
from utils import run_subprocess
from ssf.results import *


@pytest.mark.fast
def test_test(port):
    result, _, _ = run_subprocess(
        [
            "gc-ssf",
            "--config",
            "examples/simple/ssf_config.yaml",
            "--stdout-log-level",
            "DEBUG",
            "--port",
            str(port),
            "init",
            "build",
            "package",
            "test",
        ]
    )
    assert result == RESULT_OK
