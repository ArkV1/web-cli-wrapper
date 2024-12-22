# src/custom_logger.py

import logging
import colorlog
from gunicorn import glogging

class CustomGunicornLogger(glogging.Logger):
    """
    A custom Gunicorn logger that uses colorlog for the Gunicorn master logs
    (including Gunicorn's error logs and access logs).
    """
    def setup(self, cfg):
        super().setup(cfg)

        # Remove Gunicorn's built-in handlers
        for handler in self.error_log.handlers[:]:
            self.error_log.removeHandler(handler)
        for handler in self.access_log.handlers[:]:
            self.access_log.removeHandler(handler)

        # Create a colorlog formatter
        formatter = colorlog.ColoredFormatter(
            fmt="%(log_color)s[%(asctime)s] [%(levelname)s]%(reset)s %(name)s: %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
        )

        # Create a console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)

        # Attach the console handler to Gunicorn's logs
        self.error_log.addHandler(console_handler)
        self.access_log.addHandler(console_handler)

        # Adjust levels if desired
        self.error_log.setLevel(logging.INFO)
        self.access_log.setLevel(logging.INFO)
