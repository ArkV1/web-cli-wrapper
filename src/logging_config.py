import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File Handler (optional)
    file_handler = RotatingFileHandler("app.log", maxBytes=10**6, backupCount=5)
    file_handler.setFormatter(formatter)

    # Root Logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler]
    )

    logging.info("Logging is configured.")
