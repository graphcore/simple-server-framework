# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import model


@pytest.mark.slow
@pytest.mark.ipu
@pytest.mark.model
@pytest.mark.skip(reason="Temporary skip")
class TestsStableDiffusion(model.TestModel):
    def configure(self):
        self.deploy_name = "test_model_stable_diffusion"
        self.config_file = "examples/models/stable_diffusion/ssf_config.yaml"

    def test_stable_diffusion(self):
        return self.test_model()

    def test_stable_diffusion_within_ssf(self):
        return self.test_model_within_ssf()
