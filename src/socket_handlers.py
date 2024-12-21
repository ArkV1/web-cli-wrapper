import logging
from flask_socketio import emit, join_room, disconnect
from flask import request
from threading import Lock

logger = logging.getLogger(__name__)

def init_socket_handlers(socketio, manager):
    # Track active clients
    active_clients = {}
    active_clients_lock = Lock()

    @socketio.on('connect')
    def handle_connect():
        client_id = request.sid
        logger.info(f'WebSocket connected successfully')
        logger.info(f'Client ID: {client_id}')
        
        with active_clients_lock:
            active_clients[client_id] = {'connected': True}
        
        join_room(client_id)
        emit('connection_established', {'status': 'connected'})
        logger.info('Sent connection_established event')

    @socketio.on('disconnect')
    def handle_disconnect():
        client_id = request.sid
        logger.info(f'WebSocket disconnected (Client ID: {client_id})')
        
        with active_clients_lock:
            if client_id in active_clients:
                active_clients[client_id]['connected'] = False
                del active_clients[client_id]

    @socketio.on('check_progress')
    def handle_check_progress(data):
        """Handle progress check requests from clients."""
        task_id = data.get('task_id')
        client_id = request.sid
        
        logger.info(f"Received check_progress event for task {task_id} from client {client_id}")
        
        # Get current progress from manager
        progress = manager.get_progress(task_id)
        if progress:
            emit('transcription_progress', progress)

    @socketio.on_error()
    def error_handler(e):
        error_info = {
            'error': str(e),
            'client_id': request.sid,
            'remote_addr': request.remote_addr
        }
        logger.error(f'WebSocket error: {str(e)}', extra=error_info)