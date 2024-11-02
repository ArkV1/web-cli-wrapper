from gevent import monkey
monkey.patch_all()

from flask import Flask
from flask_socketio import SocketIO
from src.routes import register_routes
from src.api_routes import register_api_routes
# from src.socket_handlers import register_socket_handlers
import os
from pathlib import Path
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-default-secret-key')

# Configure longer timeouts for SocketIO
socketio = SocketIO(
    app,
    async_mode='gevent',
    ping_timeout=60,  # Reduce to 1 minute
    ping_interval=25,
    cors_allowed_origins="*",
    max_http_buffer_size=50 * 1024 * 1024,  # Reduce to 50MB buffer
    logger=True,  # Enable logging for debugging
    engineio_logger=True,  # Enable Engine.IO logging for debugging
    path='/socket.io/',  # Explicitly set the path
    message_queue=None  # Add this line to ensure proper message handling
)

# Add after imports
temp_dir = Path('temp_audio')
temp_dir.mkdir(exist_ok=True)

# Register your routes
register_routes(app)
register_api_routes(app, socketio)
# register_socket_handlers(socketio)

def setup_websocket_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

# Add this right after creating the Flask app
setup_websocket_logging()

if __name__ == '__main__':
    # Increase worker timeout
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('FLASK_RUN_PORT', 5000)),
        worker_timeout=300  # 5 minutes timeout
    )
