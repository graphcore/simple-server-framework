# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os
import pytest
import tempfile
import utils
import time
import shutil
import sys
from ssf.load_config import ConfigGenerator
from ssf.sdk_utils import (
    CACHE_SDK,
    CACHE_CUSTOM,
    enumerate_downloadable_sdks,
    default_ubuntu_version,
    default_poplar_version,
    download_sdk,
    maybe_activate_poplar_sdk,
    get_poplar_sdk,
    url_to_path,
    enable_sdk,
)
from ssf.utils import poplar_version_ok, get_poplar_version

downloadable_sdks = None

TEST_SDK_FOLDER = os.path.abspath("./test_sdks")
TEST_UBUNTU_VERSION = "20.04"
TEST_POPLAR_VERSION = "3.3.0"
TEST_WRONG_POPLAR_VERSION = "2.6.0"
TEST_POPLAR_SDK_PATH = os.path.join(
    TEST_SDK_FOLDER, f"{TEST_UBUNTU_VERSION}_{TEST_POPLAR_VERSION}"
)
TEST_POPLAR_SDK_URL = None  # Established by `initialise_from_enumeration`

# Define some paths for the test(s)
# These are anticipated given TEST_UBUNTU_VERSION and TEST_POPLAR_VERSION and must be updated if those are modified.
PREENABLED_SDK_POPLAR_PATH = os.path.join(
    TEST_SDK_FOLDER,
    f"{TEST_UBUNTU_VERSION}_{TEST_POPLAR_VERSION}",
    "poplar-ubuntu_20_04-3.3.0+7857-b67b751185",
)
CACHED_SDK_POPLAR_PATH = os.path.join(
    CACHE_SDK,
    f"{TEST_UBUNTU_VERSION}_{TEST_POPLAR_VERSION}",
    "poplar-ubuntu_20_04-3.3.0+7857-b67b751185",
)
CUSTOM_SDK_POPLAR_PATH = None  # Established by `initialise_from_enumeration`


@pytest.fixture
def delete_test_sdks():
    if os.path.isdir(TEST_SDK_FOLDER):
        print(f"Deleting test SDKs folder {TEST_SDK_FOLDER}")
        shutil.rmtree(TEST_SDK_FOLDER)


@pytest.fixture
def delete_cached_sdks():
    if os.path.isdir(CACHE_SDK):
        print(f"Deleting cached release SDKs {CACHE_SDK}")
        shutil.rmtree(CACHE_SDK)
    if os.path.isdir(CACHE_CUSTOM):
        print(f"Deleting cached custom SDKs {CACHE_CUSTOM}")
        shutil.rmtree(CACHE_CUSTOM)


@pytest.fixture
def initialise_from_enumeration():
    global TEST_POPLAR_SDK_URL
    global CUSTOM_SDK_POPLAR_PATH
    global downloadable_sdks
    downloadable_sdks = enumerate_downloadable_sdks()
    TEST_POPLAR_SDK_URL = downloadable_sdks[TEST_UBUNTU_VERSION][TEST_POPLAR_VERSION][
        "wget"
    ]
    CUSTOM_SDK_POPLAR_PATH = os.path.join(
        CACHE_CUSTOM,
        url_to_path(TEST_POPLAR_SDK_URL),
        "poplar-ubuntu_20_04-3.3.0+7857-b67b751185",
    )
    print("Initialised from enumeration")
    print(f"TEST_POPLAR_SDK_URL : {TEST_POPLAR_SDK_URL}")
    print(f"CUSTOM_SDK_POPLAR_PATH : {CUSTOM_SDK_POPLAR_PATH}")


def activate_sdk(ubuntu: str, poplar: str):
    # Download an SDK release and activate it in the current environment
    sdk_root_path = os.path.join(TEST_SDK_FOLDER, f"{ubuntu}_{poplar}")
    if not os.path.isdir(sdk_root_path):
        download_sdk(ubuntu, poplar, sdk_root_path)
    enable_sdk(os.environ, sdk_root_path)


@pytest.mark.fast
def test_default_versions():
    ubuntu = default_ubuntu_version()
    poplar = default_poplar_version(ubuntu)
    print(f"Default Ubuntu {ubuntu}")
    print(f"Default Poplar {poplar}")


@pytest.mark.slow
def test_download_release():
    print(
        f"Checking download link for sdk Ubuntu {TEST_UBUNTU_VERSION} Poplar {TEST_POPLAR_VERSION}"
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        download_sdk(TEST_UBUNTU_VERSION, TEST_POPLAR_VERSION, temp_dir)


@pytest.mark.fast
def test_activate_sdk(delete_cached_sdks):
    ssf_config = ConfigGenerator("examples/simple/ssf_config.yaml", True).load()
    ssf_config.application.dependencies.update({"poplar": [TEST_POPLAR_VERSION]})
    activate_sdk(TEST_UBUNTU_VERSION, TEST_POPLAR_VERSION)
    assert poplar_version_ok(ssf_config, os.environ)


@pytest.mark.fast
def test_custom_sdk_path(initialise_from_enumeration, delete_cached_sdks):
    # Clear existing SDK (if any) and get the test poplar SDK.
    if os.environ.get("POPLAR_SDK_ENABLED"):
        os.environ.pop("POPLAR_SDK_ENABLED")
    ssf_config = ConfigGenerator("examples/simple/ssf_config.yaml", True).load()
    ssf_config.application.dependencies.update({"poplar": [TEST_POPLAR_VERSION]})
    ssf_config.application.dependencies.update({"poplar_location": TEST_POPLAR_SDK_URL})
    path = get_poplar_sdk(ssf_config)

    # Check location and try to enable it.
    poplar_location = url_to_path(TEST_POPLAR_SDK_URL)
    assert poplar_location in path
    enable_sdk(os.environ, os.path.join(CACHE_CUSTOM, poplar_location))

    # Assert expected version.
    current = get_poplar_version(os.environ)
    assert current == TEST_POPLAR_VERSION


@pytest.mark.fast
def test_maybe_activate_poplar_sdk(
    initialise_from_enumeration, delete_cached_sdks, delete_test_sdks
):
    parameters = [
        # Pre-enabled, matching required -> should keep the current paths
        (TEST_POPLAR_VERSION, TEST_POPLAR_VERSION, None, PREENABLED_SDK_POPLAR_PATH),
        # Not pre-enabled, required -> should download/enable the sdk release (hence use cache)
        (None, TEST_POPLAR_VERSION, None, CACHED_SDK_POPLAR_PATH),
        # Not pre-enabled, required + specific path in config -> should get sdk from there and enable
        (None, TEST_POPLAR_VERSION, TEST_POPLAR_SDK_PATH, PREENABLED_SDK_POPLAR_PATH),
        # Not pre-enabled, required + specific URL in config -> should get sdk from there and enable
        (None, TEST_POPLAR_VERSION, TEST_POPLAR_SDK_URL, CUSTOM_SDK_POPLAR_PATH),
        # Pre-enabled, matching required + specific poplar_location in config -> should keep the current paths
        (
            TEST_POPLAR_VERSION,
            TEST_POPLAR_VERSION,
            TEST_POPLAR_SDK_PATH,
            PREENABLED_SDK_POPLAR_PATH,
        ),
        # Pre-enabled, not required -> keep the current paths
        (TEST_POPLAR_VERSION, None, None, PREENABLED_SDK_POPLAR_PATH),
        # Pre-enabled, not matching required -> should fallback & download/enable the sdk release
        (TEST_WRONG_POPLAR_VERSION, TEST_POPLAR_VERSION, None, CACHED_SDK_POPLAR_PATH),
        # Pre-enabled, not maching required + specific poplar_location in config -> should get sdk from poplar_location and enable
        (
            TEST_WRONG_POPLAR_VERSION,
            TEST_POPLAR_VERSION,
            TEST_POPLAR_SDK_URL,
            CUSTOM_SDK_POPLAR_PATH,
        ),
        # Not pre-enabled, not required
        (None, None, None, None),
    ]

    download_sdk(
        TEST_UBUNTU_VERSION,
        TEST_POPLAR_VERSION,
        os.path.join(TEST_SDK_FOLDER, f"{TEST_UBUNTU_VERSION}_{TEST_POPLAR_VERSION}"),
    )

    for i, p in enumerate(parameters):
        initial_poplar = p[0]
        required_poplar = p[1]
        location = p[2]
        expected_path = p[3]

        print(f"Subtest {i} inputs")
        print(f" initial_poplar  : {initial_poplar}")
        print(f" required_poplar : {required_poplar}")
        print(f" location        : {location}")
        print(f" expected_path   : {expected_path}")

        # Prepare based on parameters
        ssf_config = ConfigGenerator("examples/simple/ssf_config.yaml", True).load()
        if required_poplar is not None:
            ssf_config.application.dependencies.update({"poplar": [required_poplar]})
        if location is not None:
            ssf_config.application.dependencies.update({"poplar_location": location})
        if initial_poplar:
            activate_sdk(TEST_UBUNTU_VERSION, initial_poplar)
        elif os.environ.get("POPLAR_SDK_ENABLED"):
            os.environ.pop("POPLAR_SDK_ENABLED")

        # Run test.
        env = maybe_activate_poplar_sdk(ssf_config)

        # Assert result.
        poplar_sdk_enabled = env.get("POPLAR_SDK_ENABLED")
        print(f"Subtest {i} result")
        print(f" poplar_sdk_enabled == {poplar_sdk_enabled}")
        assert poplar_sdk_enabled == expected_path
        assert poplar_version_ok(ssf_config, env)
        print(" poplar_version_ok")


# Set IPU dependency so this is only run where the system has IPU.
# This is because this test needs to download and import the tensorflow
# wheel that was built for either AMD or Intel. The Intel build assumes
# AVX512F is available which is not always true for standard GitHub
# action runners.
@pytest.mark.slow
@pytest.mark.ipu
class TestsSDKWheels(utils.TestClient):
    def configure(self):
        self.config_file = "tests/app_usecases/check_sdk_wheels.yaml"
        self.wait_ready = False
        self.ssf_commands = ["init", "build"]
        config = ConfigGenerator(self.config_file, True).load()
        self.venv_dir = config.application.venv_dir

    def wait_build_finishes(self):
        while True:
            time.sleep(5)
            if self.is_string_in_logs("MyApp build"):
                break
            if not self.process_is_running():
                utils.raise_exception("wait_build_finishes: Process has stopped")

    print(sys.version_info)

    @pytest.mark.skipif(
        (sys.version_info.major, sys.version_info.minor) != (3, 8),
        reason=f"Python {sys.version_info} is not supported for this test",
    )
    def test_sdk_packages_import(self):
        self.wait_build_finishes()
        # Run from app venv: check packages are all importable
        activate_sdk(TEST_UBUNTU_VERSION, TEST_POPLAR_VERSION)
        venv_python = f"{self.venv_dir}/bin/python"
        result, _, _ = utils.run_subprocess(
            [venv_python, "tests/import_sdk_packages.py"]
        )
        assert result == 0
