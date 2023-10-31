# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import requests
from ssf.utils import API_FASTAPI, API_GRPC
import utils
import json

from ssf.results import *


@pytest.mark.fast
class TestsInputExamplesSimple(utils.TestClient):
    def configure(self):
        self.config_file = "examples/simple/ssf_config.yaml"
        self.api = API_FASTAPI

    def test_examples(self):
        response = requests.get(
            self.base_url + "/openapi.json",
        )
        assert response.status_code == 200
        api = json.loads(response.text)
        print(json.dumps(api, indent=2))

        # JSON input
        # Anticipate the example referenced as schema.
        schema_ref = api["paths"]["/v1/Test1"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        # Walk API to the schema.
        examples = api
        schema_ref = schema_ref.replace("#/", "").split("/")
        for s in schema_ref:
            examples = examples[s]

        examples = examples["examples"][0]
        assert examples["x"] == 101

        # Query input
        # Anticipate the example embedded in path definition.
        example = api["paths"]["/v1/TestQuery"]["post"]["parameters"][0]["example"]
        assert example == 102

    def test_exit_after_success(self):
        # Force stop.
        self.stop_process()

        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_OK
        assert self.server_stopped()


class TestsInputExamplesTypes(utils.TestClient):
    def configure(self):
        self.config_file = "examples/types/ssf_config.yaml"
        self.api = API_FASTAPI

    def test_openapi(self):
        response = requests.get(
            self.base_url + "/openapi.json",
        )
        assert response.status_code == 200
        api = json.loads(response.text)
        print(json.dumps(api, indent=2))

        # JSON input
        # Anticipate the example referenced as schema.
        schema_ref = api["paths"]["/v1/TestTypes"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        # Walk API to the schema.
        examples = api
        schema_ref = schema_ref.replace("#/", "").split("/")
        for s in schema_ref:
            examples = examples[s]

        examples = examples["examples"][0]
        assert examples["x_strings_list"] == ["a", "b", "c"]
        assert examples["x_ints_list"] == [1, 2, 3]
        assert examples["x_floats_list"] == [1.2, 2.2, 3.3]
        assert examples["x_bools_list"] == [False, True, False]
        assert examples["x_bool_only"] == False
        assert examples["x_int_only"] == 1
        assert examples["x_list_any"] == ["hello", "1", "1.1", "False"]

    def test_exit_after_success(self):
        # Force stop.
        self.stop_process()

        assert not self.process_is_running()
        assert self.get_return_code() == RESULT_OK
        assert self.server_stopped()
