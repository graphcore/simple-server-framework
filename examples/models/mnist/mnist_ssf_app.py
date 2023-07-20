# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import logging
import requests
import torch
import torch.nn as nn
import torchvision
import poptorch
import torch.optim as optim
from PIL import Image
import json
import os
import numpy
from typing import Tuple
from pathlib import Path
import random

from ssf.application import SSFApplicationInterface, SSFApplicationTestInterface
from ssf.results import *

logger = logging.getLogger("MNIST")

##### MNIST Model arch definition START #####
#
# Taken from
# https://github.com/graphcore/examples/blob/v3.2.0/tutorials/simple_applications/pytorch/mnist/mnist_poptorch.ipynb
#
class Block(nn.Module):
    def __init__(self, in_channels, num_filters, kernel_size, pool_size):
        super(Block, self).__init__()
        self.conv = nn.Conv2d(in_channels, num_filters, kernel_size=kernel_size)
        self.pool = nn.MaxPool2d(kernel_size=pool_size)
        self.relu = nn.ReLU()

    def forward(self, x):
        x = self.conv(x)
        x = self.pool(x)
        x = self.relu(x)
        return x


class Network(nn.Module):
    def __init__(self):
        super(Network, self).__init__()
        self.layer1 = Block(1, 32, 3, 2)
        self.layer2 = Block(32, 64, 3, 2)
        self.layer3 = nn.Linear(1600, 128)
        self.layer3_act = nn.ReLU()
        self.layer3_dropout = torch.nn.Dropout(0.5)
        self.layer4 = nn.Linear(128, 10)
        self.softmax = nn.Softmax(1)

    def forward(self, x):
        x = self.layer1(x)
        x = self.layer2(x)
        # Flatten layer
        x = x.view(-1, 1600)
        x = self.layer3_act(self.layer3(x))
        x = self.layer4(self.layer3_dropout(x))
        x = self.softmax(x)
        return x


class TrainingModelWithLoss(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.loss = torch.nn.CrossEntropyLoss()

    def forward(self, args, labels=None):
        output = self.model(args)
        if labels is None:
            return output
        else:
            loss = self.loss(output, labels)
            return output, loss


##### MNIST Model arch definition END #####


def convert_to_mnist(image_path):
    # Load the image
    image = Image.open(image_path)

    # Resize the image to 28x28 pixels
    image = image.resize((28, 28))

    # Convert the image to grayscale
    image = image.convert("L")

    # Convert PIL image to PyTorch tensor
    image_tensor = torchvision.transforms.ToTensor()(image)

    return image_tensor


def get_fake_tensor():
    fake_shape = [1, 1, 28, 28]
    fake_tensor = torch.ones(fake_shape, dtype=torch.float)
    return fake_tensor


class MNISTAPI(SSFApplicationInterface):
    def __init__(self):
        logger.info(f"MNIST API init - enter")

        self._inference_model = None
        self._local_dataset_path = "mnist_datasets_downloaded"
        self._inference_popef_fn = "exe_cache/mnist_inference.popef"

    def build(self) -> int:
        logger.info(f"MNIST API build - enter")

        # Build model
        # Training hyper-parameters
        LEARNING_RATE = 0.03
        EPOCHS = 10
        BATCH_SIZE = 8
        DEVICE_ITERATIONS = 50
        torch.manual_seed(0)
        numpy.random.seed(0)
        random.seed(0)

        transform_mnist = torchvision.transforms.Compose(
            [
                torchvision.transforms.ToTensor(),
                torchvision.transforms.Normalize((0.1307,), (0.3081,)),
            ]
        )
        training_dataset = torchvision.datasets.MNIST(
            self._local_dataset_path,
            train=True,
            download=True,
            transform=transform_mnist,
        )

        training_opts = poptorch.Options()
        training_opts = training_opts.deviceIterations(DEVICE_ITERATIONS)
        training_opts = training_opts.randomSeed(0)

        training_data = poptorch.DataLoader(
            options=training_opts,
            dataset=training_dataset,
            batch_size=BATCH_SIZE,
            shuffle=True,
            drop_last=True,
        )

        model = Network()
        model_with_loss = TrainingModelWithLoss(model)

        training_opts = poptorch.Options()
        training_opts = training_opts.deviceIterations(DEVICE_ITERATIONS)
        training_opts = training_opts.randomSeed(0)
        training_opts = training_opts.outputMode(poptorch.OutputMode.All)

        training_model = poptorch.trainingModel(
            model_with_loss,
            training_opts,
            optimizer=optim.SGD(model.parameters(), lr=LEARNING_RATE),
        )

        for epoch in range(EPOCHS):
            for data, labels in training_data:
                training_model(data, labels)
        # training_model.detachFromDevice()
        self._inference_model = poptorch.inferenceModel(model_with_loss)
        self._inference_model(get_fake_tensor())
        self._inference_model.save(self._inference_popef_fn)

        return RESULT_OK

    def startup(self) -> int:
        logger.info("MNIST API startup - enter")

        if self._inference_model is None:
            popef_file = Path(self._inference_popef_fn)

            if popef_file.exists():
                self._inference_model = poptorch.load(self._inference_popef_fn)
                logger.info(f"Using cached inference model")
            else:
                logger.error(
                    "No saved inference model. Build it with 'build' command first"
                )
                return RESULT_FAIL

        # Make first test inference
        self._inference_model(get_fake_tensor())

        return RESULT_OK

    def request(self, params: dict, meta: dict) -> dict:
        logger.info(f"MNIST API request with params={params} meta={meta}")

        input_tensor = convert_to_mnist(params["digit_bin"])
        # Add one more dimension to the tensor
        input_tensor = input_tensor.unsqueeze(0)
        result_tensor = self._inference_model(input_tensor)

        arr = numpy.array(result_tensor)

        # Convert the index to multi-dimensional coordinates
        max_position = numpy.unravel_index(numpy.argmax(arr), arr.shape)

        # Index we're looking for is in second in the tuple
        result_dict = {"result": max_position[1]}
        logger.info(f"MNIST 2 API returning result={result_dict}")

        return result_dict

    def shutdown(self) -> int:
        logger.info("MNIST API shutdown")
        return RESULT_OK

    def is_healthy(self) -> bool:
        logger.info("MNIST API check health")
        return True


# NOTE:
# This can be called multiple times (with separate processes)
# if running with multiple workers (replicas). Be careful that
# your application can handle multiple parallel worker processes.
# (for example, that there is no conflict for file I/O).
def create_ssf_application_instance() -> SSFApplicationInterface:
    logger.info("MNIST API instance - enter")
    return MNISTAPI()


class MyApplicationTest(SSFApplicationTestInterface):
    def begin(self, session, ipaddr: str) -> int:
        logger.info("MyApp test begin")
        return RESULT_OK

    def subtest(self, session, ipaddr: str, index: int) -> Tuple[bool, str, bool]:

        logger.info(f"Running MNIST test.")

        subtests = 10
        last_index = subtests - 1

        input_image = f"test_images/{index}.png"

        try:
            files = {
                "digit_bin": (
                    os.path.basename(input_image),
                    open(input_image, "rb"),
                    "image/png",
                )
            }
            url = f"{ipaddr}/v1/mnist_api"
            response = session.post(
                url,
                files=files,
                headers={
                    "accept": "*/*",
                },
                timeout=10,
            )

            logger.info(f"response=={response}")
            MAGIC1 = 200
            ok1 = response.status_code == MAGIC1
            if not ok1:
                logger.error(
                    f"Failed {url} with {input_image} : {response.status_code} v expected {MAGIC1}"
                )

            test_expected = {"result": index}
            ok2 = json.loads(response.content) == test_expected
            if not ok2:
                logger.error(
                    f"Failed {url} with {input_image} : {response.content} v expected {index}"
                )

            return (
                ok1 == ok2 == True,
                f"v1/mnist_api {input_image}",
                index < last_index,
            )

        except requests.exceptions.RequestException as e:
            logger.info(f"Exception {e}")
            return (False, e, False)

    def end(self, session, ipaddr: str) -> int:
        logger.info("MyApp test end")
        return RESULT_OK


def create_ssf_application_test_instance(ssf_config) -> SSFApplicationTestInterface:
    logger.info("Create MyApplication test instance")
    return MyApplicationTest()
