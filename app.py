##############################################################################
# We rely on gevent monkey-patching so that Flask-SocketIO can handle real-time
# WebSocket connections under Gunicorn's gevent worker.
#
# Note: Because gevent patches low-level sockets, it can conflict with
# `multiprocessing.Manager()` on macOS. If you need CPU-heavy tasks plus progress
# updates, consider:
#  - A file-based approach or external queue (like Redis) for progress, or
#  - Running a separate transcription service using a sync/gthread worker.
##############################################################################
from gevent import monkey
monkey.patch_all()

import os
import logging
from pathlib import Path
from flask import Flask
from flask_socketio import SocketIO

# Import route registration functions
from src.routes import register_routes
from src.api_routes import register_api_routes

# Create a logger for this module
logger = logging.getLogger(__name__)

# Create the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-default-secret-key')

##############################################################################
# Because we are using gevent workers, we can now set `async_mode='gevent'`.
# This ensures native WebSocket support rather than falling back to long-polling.
##############################################################################
socketio = SocketIO(
    app,
    async_mode='gevent',
    ping_timeout=60,  # 1 minute
    ping_interval=25,
    cors_allowed_origins="*",
    max_http_buffer_size=50 * 1024 * 1024,  # 50MB buffer
    path='/socket.io/',
    message_queue=None
)

# Create temp directory for audio files
temp_dir = Path('temp_audio')
temp_dir.mkdir(exist_ok=True)

# Register routes
logger.debug("Registering Flask routes...")
register_routes(app)
register_api_routes(app, socketio)
logger.debug("Routes registered successfully.")

if __name__ == '__main__':
    # If you run "python app.py" directly, it will run with gevent locally,
    # but in production you typically do: `gunicorn -c gunicorn.conf.py app:app`
    logger.info("Starting Flask application in development mode.")
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('FLASK_RUN_PORT', 5000)),
        worker_timeout=300  # 5 minutes
    )
    logger.info("Flask application has stopped.")
