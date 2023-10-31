# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import grpc
import pytest
import requests
from ssf.utils import API_FASTAPI, API_GRPC
import utils
import time
import yaml
import json
import os

from ssf.results import (
    RESULT_OK,
    RESULT_APPLICATION_ERROR,
    RESULT_APPLICATION_CONFIG_ERROR,
    RESULT_APPLICATION_MODULE_ERROR,
    RESULT_PACKAGING_ERROR,
    RESULT_DOCKER_SERVER_ERROR,
    RESULT_DEPLOYMENT_ERROR,
    RESULT_GCORE_DEPLOYMENT_ERROR,
    RESULT_PAPERSPACE_DEPLOYMENT_ERROR,
    RESULT_SSH_ERROR,
    RESULT_GIT_REPO_ERROR,
    RESULT_UNMET_REQUIREMENT,
)


@pytest.mark.fast
class TestsErrorCorruptConfig(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_0.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit()
        # Expect RESULT_APPLICATION_CONFIG_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_CONFIG_ERROR


@pytest.mark.fast
class TestsErrorCorruptModule(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_1.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit()
        # Expect RESULT_APPLICATION_MODULE_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_MODULE_ERROR


@pytest.mark.fast
class TestsErrorMissingClassFunctions(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_2.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit()
        # Expect RESULT_APPLICATION_MODULE_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_MODULE_ERROR

        assert self.is_string_in_logs(
            "Can't instantiate abstract class MyApplication with abstract methods"
        )
        assert self.is_string_in_logs(
            "Could not create simple-test application main interface"
        )


@pytest.mark.fast
class TestsErrorMissingNonClassFunctions(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_3.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit()
        # Expect RESULT_APPLICATION_MODULE_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_MODULE_ERROR

        assert self.is_string_in_logs("Interface 'build' missing or not callable")
        assert self.is_string_in_logs("Interface 'startup' missing or not callable")
        assert self.is_string_in_logs("Interface 'request' missing or not callable")
        assert self.is_string_in_logs("Interface 'shutdown' missing or not callable")
        assert self.is_string_in_logs("Interface 'watchdog' missing or not callable")


@pytest.mark.fast
@pytest.mark.dependency()
class TestsErrorTestInterfacePrecursor(utils.TestClient):
    # Package the test app first (one-time) so it is already
    # available to the set of TestsErrorsTestInterface*** tests.
    def configure(self):
        self.config_file = "tests/app_usecases/error_9.yaml"
        self.wait_ready = False
        self.ssf_commands = ["init", "build", "package"]

    def test_precursor(self):
        # This test issues 'package' to completion which can take some time on a clean system
        # when all layers need to be pulled/cached.
        self.wait_process_exit(timeout=300)
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsErrorTestInterfacePrecursor::test_precursor"])
class TestsErrorTestInterfaceMissingClassFunctions(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_9.yaml"
        self.wait_ready = False
        self.ssf_commands = ["test"]

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_APPLICATION_MODULE_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_MODULE_ERROR

        assert self.is_string_in_logs(
            "Can't instantiate abstract class MyApplicationTest with abstract methods"
        )
        assert self.is_string_in_logs(
            "Could not create simple-test application test interface"
        )


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsErrorTestInterfacePrecursor::test_precursor"])
class TestsErrorTestInterfaceMissingNonClassFunctions(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_10.yaml"
        self.wait_ready = False
        self.ssf_commands = ["test"]

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_APPLICATION_MODULE_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_MODULE_ERROR

        assert self.is_string_in_logs("Interface 'begin' missing or not callable")
        assert self.is_string_in_logs("Interface 'subtest' missing or not callable")
        assert self.is_string_in_logs("Interface 'end' missing or not callable")


@pytest.mark.fast
class TestsErrorPackageSkipBuild(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = ["init", "package"]
        self.wait_ready = False

    def test_exit_after_success(self):
        # This test issues 'package' to completion (at least for gRPC)
        # which can take some time on a clean system
        # when all layers need to be pulled/cached.
        self.wait_process_exit(timeout=300)
        # Expect RESULT_PACKAGE_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        if self.api == API_FASTAPI:
            assert self.get_return_code() == RESULT_PACKAGING_ERROR
            assert self.is_string_in_logs("Missing endpoint file")
        elif self.api == API_GRPC:
            # No endpoint files are expected so packaging is ok
            assert self.get_return_code() == RESULT_OK


@pytest.mark.fast
class TestsErrorPackageInclusionsExclusions(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = ["init", "build", "package"]
        self.wait_ready = False

    def test_exit_after_success(self):
        # This test issues 'package' to completion which can take some time on a clean system
        # when all layers need to be pulled/cached.
        self.wait_process_exit(timeout=300)
        # Expect RESULT_OK but some logging to warn about empty inclusion/exclusion matches.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK

        assert self.is_string_in_logs(
            "No matching files found for inclusions 'missingfile'"
        )
        assert self.is_string_in_logs(
            "No matching files found for exclusions 'missingfile'"
        )


@pytest.mark.fast
class TestsErrorPackageBadDockerRun(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_5.yaml"
        self.ssf_commands = ["init", "build", "package"]
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_PACKAGING_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_PACKAGING_ERROR


@pytest.mark.fast
class TestsErrorPublishDockerBogusLogin(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "publish",
            "--docker-username",
            "bogus",
            "--docker-password",
            "bogus",
        ]

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_DOCKER_SERVER_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_DOCKER_SERVER_ERROR

        assert self.is_string_in_logs("Login to DockerHub errored")


@pytest.mark.fast
class TestsErrorPublishDockerBogusPackage(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "publish",
            "--package-tag",
            "bogus",
        ]

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_DOCKER_SERVER_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_DOCKER_SERVER_ERROR

        assert self.is_string_in_logs("Push bogus errored")


@pytest.mark.fast
class TestsErrorDeployGcoreMissingTarget(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "deploy",
            "--deploy-platform",
            "Gcore",
        ]

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_GCORE_DEPLOYMENT_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_GCORE_DEPLOYMENT_ERROR

        assert self.is_string_in_logs("Target address must be specified")


@pytest.mark.fast
class TestsErrorDeployGcoreBogusPackage(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "deploy",
            "--deploy-platform",
            "Gcore",
            "--deploy-gcore-target-address",
            "0.0.0.0",
            "--package-tag",
            "bogus",
        ]

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_GCORE_DEPLOYMENT_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_GCORE_DEPLOYMENT_ERROR

        assert self.is_string_in_logs(
            "Execute boot file simple-test-boot.sh at 0.0.0.0 errored"
        )


@pytest.mark.fast
class TestsErrorDeployPaperspaceMissingProject(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        os.environ["TEST_API_KEY"] = "0000"
        self.ssf_commands = [
            "deploy",
            "--deploy-platform",
            "Paperspace",
            "--deploy-paperspace-api-key",
            "0000",
            "--package-tag",
            "bogus",
        ]

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_PAPERSPACE_DEPLOYMENT_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_PAPERSPACE_DEPLOYMENT_ERROR

        assert self.is_string_in_logs("Deployment project id must be specified")


@pytest.mark.fast
class TestsErrorDeployPaperspaceMissingAPIKeyArg(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "deploy",
            "--deploy-platform",
            "Paperspace",
            "--deploy-paperspace-project-id",
            "0000",
            "--package-tag",
            "bogus",
        ]
        os.environ["TEST_API_KEY"] = "0000"

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_PAPERSPACE_DEPLOYMENT_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_PAPERSPACE_DEPLOYMENT_ERROR

        assert self.is_string_in_logs("Deployment API key must be specifie")


@pytest.mark.fast
class TestsErrorDeployPaperspaceMissingAPIKeyEnv(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "deploy",
            "--deploy-platform",
            "Paperspace",
            "--deploy-paperspace-project-id",
            "0000",
            "--deploy-paperspace-api-key",
            "TEST_API_KEY",
            "--package-tag",
            "bogus",
        ]
        os.environ.pop("TEST_API_KEY", None)

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_PAPERSPACE_DEPLOYMENT_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_PAPERSPACE_DEPLOYMENT_ERROR

        assert self.is_string_in_logs(
            "Deployment API key 'TEST_API_KEY' must be set in environment"
        )


@pytest.mark.fast
class TestsErrorDeployPaperspaceFailAPI(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "deploy",
            "--deploy-platform",
            "Paperspace",
            "--deploy-paperspace-project-id",
            "0000",
            "--deploy-paperspace-api-key",
            "TEST_API_KEY",
            "--package-tag",
            "bogus",
        ]
        os.environ["TEST_API_KEY"] = "0000"

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_PAPERSPACE_DEPLOYMENT_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_PAPERSPACE_DEPLOYMENT_ERROR

        assert self.is_string_in_logs("Failed to create deployment")


@pytest.mark.fast
class TestsErrorAddSshKeyEnv(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_4.yaml"
        self.ssf_commands = [
            "--add-ssh-key",
            "TEST_SSH_KEY",
            "deploy",
            "--deploy-platform",
            "Gcore",
            "--deploy-gcore-target-address",
            "0.0.0.0",
            "--package-tag",
            "bogus",
        ]

        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_SSH_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_SSH_ERROR

        assert self.is_string_in_logs(
            "SSH key 'TEST_SSH_KEY' must be set in environment"
        )


@pytest.mark.fast
class TestsErrorInitGitConfig(utils.TestClient):
    def configure(self):
        self.config_file = "git@github.com:bogus|ssf/ssf_config.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_GIT_REPO_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_GIT_REPO_ERROR

        assert self.is_string_in_logs("Git clone errored")


@pytest.mark.fast
class TestsErrorUnmetRequirementInit(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_6.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit()
        # Expect RESULT_UNMET_REQUIREMENT to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_UNMET_REQUIREMENT

        assert self.is_string_in_logs("Unspecified unmet requirement from init")


@pytest.mark.fast
class TestsErrorUnmetRequirementBuild(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_7.yaml"
        self.wait_ready = False

    def test_exit_after_failure(self):
        self.wait_process_exit()
        # Expect RESULT_UNMET_REQUIREMENT to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_UNMET_REQUIREMENT

        assert self.is_string_in_logs("Unspecified unmet requirement from build")


@pytest.mark.fast
class TestsErrorUnmetRequirementStartupWithoutStop(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_8.yaml"
        self.wait_ready = False
        self.stop_on_error = False

    def test_startup_fails_without_stop(self):
        # Wait to be sure SSF server does not force stop.
        print("Waiting for stop...")
        self.wait_process_no_exit()
        print("Waiting for stop...done")

        print("Checking status")

        # Default behaviour is that the server continues to run
        # and will serve the health probes (startup == OK)
        # liveness and readiness should fails
        assert self.process_is_running()
        assert self.get_return_code() == None

        assert self.health_startup()
        assert not self.health_ready()
        assert not self.health_live()

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_UNMET_REQUIREMENT to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_UNMET_REQUIREMENT
        assert self.server_stopped()

        assert self.is_string_in_logs("Unspecified unmet requirement from startup")

        assert self.is_string_in_logs("Dispatcher failed to start")
        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsErrorUnmetRequirementStartupWithStop(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/error_8.yaml"
        self.wait_ready = False
        self.stop_on_error = True

    def test_startup_fails_with_stop(self):
        print("Waiting for stop...")
        self.wait_process_exit()
        print("Waiting for stop...done")

        print("Checking status")

        # With stop-on-error, behaviour is that the server stops itself.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_UNMET_REQUIREMENT
        assert self.server_stopped()

        assert not self.health_startup()
        assert not self.health_ready()
        assert not self.health_live()

        assert self.is_string_in_logs("Unspecified unmet requirement from startup")

        assert self.is_string_in_logs("Dispatcher failed to start")
        assert self.is_string_in_logs("Application has errored")
        assert self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsErrorClientBadRequest(utils.TestClient):
    """Test error propagation to client response when request is malformed"""

    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"

    def test_error_to_client_propagation(self):
        if self.api == API_GRPC:
            try:
                response = self.grpc_session.grpc_send_infer_request(
                    "2", "Test1", {"x": 0}
                )
            except Exception as e:
                assert "INVALID_ARGUMENT" in str(e), "Bad user message"
                assert "Endpoint version '2' of endpoint 'Test1' not found" in str(
                    e
                ), "Bad user message"

            try:
                response = self.grpc_session.grpc_send_infer_request(
                    "1", "Test3", {"x": 0}
                )
            except Exception as e:
                assert "INVALID_ARGUMENT" in str(e), "Bad user message"
                assert "Endpoint 'Test3' not found" in str(e), "Bad user message"

            try:
                response = self.grpc_session.grpc_send_infer_request(
                    "1", "Test1", {"y": 0}
                )
            except Exception as e:
                assert "INVALID_ARGUMENT" in str(e), "Bad user message"
                assert "Input name = 'x', type = 'Integer' not found" in str(
                    e
                ), "Bad user message"

        else:
            url = f"{self.base_url}/v1/Test1"
            response = requests.post(
                url, json={"y": 0}, headers={"accept": "application/json"}, timeout=1
            )
            # 422 Unprocessable Content
            assert response.status_code == 422


test_grpc = [
    TestsErrorCorruptConfig,
    TestsErrorCorruptModule,
    TestsErrorMissingClassFunctions,
    TestsErrorMissingNonClassFunctions,
    TestsErrorTestInterfacePrecursor,
    TestsErrorTestInterfaceMissingClassFunctions,
    TestsErrorTestInterfaceMissingNonClassFunctions,
    TestsErrorPackageSkipBuild,
    TestsErrorPackageInclusionsExclusions,
    TestsErrorPackageBadDockerRun,
    TestsErrorPublishDockerBogusLogin,
    TestsErrorPublishDockerBogusPackage,
    TestsErrorDeployGcoreMissingTarget,
    TestsErrorDeployGcoreBogusPackage,
    TestsErrorDeployPaperspaceMissingProject,
    TestsErrorDeployPaperspaceMissingAPIKeyArg,
    TestsErrorDeployPaperspaceMissingAPIKeyEnv,
    TestsErrorDeployPaperspaceFailAPI,
    TestsErrorAddSshKeyEnv,
    TestsErrorInitGitConfig,
    TestsErrorUnmetRequirementInit,
    TestsErrorUnmetRequirementBuild,
    TestsErrorUnmetRequirementStartupWithoutStop,
    TestsErrorUnmetRequirementStartupWithStop,
    TestsErrorClientBadRequest,
]

for c in test_grpc:
    globals()[f"{c.__name__}GRPC"] = utils.withGRPC(c)
