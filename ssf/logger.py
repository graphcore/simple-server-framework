# Copyright (c) 2023 Graphcore Ltd. All rights reserved.

import logging
from logging.handlers import QueueHandler
import sys
import traceback
import multiprocessing as mp
import atexit
from ssf.results import SSFExceptionInternalError

ctx = mp.get_context("spawn")
default_logging_level_file = logging.DEBUG
default_logging_level_stdout = logging.INFO

log_queue = None
listener = None

LOG_FILENAME = "ssf.log"


def reset_log():
    # (Re)create empty log file.
    open(LOG_FILENAME, "w")


def log_listener_process(
    queue, init_logging, default_logging_level_file, default_logging_level_stdout
):
    # Initialize root-level logger
    init_logging(
        None,
        LOG_FILENAME,
        "w",
        default_logging_level_file,
        True,
        default_logging_level_stdout,
    )
    while True:
        try:
            record = queue.get()
            if record is None:
                break
            logger = logging.getLogger(record.name)
            logger.handle(record)
        except KeyboardInterrupt:
            pass
        except Exception:
            import sys, traceback

            print("Exception in logger process.", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            break


def str_to_log_level(level: str):
    if level == "DEBUG":
        return logging.DEBUG
    elif level == "INFO":
        return logging.INFO
    elif level == "WARNING":
        return logging.WARNING
    elif level == "ERROR":
        return logging.ERROR
    elif level == "CRITICAL":
        return logging.CRITICAL
    raise SSFExceptionInternalError(f"Unknown log level {level}")


def set_default_logging_levels(file_level, stdout_level):
    global default_logging_level_file
    global default_logging_level_stdout
    default_logging_level_file = str_to_log_level(file_level)
    default_logging_level_stdout = str_to_log_level(stdout_level)


def get_default_logging_levels():
    return (default_logging_level_file, default_logging_level_stdout)


class SmartLoggingFormatter(logging.Formatter):
    def __init__(self, stream: bool = False, **kwds):
        super(SmartLoggingFormatter, self).__init__(**kwds)
        self.stream = True

    RED = "\033[1;31m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Default format
    default_format = "%(asctime)s %(process)-10.10s %(levelname)-8.8s  %(message)s (%(filename)s:%(lineno)d)"

    # Wrap default format with colour depending on log level
    log_level_formats = {
        logging.DEBUG: RESET + default_format,
        logging.INFO: RESET + default_format,
        logging.WARNING: RESET + YELLOW + default_format + RESET,
        logging.ERROR: RESET + RED + default_format + RESET,
        logging.CRITICAL: RESET + BOLD + RED + default_format + RESET,
    }

    # Heading lines format
    heading_format = RESET + BOLD + GREEN + default_format + RESET

    def format(self, record):
        if type(record.msg) == str and len(record.msg) and record.msg[0] == ">":
            log_fmt = self.heading_format
        else:
            log_fmt = self.log_level_formats.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def init_logging(
    name: str,
    filename: str,
    filemode: str,
    file_level: int = None,
    add_stream_handlers: bool = True,
    stdout_level: int = None,
):
    if file_level is None:
        global default_logging_level_file
        file_level = default_logging_level_file
        print(f"Using default log level for file {file_level}")
    if stdout_level is None:
        global default_logging_level_stdout
        stdout_level = default_logging_level_stdout
        print(f"Using default log level for stdout {stdout_level}")

    # Unique logger.
    logger = logging.getLogger(name)

    # Log to file if specified.
    if filename:
        log_file = logging.FileHandler(filename, filemode, encoding="utf-8")
        log_file.setFormatter(SmartLoggingFormatter())
        logger.addHandler(log_file)

    if add_stream_handlers:
        # Log >= ERROR to stderr.
        sys.stderr.reconfigure(encoding="utf-8")
        log_stderr = logging.StreamHandler(sys.stderr)
        log_stderr.addFilter(lambda record: record.levelno >= logging.ERROR)
        log_stderr.setFormatter(SmartLoggingFormatter(stream=True))
        logger.addHandler(log_stderr)

        # Log [INFO:WARNING] to stdout.
        sys.stdout.reconfigure(encoding="utf-8")
        log_stdout = logging.StreamHandler(sys.stdout)
        log_stdout.addFilter(
            lambda record: record.levelno >= stdout_level
            and record.levelno <= logging.WARNING
        )
        log_stdout.setFormatter(SmartLoggingFormatter(stream=True))
        logger.addHandler(log_stdout)

    logger.setLevel(file_level)

    # Log any/all uncaught exceptions.
    def log_exceptions(type, value, tb):
        # Log traceback.
        # logger.exception(value, exc_info=True)
        lines = []
        for line in traceback.TracebackException(type, value, tb).format(chain=True):
            line = line.strip()
            if len(line) > 0:
                lines.append(line)
        msg = "\n".join(lines)
        logger.critical(msg)
        log_queue.put_nowait(None)
        # Pass through to default excepthook?
        # sys.__excepthook__(type, value, tb)

    sys.excepthook = log_exceptions

    return logger


def configure_log_queue(queue):
    h = logging.handlers.QueueHandler(queue)
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(logging.DEBUG)


def init_global_logging():
    global listener
    global log_queue
    if log_queue is None or listener is None:
        log_queue = ctx.Queue(5000)
        listener = ctx.Process(
            target=log_listener_process,
            args=(
                log_queue,
                init_logging,
                default_logging_level_file,
                default_logging_level_stdout,
            ),
        )
        listener.start()
        configure_log_queue(log_queue)
        logger = logging.getLogger()
        logger.debug(f"> Logger process has started (pid: {listener.pid})")
        atexit.register(stop_global_logging)


def stop_global_logging():
    global listener
    global log_queue
    log_queue.put_nowait(None)
    listener.join()


def get_log_queue():
    global log_queue
    return log_queue
