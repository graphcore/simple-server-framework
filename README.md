<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->

# Simple Server Framework

## Documentation:
📖 [SSF user guide](https://graphcore.github.io/simple-server-framework/docs)

## Overview

Graphcore's Simple Server Framework (SSF) is a tool for building, running and packaging (containerising) applications for serving.
It can be used to serve any machine learning inference models running on IPUs and automate their deployment on supported cloud platforms.

Using SSF simplifies deployment and reduces code repetition and redundancy when working with several independent applications.

 SSF has the following features:

- Minimal code required for applications
- Declarative configuration that is serving framework agnostic
- No specific machine learning model formats required
- Standardised application interface
- Serving framework implementation details are retained by SSF


## Basics

Each application requires two things:

-  An application interface (Python module to receive 'build' and 'run' requests)
-  A declarative configuration that provides some details, including a definition of request inputs and outputs.

Once the application interface and configuration have been set up then SSF can be used with the following commands (note that these commands can be issued individually or combined):

- `init`
- `build`
- `run`
- `package`
- `publish`
- `deploy`

As an example, if you run:

```bash
gc-ssf --config examples/simple/ssf_config.yaml init build package
```
you will create a clean packaged application with served endpoints.
To take another example, if you run:

```bash
gc-ssf --config examples/simple/ssf_config.yaml build run
```
you will build and run the application with served endpoints from source.