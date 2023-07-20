<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Example Model: Stable Diffusion2

The SSF `examples/models` sources are provided for reference and are not part of the core SSF application nor are the examples included in the SSF pre-built image.
The `examples/models` sources do not include the model datasets nor weights; these are downloaded only if `build` or `run` is issued for the example model.

Note however, if `package` is subsequently issued, then the resultant image will contain the downloaded model weights.

# Licensing

This example uses libraries from HuggingFace and the Stable Diffusion 2 model from Stability AI.

## Huggingface

Apache License, Version 2.0, January 2004

https://github.com/huggingface/diffusers/blob/main/LICENSE

Apache License, Version 2.0, January 2004

https://github.com/huggingface/optimum-graphcore/blob/main/LICENSE

## Stable diffusion 2 Model

CreativeML Open RAIL++-M License, November 24, 2022

https://huggingface.co/stabilityai/stable-diffusion-2/blob/main/LICENSE-MODEL
