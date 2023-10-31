# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import model
from ssf.utils import API_GRPC


@pytest.mark.fast
class TestsSimpleGRPC(model.TestModel):
    def configure(self):
        self.deploy_name = "test_simple_grpc"
        self.config_file = "examples/types/ssf_config_grpc.yaml"

    def test_grpc(self):
        return self.test_model(API_GRPC)

    @pytest.mark.skipif(
        not model.check_image_available(),
        reason=f"Skipped test (Image {model.get_default_ssf_image()} is not available)",
    )
    def test_grpc_within_ssf(self):
        return self.test_model_within_ssf(API_GRPC)
