# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# NOTE:
# Do not import external packages in application_interface modules
# to avoid introducing additional dependencies for the application.
# Only import SSF modules that are also in application_interface.

import contextlib
import importlib.util
import logging
import os
import sys
import multiprocessing.managers
import subprocess

from ssf.application_interface.results import SSFExceptionApplicationModuleError

API_FASTAPI = "fastapi"
API_GRPC = "grpc"

logger = logging.getLogger("ssf")


def get_ipu_count(env=None) -> int:
    try:
        result = subprocess.run(
            ["gc-info", "--ipu-count"],
            stdout=subprocess.PIPE,
            env=os.environ.copy() if env is None else env,
        )
        if result.returncode == 0:
            output = result.stdout.decode("utf-8")
            return int(output)
    except Exception as e:
        logger.debug(f"Failed get_ipu_count ({e})")
        pass
    return 0


def load_module(module_file: str, module_name: str):
    if not module_name in sys.modules:
        logger.info(f"loading module {module_file} with module name {module_name}")
        try:
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            _module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = _module
            spec.loader.exec_module(_module)
        except Exception as e:
            raise SSFExceptionApplicationModuleError(
                f"Failure loading {module_file}."
            ) from e
    return sys.modules[module_name]


@contextlib.contextmanager
def temporary_cwd(target_cwd: str):
    orig_cwd = os.getcwd()
    os.chdir(target_cwd)
    try:
        logger.debug(f"Temporary change directory to {target_cwd}")
        yield
    finally:
        os.chdir(orig_cwd)
        logger.debug(f"Temporary change directory reverted to {orig_cwd}")


class ReplicaManager(multiprocessing.managers.SyncManager):
    pass
