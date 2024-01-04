# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
from ssf.app_venv import create_app_venv
from ssf.load_config import ConfigGenerator
import os
import shutil
import utils
import pytest
import sys
import requests
import subprocess
from typing import List


def check_pip_packages(venv_dir: str, packages: List[str]):
    out = subprocess.check_output([venv_dir + "/bin/python", "-m", "pip", "list"])
    for p in packages:
        assert p.casefold() in str(out).casefold(), f"{p} missing from venv {venv_dir}"


@pytest.mark.fast
def test_app_venv_creation_list():

    yaml_path = "tests/app_usecases/req_list.yaml"
    config = ConfigGenerator(yaml_path, True).load()

    expected = os.path.realpath(
        os.path.join(os.getcwd(), f"ssf-{config.application.id}-venv")
    )
    assert config.application.venv_dir == expected, "Error: Wrong app venv dir"

    # Clean if already created by other tests
    if os.path.isdir(config.application.venv_dir):
        shutil.rmtree(config.application.venv_dir)

    create_app_venv(config)
    assert os.path.isdir(config.application.venv_dir), "Error: Failed creating app venv"
    check_pip_packages(config.application.venv_dir, ["numpy", "matplotlib"])
    shutil.rmtree(config.application.venv_dir)


@pytest.mark.fast
def test_app_venv_creation_mix():

    yaml_path = "tests/app_usecases/req_mix.yaml"
    config = ConfigGenerator(yaml_path, True).load()

    expected = os.path.realpath(
        os.path.join(os.getcwd(), f"ssf-{config.application.id}-venv")
    )
    assert config.application.venv_dir == expected, "Error: Wrong app venv dir"

    # Clean if already created by other tests
    if os.path.isdir(config.application.venv_dir):
        shutil.rmtree(config.application.venv_dir)

    create_app_venv(config)
    assert os.path.isdir(config.application.venv_dir), "Error: Failed creating app venv"
    check_pip_packages(config.application.venv_dir, ["numpy", "matplotlib", "pillow"])
    shutil.rmtree(config.application.venv_dir)


@pytest.mark.fast
def test_zero_dependencies():
    """
    Make sure worker has zero external dependencies
    """

    subprocess.check_output(["python", "-m", "venv", "raw_venv"])
    process = subprocess.run(
        ["raw_venv/bin/python", "ssf/worker.py", "-1"], capture_output=True, text=True
    )
    stderr = process.stderr
    if "ModuleNotFoundError" in stderr:
        print(stderr)
        raise ModuleNotFoundError


@pytest.mark.fast
class TestsSeparatePackage(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/check_package.yaml"
        config = ConfigGenerator(self.config_file, True).load()
        self.venv_dir = config.application.venv_dir
        expected = os.path.realpath(
            os.path.join(os.getcwd(), f"ssf-{config.application.id}-venv")
        )
        assert self.venv_dir == expected, "Error: Wrong app venv dir"

    def test_check_environment(self):
        assert self.is_string_in_logs("build import:")
        version = str(sys.version_info[0]) + "." + str(sys.version_info[1])
        assert self.is_string_in_logs(
            f"{self.venv_dir}/lib/python{version}/site-packages/google/protobuf/__init__.py"
        )
        assert self.is_string_in_logs("build executable:")
        assert self.is_string_in_logs(f"{self.venv_dir}/bin/python")

    def test_runtime_import_correct_package(self):
        response = requests.post(
            self.base_url + "/v1/Test1",
            json={"x": 0},
            headers={"accept": "application/json"},
            timeout=5,
        )
        assert response.status_code == 200
        assert response.text == '{"response":"ok"}'
        shutil.rmtree(self.venv_dir)
