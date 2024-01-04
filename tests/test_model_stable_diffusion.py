# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import model


@pytest.mark.slow
@pytest.mark.ipu
@pytest.mark.model
class TestsStableDiffusion(model.TestModel):
    def configure(self):
        self.deploy_name = "test_model_stable_diffusion"
        self.config_file = "examples/models/stable_diffusion/ssf_config.yaml"

    def test_stable_diffusion(self):
        return self.test_model()

    @pytest.mark.skipif(
        not model.check_image_available(),
        reason=f"Skipped test (Image {model.get_default_ssf_image()} is not available)",
    )
    def test_stable_diffusion_within_ssf(self):
        return self.test_model_within_ssf()
