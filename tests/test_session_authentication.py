# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import requests
import os
import utils


class SessionAuthenticationTest(utils.TestClient):
    def get_session(self):
        if self.session is None:
            print("Creating requests session")
            self.session = requests.Session()
        else:
            print("Using existing session")
        return self.session

    def TestEndpoint(self, expected_status_code=200, expected_user_id=None):
        print(f"Post TestEndpoint...")
        s = self.get_session()
        response = s.post(
            self.base_url + "/v1/Test1",
            json={"x": 101},
            timeout=5,
        )
        print(f"Post TestEndpoint...done")
        print(f"Response {response}")
        if (
            response.status_code == 200
            and expected_status_code == response.status_code
            and expected_user_id is not None
        ):
            assert self.wait_string_in_logs(
                f"'user_id': '{expected_user_id}'", timeout=10
            )
        return response.status_code == expected_status_code

    def TestLogin(self, auth, expected_status_code=200):
        print(f"Get session_login...")
        s = self.get_session()
        response = s.get(self.base_url + "/session_login", auth=auth)
        print(f"Get session_login...done")
        print(f"Response {response}")

        if response.status_code == 200 and expected_status_code == response.status_code:
            assert self.wait_string_in_logs(f"Created session", timeout=10)
        return response.status_code == expected_status_code

    def TestLogout(self, expected_status_code=200):
        print(f"Get session_logout...")
        s = self.get_session()
        response = s.get(
            self.base_url + "/session_logout",
        )
        print(f"Get session_logout...done")
        print(f"Response {response}")

        if response.status_code == 200 and expected_status_code == response.status_code:
            assert self.wait_string_in_logs(f"Deleted session", timeout=10)
        return response.status_code == expected_status_code

    def TestStatus(self, expected_status_code=200, expected_user_id="1"):
        print(f"Get session_status...")
        s = self.get_session()
        response = s.get(
            self.base_url + "/session_status",
        )
        print(f"Get session_status...done")
        print(f"Response {response}")

        if response.status_code == 200 and expected_status_code == response.status_code:
            data = response.json()
            print(f"Data {data}")
            assert data["user_id"] == expected_user_id
        return response.status_code == expected_status_code

    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        if not getattr(self, "extra_arguments", None):
            self.extra_arguments = []
        self.session = None

    def test_ready_start(self):
        assert self.is_ready
        assert self.is_string_in_logs("Dispatcher ready")


@pytest.mark.fast
@pytest.mark.dependency()
class TestsNoAuthentication(SessionAuthenticationTest):
    # Default configure (init, build, run) with authentication disabled.
    def test_no_authentication(self):
        assert self.TestEndpoint()


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsNoAuthentication::test_no_authentication"])
class TestsAuthenticationNoLogin(SessionAuthenticationTest):
    def configure(self):
        SessionAuthenticationTest.configure(self)

        # Just 'run' again with extra args to enable authentication.
        self.ssf_commands = ["run"]
        self.extra_arguments.extend(["--enable-session-authentication"])

    def test_authentication_no_login(self):
        assert self.TestEndpoint(expected_status_code=403)


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsNoAuthentication::test_no_authentication"])
class TestsAuthenticationLogin(SessionAuthenticationTest):
    def configure(self):
        SessionAuthenticationTest.configure(self)

        # Just 'run' again with extra args to enable authentication.
        self.ssf_commands = ["run"]
        self.extra_arguments.extend(["--enable-session-authentication"])

    def test_authentication_login(self):
        assert self.TestLogin(auth=("test", "wrongpassword"), expected_status_code=401)
        assert self.TestLogin(auth=("test", "123456"), expected_status_code=200)
        assert self.TestEndpoint(expected_user_id="1")
        assert self.TestStatus(expected_user_id="1")
        assert self.TestLogout()
        assert self.TestEndpoint(expected_status_code=403)


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsNoAuthentication::test_no_authentication"])
class TestsAuthenticationCustom(SessionAuthenticationTest):
    def configure(self):
        SessionAuthenticationTest.configure(self)

        # Just 'run' again with extra args to enable authentication with a custom authenticate_user implementation.
        self.ssf_commands = ["run"]
        self.extra_arguments.extend(["--enable-session-authentication"])
        self.extra_arguments.extend(
            [
                "--session-authentication-module-file",
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "app_usecases",
                    "custom_authenticate_user.py",
                ),
            ]
        )

    def test_authentication_custom(self):
        assert self.TestLogin(auth=("test", "123456"), expected_status_code=401)
        assert self.TestLogin(auth=("freddy", "password"), expected_status_code=200)
        assert self.TestEndpoint(expected_user_id="freddy")
        assert self.TestStatus(expected_user_id="freddy")
        assert self.TestLogout()
        assert self.TestEndpoint(expected_status_code=403)
