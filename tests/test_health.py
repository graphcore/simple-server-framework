# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import requests
import utils
import time
import yaml
import json

from ssf.results import RESULT_OK, RESULT_APPLICATION_ERROR


class HealthTest(utils.TestClient):
    def Test1(self, x=0):
        print("Post Test1...")
        response = requests.post(
            self.base_url + "/v1/Test1",
            json={"x": x},
            headers={"accept": "application/json"},
            timeout=5,
        )
        print("Post Test1...done")
        print("Assert response.status_code == 200")
        assert response.status_code == 200
        d = json.loads(response.text)
        print(f"response = {d}")
        # Test apps return "reponse", "replica" and/or "requests"
        # Adapt to any/all of these.
        ok = d.get("response", "n/a")
        request_count = d.get("requests", 1)
        replica = d.get("replica", 0)
        result = (replica, request_count, ok)
        print(f"Post Test1...OK {result}")
        return result

    def Fail(self, failure_type="div0"):
        print("Post Fail...")
        response = requests.post(
            self.base_url + "/v1/Fail",
            json={"failure_type": failure_type},
            headers={"accept": "application/json"},
            timeout=5,
        )
        print("Post Fail...done")
        print("Assert response.status_code != 200")
        assert response.status_code != 200
        d = json.loads(response.text)
        print(f"response = {d}")
        print("Assert 'error' in detail")
        assert "error" in d["detail"].lower()
        # Application failure handling and restart is asynchronous
        # so checking state transitions from the test can be tricky.
        # The dispatcher may still be processing the failure so there is a
        # small window where it's possible for readiness to still be up.
        # Once we see the test app shutdown for the dispatcher PID that
        # made the last request, then we know this has finished.
        # Adding this pause here means the individual tests can make their
        # asserts immediately on return from Fail().
        self.wait_string_in_logs(
            f"{self.most_recent_dispatcher_request_pid:11}INFO      MyApp shutdown",
            timeout=5,
        )
        print("Post Fail...OK")


@pytest.mark.fast
class TestsBasicHealth(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"

    def test_ready_start(self):
        assert self.is_ready
        assert self.is_string_in_logs("Dispatcher ready")

    def test_startup_start(self):
        assert self.health_startup()

    def test_liveness_start(self):
        assert self.health_live()

    def test_endpoint(self):
        assert self.Test1() == (0, 1, "n/a")

    def test_exit_after_success(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_OK to indicate there were no failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_OK
        assert self.server_stopped()

        assert not self.is_string_in_logs("App startup failed")
        assert not self.is_string_in_logs("Dispatcher failed to start")
        assert not self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsReadinessChange(HealthTest):
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

        # Check functional endpoint.
        print("Check functional endpoint...")
        assert self.Test1() == (0, 1, "ok")
        print("Check functional endpoint...OK")

        # Trigger internal application failure.
        print("Trigger failure...")
        self.Fail()
        print("Trigger failure...OK")

        # Readiness should now be down.
        # Following this we expect health_ready() to report KO at
        # least until the server has restarted the dispatcher (application).
        # NOTE: The health_1.yaml config file specifies module long_start_app.py
        # module which adds a 5s delay to the app re-start to avoid a race.
        print("Assert NOT self.health_ready()")
        assert not self.health_ready()

        # Watchdog should spot the dead worker
        # and bring it back up.
        print("wait_server_ready()...")
        self.wait_server_ready(timeout=30)
        print("wait_server_ready()...OK")
        print("Assert 'is not alive' in logs")
        assert self.is_string_in_logs("is not alive")

        # Check functional endpoint (post recovery)
        print("Check functional endpoint...")
        assert self.Test1() == (0, 1, "ok")
        print("Check functional endpoint...OK")

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert not self.is_string_in_logs("App startup failed")
        assert not self.is_string_in_logs("Dispatcher failed to start")
        assert self.is_string_in_logs("Application has errored")


@pytest.mark.fast
class TestsReadinessReplicas(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        self.worker_replicas = 2

    def test_readiness_replicas(self):

        assert self.Test1()[1] == 1

        # Fail the first replica
        # check readiness is still up,
        self.Fail()
        assert self.health_ready()

        assert self.Test1()[1] <= 2

        # Fail the 2nd replica
        # check readiness is down
        self.Fail(2)
        assert not self.health_ready()

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsRestartReplicas(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        self.worker_replicas = 4

    def test_restart_replicas(self):

        assert self.health_startup()
        assert self.health_live()
        assert self.health_ready()

        assert len(self.workers_pid) == self.worker_replicas

        request_uid = 0

        # Helper that repeatedly issues requests until each replica has contributed at a least once.
        # We assert that scheduling can meet this in a reasonably finite time, at least for a low number of replicas.
        # Returns the total requests issued, the accumulated replica request count and which replicas have been reset.
        def submit_requests_for_all_replicas(previous_request_counts=None):
            nonlocal request_uid
            request_counts = [0] * self.worker_replicas
            resets = [None] * self.worker_replicas
            timeout = 30
            requests = 0
            resets = [None] * self.worker_replicas
            t0 = time.time()
            while any([r == None for r in resets]):
                replica, result, _ = self.Test1(request_uid)
                if resets[replica] is None:
                    resets[replica] = (
                        False
                        if previous_request_counts is None
                        else (result <= previous_request_counts[replica])
                    )
                request_counts[replica] = result
                request_uid += 1
                requests += 1
                elapsed = time.time() - t0
                print(
                    f"{elapsed} :: requests:{requests} uid:{request_uid} : {request_counts} {resets} (Total:{sum(request_counts)})"
                )
                assert elapsed < timeout
            return requests, request_counts, resets

        # Initial (pre-fail) submissions.
        (
            pre_fail_requests,
            pre_fail_request_counts,
            _,
        ) = submit_requests_for_all_replicas()
        assert sum(pre_fail_request_counts) == pre_fail_requests

        # Fail one replica.
        self.Fail()

        # Wait for it to come back.
        wait = 0
        while True:
            time.sleep(10)
            wait += 10
            print(f"workers {self.workers_pid}")
            if len(self.workers_pid) > self.worker_replicas and self.health_ready():
                break
            assert wait < 30

        # Expect one replica to have been restarted.
        assert len(self.workers_pid) == self.worker_replicas + 1

        # Post-fail submissions.
        (
            post_fail_requests,
            post_fail_request_counts,
            resets,
        ) = submit_requests_for_all_replicas(
            previous_request_counts=pre_fail_request_counts
        )

        # One replica should have had its request count reset.
        assert resets.count(True) == 1
        reset_index = resets.index(True)

        # If we hadn't failed and therefore restarted a replica we could assert something like:
        # assert sum(post_fail_request_counts) == pre_fail_requests + post_fail_requests
        # However, we expect the request count for the replica that was restarted to have been reset.
        # Post fail request counts should be the total requests less those 'lost' due to reset.
        expected = (
            pre_fail_requests
            + post_fail_requests
            - pre_fail_request_counts[reset_index]
        )
        print(f"Post fail resets : {resets} (reset index {reset_index})")
        print(
            f"Pre fail requests : {pre_fail_request_counts} sum {sum(pre_fail_request_counts)} (from {pre_fail_requests} requests)"
        )
        print(
            f"Post fail requests : {post_fail_request_counts} sum {sum(post_fail_request_counts)} (from {post_fail_requests} requests)"
        )
        print(f"Post fail requests expected : {expected}")

        assert expected == sum(post_fail_request_counts)

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsRequestFailureWithStop(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        self.stop_on_error = True

    def test_failure_with_stop(self):

        assert self.health_startup()
        assert self.health_live()
        assert self.health_ready()

        assert self.Test1() == (0, 1, "n/a")

        # Fail
        self.Fail()

        print("Waiting for stop...")
        self.wait_process_exit()
        print("Waiting for stop...done")

        print("Checking status")
        # With stop-on-error, behaviour is that the server stops itself.
        assert self.get_return_code() == RESULT_APPLICATION_ERROR

        assert not self.health_startup()
        assert not self.health_ready()
        assert not self.health_live()

        assert self.is_string_in_logs("Application has errored")
        assert self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsStartupFailsWithoutStop(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_2.yaml"
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
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert self.is_string_in_logs("App startup failed")
        assert self.is_string_in_logs("Dispatcher failed to start")
        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsStartupFailsWithStop(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_2.yaml"
        self.wait_ready = False
        self.stop_on_error = True

    def test_startup_fails_with_stop(self):
        print("Waiting for stop...")
        self.wait_process_exit()
        print("Waiting for stop...done")

        print("Checking status")

        # With stop-on-error, behaviour is that the server stops itself.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert not self.health_startup()
        assert not self.health_ready()
        assert not self.health_live()

        assert self.is_string_in_logs("App startup failed")
        assert self.is_string_in_logs("Dispatcher failed to start")
        assert self.is_string_in_logs("Application has errored")
        assert self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsAppHealthFailsWatchdogEnabled(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_3.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)

    def test_liveness_fail_loops(self):
        # check initial liveness is up
        assert self.health_live()
        # now configure the app to always fails health check
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": False}, file)
        # check liveness turns down after some time failing
        t0 = time.time()
        while time.time() - t0 < 20:
            time.sleep(2)
            if not self.health_live():
                assert self.is_string_in_logs("health check kept failing after")
                return
        raise Exception("Timeout")

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsAppHealthFailsIsHealthy(TestsAppHealthFailsWatchdogEnabled):
    def configure(self):
        self.config_file = "tests/app_usecases/health_4.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)

    def test_exit_after_failures(self):
        # As before.
        super(TestsAppHealthFailsIsHealthy, self).test_exit_after_failures()
        # Plus, check for specific warning about using 'is_healthy'.
        assert self.is_string_in_logs(
            "Using application interface 'is_healthy' as 'watchdog'"
        )


@pytest.mark.fast
class TestsAppHealthRecovery(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_3.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)

    def test_liveness_up_recovery(self):
        # check initial liveness is up
        assert self.health_live()
        # now configure the app to always fails health check
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": False}, file)
        time.sleep(5)
        # check readiness is down but liveness up
        assert not self.health_ready()
        assert self.health_live()
        # now reconfigure the app to succeed health checks
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)
        # wait until readiness is back up
        self.wait_server_ready(timeout=10)
        # make sure liveness is still up
        assert self.health_live()

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsAppHealthFailsWatchdogDisabled(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_3.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)
        self.watchdog_ready_period = 0

    def test_liveness_fail_loops(self):
        # check initial liveness is up
        assert self.health_live()
        # now configure the app to always fails health check
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": False}, file)
        # check liveness does NOT turn down after some time failing
        t0 = time.time()
        while time.time() - t0 < 20:
            time.sleep(2)
            if not self.health_live():
                raise Exception("Should still be alive")

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_OK
        assert self.server_stopped()
        assert not self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsAppHealthFailsWatchdogWithoutRequests(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_3.yaml"
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": True}, file)
        self.watchdog_ready_period = 5

    def test_liveness_fail_loops(self):
        # check initial liveness is up
        assert self.health_live()
        assert self.Test1() == (0, 1, "ok")

        # now configure the app to always fails health check
        with open("tests/app_usecases/status.yaml", "w") as file:
            yaml.dump({"healthy": False}, file)

        # check liveness does NOT turn down while we keep issuing requests
        t0 = time.time()
        while time.time() - t0 < 20:
            self.Test1()
            time.sleep(2)
            if not self.health_live():
                raise Exception("Should still be alive")

        # check liveness does turn down once we stop issuing requests
        t0 = time.time()
        while time.time() - t0 < 20:
            time.sleep(2)
            if not self.health_live():
                assert self.is_string_in_logs("health check kept failing after")
                return
        raise Exception("Timeout")

    def test_exit_after_failures(self):
        # Force stop.
        self.stop_process()

        # After the process is forceably stopped, then we should
        # still RESULT_APPLICATION_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_APPLICATION_ERROR
        assert self.server_stopped()

        assert self.is_string_in_logs("Application has errored")
        assert not self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsRequestFailureMalformedUnbatchedResult(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        self.stop_on_error = True

    def test_failure_with_stop(self):

        assert self.health_startup()
        assert self.health_live()
        assert self.health_ready()

        assert self.Test1() == (0, 1, "n/a")

        # Fail
        self.Fail(failure_type="malformed_result")

        print("Waiting for stop...")
        self.wait_process_exit()
        print("Waiting for stop...done")

        print("Checking status")
        # With stop-on-error, behaviour is that the server stops itself.
        assert self.get_return_code() == RESULT_APPLICATION_ERROR

        assert not self.health_startup()
        assert not self.health_ready()
        assert not self.health_live()

        assert self.is_string_in_logs("Expected result as dict for unbatched request")
        assert self.is_string_in_logs("Application has errored")
        assert self.is_string_in_logs("Stopping server")


@pytest.mark.fast
class TestsRequestFailureMalformedBatchedResult(HealthTest):
    def configure(self):
        self.config_file = "tests/app_usecases/health_5.yaml"
        self.stop_on_error = True

    def test_failure_with_stop(self):
        assert self.health_startup()
        assert self.health_live()
        assert self.health_ready()

        assert self.Test1() == (0, 1, "n/a")

        # Fail
        self.Fail(failure_type="malformed_result")

        print("Waiting for stop...")
        self.wait_process_exit()
        print("Waiting for stop...done")

        print("Checking status")
        # With stop-on-error, behaviour is that the server stops itself.
        assert self.get_return_code() == RESULT_APPLICATION_ERROR

        assert not self.health_startup()
        assert not self.health_ready()
        assert not self.health_live()

        assert self.is_string_in_logs(
            "Expected result as list of dict for batched request"
        )
        assert self.is_string_in_logs("Application has errored")
        assert self.is_string_in_logs("Stopping server")
