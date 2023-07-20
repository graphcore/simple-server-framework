# Copyright (c) 2023 Graphcore Ltd. All rights reserved.
VERSION = "1.0.0"
ID = "simple-server-framework"
NAME = "Simple Server Framework"

# Set MINIMUM_SUPPORTED_VERSION and MAXIMUM_SUPPORTED_VERSION
# to the inclusive range of supported ssf-version or None if
# there is no bound.
MINIMUM_SUPPORTED_VERSION = "0.0.1"
MAXIMUM_SUPPORTED_VERSION = "1.0.0"

# The default baseimage used for packaging (container image) when
# neither the application config nor the CLI arg --package-baseimage are available.
PACKAGE_DEFAULT_BASEIMAGE = "graphcore/pytorch:3.2.0-ubuntu-20.04-20230314"

# The default SSF image to deploy (the default image used when the --deploy-package option is NOT set)
SSF_DEPLOY_IMAGE = "graphcore/simple-server-framework:" + VERSION
