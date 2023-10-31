# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import os


def builder():
    try:
        os.makedirs("generated")
    except:
        pass
    with open("generated/a", "w") as f:
        f.write("generated file")
    with open("generated/b", "w") as f:
        f.write("generated file")
