import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from flask import Blueprint, request, jsonify

# Configure client logging
client_logger = logging.getLogger('client_logs')
client_logger.setLevel(logging.INFO)

# Ensure logs directory exists
LOGS_DIR = Path('logs/client')
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Create a file handler that logs client events
log_file = LOGS_DIR / 'client.log'
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
client_logger.addHandler(file_handler)

def register_client_logging_routes(app):
    """Register routes for client-side logging."""
    client_logs = Blueprint('client_logs', __name__)

    @client_logs.route('/api/logs', methods=['POST'])
    def submit_log():
        try:
            log_data = request.get_json()
            
            # Required fields
            level = log_data.get('level', 'INFO').upper()
            message = log_data.get('message')
            
            # Optional metadata
            metadata = log_data.get('metadata', {})
            client_info = {
                'timestamp': datetime.utcnow().isoformat(),
                'ip': request.remote_addr,
                'user_agent': request.headers.get('User-Agent'),
                **metadata
            }
            
            # Format the log message
            formatted_message = f"{message} | Client Info: {client_info}"
            
            # Log based on level
            if level == 'ERROR':
                client_logger.error(formatted_message)
            elif level == 'WARNING':
                client_logger.warning(formatted_message)
            else:
                client_logger.info(formatted_message)
            
            return jsonify({'status': 'success', 'message': 'Log submitted successfully'})
        
        except Exception as e:
            client_logger.error(f"Error processing client log: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    app.register_blueprint(client_logs) 