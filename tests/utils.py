# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os
import subprocess
import sys
from abc import ABC, abstractmethod
import requests
import time
from threading import Thread
import signal
import regex as re


def run_subprocess(command_line_args, piped_input=None):
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

    process = subprocess.Popen(
        command_line_args,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=mod_env,
    )

    if piped_input:
        stdout, stderr = process.communicate(input=piped_input)
        result = process.wait()

        stdout = stdout.decode("utf-8").split("\n")
        stderr = stderr.decode("utf-8").split("\n")
    else:
        stdout = []
        stderr = []

        def reader(pipe, sysout, outlist, label):
            for line in pipe:
                try:
                    line = line.decode("utf-8").rstrip()
                    outlist.append(line)
                    sysout.write(f"SUBPROCESS {label}: {line}\n")
                    sysout.flush()
                except:
                    pass

        tout = Thread(
            target=reader, args=[process.stdout, sys.stdout, stdout, "STDOUT"]
        )
        terr = Thread(
            target=reader, args=[process.stderr, sys.stderr, stderr, "STDERR"]
        )
        tout.start()
        terr.start()
        result = process.wait()
        tout.join()
        terr.join()

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


class TestClient(ABC):
    def wait_server_ready(self, timeout=60):
        print("Waiting for test server to be up...")
        t0 = time.time()
        timeout_raised = False
        while True:
            time.sleep(3)
            try:
                response = requests.get(self.base_url + "/health/ready")
                if response.status_code == 200:
                    self.is_ready = True
                    break
                if (time.time() - t0) > timeout:
                    timeout_raised = True
                    break
            except:
                pass
        if timeout_raised:
            raise Exception("wait_server_ready: Timeout")

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
        cls.config_file: str = ""
        cls.process = None
        cls.base_url = "http://localhost:8100"
        cls.is_ready = False
        cls.wait_ready = True
        cls.tout = None
        cls.terr = None
        cls.workers_pid = []
        cls.worker_replicas = 1
        cls.check_logs = ""
        cls.check_logs
        cls.ssf_commands = ["init", "build", "run"]

        cls.configure(cls)

        cls.process = subprocess.Popen(
            [
                "gc-ssf",
                "--config",
                cls.config_file,
                "--replicate-application",
                str(cls.worker_replicas),
                *cls.ssf_commands,
            ],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        cls.setup_pipe(cls)
        if cls.wait_ready:
            cls.wait_server_ready(cls)

    @classmethod
    def teardown_class(cls):
        """teardown any state that was previously setup with a call to
        setup_class.
        """
        print("TEARDOWN:", cls.process.pid)
        cls.process.send_signal(signal.SIGINT)
        cls.tout.join()
        cls.terr.join()
        print("TEARDOWN OK ")

    def is_string_in_logs(self, search_string: str):
        with open("ssf.log", "r") as file:
            for line in file:
                if search_string in line:
                    print(
                        f"The search string '{search_string}' was found in the log file."
                    )
                    return True
            else:
                print(
                    f"The search string '{search_string}' was not found in the log file."
                )
                return False

    def setup_pipe(self):
        stdout = []
        stderr = []

        def extract_worker_pid_from_log(log_line):
            match = re.search(r"\[(\d+)->(\d+)\]", log_line)
            if match:
                return match.group(2)
            else:
                return None

        def log_analysis(log_line):
            "Extract information from the logs in real time"
            pid = extract_worker_pid_from_log(log_line)
            if pid is not None:
                self.workers_pid.append(pid)

        def reader(pipe, sysout, outlist, label):
            for line in pipe:
                try:
                    line = line.decode("utf-8").rstrip()
                    outlist.append(line)
                    sysout.write(f"SUBPROCESS {label}: {line}\n")
                    sysout.flush()
                    log_analysis(line)

                except:
                    pass

        self.tout = Thread(
            target=reader, args=[self.process.stdout, sys.stdout, stdout, "STDOUT"]
        )
        self.terr = Thread(
            target=reader, args=[self.process.stderr, sys.stderr, stderr, "STDERR"]
        )
        self.tout.start()
        self.terr.start()
