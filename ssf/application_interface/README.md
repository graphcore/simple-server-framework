<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Simple Server Framework - Application Interface

Code available to the user-facing application
Do not import external packages in application_interface modules
to avoid introducing additional dependencies for the application.
Only import SSF modules that are also in application_interface.

- `application.py` : The application interface definition
- `results.py` : Result codes and exceptions
- `config.py` : The SSF config
- `worker.py` : The bridge for SSF<->Application process isolation
- `logger.py` : Logging utilities
- `utils.py` : Utilities available to the application
- `runtime_settings.py` : Settings and headers for runtime
