# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os
import pytest
from pathlib import Path
import utils
from ssf.application_interface.results import *

# TODO:
# Add more Bash CLI tests

bash_cli_expected_endpoints = [
    "ssf-cli-endpoint-0-fastapi.py",
]

bash_cli_config = "tests/app_usecases/bash_cli.yaml"


@pytest.mark.parametrize(
    "api, expected_endpoint_files",
    [
        (None, bash_cli_expected_endpoints),
        ("grpc", []),
        ("fastapi", bash_cli_expected_endpoints),
    ],
)
class TestBashCLI:
    @pytest.mark.fast
    def test_example_cli_build(self, api, expected_endpoint_files):
        for f in bash_cli_expected_endpoints:
            if os.path.isfile(f):
                os.remove(f)

        result, stdout, stderr = utils.run_subprocess(
            ["gc-ssf", "--config", bash_cli_config, "init", "build"]
            + (["--api", api] if api else [])
        )

        assert result == RESULT_OK
        for f in expected_endpoint_files:
            assert os.path.isfile(f)

    @pytest.mark.fast
    def test_example_cli_build_outside_projectdir(self, api, expected_endpoint_files):
        altered_cwd = "../"

        if not os.path.exists(altered_cwd):
            assert (
                False
            ), "Test cannot be run from this directory since it doesn't have parent directory"

        ssf_dir_path_relative_to_altered = Path(os.getcwd()).relative_to(
            os.path.realpath(altered_cwd)
        )

        for f in expected_endpoint_files:
            if os.path.isfile(os.path.join(altered_cwd, f)):
                os.remove(os.path.join(altered_cwd, f))

        result, _, _ = utils.run_subprocess(
            [
                "gc-ssf",
                "--config",
                os.path.join(ssf_dir_path_relative_to_altered, bash_cli_config),
                "init",
                "build",
            ]
            + (["--api", api] if api else []),
            cwd=altered_cwd,
        )

        assert result == RESULT_OK
        for f in expected_endpoint_files:
            assert os.path.isfile(os.path.join(altered_cwd, f))

    @pytest.mark.fast
    def test_example_cli_init(self, api, expected_endpoint_files):
        for f in expected_endpoint_files:
            with open(f, mode="a"):
                pass
            assert os.path.isfile(f)

        result, stdout, stderr = utils.run_subprocess(
            ["gc-ssf", "--config", bash_cli_config, "init"]
            + (["--api", api] if api else [])
        )

        assert result == RESULT_OK
        for f in expected_endpoint_files:
            assert not os.path.isfile(f)


@pytest.mark.fast
class TestsUnknownArgs(utils.TestClient):
    def configure(self):
        self.config_file = bash_cli_config
        # Issue a mix of known and unknown commands and arguments in an odd order.
        self.ssf_commands = ["build", "--unknown", "run", "X", "init", "Y"]

    def test_args_in_application(self):
        # Force stop.
        assert self.is_ready
        assert self.process_is_running()
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_OK to indicate there were no failures.
        assert self.is_ready
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_OK
        assert self.server_stopped()

        # Assert expected trace in log generated by SSF.
        assert self.is_string_in_logs("==== Init ====")
        assert self.is_string_in_logs("==== Build ====")
        assert self.is_string_in_logs("==== Run ====")
        assert self.is_string_in_logs("Ignoring unknown arguments ['--unknown']")
        assert self.is_string_in_logs("Ignoring unknown SSF commands ['X', 'Y']")

        # Assert expected trace in log generated by app_usecase/bash_cli.py.
        assert self.is_string_in_logs("bash_cli : unknown_args=['--unknown']")
        assert self.is_string_in_logs(
            "bash_cli : commands=['X', 'Y', 'build', 'run', 'init']"
        )
