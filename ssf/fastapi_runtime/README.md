<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Simple Server Framework - FastAPI Runtime

Code to run SSF server with FastAPI.


- `ssf_run.py` : Entry point (starts uvicorn)
- `server.py` : Main server app
- `server_security.py` : Conditional security endpoints and handlers
- `dispatcher.py` : The endpoint dispatch interface and associated queue(s)
- `config.py` : Defines settings (from environment/.env)
- `common.py` : Some support pieces required by app FastAPI endpoints
- `requirements.txt` : Required packages to run the FastAPI server runtime


NOTE:
The uvicorn server is started with N workers using the SSF --replicate option.
In practice, this means that server.py can end up being run N times for each replicate as an entirely independent process.
Each server (replicate) will have its own dispatcher/queue (for each registered application; normally just one)
The dispatcher calls through the application interface to create/acquire a user application interface instance at start up.
The user application interface instance must be unique and independent per dispatcher;  this provides a mechanism for scaling
the same end-point to fully utilise a system.



## Environment variables

These variables are set automatically by SSF when `ssf run` is issued (see `ssf_run.py`):

- `SSF_CONFIG_FILE` : The config file to run.
- `FILE_LOG_LEVEL` : Set log level for file log
- `STDOUT_LOG_LEVEL` : Set the log level for stdout
- `API_KEY` : The API key to use (only set or overridden by SSF when --key is specified)
- `REPLICATE_DISPATCHER` : Number of application replicas
- `WATCHDOG_REQUEST_THRESHOLD` : Request duration watchdog threshold
- `WATCHDOG_REQUEST_AVERAGE` : Number of last requests factored in request duration watchdog
- `BATCHING_TIMEOUT` : Timeout in seconds the server waits to accumulate samples if batching is enabled

These variables are not current set via SSF when `ssf run` is issued:

- `API_KEY_TIMEOUT` : The API key auto-logout timeout.
- `ALLOW_ORIGIN_REGEX` : Set a regex to use for allow_origin (CORS); the default allows localhost or 127.0.0.1 with any port.
