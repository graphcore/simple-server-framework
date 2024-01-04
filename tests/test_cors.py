# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import requests
import utils


class CorsTest(utils.TestClient):
    def TestOrigin(self, test_origin):
        print(f"Post TestOrigin {test_origin}...")
        headers = {"accept": "application/json"}
        if test_origin:
            headers["origin"] = test_origin
        response = requests.post(
            self.base_url + "/v1/Test1",
            json={"x": 101},
            headers=headers,
            timeout=5,
        )
        print(f"Post TestOrigin {test_origin}...done")

        print("Assert response.status_code == 200")
        assert response.status_code == 200

        print(f"Response headers {response.headers}")
        if "access-control-allow-origin" in response.headers:
            print(f"Origin {test_origin} allowed")
            return True
        else:
            print(f"Origin {test_origin} not matched or CORS is not enabled")
            return False

    def configure(self):
        self.config_file = "tests/app_usecases/health_0.yaml"
        if not getattr(self, "extra_arguments", None):
            self.extra_arguments = []

    def test_ready_start(self):
        assert self.is_ready
        assert self.is_string_in_logs("Dispatcher ready")


@pytest.mark.fast
@pytest.mark.dependency()
class TestsNoCors(CorsTest):

    # Default configure (init, build, run) with CORS disabled.
    def test_no_cors_origin(self):
        assert not self.TestOrigin(None)
        assert not self.TestOrigin("http://localhost")


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsNoCors::test_no_cors_origin"])
class TestsCorsDefault(CorsTest):
    def configure(self):
        CorsTest.configure(self)

        # Just 'run' again with extra args for CORS.
        self.ssf_commands = ["run"]
        self.extra_arguments.extend(["--enable-cors-middleware"])

    def test_default_cors_origin(self):
        # Default accepts http/https from localhost or 127.0.0.1
        assert self.TestOrigin("http://localhost")
        assert self.TestOrigin("http://127.0.0.1")
        assert self.TestOrigin("https://localhost")
        assert self.TestOrigin("https://127.0.0.1")
        # Default accepts with any port
        assert self.TestOrigin(f"http://localhost:8100")
        assert self.TestOrigin(f"http://localhost:8101")
        # Arbitrary bogus origin should be refused
        assert not self.TestOrigin(f"https://bogus")


@pytest.mark.fast
@pytest.mark.dependency(depends=["TestsNoCors::test_no_cors_origin"])
class TestsCorsCustom(CorsTest):
    def configure(self):
        CorsTest.configure(self)

        # Just 'run' again with extra args for CORS.
        self.ssf_commands = ["run"]
        self.extra_arguments.extend(["--enable-cors-middleware"])
        self.extra_arguments.extend(
            ["--cors-allow-origin-regex", "http://custom.origin.com"]
        )

    def test_default_cors_origin(self):
        # Must match the specified origin
        assert not self.TestOrigin("http://localhost")
        assert self.TestOrigin("http://custom.origin.com")
