# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest

import os
from copy import deepcopy

from utils import run_subprocess
from ssf.results import *


def paths_from_log(stdout):
    log_keys = {
        "create_ssf_application_test_instance CWD:": None,
        "test begin CWD:": None,
        "test subtest CWD:": None,
        "test end CWD:": None,
        "create_ssf_application_instance CWD:": None,
        "build CWD:": None,
        "startup CWD:": None,
        "request CWD:": None,
        "shutdown CWD:": None,
        "is_healthy CWD:": None,
    }

    regular = deepcopy(log_keys)
    container = deepcopy(log_keys)

    for l in stdout:
        for k in log_keys.keys():
            if k in l:
                cwd = l.split("CWD:")[1].split(" ")[0]
                if "[docker logs]" in l:
                    container[k] = os.path.abspath(cwd)
                else:
                    regular[k] = os.path.abspath(cwd)

    return regular, container


@pytest.mark.fast
def test_regular_cwd():
    result, stdout, stderr = run_subprocess(
        [
            "gc-ssf",
            "--config",
            "tests/app_usecases/cwd/regular/ssf_config.yaml",
            "--stdout-log-level",
            "DEBUG",
            "init",
            "build",
            "package",
            "test",
        ]
    )
    assert result == RESULT_OK

    regular, container = paths_from_log(stdout)

    regular_expected_cwd = os.path.abspath(
        os.path.join(os.getcwd(), "tests/app_usecases/cwd/regular")
    )
    print(f"Regular {regular_expected_cwd} v {regular}")
    for k in regular.keys():
        assert regular[k] == None or regular[k] == regular_expected_cwd

    container_expected_cwd = os.path.abspath("/src/app")
    print(f"Container {container_expected_cwd} v {container}")
    for k in container.keys():
        assert container[k] == None or container[k] == container_expected_cwd

    # Check packaging contains the files we expect in the locations we expect.

    # Regular:
    # Generated artifacts
    assert os.path.isfile("ssf-cwd-regular-test-endpoint-0-fastapi.py")
    assert os.path.isfile("tests/app_usecases/cwd/regular/generated/a")
    assert os.path.isfile("tests/app_usecases/cwd/regular/generated/b")

    # Container:
    # Config
    assert os.path.isfile(".package/cwd-regular-test/src/app/ssf_config.yaml")
    # Application
    assert os.path.isfile(".package/cwd-regular-test/src/app/my_application.py")
    # Generated artifacts
    assert os.path.isfile(
        ".package/cwd-regular-test/src/ssf-cwd-regular-test-endpoint-0-fastapi.py"
    )
    assert os.path.isfile(".package/cwd-regular-test/src/app/generated/a")
    assert not os.path.isfile(
        ".package/cwd-regular-test/src/app/generated/b"
    )  # (Excluded)


@pytest.mark.fast
def test_complex_cwd():
    result, stdout, _ = run_subprocess(
        [
            "gc-ssf",
            "--config",
            "tests/app_usecases/cwd/complex/config/ssf_config.yaml",
            "--stdout-log-level",
            "DEBUG",
            "init",
            "build",
            "package",
            "test",
        ]
    )
    assert result == RESULT_OK

    regular, container = paths_from_log(stdout)

    regular_expected_cwd = os.path.abspath(
        os.path.join(os.getcwd(), "tests/app_usecases/cwd/complex_app")
    )
    print(f"Regular {regular_expected_cwd} v {regular}")
    for k in regular.keys():
        assert regular[k] == None or regular[k] == regular_expected_cwd

    container_expected_cwd = os.path.abspath("/src/app/complex_app")
    print(f"Container {container_expected_cwd} v {container}")
    for k in container.keys():
        assert container[k] == None or container[k] == container_expected_cwd

    # Check packaging contains the files we expect in the locations we expect.

    # Regular:
    # Generated artifacts
    assert os.path.isfile("ssf-cwd-complex-test-endpoint-0-fastapi.py")
    assert os.path.isfile("tests/app_usecases/cwd/complex_app/generated/a")
    assert os.path.isfile("tests/app_usecases/cwd/complex_app/generated/b")

    # Container:
    # Config
    assert os.path.isfile(
        ".package/cwd-complex-test/src/app/complex/config/ssf_config.yaml"
    )
    # Application
    assert os.path.isfile(
        ".package/cwd-complex-test/src/app/complex_app/my_application.py"
    )
    # Generated artifacts
    assert os.path.isfile(
        ".package/cwd-complex-test/src/ssf-cwd-complex-test-endpoint-0-fastapi.py"
    )
    assert os.path.isfile(".package/cwd-complex-test/src/app/complex_app/generated/a")
    assert not os.path.isfile(
        ".package/cwd-complex-test/src/app/complex_app/generated/b"
    )  # (Excluded)
