# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import contextlib
import importlib.util
import glob
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from typing import List, Optional, Dict, Union
from threading import Thread
from yaml import safe_load as yaml_safe_load

from argparse import Namespace
from dataclasses import is_dataclass
from ssf.config import SSFConfig

logger = logging.getLogger("ssf")

# Lookup value from a dict and return it as a string.
# Return a default if it doesn't exist
# e.g.
#  application.name ->
#  d['application']['name']
# e.g.
#  application.trace:False ->
#  d['application']['trace'] or False
def lookup_dict(d: Optional[Dict], symbol_id: str, namespaced=False) -> str:
    ret = None

    # symbol_id refs the dict as 'dictnamespace.y.z:default'
    default = None
    # Skip dictnamespace
    if namespaced:
        symbol_id = symbol_id[symbol_id.find(".") + 1 :]
    # Look for default (if any)
    default_at = symbol_id.find(":")
    if default_at >= 0:
        default = symbol_id[default_at + 1 :]
        symbol_id = symbol_id[:default_at]
    try:
        # Split and walk the ref.
        ref = symbol_id.split(".")
        c = d
        for r in ref:
            c = c[r] if not is_dataclass(d) else getattr(c, r)
        ret = str(c)
    except:
        pass

    if not ret:
        if default is None:
            raise ValueError(f"{symbol_id} not specified and there is no default")
        else:
            logger.warning(f"{symbol_id} not specified - defaulting to '{default}'")
            ret = default

    return ret


# Expand all symbols in string using specified dictionary.
def expand_str(entry: str, d: dict):
    while True:
        sym_begin = entry.find("{{")
        if sym_begin < 0:
            break
        sym_end = sym_begin + 2 + entry[sym_begin + 2 :].find("}}") + 1
        if sym_end < 0:
            raise ValueError(
                f"Failed to find closing brackets for symbol beginning at position {sym_begin}, entry {entry}"
            )
        symbol = entry[sym_begin + 2 : sym_end - 1]
        symval = lookup_dict(d, symbol)
        entry = entry[0:sym_begin] + symval + entry[sym_end + 1 :]
    return entry


def logged_subprocess(
    tag,
    command_line_args,
    file_output=None,
    piped_input=None,
    stdout_log_level=logging.DEBUG,
    stderr_log_level=logging.DEBUG,
) -> int:
    # NOTES:
    # Option: Specifiy file_output to copy output to file in addition to logger
    # Option: Specify pipe_input to pass input to process
    # Logging errors as debug by default because many external apps (e.g. git)
    # write non-errors to stderr which generates bogus red-ink ERROR lines in
    # the log. The exit result must be used to trap real errors.
    def log_line(tag, line, level, file_output):
        if level is not None:
            logger.log(level, f"[{tag}] {line}")
        if file_output:
            file_output.write(line + "\n")

    process = subprocess.Popen(
        command_line_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
    )

    if piped_input:
        out, err = process.communicate(piped_input)
        result = process.wait()
        for line in out.decode("utf-8").split("\n"):
            log_line(tag, line, stdout_log_level, file_output)
        for line in err.decode("utf-8").split("\n"):
            log_line(tag, line, stderr_log_level, file_output)
    else:

        def reader(pipe, tag, level, file_output):
            for line in pipe:
                try:
                    log_line(tag, line.decode("utf-8").rstrip(), level, file_output)
                except:
                    pass

        tout = Thread(
            target=reader, args=[process.stdout, tag, stdout_log_level, file_output]
        )
        terr = Thread(
            target=reader, args=[process.stderr, tag, stderr_log_level, file_output]
        )
        tout.start()
        terr.start()
        result = process.wait()
        tout.join()
        terr.join()
    return result


def install_python_packages(python_packages: str) -> int:
    ret = 0
    logger.info(f"installing python packages {python_packages}")
    for p in python_packages.split(","):
        logger.debug(f"pip-installing package {p}")
        ret = ret + logged_subprocess(
            "pip", [sys.executable, "-m", "pip", "install", p]
        )
    return ret


def install_python_requirements(python_requirements: str) -> int:
    ret = 0
    logger.info(f"installing python requirements {python_requirements}")
    for r in python_requirements.split(","):
        logger.debug(f"pip-installing requirements {r}")
        ret = ret + logged_subprocess(
            "pip", [sys.executable, "-m", "pip", "install", "-r", r]
        )
    return ret


def load_module(module_file: str, module_name: str):
    if not module_name in sys.modules:
        logger.info(f"loading module {module_file} with module name {module_name}")
        spec = importlib.util.spec_from_file_location(module_name, module_file)
        _module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = _module
        spec.loader.exec_module(_module)
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


def build_file_list(
    src_dir: str,
    glob_inclusions: List[str],
    glob_exclusions: List[str] = [],
    always: List[str] = [],
):
    """
    Build a file list from src_dir.
    Include all glob searchs in glob_inclusions.
    Exclude all glob searchs in glob_inclusions.
    Ensure files in always are always present.

    Returns:
        Root dir and a list of files
    """

    # Move to the src directory which is where we glob from.
    # This is to support relative glob paths.
    with temporary_cwd(src_dir):

        # Establish absolute path.
        src_dir = os.path.abspath(".")

        logger.debug(f"glob_inclusions={glob_inclusions}")
        logger.debug(f"glob_exclusions={glob_exclusions}")
        logger.debug(f"always={always}")

        # Build complete include/exclude file list.
        files_include = []
        files_exclude = []
        for g in glob_inclusions:
            files_include.extend(
                [g for g in glob.glob(g, recursive=True) if os.path.isfile(g)]
            )
        for g in glob_exclusions:
            files_exclude.extend(
                [g for g in glob.glob(g, recursive=True) if os.path.isfile(g)]
            )

        files = sorted(list((set(files_include) - set(files_exclude)) | set(always)))

        root_src_dir = None

        # Establish the root_src_dir with the discovered highest level src directory.
        # i.e. Find the common path given set of absolute paths.
        abs_files = []
        for f in files:
            abs_files.append(os.path.abspath(f))
        if len(abs_files):
            root_src_dir = os.path.commonpath(abs_files)

    # Return root and files.
    return src_dir, root_src_dir, abs_files


def get_default_ipaddr():
    with tempfile.TemporaryFile(mode="w+t") as capture:
        exit_code = logged_subprocess(
            f"Get IP", ["ip", "route", "show"], file_output=capture
        )
        if exit_code:
            raise ValueError(f"Get IP errored {exit_code}")
        capture.seek(0)
        capture = capture.readlines()
        # Get device from default route:
        # e.g. "default via 10.129.96.1 dev ens1f0np0 proto dhcp src 10.129.96.101 metric 100"
        #   => "ens1f0np0"
        device = None
        for line in capture:
            if "default " in line:
                if "dev " in line:
                    line = line.split("dev ")
                    device = line[1].split(" ")[0]

        if not device:
            logger.error(f"Error finding default route device")
            return None

        # Get ipaddr from default device:
        # e.g. "10.129.96.1 dev ens1f0np0 proto dhcp scope link src 10.129.96.101 metric 100"
        #   => "10.129.96.101"
        ipaddr = None
        for line in capture:
            if (not "default " in line) and "src " in line:
                if f"dev {device}" in line:
                    line = line.split("src ")
                    ipaddr = line[1].split(" ")[0]
        if not ipaddr:
            logger.error(f"Error finding ipaddr for device {device}")
            return None

        return ipaddr


def get_poplar_version():
    try:
        result = subprocess.run(["gc-info", "--version"], stdout=subprocess.PIPE)
        if result.returncode == 0:
            output = result.stdout.decode("utf-8")
            # e.g. "Poplar version: 3.1.0"
            output = output.split(":")
            if len(output) == 2:
                poplar_version = output[1].strip()
                return poplar_version
    except:
        pass
    return None


def get_poplar_requirement(ssf_config: SSFConfig) -> str:
    try:
        return ssf_config.application.dependencies["poplar"]
    except:
        return None


def get_ipu_count_requirement(ssf_config: SSFConfig) -> int:
    """Gets the number of IPUs required for running the application.

    Args:
        ssf_config (SSFConfig): SSF config for application.

    Returns:
        int: number of IPUs required to run.
    """

    try:
        return ssf_config.application.total_ipus
    except:
        return None


def get_ipu_count() -> int:
    try:
        result = subprocess.run(["gc-info", "--ipu-count"], stdout=subprocess.PIPE)
        if result.returncode == 0:
            output = result.stdout.decode("utf-8")
            return int(output)
    except:
        pass
    return 0


def poplar_version_ok(ssf_config: SSFConfig) -> bool:
    requirement = get_poplar_requirement(ssf_config)
    if not requirement:
        logger.debug("Application has no specific Poplar requirement")
        return True

    current = get_poplar_version()

    if current is not None:
        if current in requirement:
            logger.debug(f"Poplar '{current}' satisfies application with {requirement}")
            return True

    logger.debug(f"Poplar '{current}' does not satisfy application with {requirement}")
    return False


def ipu_count_ok(ssf_config: SSFConfig, step_name: str) -> bool:
    """Checks is system has required number of IPUs to perform given action.

    Args:
        ssf_config (SSFConfig): SSF config for application.
        action_name (str): name of the action (step) to be performed.

    Returns:
        bool: True is IPU count requirements are met, False otherwise.
    """

    if step_name not in ["test", "run"]:
        return True

    requirement = get_ipu_count_requirement(ssf_config)
    if not requirement >= 1:
        logger.debug("Application has no specific IPU requirement")
        return True

    current = get_ipu_count()
    if current >= requirement:
        logger.debug(f"IPUs {current} satisfies application with {requirement}")
        return True

    msg = (
        f"Insufficient IPUs - needs to perform {step_name} step. "
        f"Required {requirement}, available {current}."
    )

    logger.error(msg)
    return False
