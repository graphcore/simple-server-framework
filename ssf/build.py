# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import subprocess
from socket import socket
import os

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *
from ssf.application_interface.logger import get_log_queue

from ssf.generate_endpoints import generate_endpoints
from ssf.app_venv import create_app_venv
from ssf.utils import poplar_version_ok, get_poplar_requirement
from ssf.utils import ReplicaManager
from ssf.sdk_utils import maybe_activate_poplar_sdk

logger = logging.getLogger("ssf")


def build(ssf_config: SSFConfig):
    logger.info("> ==== Build ====")
    env = maybe_activate_poplar_sdk(ssf_config)
    if not poplar_version_ok(ssf_config, env):
        raise SSFExceptionUnmetRequirement(
            f"Missing or unsupported Poplar version - needs {get_poplar_requirement(ssf_config)}"
        )

    logger.info("> Generate endpoints")
    generate_endpoints(ssf_config)

    logger.info(f"> Checking application venv")
    create_app_venv(ssf_config)

    log_queue = get_log_queue()
    with socket() as s:
        s.bind(("", 0))
        # Get a free port from OS
        port = s.getsockname()[1]
        manager = ReplicaManager(address=("localhost", port), authkey=b"ssf")
    manager.register(
        "config", callable=lambda: {"ssf_config": ssf_config, "server_pid": os.getpid()}
    )
    manager.register("log_queue", callable=lambda: log_queue)
    manager.start()
    worker_pth = os.path.realpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "application_interface/worker.py",
        )
    )
    bin_path = os.path.join(ssf_config.application.venv_dir, "bin/python")
    JUST_BUILD_APP = -1
    builder_process = subprocess.Popen(
        [bin_path, worker_pth, str(JUST_BUILD_APP), str(port)], env=env
    )
    builder_process.communicate()
    ret = builder_process.returncode
    return ret
