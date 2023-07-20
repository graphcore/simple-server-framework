<!-- Copyright (c) 2023 Graphcore Ltd. All rights reserved. -->
# Simple Server Framework - Tests

## Environment

Follow the instructions for running SSF from source in the "Installation" section of the 📖 [SSF user guide](https://graphcore.github.io/simple-server-framework/docs/installation)

## Run tests

From repository root, run:

```bash
pytest tests
```

or, with trace,

```bash
pytest tests -s
```

Run a specific test by name:

```bash
pytest tests -k "test_example_simple_init"
```

## Markers

To list markers:

```bash
pytest tests --markers
```

### Custom markers

- `fast`  : mark test as relatively fast
- `slow`  : mark test as relatively slow
- `ipu`   : mark test as requiring IPU
- `model` : mark test as a 'model' (full application)

To limit tests use `-m <markers>`
E.g. Pull request testing uses:

```bash
pytest tests -m "fast and not ipu"
```

If new markers are required, add them to `pytest.ini`
