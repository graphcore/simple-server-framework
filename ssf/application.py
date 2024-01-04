# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
# All application interface modules are now in their own
# application_interface sub-folder. Modules in that folder
# must NOT introduce external package dependencies.
# This redirection exists to support backwards compatibility with
# existing user applications that still import from ssf.***
from ssf.application_interface.application import *
