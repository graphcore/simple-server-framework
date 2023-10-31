# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
import subprocess
import sys

# Temporary workaround to install pip dependencies clashing at ssf-packaging time
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


install("optimum-graphcore==0.7.1")
