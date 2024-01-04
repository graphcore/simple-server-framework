# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import utils
import pytest
import time
import os

from ssf.results import RESULT_OK, RESULT_APPLICATION_MODULE_ERROR


@pytest.mark.fast
class TestAmbiguousBuilder(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/ambiguous_builder.yaml"
        self.wait_ready = False
        self.ssf_commands = ["init", "build"]

    def test_main(self):
        self.wait_process_exit()
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_MODULE_ERROR
        assert self.server_stopped()
        assert self.is_string_in_logs(
            "Only one application main interface should be defined"
        )


@pytest.mark.fast
class TestsImplicitBuildAndTest(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/implicit_builder.yaml"
        self.ssf_commands = ["init", "build", "package", "test"]
        self.wait_ready = False

    def test_main(self):
        self.wait_process_exit()
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK
        assert self.is_string_in_logs(
            "Found <class 'implicit-builder-test.MyApplicationTest'>"
        )


@pytest.mark.fast
class TestsImplicitBuilderReplicateApp(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/implicit_builder.yaml"
        self.worker_replicas = 2

    def test_main(self):
        assert self.is_ready
        assert self.is_string_in_logs("Dispatcher ready")
        # Force stop.
        self.stop_process()
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK

    def test_num_workers_ok(self):
        assert len(self.workers_pid) == 2, f"Worker pids {self.workers_pid}"


@pytest.mark.fast
class TestsConfigImplicitBuilder(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/config_implicit_builder.yaml"
        self.ssf_commands = ["init", "build", "package", "test"]
        self.wait_ready = False

    def test_main(self):
        self.wait_process_exit()
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK
        assert self.is_string_in_logs(
            "Found <class 'config-implicit-builder-test.MyApplication'>"
        )
        assert self.is_string_in_logs(
            "Found <class 'config-implicit-builder-test.MyApplicationTest'>"
        )


@pytest.mark.fast
class TestsConfigExplicitBuilder(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/config_explicit_builder.yaml"
        self.ssf_commands = ["init", "build", "package", "test"]
        self.wait_ready = False

    def test_main(self):
        self.wait_process_exit()
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK
        assert self.is_string_in_logs(
            "Application instantiated by user-defined function`create_ssf_application_instance`"
        )
        assert self.is_string_in_logs(
            "Application instantiated by user-defined function`create_ssf_application_test_instance`"
        )
