# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import model


@pytest.mark.slow
@pytest.mark.ipu
@pytest.mark.model
class TestsWalkthrough(model.TestModel):
    def configure(self):
        self.deploy_name = "test_model_walkthrough"
        self.config_file = "examples/walkthrough/ssf_config.yaml"

    def test_walkthrough(self):
        return self.test_model()


# Skip the test_model_within_ssf for the walkthrough
