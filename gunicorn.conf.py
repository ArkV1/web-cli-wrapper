import logging
import warnings
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog
from src.custom_logger import CustomGunicornLogger  # <-- Our custom Gunicorn logger

##############################################################################
# Gunicorn Basic Settings
##############################################################################
bind = "0.0.0.0:3003"
backlog = 2048

workers = 1
worker_class = "gevent"
worker_connections = 1000

timeout = 3600
graceful_timeout = 120
keepalive = 5

proc_name = "web-toolkit"
default_proc_name = "web-toolkit"

# Use our custom Gunicorn logger for Gunicorn's own logs
logger_class = "src.custom_logger.CustomGunicornLogger"

##############################################################################
# Logging Settings
##############################################################################
accesslog = "-"
errorlog = "-"
loglevel = "debug"
access_log_format = '[%(t)s] [ACCESS] %(h)s "%(r)s" %(s)s %(b)s'

reload = True
reload_engine = "auto"
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

##############################################################################
# WebSocket Settings
##############################################################################
websocket_ping_interval = 25
websocket_ping_timeout = 60

##############################################################################
# Create /logs if it doesn't exist
##############################################################################
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

##############################################################################
# Configure Application Logging (for your Flask or other Python logs)
##############################################################################
def configure_app_logging(force=False):
    """
    This configures standard Python logging with colorlog for your app-level logs.
    `force=True` means we attach handlers even if they were attached previously—
    useful in worker processes that might share the same logger object.
    """
    logging.captureWarnings(True)
    
    # Create formatters
    file_formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S.%fZ'
    )

    console_formatter = colorlog.ColoredFormatter(
        fmt="%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s %(name)s: %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )

    # Rotating file handlers
    access_handler = RotatingFileHandler(
        logs_dir / "access.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(file_formatter)

    error_handler = RotatingFileHandler(
        logs_dir / "error.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(file_formatter)

    debug_handler = RotatingFileHandler(
        logs_dir / "debug.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(file_formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(console_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # If force=True, or if there are no handlers yet, attach them
    if force or not root_logger.handlers:
        # Remove existing handlers if force=True
        if force:
            for h in list(root_logger.handlers):
                root_logger.removeHandler(h)

        root_logger.addHandler(access_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(debug_handler)
        root_logger.addHandler(console_handler)

    logging.info("Application logging configured.")

# Call it *once* in the master process (for good measure)
configure_app_logging()

##############################################################################
# Gunicorn Lifecycle Hooks
##############################################################################
def post_fork(server, worker):
    """
    Gunicorn calls this after a worker process is forked. 
    We re-invoke our app logging config, ensuring colorlog is attached 
    within the worker, so debug logs from the worker show up colorized.
    """
    configure_app_logging(force=True)
    logging.debug("post_fork: Worker logging has been configured.")
