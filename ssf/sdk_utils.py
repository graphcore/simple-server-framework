# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import requests
import tarfile
import os
import re
from shutil import copytree, rmtree
import logging
import tempfile
import base64
from packaging import version
from urllib.parse import urlparse

from ssf.application_interface.config import SSFConfig
from ssf.application_interface.results import *
from ssf.utils import get_poplar_requirement
from ssf.utils import poplar_version_ok
from ssf.utils import logged_subprocess

logger = logging.getLogger("ssf")

# The URL from which available SDK are enumerated.
GRAPHCORE_DOWNLOADS = "https://www.graphcore.ai/downloads"
POPLAR_UBUNTU_ROOT = "poplar_sdk-ubuntu_"
POPLAR_SUFFIX_ROOT = ".tar.gz"

CACHE_BASE = os.path.realpath(os.path.abspath(os.path.expanduser("~/.cache/ssf")))
CACHE_SDK = os.path.join(CACHE_BASE, "sdks")
CACHE_CUSTOM = os.path.join(CACHE_BASE, "custom")

DISTRIBUTION_INFO_FILE = "/etc/os-release"

# Set this to True to enable logging of the entire archive.
# This is disabled by default because it is observed
# to generate 'queue.Full' errors (at least for Github runs)
# presumably because it floods the logger queue.
WANT_LOG_ARCHIVE_FILENAMES = False

# Unique filename prefixes for each known Poplar SDK wheel.
# Plus, for each, is there a cpu-vendor specific variant.
known_poplar_wheels = {
    "poptorch": ("poptorch-", False),
    "poptorch_geometric": ("poptorch_geometric-", False),
    "tensorflow": ("tensorflow-", True),
    "keras": ("keras-", False),
    "ipu_tensorflow_addons": ("ipu_tensorflow_addons-", False),
}

# Downloadable SDKs
# This is keyed on Ubuntu version (for example "20.04") and Poplar version (for example "3.0.0") and
# returns a dictionary with hash and the wget to use.
# For example: packages["20.04"]["3.0.0"]
# => {"hash": "1b114aac3a", "wget": "https://downloads.graphcore.ai/direct?package=poplar-poplar_sdk_ubuntu_20_04_3.0.0_1b114aac3a-3.0.0&amp;file=poplar_sdk-ubuntu_20_04-3.0.0-1b114aac3a.tar.gz" }
downloadable_sdks = None


def enumerate_downloadable_sdks():
    global downloadable_sdks
    if downloadable_sdks is not None:
        return downloadable_sdks
    downloadable_sdks = {}
    logger.info(f"> Enumerating downloadable SDKs")
    response = requests.get(GRAPHCORE_DOWNLOADS)
    logger.info(f"{GRAPHCORE_DOWNLOADS} response {response}")
    for l in response.iter_lines():
        l = l.decode()
        if POPLAR_UBUNTU_ROOT in l:
            if "wget" in l:
                # For examples: "$ wget -O 'poplar_sdk-ubuntu_20_04-3.0.0-1b114aac3a.tar.gz' 'https://downloads.graphcore.ai/direct?package=poplar-poplar_sdk_ubuntu_20_04_3.0.0_1b114aac3a-3.0.0&amp;file=poplar_sdk-ubuntu_20_04-3.0.0-1b114aac3a.tar.gz'</code></pre>"
                parsed = l
                parsed = parsed.replace("$ ", "")
                parsed = parsed.replace("wget", "")
                parsed = parsed.replace("-O", "")
                parsed = parsed.replace("</code></pre>", "")
                parsed = parsed.replace("&amp;", "&")
                parsed = parsed.strip()
                parsed = parsed.split(" ")
                for i, p in enumerate(parsed):
                    parsed[i] = p.replace("'", "")
                if len(parsed) == 2:
                    logger.debug(f"Parsed {l} as {parsed}")
                    v = parsed[0].split(POPLAR_UBUNTU_ROOT)
                    v = v[1]
                    v = v.split(POPLAR_SUFFIX_ROOT)
                    v = v[0]
                    # For example: "poplar_sdk-ubuntu_20_04-3.3.0-208993bbb7.tar.gz" => 20.04, 3.0.0, 1b114aac3a
                    versions = v.split("-")
                    ubuntu_version = versions[0].replace("_", ".")
                    poplar_version = versions[1]
                    poplar_hash = versions[2]
                    downloadable_sdks.setdefault(ubuntu_version, {})[poplar_version] = {
                        "hash": poplar_hash,
                        "wget": parsed[1],
                    }
                else:
                    logger.warning(f"Failed to parse package {l} (parsed as {parsed})")
    logger.info(f"Available downloadable SDKs {downloadable_sdks}")
    return downloadable_sdks


def get_distro_information():
    distro = {}
    with open(DISTRIBUTION_INFO_FILE) as file:
        lines = [line.rstrip() for line in file]
    for l in lines:
        kv = l.split("=")
        distro[kv[0].strip(' "')] = kv[1].strip(' "')
    return distro


def default_ubuntu_version():
    distro = get_distro_information()
    assert distro["NAME"] == "Ubuntu"
    return distro["VERSION_ID"]


def default_poplar_version(ubuntu):
    sdks = enumerate_downloadable_sdks()
    latest = None
    if ubuntu in sdks:
        poplars = sdks[ubuntu]
        for poplar in poplars:
            if latest is None or version.parse(poplar) > version.parse(latest):
                latest = poplar
    return latest


def sdk_url(ubuntu=None, poplar=None):
    sdks = enumerate_downloadable_sdks()
    try:
        if ubuntu is None:
            ubuntu = default_ubuntu_version()
            logger.info(f"Defaulting Ubuntu version to current version {ubuntu}")
        if poplar is None:
            poplar = sdks[ubuntu][0]
            logger.info(f"Defaulting Poplar version to first entry {poplar}")
        url = sdks[ubuntu][poplar]["wget"]
        logger.debug(f"SDK URL {url}")
        return url
    except Exception as e:
        logger.info(f"Failed to find package for Ubuntu {ubuntu}, Poplar {poplar}")
    return None


def url_to_path(url):
    # create a cache dir name for custom URL
    path = str(base64.b64encode(url.encode("utf-8")))
    path = re.sub(r"[^a-zA-Z0-9-_]", "", path)
    return path[:20]


def get_poplar_sdk(ssf_config: SSFConfig) -> str:
    """Return a path to an unpacked  Poplar SDK root
    Download or use cache if necessary

    Args:
        ssf_config (SSFConfig): _description_

    Raises:
        SSFExceptionInstallationError: _description_
        SSFExceptionInstallationError: _description_

    Returns:
        str: path to unpacked poplar SDK root,
        which also contains packages .whl files
    """
    download = True
    cache = None

    poplar_location = ssf_config.application.dependencies.get("poplar_location", False)
    sdk_enabled = os.environ.get("POPLAR_SDK_ENABLED", False)

    # If SDK already enabled
    if sdk_enabled and poplar_version_ok(ssf_config, os.environ.copy()):
        sdk_root = os.path.abspath(os.path.join(sdk_enabled, ".."))
        if find_whl_in_dir("poptorch", sdk_root) is None:
            logger.debug(f"Cannot find .whl files in the enabled SDK {sdk_enabled}.")
        else:
            logger.info(f"Using the enabled Poplar SDK: {sdk_root}")
            return sdk_root

    # Check if user specified a custom SDK location
    if poplar_location:
        result = urlparse(poplar_location)
        if result.scheme and result.netloc:
            url = poplar_location
            logger.info(f"Using Poplar SDK from URL {poplar_location}")
        # invalid url:
        elif os.path.isdir(poplar_location):
            logger.info(f"Using Poplar SDK from path {poplar_location}")
            return poplar_location
        # invalid path or url:
        else:
            raise SSFExceptionInstallationError(
                f"dependecies.poplar_location (path nor URL) {poplar_location} cannot be found."
            )

        cache_path = os.path.join(CACHE_CUSTOM, url_to_path(url))
        if os.path.isdir(cache_path):
            download = False
            cache = cache_path
            logger.debug(f"Using cached Poplar SDK from {cache}")
        if not download:
            return cache
        logger.info(f"Downloading Poplar SDK from {url}")
        return download_tar(url, cache_path)

    # Download SDK or use the cache
    else:
        ubuntu = default_ubuntu_version()
        poplar = ssf_config.application.dependencies.get("poplar")[0]
        url = sdk_url(ubuntu=ubuntu, poplar=poplar)
        if not url:
            raise SSFExceptionInstallationError(
                f"Ubuntu {ubuntu} Poplar {poplar} not found. Supported SDKs: {downloadable_sdks}"
            )
        cache_path = os.path.join(CACHE_SDK, f"{ubuntu}_{poplar}")
        if os.path.isdir(cache_path):
            download = False
            cache = cache_path
        if not download:
            return cache
        logger.info(f"Downloading SDK release for Ubuntu {ubuntu} Poplar {poplar}")
        return download_sdk(ubuntu, poplar, cache_path)


def download_tar(url, cache_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.debug(
            f"Downloading SDK from {url} to {cache_path} using intermediate temp dir {temp_dir}"
        )
        temp_filename = os.path.join(temp_dir, "archive.tar.gz")
        ONE_MB = 1024 * 1024
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            c = 0
            logger.debug(f"Writing to {temp_filename}")
            with open(temp_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=ONE_MB):
                    f.write(chunk)
                    if (c % 256) == 0:
                        logger.debug(f" Written {c} chunks ({(f.tell()/ONE_MB):.2f}MB)")
                    c += 1
        try:
            # open file
            fstat = os.stat(temp_filename)
            logger.debug(
                f"Opening archive {temp_filename} ({(fstat.st_size/ONE_MB):.2f}MB)"
            )
            file = tarfile.open(temp_filename)
            # extracting file
            getnames = file.getnames()
            logger.debug(f"Archive contains {len(getnames)} files")
            if WANT_LOG_ARCHIVE_FILENAMES:
                for n in getnames:
                    logger.debug(" [Archive] " + n)
            commonprefix = os.path.commonprefix(getnames)
            logger.debug(f"Commonprefix {commonprefix}")
            logger.debug("Extractall")
            file.extractall(temp_dir)
            logger.debug("Close")
            file.close()
            extracted_path = os.path.join(temp_dir, commonprefix)
            logger.debug(f"Extracted_path {extracted_path}")
            top_level_dirs = []
            top_level_files = []
            for f in os.listdir(extracted_path):
                if os.path.isdir(os.path.join(extracted_path, f)):
                    top_level_dirs.append(f)
                else:
                    top_level_files.append(f)
            for f in sorted(top_level_dirs):
                logger.debug(f" [Extracted] {f}/")
            for f in sorted(top_level_files):
                logger.debug(f" [Extracted] {f}")
            logger.debug(f"Calling rmtree {cache_path}")
            rmtree(path=cache_path, ignore_errors=True)
            logger.debug(f"Calling copytree {extracted_path} -> {cache_path}")
            copytree(
                src=extracted_path,
                dst=cache_path,
                ignore_dangling_symlinks=True,
            )
            with open(os.path.join(cache_path, "ssf.meta"), "w") as meta:
                meta.write(f"original-url={url}\n")
                meta.write(f"original-filename={temp_filename}\n")
                meta.write(f"original-cache_path={cache_path}\n")
            logger.debug(f"Cache entry updated {cache_path}")
            return cache_path

        except:
            raise SSFExceptionInstallationError(
                f"Error extracting the downloaded SDK archive: {temp_filename}.\
                Target should be tar file."
            )


def download_sdk(ubuntu: str, poplar: str, cache_path: str):
    url = sdk_url(ubuntu=ubuntu, poplar=poplar)
    if url:
        download_tar(url, cache_path)
    else:
        raise SSFExceptionInstallationError(
            f"Ubuntu {ubuntu} Poplar {poplar} not found. Supported SDKs: {downloadable_sdks}"
        )
    return cache_path


def check_cpu_vendor():
    try:
        # Read the CPU information from /proc/cpuinfo
        with open("/proc/cpuinfo", "r") as cpuinfo_file:
            cpuinfo = cpuinfo_file.read()
        if "Intel" in cpuinfo:
            return "intel"
        elif "AMD" in cpuinfo:
            return "amd"
        else:
            return "Unknown"

    except Exception as e:
        raise SSFExceptionInstallationError("Failed to check '/proc/cpuinfo'")


def find_whl_in_dir(prefix: str, dir: str, requires_cpu_vendor: bool = False):
    def filter_name(filename: str):
        if requires_cpu_vendor:
            cpu_vendor = check_cpu_vendor()
            if cpu_vendor == "unknown":
                logger.error(
                    f"dependencies.poplar_wheels: {prefix} requires a cpu-vendor specific wheel, but the cpu vendor is unknown."
                )
                return False
            elif cpu_vendor not in filename:
                logger.debug(
                    f"Skipping {filename} (doesn't match required cpu vendor {cpu_vendor})"
                )
                return False

        return filename.startswith(prefix) and filename.endswith(".whl")

    files_in_cache = os.listdir(dir)
    for filename in files_in_cache:
        if filter_name(filename):
            return os.path.join(dir, filename)
    return None


def get_poplar_wheels(poplar_wheels, sdk_path):
    wheels = []
    missing = []
    for p in poplar_wheels.split(","):
        prefix = p.strip()
        requires_cpu_vendor = False
        if prefix in known_poplar_wheels.keys():
            prefix, requires_cpu_vendor = known_poplar_wheels.get(p)
        else:
            logger.warning(
                f"{prefix} is not a known Poplar wheel. Known wheel:\
                {known_poplar_wheels.keys()}"
            )
        wheel_path = find_whl_in_dir(prefix, sdk_path, requires_cpu_vendor)
        if wheel_path:
            wheels.append(wheel_path)
        else:
            missing.append(p)
    return wheels, missing


def find_subdir_from_prefix(prefix: str, dir: str):
    files = os.listdir(dir)
    for filename in files:
        if filename.startswith(prefix) and os.path.isdir(os.path.join(dir, filename)):
            return os.path.join(dir, filename)
    return None


def enable_sdk(env: dict, sdk_root_path: str):
    # Run the poplar SDK enable scripts and extract the environment changes.
    enable_script = os.path.join(sdk_root_path, "enable")
    logger.debug(f"Enabling SDK with {enable_script}")
    with tempfile.NamedTemporaryFile(mode="w+t") as wrapped_enable_script:
        ENV_HEADER = "--ENV--"
        wrapped_enable_script.write('echo "Enabling SDK"\n')
        wrapped_enable_script.write("unset POPLAR_SDK_ENABLED\n")
        wrapped_enable_script.write(f"source {enable_script}\n")
        wrapped_enable_script.write(f"echo '{ENV_HEADER}'\n")
        wrapped_enable_script.write("env -0\n")
        logger.debug("Running wrapped enable script")
        with tempfile.NamedTemporaryFile(mode="w+t") as log_output:
            wrapped_enable_script.seek(0)
            exit_code = logged_subprocess(
                "enable sdk",
                ["/bin/bash", wrapped_enable_script.name],
                stdout_log_level=None,
                stderr_log_level=None,
                file_output=log_output,
                environ=env,
            )
            if exit_code:
                raise SSFExceptionInstallationError(f"Failed to enable SDK {exit_code}")

            # Read back the environment changes (changes and additions).
            logger.debug("Processing enabled environment")
            log_output.seek(0)
            lines = log_output.readlines()
            ignore_list = ["SHLVL", "_"]
            parsing_env = False
            modifications = 0
            envcap = ""

            # Find the start of the env output and capture it to a single string.
            for line in lines:
                if ENV_HEADER in line:
                    parsing_env = True
                    logger.debug(f"Found {ENV_HEADER}")
                    continue
                if not parsing_env:
                    continue
                envcap += line

            # Process the env output; this is a set of null ("\0") terminated environment variables.
            for e in envcap.split("\0"):
                if "=" in e:
                    e = e.strip()
                    (k, v) = e.split("=", 1)
                    if k in ignore_list:
                        continue

                    def secret_or_string(k, v):
                        # Rudimentary filtering of secrets.
                        SECRETS = ["key", "password", "secret", "cert", "credential"]
                        return (
                            "****"
                            if any(s in k.lower() or s in v.lower() for s in SECRETS)
                            else v
                        )

                    if k in env:
                        if env[k] != v:
                            logger.debug(f"--- {k} changed ---")
                            logger.debug(
                                secret_or_string(k, env[k])
                                + " -> "
                                + secret_or_string(k, v)
                            )
                            env[k] = v
                            modifications += 1
                    else:
                        logger.debug(f"--- {k} added ---")
                        logger.debug(secret_or_string(k, v))
                        env[k] = v
                        modifications += 1
            logger.debug(f"Made {modifications} modifications to existing env")


def maybe_activate_poplar_sdk(ssf_config: SSFConfig):
    """Return a copy of current sys.environ dict
    with activated SDK paths if required

    Args:
        ssf_config (SSFConfig): ssf config

    Returns:
        dict[str, str]: environment with SDK paths if required
    """
    require_poplar = get_poplar_requirement(ssf_config)
    sdk_enabled = os.environ.get("POPLAR_SDK_ENABLED", False)
    env = os.environ.copy()

    if sdk_enabled:
        if poplar_version_ok(ssf_config, env):
            logger.info(
                f"The current environment provides a Poplar SDK that meets requirements and can be used: {sdk_enabled}"
            )
            return env
        logger.warning(
            "The current environment provides a Poplar SDK but it doesn't match requirements and will not be used."
        )

    if require_poplar:
        sdk_root_path = get_poplar_sdk(ssf_config)
        logger.info(f"> Enabling SDK for application environment at {sdk_root_path}")
        enable_sdk(env, sdk_root_path)

    return env
