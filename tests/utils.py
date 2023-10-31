# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import copy
import os
import signal
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from threading import Thread
from typing import Any, Dict, List
import grpc

import regex as re
import requests
from ssf.grpc_runtime import grpc_predict_v2_pb2, grpc_predict_v2_pb2_grpc
from ssf.grpc_runtime.test_utils_grpc import GRPCSession

from ssf.utils import API_FASTAPI, API_GRPC

# Default timeouts to wait for return/ready state.
DEFAULT_WAIT_TIMEOUT = 180
DEFAULT_WAIT_TIMEOUT_FOR_PACKAGING = 300
DEFAULT_WAIT_TIMEOUT_NO_EXIT = 30


def print_header_separator(title):
    title = " " + title + " "
    lt = len(title)
    w = max(120, lt + 10)
    x1 = int((w - lt) / 2)
    x2 = w - lt - x1
    print("\n" + "=" * x1 + title + "=" * x2 + "\n")


def raise_exception(msg):
    print("Exception: " + msg)
    raise Exception(msg)


def run_subprocess(command_line_args, piped_input=None, cwd=None):
    """
    Runs a command in subprocess.
    :param command_line_args: Command and arguments as list
    :param piped_input: Optional input to pipe through stdin to process
    :return: Command exit code, Stdout as list of lines, Stderr as list of lines
    """

    sys.stdout.reconfigure(encoding="utf-8", line_buffering=False)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=False)
    mod_env = os.environ.copy()
    mod_env["PYTHONUNBUFFERED"] = "1"

    print(f"Creating process with {command_line_args}")
    process = subprocess.Popen(
        command_line_args,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=mod_env,
        cwd=cwd,
    )
    print(f"Created process {process.pid}")

    if piped_input:
        print(f"Communicate piped input to {process.pid}")
        stdout, stderr = process.communicate(input=piped_input)
        print(f"Waiting for process result from {process.pid}")
        result = process.wait()
        print(f"Process {process.pid} completed with result {result}")
        print(f"Capturing output for {process.pid}")
        stdout = stdout.decode("utf-8").split("\n")
        stderr = stderr.decode("utf-8").split("\n")
    else:
        stdout = []
        stderr = []

        def reader(pipe, sysout, outlist, label):
            print(f"Enter reader for pipe {pipe}")
            for line in pipe:
                try:
                    line = line.decode("utf-8").rstrip()
                    outlist.append(line)
                    sysout.write(f"{label} {line}\n")
                    sysout.flush()
                except:
                    pass
            print(f"Leave reader for pipe {pipe}")

        print("Creating threaded readers")
        tout = Thread(
            target=reader,
            args=[process.stdout, sys.stdout, stdout, f"[{process.pid}] [STDOUT]"],
        )
        terr = Thread(
            target=reader,
            args=[process.stderr, sys.stderr, stderr, f"[{process.pid}] [STDERR]"],
        )
        print("Starting threaded readers")
        tout.start()
        terr.start()
        print(f"Waiting for process result from {process.pid}")
        result = process.wait()
        print(f"Process {process.pid} completed with result {result}")
        print("Joining threaded readers")
        tout.join()
        terr.join()

    print(f"Returning result {result}")
    return result, stdout, stderr


def get_stdout_stderr(capfd):
    """
    Helper used to process captured stdout and stderr from a test and
    return a list of lines consistent with run_subprocess().
    :param capfd: Pytest fixture for capture of output (from test)
    :return: Stdout as list of lines, Stderr as list of lines
    """
    stdout, stderr = capfd.readouterr()
    stdout = stdout.split("\n")
    for line in stdout:
        sys.stdout.write(f"CAPTURED STDOUT: {line}\n")
    stderr = stderr.split("\n")
    for line in stderr:
        sys.stderr.write(f"CAPTURED STDERR: {line}\n")
    return stdout, stderr


def withGRPC(base, extra_arguments=[]):
    """Helper function for TestClient to run test with gRPC

    Args:
        base (TestClient): class to run with gRPC

    Returns:
        class wrapper so it was called also for gRPC
    """

    class TestClass(base):
        def configure(self):
            self.api = API_GRPC
            if getattr(self, "extra_arguments", []):
                self.extra_arguments.extend(extra_arguments)
            else:
                self.extra_arguments = extra_arguments
            super().configure(self)

    return TestClass


class TestClient(ABC):
    def wait_server_ready(self, timeout=None):
        timeout = self.default_wait_timeout if timeout is None else timeout
        print(f"Waiting for test server to be up... (max {timeout}s)")
        t0 = time.time()
        timeout_raised = False
        while True:
            time.sleep(3)
            if not self.process_is_running():
                raise_exception("wait_server_ready: Process has stopped")
            try:
                if self.api == API_FASTAPI:
                    response = requests.get(self.base_url + "/health/ready")
                elif self.api == API_GRPC:
                    response = self.grpc_session.get(self.base_url + "/health/ready")
                else:
                    raise_exception(f"Bad API: {self.api}")
                if response.status_code == 200:
                    self.is_ready = True
                    break
            except:
                pass
            ela = time.time() - t0
            if ela > timeout:
                print(f"wait_server_ready : timeout after {ela}s")
                timeout_raised = True
                break
        if timeout_raised:
            self.terminate_process()
            raise_exception("wait_server_ready: timeout before ready")
        print("wait_server_ready: ready")

    @abstractmethod
    def configure(self):
        """
        set the following to initialize:
        self.config_file
        """

    @classmethod
    def setup_class(cls):
        """setup any state specific to the execution of the given class (which
        usually contains tests).
        """
        from pytest import server_port

        print_header_separator(f"Setup test {cls.__name__}")
        cls.config_file: str = ""
        cls.process = None
        cls.return_code = None
        cls.base_host = "localhost"
        cls.base_url = f"http://{cls.base_host}:{server_port}"
        cls.is_ready = False
        cls.wait_ready = True
        cls.tout = None
        cls.terr = None
        cls.workers_pid = []
        cls.most_recent_dispatcher_request_pid = None
        cls.worker_replicas = 1
        cls.watchdog_ready_period = 1
        cls.max_allowed_restarts = None
        cls.check_logs = ""
        cls.ssf_commands = ["init", "build", "run"]
        cls.stop_on_error = False
        cls.api = None
        cls.default_wait_timeout = DEFAULT_WAIT_TIMEOUT

        cls.configure(cls)

        if "package" in cls.ssf_commands:
            cls.default_wait_timeout = DEFAULT_WAIT_TIMEOUT_FOR_PACKAGING
            print(
                f"Extended default_wait_timeout for 'package' ({cls.default_wait_timeout}s)"
            )

        ssf_process_args = [
            "gc-ssf",
            "--config",
            cls.config_file,
            "--port",
            str(server_port),
            "--replicate-application",
            str(cls.worker_replicas),
            "--watchdog-ready-period",
            str(cls.watchdog_ready_period),
            "--stdout-log-level",
            "DEBUG",
            *cls.ssf_commands,
        ]

        if cls.api:
            ssf_process_args.extend(["--api", cls.api])

        if cls.stop_on_error:
            ssf_process_args.append("--stop-on-error")

        if cls.max_allowed_restarts:
            ssf_process_args.extend(
                ["--max-allowed-restarts", str(cls.max_allowed_restarts)]
            )
        if hasattr(cls, "extra_arguments"):
            ssf_process_args.extend(cls.extra_arguments)

        print(ssf_process_args)

        if cls.api == API_GRPC:
            cls.proto_predict_v2 = grpc_predict_v2_pb2
            cls.proto_predict_v2_grpc = grpc_predict_v2_pb2_grpc

            cls.channel = grpc.insecure_channel(f"{cls.base_host}:{server_port}")
            cls.stub = cls.proto_predict_v2_grpc.GRPCInferenceServiceStub(cls.channel)
            cls.grpc_session = GRPCSession(cls.base_host, server_port)

        print(f"Creating process with {ssf_process_args}")
        cls.process = subprocess.Popen(
            ssf_process_args,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
        print(
            f"Created process {cls.process.pid} with pgid {os.getpgid(cls.process.pid)}"
        )

        if not cls.api:
            cls.api = API_FASTAPI

        cls.setup_pipe(cls)
        if cls.wait_ready:
            cls.wait_server_ready(cls)

    @classmethod
    def stop_process(cls, force_terminate: bool = False):
        if cls.process:
            if force_terminate:
                print(
                    f"Terminate process {cls.process.pid} with pgid {os.getpgid(cls.process.pid)}"
                )
                os.killpg(os.getpgid(cls.process.pid), signal.SIGTERM)
            else:
                print(f"Stop process {cls.process.pid}")
                cls.process.send_signal(signal.SIGINT)
            print("Joining threaded readers")
            cls.tout.join()
            cls.terr.join()
            print(f"Waiting for process communicate from {cls.process.pid}")
            cls.process.communicate()[0]
            cls.return_code = cls.process.returncode
            print(f"Process {cls.process.pid} completed with result {cls.return_code}")
            cls.process = None
        return cls.return_code

    @classmethod
    def terminate_process(cls):
        cls.stop_process(True)

    @classmethod
    def process_is_running(cls):
        return cls.process is not None and cls.process.poll() is None

    @classmethod
    def get_return_code(cls):
        if cls.process:
            if cls.process.poll() is not None:
                cls.return_code = cls.process.returncode
                cls.process = None
        return cls.return_code

    @classmethod
    def health_ready(cls):
        try:
            if cls.api == API_FASTAPI:
                response = requests.get(cls.base_url + "/health/ready")
                return response.status_code == 200
            elif cls.api == API_GRPC:
                request = cls.proto_predict_v2.ServerReadyRequest()
                response, _ = cls.stub.ServerReady.with_call(request)
                return response.ready
        except:
            return False

    @classmethod
    def health_live(cls):
        try:
            if cls.api == API_FASTAPI:
                response = requests.get(cls.base_url + "/health/live")
                return response.status_code == 200
            elif cls.api == API_GRPC:
                # KServe protocol does not expose such status
                return cls.health_ready()
        except:
            return False

    @classmethod
    def health_startup(cls):
        try:
            if cls.api == API_FASTAPI:
                response = requests.get(cls.base_url + "/health/startup")
                return response.status_code == 200
            elif cls.api == API_GRPC:
                request = cls.proto_predict_v2.ServerLiveRequest()
                response, _ = cls.stub.ServerLive.with_call(request)
                return response.live
        except Exception as e:
            return False

    @classmethod
    def server_stopped(cls):
        try:
            requests.get(cls.base_url + "/health/startup")
        except Exception as e:
            return e.__class__.__name__ == "ConnectionError"

    @classmethod
    def wait_process_return_code(cls, timeout=None):
        timeout = cls.default_wait_timeout if timeout is None else timeout
        print(f"Waiting for test server return code... (max {timeout}s)")
        t0 = time.time()
        while True:
            time.sleep(3)
            return_code = cls.get_return_code()
            if (time.time() - t0) > timeout or return_code is not None:
                print(f"Waiting for test server return code...{return_code}")
                return return_code

    @classmethod
    def wait_process_exit(cls, timeout=None):
        if cls.wait_process_return_code(timeout=timeout) is None:
            cls.terminate_process()
            raise_exception("wait_process_exit: timeout before exit")

    @classmethod
    def wait_process_no_exit(cls, timeout=DEFAULT_WAIT_TIMEOUT_NO_EXIT):
        if cls.wait_process_return_code(timeout=timeout) is not None:
            raise_exception("wait_process_no_exit: unexpected exit")

    @classmethod
    def teardown_class(cls):
        """teardown any state that was previously setup with a call to
        setup_class.
        """
        cls.terminate_process()

    def is_string_in_logs(cls, search_string: str):
        with open("ssf.log", "r") as file:
            for line in file:
                if search_string in line:
                    return True
            else:
                return False

    def wait_string_in_logs(cls, search_string: str, timeout=None):
        timeout = cls.default_wait_timeout if timeout is None else timeout
        print(f"Waiting for '{search_string}' in logs... (max {timeout}s)")
        t0 = time.time()
        while True:
            if cls.is_string_in_logs(search_string):
                print(f"Waiting for '{search_string}' in logs...OK")
                return True
            if (time.time() - t0) > timeout:
                print(f"Waiting for '{search_string}' in logs...timeout")
                return False

    def setup_pipe(self):
        stdout = []
        stderr = []

        def extract_worker_pid_from_log(log_line):
            # for example:
            # "[37090] [STDOUT] 2023-10-30 11:27:24,983 37109      INFO      > [0] Dispatcher started for simple-test [37090->37109] (dispatcher.py:179)"
            # Return "37109"
            match = re.search(r"\[(\d+)->(\d+)\]", log_line)
            return match.group(2) if match else None

        def extract_dispatcher_pid_from_log(log_line):
            # for example:
            # "[37090] [STDOUT] 2023-10-30 11:27:32,973 37109      DEBUG     [0] Dispatcher issuing request with params=[{'failure_type': 'div0'}] meta=[{'endpoint_id': 'Fail', 'endpoint_version': '1', 'endpoint_index': 1, 'replica': 0}] (dispatcher.py:266)"
            # Return "37109"
            match = re.search(
                r"(\d+)\s+DEBUG\s+\[\d\] Dispatcher issuing request", log_line
            )
            return match.group(1) if match else None

        def log_analysis(log_line):
            "Extract information from the logs in real time"
            pid = extract_worker_pid_from_log(log_line)
            if pid is not None:
                print(f"Captured dispatcher creation for PID {pid}")
                self.workers_pid.append(pid)
            dispatcher_request_pid = extract_dispatcher_pid_from_log(log_line)
            if dispatcher_request_pid is not None:
                print(f"Captured dispatcher request for PID {dispatcher_request_pid}")
                self.most_recent_dispatcher_request_pid = dispatcher_request_pid

        def reader(pipe, sysout, outlist, label):
            print(f"Enter reader for pipe {pipe}")
            for line in pipe:
                try:
                    line = line.decode("utf-8").rstrip()
                    outlist.append(line)
                    sysout.write(f"{label} {line}\n")
                    sysout.flush()
                    log_analysis(line)

                except:
                    pass
            print(f"Leave reader for pipe {pipe}")

        print("Creating threaded readers")
        self.tout = Thread(
            target=reader,
            args=[
                self.process.stdout,
                sys.stdout,
                stdout,
                f"[{self.process.pid}] [STDOUT]",
            ],
        )
        self.terr = Thread(
            target=reader,
            args=[
                self.process.stderr,
                sys.stderr,
                stderr,
                f"[{self.process.pid}] [STDERR]",
            ],
        )
        print("Starting threaded readers")
        self.tout.start()
        self.terr.start()


def parametrize_keys(keys_list: List[str], params_in_name: List[str]):
    """Helper to be passed as `preprocess` argument of `parametrize_from_file` to
    add another layer of parametrization on a basis of list read from parametrization
    file. Additionally allows to construct meaningful names (ids) of tests instead of
    indexes.

    Example:

    @parametrize_from_file(preprocess=parametrize_keys(['test_key_B'], [""]))

    will expand:
    {"test_key_A" : ["1", "2"], "test_key_B" : ["3", "4"]}

    to two test cases:
    {"test_key_A" : ["1", "2"], "test_key_B" : "3"}
    {"test_key_A" : ["1", "2"], "test_key_B" : "4"}

    Args:
        keys_list (List[str]): List of keys to be expanded to separate test cases
        params_in_name : List[str]: List of keys to be concatenated to construct test name

    Returns:
        Callable: Input to `preprocess` argument of `parametrize_from_file`
    """

    def _parametrize_keys(
        keys_to_expand: List[str], params_in_name: List[str], test_cases: Any
    ) -> List[Dict[str, Any]]:

        expanded_test_cases = []
        idx = 0
        params_in_name = ["id"] + params_in_name

        for test in test_cases:
            for key in keys_to_expand:
                test[key] = test[key] if isinstance(test[key], list) else [test[key]]
                for api in test[key]:
                    new_test = copy.deepcopy(test)
                    new_test[key] = api

                    # give a meaningful id/name to the test
                    new_test["id"] = str(idx)
                    id_parts = [
                        re.sub("[^A-Za-z0-9]+", "-", str(new_test[key]))
                        for key in params_in_name
                    ]
                    new_test["id"] = "_".join(id_parts)
                    idx += 1

                    expanded_test_cases.append(new_test)

        return expanded_test_cases

    return lambda test_cases: _parametrize_keys(keys_list, params_in_name, test_cases)
