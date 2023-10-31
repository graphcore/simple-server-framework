# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import utils
import pytest
import time
import requests

from ssf.results import RESULT_OK, RESULT_APPLICATION_CONFIG_ERROR


class ModifyConfigBase(utils.TestClient):
    # All interfaces (includes 'run')
    all_commands = ["init", "build", "run"]
    all_interfaces = ["build", "startup", "request", "shutdown", "watchdog"]

    # Quick excludes 'run'
    quick_commands = ["init", "build"]
    quick_interfaces = ["build"]

    all = False

    def configure(self, all: bool = False):
        self.config_file = "tests/app_usecases/modify_config.yaml"
        self.all = all
        self.watchdog_ready_period = 1
        self.stop_on_error = True
        if all:
            self.ssf_commands = self.all_commands.copy()
            self.interfaces = self.all_interfaces.copy()
            self.wait_ready = True
        else:
            self.ssf_commands = self.quick_commands.copy()
            self.interfaces = self.quick_interfaces.copy()
            self.wait_ready = False

    def request(self):
        response = requests.post(
            self.base_url + "/v1/Test1",
            json={"x": 0},
            headers={"accept": "application/json"},
            timeout=5,
        )
        assert response.status_code == 200
        assert response.text == '{"response":"ok"}'

    def verify_app_interfaces(self, expected: str):
        interfaces = self.interfaces
        for interface in interfaces:
            lookfor = f"Verify {interface} {expected}"
            if not self.is_string_in_logs(lookfor):
                print(f"Error - missing log line '{lookfor}'")
                return False
        return True

    def expect_success(self):
        if self.all:
            # Issue requests and provoke watchdog (iff we configured with 'all')
            assert self.process_is_running()
            self.request()
            # Stall for watchdog
            time.sleep(2)
            self.stop_process()
        self.wait_process_exit(timeout=60)
        # Expect RESULT_OK but some logging to indicate set-config.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK

    def expect_failure(self):
        self.wait_process_exit(timeout=60)
        # Expect RESULT_APPLICATION_CONFIG_ERROR to indicate there were failures.
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_APPLICATION_CONFIG_ERROR


@pytest.mark.fast
class TestsModifyConfigBaseFastapiOK(ModifyConfigBase):
    def configure(self):
        # Testing 'all' interfaces for base test.
        super().configure(self, all=True)

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces("application.custom==(None, None)")
        assert self.verify_app_interfaces("testlist==(['X', 'Y', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 1, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )

        # Assert context.status.
        # This is a (sorted) set written into the Application's ssf_config.config_dict arg.
        # Each function called is appended, so this forms a 'trace'.
        # Since we use a **copy** of the SSFConfig, the set should NOT be propagated
        # between 'build' and the 'run' runtime application instances.
        # Build application
        assert self.is_string_in_logs(
            "Verify __init__ context.status==(['__init__'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify build context.status==(['__init__', 'build'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify shutdown context.status==(['__init__', 'build', 'shutdown'], 'set')"
        )
        # Runtime application
        assert self.is_string_in_logs(
            "Verify startup context.status==(['__init__', 'startup'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify watchdog context.status==(['__init__', 'request', 'startup', 'watchdog'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify shutdown context.status==(['__init__', 'request', 'shutdown', 'startup', 'watchdog'], 'set')"
        )


@pytest.mark.fast
class TestsModifyConfigBaseGrpcOK(ModifyConfigBase):
    def configure(self):
        super().configure(self, all=True)
        self.ssf_commands += ["--api", "grpc"]
        # NOTE:
        # We skip actual requests for this api (grpc)
        # but we can at least check the remaining interfaces.
        self.interfaces = ["build", "startup", "shutdown", "watchdog"]
        self.wait_ready = False

    def test_application(self):
        # We don't wait for the process to be ready.
        # Just wait some small period and then stop it.
        time.sleep(3)
        self.stop_process()
        self.wait_process_exit(timeout=60)
        assert not self.process_is_running()
        assert self.server_stopped()
        assert self.get_return_code() == RESULT_OK

        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces("application.custom==(None, None)")
        assert self.verify_app_interfaces("testlist==(['X', 'Y', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 1, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )

        # Assert context.status.
        # As for FastAPI - except we don't run the 'request' API so we can't verify that part.
        # Build application
        assert self.is_string_in_logs(
            "Verify __init__ context.status==(['__init__'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify build context.status==(['__init__', 'build'], 'set')"
        )
        # Runtime application
        assert self.is_string_in_logs(
            "Verify shutdown context.status==(['__init__', 'build', 'shutdown'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify watchdog context.status==(['__init__', 'startup', 'watchdog'], 'set')"
        )
        assert self.is_string_in_logs(
            "Verify shutdown context.status==(['__init__', 'shutdown', 'startup', 'watchdog'], 'set')"
        )


@pytest.mark.fast
class TestsModifyConfigChangeOK(ModifyConfigBase):
    def configure(self):
        # Testing 'all' interfaces for this first test (remainder can default to 'quick')
        super().configure(self, all=True)
        self.ssf_commands += [
            "--modify-config",
            "application.trace=False;testtypes.t_int=2;application.custom=my custom field",
        ]

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(False, 'bool')")
        assert self.verify_app_interfaces(
            "application.custom==('my custom field', 'str')"
        )
        assert self.verify_app_interfaces("testlist==(['X', 'Y', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 2, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )


@pytest.mark.fast
class TestsModifyConfigExistingFieldTypesOK(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        # Attempt to modify to 'wrong' type (expects bool)
        self.ssf_commands += [
            "--modify-config",
            "testtypes.t_int=2;testtypes.t_float=2.0;testtypes.t_bool=True;testtypes.t_str=ok",
        ]

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces("application.custom==(None, None)")
        assert self.verify_app_interfaces("testlist==(['X', 'Y', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 2, 't_float': 2.0, 't_str': 'ok', 't_bool': True}, 'dict')"
        )


@pytest.mark.fast
class TestsModifyConfigExistingFieldTypesKO(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        # Attempt to modify to 'wrong' type (expects bool)
        self.ssf_commands += [
            "--modify-config",
            "testtypes.t_int=2.0;testtypes.t_float=ko;testtypes.t_bool=2;testtypes.t_str=2",
        ]

    def test_application(self):
        self.expect_failure()
        assert self.is_string_in_logs(
            "Config field can not be set with `testtypes.t_int=2.0"
        )
        assert self.is_string_in_logs(
            "Config field can not be set with `testtypes.t_bool=2"
        )
        assert self.is_string_in_logs(
            "Config field can not be set with `testtypes.t_float=ko"
        )
        assert self.is_string_in_logs(
            "Failed to modify config with `['testtypes.t_int=2.0', 'testtypes.t_float=ko', 'testtypes.t_bool=2', 'testtypes.t_str=2']`"
        )


@pytest.mark.fast
class TestsModifyConfigExistingFieldNonLeafKO(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        self.ssf_commands += ["--modify-config", "application=test"]

    def test_application(self):
        self.expect_failure()
        assert self.is_string_in_logs(
            "set dict: 'application' references an existing non-leaf field"
        )


@pytest.mark.fast
class TestsModifyConfigListModifyWithIndexOK(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        self.ssf_commands += ["--modify-config", "testlist[1]=modified"]

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces("application.custom==(None, None)")
        assert self.verify_app_interfaces("testlist==(['X', 'modified', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 1, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )


@pytest.mark.fast
class TestsModifyConfigListModifyWithoutIndexKO(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        self.ssf_commands += ["--modify-config", "testlist=modified"]

    def test_application(self):
        self.expect_failure()
        assert self.is_string_in_logs("set dict: 'testlist' is a list; index required")


@pytest.mark.fast
class TestsModifyConfigListSetNewOK(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        self.ssf_commands += [
            "--modify-config",
            "testlist[4]=B;newlist[3]=3;newlist[0]=0",
        ]

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces("application.custom==(None, None)")
        assert self.verify_app_interfaces(
            "testlist==(['X', 'Y', 'Z', None, 'B'], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(['0', None, None, '3'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 1, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )


@pytest.mark.fast
class TestsModifyConfigListModifyDictWithIndexOK(ModifyConfigBase):
    def configure(self):
        super().configure(self)
        self.ssf_commands += ["--modify-config", "testlist_dict[1].desc=modified"]

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces("application.custom==(None, None)")
        assert self.verify_app_interfaces("testlist==(['X', 'Y', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'modified'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 1, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )


@pytest.mark.fast
class TestsModifyConfigWithExpansion(ModifyConfigBase):
    def configure(self):
        super().configure(self, all=True)
        self.ssf_commands += [
            "--modify-config",
            "application.custom={{application.module}}",
        ]

    def test_application(self):
        self.expect_success()
        assert self.verify_app_interfaces("application.trace==(True, 'bool')")
        assert self.verify_app_interfaces(
            "application.custom==('modify_config.py', 'str')"
        )
        assert self.verify_app_interfaces("testlist==(['X', 'Y', 'Z'], 'list')")
        assert self.verify_app_interfaces(
            "testlist_dict==([{'id': 'X', 'desc': 'X'}, {'id': 'Y', 'desc': 'Y'}, {'id': 'Z', 'desc': 'Z'}], 'list')"
        )
        assert self.verify_app_interfaces("newlist==(None, None)")
        assert self.verify_app_interfaces(
            "testtypes==({'t_int': 1, 't_float': 1.0, 't_str': '1.0', 't_bool': False}, 'dict')"
        )
        assert self.verify_app_interfaces(
            "args.modify_config==('application.custom={{application.module}}', 'str')"
        )
