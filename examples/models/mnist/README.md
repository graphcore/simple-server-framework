<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Example Model: MNIST

The SSF `examples/models` sources are provided for reference and are not part of the core SSF application nor are the examples included in the SSF pre-built image.
The `examples/models` sources do not include the model datasets nor weights; these are downloaded only if `build` or `run` is issued for the example model.

Note however, if `package` is subsequently issued, then the resultant image will contain the downloaded model dataset.

# Licensing

This example uses libraries from Pytorch and an MNIST dataset from Yann LeCun and Corinna Cortes.

## Pytorch

BSD 3-Clause License

https://github.com/pytorch/vision/blob/main/LICENSE

## MNIST Dataset

reference: https://pytorch.org/vision/stable/datasets.html#built-in-datasets

Yann LeCun and Corinna Cortes hold the copyright of MNIST dataset, which is a derivative work from original NIST datasets.
MNIST dataset is made available under the terms of the Creative Commons Attribution-Share Alike 3.0 license.

http://yann.lecun.com/exdb/mnist
