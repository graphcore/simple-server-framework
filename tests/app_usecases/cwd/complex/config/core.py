# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os

# To test priority: The user syspath should take precedence.
CORE = "test_cwd : unexpected config directory"


def core():
    print(CORE)
