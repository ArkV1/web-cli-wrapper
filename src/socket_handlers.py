from flask import request
from flask_socketio import SocketIO, emit
import logging

# Main logger
logger = logging.getLogger('websocket')

def init_socket_handlers(socketio: SocketIO, transcription_tasks, tasks_lock):
    @socketio.on('connect')
    def handle_connect():
        logger.info(f'Client connected: {request.sid}')
        emit('connection_established', {'status': 'connected'})

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected')

    @socketio.on('check_progress')
    def handle_progress_check(data):
        task_id = data.get('task_id')
        logger.info(f'Checking progress for task: {task_id}')
        
        with tasks_lock:
            if task_id in transcription_tasks:
                task_data = transcription_tasks[task_id].copy()
                task_data['task_id'] = task_id
                socketio.emit('transcription_progress', task_data, room=request.sid)
            else:
                socketio.emit('transcription_progress', {
                    'task_id': task_id,
                    'progress': 0,
                    'message': 'Task not found',
                    'complete': False,
                    'success': False,
                    'error': 'Task not found'
                }, room=request.sid)

    @socketio.on_error()
    def error_handler(e):
        logger.error('WebSocket error occurred', exc_info=True, extra={
            'error': str(e),
            'client_id': request.sid,
            'remote_addr': request.remote_addr
        })
        emit('error', {'error': str(e)})

def check_task_progress(task_id):
    """Check the progress of a transcription task."""
    try:
        task_result = AsyncResult(task_id)
        
        if task_result.ready():
            if task_result.successful():
                result = task_result.get()
                return {
                    'task_id': task_id,
                    'complete': True,
                    'success': True,
                    'progress': 100,
                    'message': 'Transcription complete!',
                    **result  # Unpack the result data, should include 'transcript'
                }
            else:
                error = str(task_result.result)
                return {
                    'task_id': task_id,
                    'complete': True,
                    'success': False,
                    'progress': 100,
                    'message': f'Task failed: {error}',
                    'error': error
                }
        else:
            # Get progress info if available
            progress_info = task_result.info or {}
            return {
                'task_id': task_id,
                'complete': False,
                'success': None,
                'progress': progress_info.get('progress', 0),
                'message': progress_info.get('message', 'Processing...'),
                'download_speed': progress_info.get('download_speed'),
                'eta': progress_info.get('eta')
            }
    except Exception as e:
        logger.error(f"Error checking task progress: {str(e)}", exc_info=True)
        return {
            'task_id': task_id,
            'complete': True,
            'success': False,
            'progress': 100,
            'message': f'Error checking progress: {str(e)}',
            'error': str(e)
        }