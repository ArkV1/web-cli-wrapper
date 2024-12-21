from gevent import monkey
monkey.patch_all()

from flask import Flask
from flask_socketio import SocketIO
from src.routes import register_routes
from src.api_routes import register_api_routes
import os
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-default-secret-key')

# Create logs directory if it doesn't exist
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

def setup_logging():
    # Create formatters
    console_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S.%fZ'
    )
    file_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S.%fZ'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # File handler for general logs
    general_log = logs_dir / 'app.log'
    file_handler = RotatingFileHandler(
        general_log,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # File handler for error logs
    error_log = logs_dir / 'error.log'
    error_handler = RotatingFileHandler(
        error_log,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setFormatter(file_formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)

    # Configure Flask logger
    app.logger.handlers = []
    for handler in root_logger.handlers:
        app.logger.addHandler(handler)

    # Configure Socket.IO logging
    socketio_logger = logging.getLogger('socketio')
    socketio_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers:
        socketio_logger.addHandler(handler)

    # Configure Engine.IO logging
    engineio_logger = logging.getLogger('engineio')
    engineio_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers:
        engineio_logger.addHandler(handler)

# Set up logging before anything else
setup_logging()

# Configure SocketIO with logging enabled
socketio = SocketIO(
    app,
    async_mode='gevent',
    ping_timeout=60,  # 1 minute
    ping_interval=25,
    cors_allowed_origins="*",
    max_http_buffer_size=50 * 1024 * 1024,  # 50MB buffer
    logger=True,
    engineio_logger=True,
    path='/socket.io/',
    message_queue=None
)

# Create temp directory for audio files
temp_dir = Path('temp_audio')
temp_dir.mkdir(exist_ok=True)

# Register routes
register_routes(app)
register_api_routes(app, socketio)

if __name__ == '__main__':
    # Increase worker timeout
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('FLASK_RUN_PORT', 5000)),
        worker_timeout=300  # 5 minutes timeout
    )
