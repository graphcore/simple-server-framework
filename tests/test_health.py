# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import requests
import utils
import time
import os
import signal
import yaml


@pytest.mark.fast
class TestsBasic(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"

    def test_ready_start(self):
        assert self.is_ready
        assert self.is_string_in_logs("Dispatcher ready")

    def test_startup_start(self):
        response = requests.get(self.base_url + "/health/startup")
        assert response.status_code == 200

    def test_liveness_start(self):
        response = requests.get(self.base_url + "/health/live")
        assert response.status_code == 200


@pytest.mark.fast
class TestsReadinessChange(utils.TestClient):
    def configure(self):
        self.wait_ready = False
        self.config_file = "tests/app_usecases/health_1.yaml"

    def test_ready_start(self):
        # app startup takes 5 second
        # verifies that ready is not up instantly
        assert not self.is_ready

    def test_startup_wait(self):
        # then wait until ready is up
        self.wait_server_ready(timeout=20)
        assert self.is_ready
        assert self.is_string_in_logs("Dispatcher ready")

    def test_process_restart(self):
        # kill the worker process
        pid = int(self.workers_pid[0])
        os.kill(pid, signal.SIGKILL)
        response = requests.get(self.base_url + "/health/ready")
        assert response.status_code != 200
        # watchdog should restart the dead worker
        # readiness should be back up
        self.wait_server_ready(timeout=30)
        assert self.is_string_in_logs("restarted")


@pytest.mark.fast
class TestsReadinessReplicas(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        self.worker_replicas = 2

    def test_readiness_replicas(self):
        pid0, pid1 = int(self.workers_pid[0]), int(self.workers_pid[1])
        print("REPLICAS:", pid0, pid1)
        os.kill(pid0, signal.SIGKILL)
        # kill the first replica
        # check readiness is still up,
        response = requests.get(self.base_url + "/health/ready")
        assert response.status_code == 200
        # kill the 2nd replica
        # check readiness is down
        os.kill(pid1, signal.SIGKILL)
        time.sleep(1)
        response = requests.get(self.base_url + "/health/ready")
        assert response.status_code != 200


@pytest.mark.fast
class TestsStartupFails(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/health_2.yaml"
        self.wait_ready = False

    def test_startup_fails(self):
        # liveness and readiness should fails
        time.sleep(5)
        response = requests.get(self.base_url + "/health/ready")
        assert response.status_code != 200
        response = requests.get(self.base_url + "/health/live")
        assert response.status_code != 200
        assert self.is_string_in_logs("Dispatcher Exception: App startup failed")
        assert self.is_string_in_logs("Dispatcher failed to start")


@pytest.mark.fast
class TestsAppHealthFails(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/health_3.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)

    def test_liveness_fail_loops(self):
        # check initial liveness is up
        response = requests.get(self.base_url + "/health/live")
        assert response.status_code == 200
        # now configure the app to always fails health check
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": False}, file)
        # check liveness turns down after some time failing
        t0 = time.time()
        while time.time() - t0 < 20:
            time.sleep(2)
            response = requests.get(self.base_url + "/health/live")
            if response.status_code != 200:
                assert self.is_string_in_logs("health check kept failing after")
                return
        raise Exception("Timeout")


@pytest.mark.fast
class TestsAppHealthRecovery(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/health_3.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)

    def test_liveness_up_recovery(self):
        # check initial liveness is up
        response = requests.get(self.base_url + "/health/live")
        assert response.status_code == 200
        # now configure the app to always fails health check
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": False}, file)
        time.sleep(1)
        # check readiness is down but liveness up
        response = requests.get(self.base_url + "/health/ready")
        assert response.status_code != 200
        response = requests.get(self.base_url + "/health/live")
        assert response.status_code == 200
        # now reconfigure the app to succeed health checks
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)
        # wait until readiness is back up
        self.wait_server_ready(timeout=10)
        # make sure liveness is still up
        response = requests.get(self.base_url + "/health/live")
        assert response.status_code == 200
