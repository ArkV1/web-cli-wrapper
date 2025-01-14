from flask import Blueprint, request, jsonify, render_template
from flask_socketio import emit, join_room, leave_room
import uuid
from pathlib import Path
import logging
from typing import List, Dict
import time

from .transcription_manager import TranscriptionManager

# Create a logger for this module
logger = logging.getLogger(__name__)

def register_queue_routes(app, socketio, manager: TranscriptionManager):
    """Registers all queue-related routes and SocketIO event handlers."""
    queue = Blueprint('queue', __name__)

    @queue.route('/queue', methods=['GET'])
    def queue_page():
        """Renders the queue interface page."""
        return render_template('queue.html')

    @queue.route('/api/queue/add-files', methods=['POST'])
    def add_files_to_queue():
        """
        Handle multiple file uploads for transcription.
        Expects multipart/form-data with:
        - files: Multiple video/audio files
        - model_name: Whisper model name
        """
        try:
            if 'files[]' not in request.files:
                return jsonify({'success': False, 'error': 'No files provided'}), 400

            files = request.files.getlist('files[]')
            if not files:
                return jsonify({'success': False, 'error': 'No files selected'}), 400

            # Check file count limit
            MAX_FILES = 100
            if len(files) > MAX_FILES:
                return jsonify({
                    'success': False, 
                    'error': f'Too many files. Maximum allowed is {MAX_FILES}'
                }), 400

            # Calculate total size
            total_size = sum(len(file.read()) for file in files)
            # Reset file pointers after reading
            for file in files:
                file.seek(0)

            # Check total size (e.g., 20GB limit)
            MAX_TOTAL_SIZE = 20 * 1024 * 1024 * 1024  # 20GB
            if total_size > MAX_TOTAL_SIZE:
                return jsonify({
                    'success': False,
                    'error': f'Total file size too large. Maximum allowed is 20GB'
                }), 400

            model_name = request.form.get('model_name', 'base')
            task_ids = []

            # Create temp directory if it doesn't exist
            temp_dir = Path('temp_audio')
            temp_dir.mkdir(exist_ok=True)

            # Process each file
            for file in files:
                if not file.filename:
                    continue

                # Check individual file size (e.g., 2GB limit)
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()
                file.seek(0)  # Reset pointer
                
                MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
                if file_size > MAX_FILE_SIZE:
                    continue  # Skip files that are too large

                task_id = str(uuid.uuid4())
                
                # Save the uploaded file
                file_ext = Path(file.filename).suffix
                temp_path = temp_dir / f"{task_id}{file_ext}"
                file.save(temp_path)

                # Store initial task state
                manager.update_progress(task_id, {
                    'task_id': task_id,
                    'filename': file.filename,
                    'model_name': model_name,
                    'status': 'pending',
                    'progress': 0,
                    'message': 'Queued',
                    'file_size': file_size,
                    'queued_at': time.strftime('%Y-%m-%d %H:%M:%S')
                })

                # Start transcription in background
                socketio.start_background_task(
                    background_file_transcription,
                    app, socketio, manager,
                    task_id, temp_path, model_name
                )
                task_ids.append(task_id)

            if not task_ids:
                return jsonify({
                    'success': False,
                    'error': 'No valid files were found to process'
                }), 400

            return jsonify({
                'success': True,
                'task_ids': task_ids,
                'message': f'Added {len(task_ids)} files to queue',
                'total_size': total_size,
                'skipped_files': len(files) - len(task_ids)
            }), 200

        except Exception as e:
            logger.exception("Error adding files to queue")
            return jsonify({'success': False, 'error': str(e)}), 500

    def background_file_transcription(app, socketio, manager, task_id, file_path, model_name):
        """Background task for handling file transcription."""
        try:
            logger.info(f"Starting file transcription task {task_id}")
            
            def progress_callback(data):
                with app.app_context():
                    data['task_id'] = task_id
                    # Update task status in manager
                    manager.update_progress(task_id, data)
                    # Emit updates
                    socketio.emit('progress_update', data, room=task_id, namespace='/')
                    socketio.emit('queue_update', data, room='queue', namespace='/')
            
            with app.app_context():
                socketio.emit('join_request', {'task_id': task_id}, namespace='/')
                time.sleep(0.1)
            
            result = manager.process_file_transcription(
                task_id=task_id,
                file_path=file_path,
                model_name=model_name,
                progress_callback=progress_callback
            )
            
            if result.get('success'):
                logger.info(f"File transcription task {task_id} completed successfully")
            else:
                logger.error(f"File transcription task {task_id} failed: {result.get('error')}")
            
        except Exception as e:
            logger.exception(f"Error in background file transcription task {task_id}")
            error_data = {
                'task_id': task_id,
                'status': 'failed',
                'progress': 100,
                'message': f'Error: {str(e)}',
                'error': str(e)
            }
            with app.app_context():
                manager.update_progress(task_id, error_data)
                socketio.emit('progress_update', error_data, room=task_id, namespace='/')
                socketio.emit('queue_update', error_data, room='queue', namespace='/')
        finally:
            # Clean up the temporary file
            try:
                Path(file_path).unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temporary file {file_path}: {str(e)}")

    @queue.route('/api/queue/add', methods=['POST'])
    def add_to_queue():
        """
        Add multiple URLs to the transcription queue.
        Expects JSON payload with:
        {
            'urls': [
                {'url': 'youtube_url', 'method': 'Both', 'model_name': 'base'},
                ...
            ]
        }
        """
        try:
            data = request.get_json()
            if not data or 'urls' not in data:
                return jsonify({'success': False, 'error': 'No URLs provided'}), 400

            urls: List[Dict] = data['urls']
            if not urls:
                return jsonify({'success': False, 'error': 'Empty URL list'}), 400

            task_ids = []
            for url_data in urls:
                url = url_data.get('url')
                if not url:
                    continue

                task_id = str(uuid.uuid4())
                method = url_data.get('method', 'Both')
                model_name = url_data.get('model_name', 'base')

                # Store initial task state in manager
                manager.update_progress(task_id, {
                    'task_id': task_id,
                    'url': url,
                    'method': method,
                    'model_name': model_name,
                    'status': 'pending',
                    'progress': 0,
                    'message': 'Queued'
                })

                # Start the transcription in background
                socketio.start_background_task(
                    background_transcription,
                    app, socketio, manager,
                    task_id, url, method, model_name
                )
                task_ids.append(task_id)

            return jsonify({
                'success': True,
                'task_ids': task_ids,
                'message': f'Added {len(task_ids)} tasks to queue'
            }), 200

        except Exception as e:
            logger.exception("Error adding tasks to queue")
            return jsonify({'success': False, 'error': str(e)}), 500

    @queue.route('/api/queue/status', methods=['GET'])
    def queue_status():
        """Get status of all tasks in the queue and completed results."""
        try:
            # Get current tasks in progress
            current_tasks = {task_id: task for task_id, task in manager.tasks.items()}
            
            # Count tasks by status
            status_counts = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0
            }
            
            for task in current_tasks.values():
                status = task.get('status', 'unknown')
                if status in status_counts:
                    status_counts[status] += 1
            
            # Get completed results
            completed_results = manager.get_all_results()
            
            return jsonify({
                'success': True,
                'current_tasks': current_tasks,
                'completed_results': completed_results,
                'queue_stats': status_counts
            }), 200
        except Exception as e:
            logger.exception("Error getting queue status")
            return jsonify({'success': False, 'error': str(e)}), 500

    @queue.route('/api/queue/result/<task_id>', methods=['GET'])
    def get_result(task_id):
        """Get the result of a specific task."""
        try:
            result = manager.get_transcription_result(task_id)
            if result:
                return jsonify({
                    'success': True,
                    'result': result
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Result not found'
                }), 404
        except Exception as e:
            logger.exception("Error getting task result")
            return jsonify({'success': False, 'error': str(e)}), 500

    @socketio.on('join_queue')
    def on_join_queue(data):
        """Client joins the queue room to receive updates about all tasks."""
        join_room('queue')
        logger.debug("Client joined queue room")

    @socketio.on('leave_queue')
    def on_leave_queue(data):
        """Client leaves the queue room."""
        leave_room('queue')
        logger.debug("Client left queue room")

    def background_transcription(app, socketio, manager, task_id, url, method, model_name):
        """Background task for handling transcription."""
        try:
            logger.info(f"Starting transcription task {task_id}")
            
            def progress_callback(data):
                with app.app_context():
                    data['task_id'] = task_id
                    socketio.emit('progress_update', data, room=task_id, namespace='/')
                    socketio.emit('queue_update', data, room='queue', namespace='/')
            
            with app.app_context():
                socketio.emit('join_request', {'task_id': task_id}, namespace='/')
                time.sleep(0.1)
            
            manager.process_transcription(
                task_id=task_id,
                url=url,
                method=method,
                model_name=model_name,
                progress_callback=progress_callback
            )
            logger.info(f"Transcription task {task_id} completed successfully")
            
        except Exception as e:
            logger.exception(f"Error in background transcription task {task_id}")
            with app.app_context():
                error_data = {
                    'task_id': task_id,
                    'progress': 100,
                    'status': 'failed',
                    'message': f'Error: {str(e)}',
                    'error': str(e)
                }
                socketio.emit('progress_update', error_data, room=task_id, namespace='/')
                socketio.emit('queue_update', error_data, room='queue', namespace='/')

    @queue.route('/api/queue/clear', methods=['POST'])
    def clear_queue():
        """Clear all completed and failed tasks from the queue."""
        try:
            cleared_count = 0
            # Get all tasks
            tasks = list(manager.tasks.items())
            
            # Remove completed and failed tasks
            for task_id, task in tasks:
                if task.get('status') in ['completed', 'failed']:
                    manager.tasks.pop(task_id, None)
                    cleared_count += 1
            
            # Also clear completed results from storage
            cleared_count += manager.clear_completed_results()
            
            return jsonify({
                'success': True,
                'cleared_count': cleared_count,
                'message': f'Cleared {cleared_count} tasks from the queue'
            }), 200
        except Exception as e:
            logger.exception("Error clearing queue")
            return jsonify({'success': False, 'error': str(e)}), 500

    # Register the Blueprint
    app.register_blueprint(queue) 