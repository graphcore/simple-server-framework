# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

from ssf.application_interface.utils import *

import glob
import logging
import os
import subprocess
import sys
import tempfile
import multiprocessing as mp
import pickle
import base64

from typing import List, Optional, Dict
from threading import Thread

from dataclasses import is_dataclass
from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import (
    SSFExceptionInternalError,
    SSFExceptionNetworkError,
)
from ssf.application_interface.utils import get_ipu_count

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
            raise SSFExceptionInternalError(
                f"{symbol_id} not specified and there is no default"
            )
        else:
            logger.info(f"{symbol_id} not specified. Defaulting to '{default}'")
            ret = default

    return ret


# Set value in dict, supporting nested dictionaries/lists.
# e.g.
#  set_dict(d, "application.name", "new application name")
# If the field is new then it will set value as string.
# If the field already exists then the type must match.
# For lists, the index must be specified:
# e.g.
#   set_dict(d, "mylist[5]", "value for mylist[5]")
# (list will be grown to accomadate the index)
# Returns True if succesful, else False.
def set_dict(d: Dict, symbol_id: str, value):
    ref = symbol_id.split(".")
    last_node = len(ref) - 1
    logger.debug(f"set dict: '{symbol_id}' = '{value}'")

    def leaf_type(x):
        return x is None or isinstance(x, (int, float, str, bool))

    for i, r in enumerate(ref):
        logger.debug(f"set dict: enum {i}/{last_node},'{r}' with d {d}")
        # Decode indexed lists.
        idx = None
        ilist = r.replace("[", ",").replace("]", ",").split(",")
        logger.debug(f"{ilist}")
        if len(ilist) == 3:
            idx = int(ilist[1])
            r = ilist[0]
            if r in d:
                if not isinstance(d[r], list):
                    logger.warning(
                        f"set dict: '{r}[{idx}]' is not valid for non-list field"
                    )
                    return False
                if idx > len(d[r]) - 1:
                    d[r].extend([None] * (idx - (len(d[r]) - 1)))
        elif r in d and isinstance(d[r], list):
            logger.warning(f"set dict: '{r}' is a list; index required `{r}[<idx>]`")
            return False

        if r in d:
            logger.debug(f"set dict: -> '{r}[{idx}]' (type {type(d[r])})")
            if isinstance(d[r], dict):
                logger.debug(f"set dict:      dict node with '{r}'")
                d = d[r]
            elif isinstance(d[r], list) and not leaf_type(d[r][idx]):
                logger.debug(
                    f"set dict:      list node with '{r}[{idx}]' (type {type(d[r][idx])})"
                )
                d = d[r][idx]
            elif idx is None:
                logger.debug(f"set dict:      leaf with '{r}' = '{value}'")
                if i < last_node:
                    logger.warning(
                        f"set dict: '{symbol_id}' includes an existing leaf field '{r}'"
                    )
                    return False
                if isinstance(d[r], bool):
                    if value not in ["True", "False"]:
                        logger.warning(
                            f"set dict: failed to set existing field value '{r}' = {type(d[r])}({value})"
                        )
                        return False
                    d[r] = value == "True"
                else:
                    try:
                        d[r] = type(d[r])(value)
                    except:
                        logger.warning(
                            f"set dict: failed to set existing field value '{r}' = {type(d[r])}({value})"
                        )
                        return False
                logger.debug(
                    f"set dict: existing field value '{r}' = {type(d[r])}({value}) == {d[r]} ({type(d[r])})"
                )
                return True
            else:
                logger.debug(f"set dict:      leaf with '{r}[{idx}]' = '{value}'")
                if i < last_node:
                    logger.warning(
                        f"set dict: '{symbol_id}' includes an existing leaf field '{r}[{idx}]'"
                    )
                    return False
                if d[r][idx] is None:
                    d[r][idx] = str(value)
                elif isinstance(d[r][idx], bool):
                    if value not in ["True", "False"]:
                        logger.warning(
                            f"set dict: failed to set existing field value '{r}[{idx}]' = {type(d[r][idx])}({value})"
                        )
                        return False
                    d[r][idx] = value == "True"
                else:
                    try:
                        d[r][idx] = type(d[r][idx])(value)
                    except:
                        logger.warning(
                            f"set dict: failed to set existing field value '{r}[{idx}]' = {type(d[r][idx])}({value})"
                        )
                        return False
                logger.debug(
                    f"set dict: existing field value '{r}[{idx}]' = {type(d[r][idx])}({value}) == {d[r][idx]} ({type(d[r][idx])})"
                )
                return True
        else:
            logger.debug(f"set dict: -> '{r}[{idx}]'")
            if idx is None:
                if i == last_node:
                    d[r] = str(value)
                    logger.debug(f"set dict: new field value '{r}' = {d[r]}")
                    return True
                d[r] = {}
                d = d[r]
            else:
                if i == last_node:
                    d[r] = [None] * (1 + idx)
                    d[r][idx] = str(value)
                    logger.debug(f"set dict: new field value '{r}[{idx}]' = '{d[r]}'")
                    return True
                d[r] = [{}] * (1 + idx)
                d = d[r][idx]

    logger.warning(f"set dict: '{symbol_id}' references an existing non-leaf field")
    return False


# Expand all symbols in string using specified dictionary.
def expand_str(entry: str, d: dict):
    while True:
        sym_begin = entry.find("{{")
        if sym_begin < 0:
            break
        sym_end = sym_begin + 2 + entry[sym_begin + 2 :].find("}}") + 1
        if sym_end < 0:
            raise SSFExceptionInternalError(
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
    environ=None,
) -> int:
    # NOTES:
    # Option: Specifiy file_output to copy output to file in addition to logger
    # Option: Specify pipe_input to pass input to process
    # Logging errors as debug by default because many external apps (e.g. git)
    # write non-errors to stderr which generates bogus red-ink ERROR lines in
    # the log. The exit result must be used to trap real errors.
    def log_line(label, line, level, file_output):
        if level is not None:
            logger.log(level, f"{label} {line}")
        if file_output:
            file_output.write(line + "\n")

    logger.debug(f"Creating process with {command_line_args} for [{tag}]")
    process = subprocess.Popen(
        command_line_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        env=os.environ.copy() if environ is None else environ,
    )
    logger.debug(f"Created process {process.pid} for [{tag}]")

    if piped_input:
        out, err = process.communicate(piped_input)
        logger.debug(f"Waiting for process result from {process.pid}")
        result = process.wait()
        logger.debug(f"Process {process.pid} [{tag}] completed with result {result}")
        logger.debug(f"Logging output for {process.pid} [{tag}]")
        for line in out.decode("utf-8").split("\n"):
            log_line(f"[{process.pid}] [{tag}]", line, stdout_log_level, file_output)
        for line in err.decode("utf-8").split("\n"):
            log_line(f"[{process.pid}] [{tag}]", line, stderr_log_level, file_output)
    else:

        def reader(pipe, label, level, file_output):
            for line in pipe:
                try:
                    log_line(label, line.decode("utf-8").rstrip(), level, file_output)
                except:
                    pass

        logger.debug("Creating threaded readers")
        tout = Thread(
            target=reader,
            args=[
                process.stdout,
                f"[{process.pid}] [{tag}]",
                stdout_log_level,
                file_output,
            ],
        )
        terr = Thread(
            target=reader,
            args=[
                process.stderr,
                f"[{process.pid}] [{tag}]",
                stderr_log_level,
                file_output,
            ],
        )
        tout.start()
        terr.start()
        logger.debug(f"Waiting for process result from {process.pid} [{tag}]")
        result = process.wait()
        logger.debug(f"Process {process.pid} [{tag}] completed with result {result}")
        tout.join()
        terr.join()
    logger.debug(f"Returning result {result} from [{tag}]")
    return result


def install_python_packages(
    python_packages: str, executable: str = sys.executable
) -> int:
    ret = 0
    logger.info(f"Installing python packages {python_packages}")
    for p in python_packages.split(","):
        extend = p.split(" ")
        logger.debug(f"pip-installing package {extend}")
        ret = ret + logged_subprocess(
            "pip", [executable, "-m", "pip", "install"] + extend
        )
    return ret


def install_python_requirements(
    python_requirements: str, executable: str = sys.executable
) -> int:
    ret = 0
    logger.info(f"installing python requirements {python_requirements}")
    for r in python_requirements.split(","):
        logger.debug(f"pip-installing requirements {r}")
        ret = ret + logged_subprocess(
            "pip", [executable, "-m", "pip", "install", "-r", r]
        )
    return ret


def build_file_list(
    src_dir: str,
    glob_inclusions: List[str],
    glob_exclusions: List[str] = [],
    always: List[str] = [],
    warn_on_empty_inclusions: bool = True,
    warn_on_empty_exclusions: bool = True,
    glob_recursion=True,
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
        logger.debug(f"recursion {glob_recursion}")

        # Build complete include/exclude file list.
        files_include = []
        files_exclude = []
        for g in glob_inclusions:
            found = [
                os.path.abspath(f)
                for f in glob.glob(g, recursive=glob_recursion)
                if os.path.isfile(f)
            ]
            if len(found) == 0:
                if warn_on_empty_inclusions:
                    logger.warning(f"No matching files found for inclusions '{g}'")
            else:
                files_include.extend(found)
        for g in glob_exclusions:
            found = [
                os.path.abspath(f)
                for f in glob.glob(g, recursive=glob_recursion)
                if os.path.isfile(f)
            ]
            if len(found) == 0:
                if warn_on_empty_exclusions:
                    logger.warning(f"No matching files found for exclusions '{g}'")
            else:
                files_exclude.extend(found)
        files_always = [os.path.abspath(a) for a in always]

        logger.debug(f"files_include={files_include}")
        logger.debug(f"files_exclude={files_exclude}")
        logger.debug(f"files_always={files_always}")

        files = sorted(
            list((set(files_include) - set(files_exclude)) | set(files_always))
        )

        root_src_dir = None

        # Establish the root_src_dir with the discovered highest level src directory.
        # i.e. Find the common path given set of absolute paths.
        # abs_files = []
        # for f in files:
        #    abs_files.append(os.path.abspath(f))
        if len(files):
            root_src_dir = os.path.commonpath(files)

    # Return root and files.
    logger.debug(f"src_dir {src_dir}, root_src_dir {root_src_dir}, files {files}")
    return src_dir, root_src_dir, files


def get_default_ipaddr():
    with tempfile.TemporaryFile(mode="w+t") as capture:
        exit_code = logged_subprocess(
            f"Get IP", ["ip", "route", "show"], file_output=capture
        )
        if exit_code:
            raise SSFExceptionNetworkError(f"Get IP errored ({exit_code})")
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


def get_poplar_version(env):
    try:
        result = subprocess.run(
            ["gc-info", "--version"], stdout=subprocess.PIPE, env=env
        )
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
    return ssf_config.application.dependencies.get("poplar", None)


def get_python_requirements(ssf_config: SSFConfig) -> ([str], [str]):
    python_dependencies = ssf_config.application.dependencies.get("python", None)
    # We support 'requirements.txt' and/or packages as comma-separated list.
    deps_requirement_files = []
    deps_packages = []
    if python_dependencies:
        for d in python_dependencies.split(","):
            d = d.strip()
            if ".txt" in d:
                deps_requirement_files.append(
                    os.path.join(ssf_config.application.dir, d)
                )
            else:
                deps_packages.append(d)
    logger.debug(f"deps_requirement_files {deps_requirement_files}")
    logger.debug(f"deps_packages {deps_packages}")
    return deps_requirement_files, deps_packages


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


def poplar_version_ok(ssf_config: SSFConfig, env: dict) -> bool:
    requirement = get_poplar_requirement(ssf_config)
    if not requirement:
        logger.debug("Application has no specific Poplar requirement")
        return True

    current = get_poplar_version(env)
    if current is not None:
        if current in requirement:
            logger.debug(f"Poplar '{current}' satisfies application with {requirement}")
            return True

    logger.debug(f"Poplar '{current}' does not satisfy application with {requirement}")
    return False


def ipu_count_ok(ssf_config: SSFConfig, step_name: str, env: dict) -> bool:
    """Checks is system has required number of IPUs to perform given action.

    Args:
        ssf_config (SSFConfig): SSF config for application.
        action_name (str): name of the action (step) to be performed.
        env: instance of os.environ in which to check

    Returns:
        bool: True if IPU count requirements are met, False otherwise.
    """

    if step_name not in ["test", "run"]:
        return True

    requirement = get_ipu_count_requirement(ssf_config)
    if not requirement >= 1:
        logger.debug("Application has no specific IPU requirement")
        return True

    current = get_ipu_count(env)
    if current >= requirement:
        logger.debug(f"IPUs {current} satisfies application with {requirement}")
        return True

    msg = (
        f"Insufficient IPUs - needs to perform {step_name} step. "
        f"Required {requirement}, available {current}."
    )

    logger.error(msg)
    return False


def get_endpoints_gen_module_path(api_name):
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            f"{api_name}_runtime",
            f"{api_name}_generate_endpoints.py",
        )
    )


def get_supported_apis():
    return [API_FASTAPI, API_GRPC]


def object_to_ascii(obj):
    return base64.b64encode(pickle.dumps(obj)).decode("ascii")


def ascii_to_object(ascii):
    return pickle.loads(base64.b64decode(ascii.encode("ascii")))
