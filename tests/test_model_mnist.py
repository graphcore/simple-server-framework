# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import pytest
import model


@pytest.mark.slow
@pytest.mark.ipu
@pytest.mark.model
class TestsMNIST(model.TestModel):
    def configure(self):
        self.deploy_name = "test_model_mnist"
        self.config_file = "examples/models/mnist/mnist_config.yaml"

    def test_mnist(self):
        return self.test_model()

    def test_mnist_within_ssf(self):
        return self.test_model_within_ssf()
