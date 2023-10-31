# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import logging
import os

from ssf.utils import logged_subprocess
from ssf.results import SSFExceptionSshError

logger = logging.getLogger()


def check_init_ssh():
    ssh_dir = os.path.expanduser("~/.ssh")
    if not os.path.exists(ssh_dir):
        logging.debug("Create ~/.ssh")
        exit_code = logged_subprocess("SSH Create ~/.ssh", ["mkdir", "-p", ssh_dir])
        if exit_code:
            raise SSFExceptionSshError(f"SSH Create ~/.ssh errored ({exit_code})")


def add_ssh_key(env_key: str):
    key = os.getenv(env_key)
    if not key:
        raise SSFExceptionSshError(f"SSH key '{env_key}' must be set in environment")
    if key[-1] != "\n":
        key = key + "\n"
    check_init_ssh()
    # NOTE:
    # Suppressing stdout trace reduce keys being logged.
    exit_code = logged_subprocess(
        "SSH Add key",
        ["ssh-add", "-"],
        piped_input=key.encode(),
        stdout_log_level=None,
    )
    if exit_code:
        raise SSFExceptionSshError(f"SSH Add key '{env_key}' errored ({exit_code})")


def add_ssh_host(host: str):
    check_init_ssh()
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    logging.debug(f"Check host {host} is known")
    exit_code = logged_subprocess(
        f"SSH Check host known", ["ssh-keygen", "-l", "-F", host]
    )
    if exit_code:
        logging.debug(f"Adding host {host} as known")
        with open(known_hosts, "a+") as write_hosts:
            exit_code = logged_subprocess(
                f"SSH - Add host",
                ["ssh-keyscan", "-H", host],
                file_output=write_hosts,
                stdout_log_level=None,
            )
            if exit_code:
                raise SSFExceptionSshError(
                    f"SSH Add host '{host}' errored ({exit_code})"
                )


def clear_ssh_keys():
    args = ["ssh-add", "-D"]
    logger.info(f"Clear all keys")
    exit_code = logged_subprocess("SSH Clear keys", ["ssh-add", "-D"])
    if exit_code:
        raise SSFExceptionSshError(f"SSH Clear all keys errored ({exit_code})")
