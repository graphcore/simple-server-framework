<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Simple Server Framework - FastAPI Runtime

Code common to all supported APIs.

- `dispatcher.py` : The endpoint dispatch interface and associated queue(s)
- `config.py` : Defines settings (from environment/.env)
- `common.py` : Some support pieces required by app FastAPI endpoints
- `headers.py` : Specific headers values used by SSF
