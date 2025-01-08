# src/api_routes.py

from flask import Blueprint, request, jsonify, send_file
from flask_socketio import emit, join_room, leave_room
import uuid
from pathlib import Path
import subprocess
import os
import tempfile
import logging
import time

from .transcription_manager import TranscriptionManager
from .text_comparison import compare_texts

# Initialize a ThreadPoolExecutor for handling blocking operations
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

# Create a logger for this module
logger = logging.getLogger(__name__)

def register_api_routes(app, socketio, manager: TranscriptionManager):
    """
    Registers all API routes and SocketIO event handlers.
    """
    api = Blueprint('api', __name__)

    ######################################
    # Transcription Endpoint
    ######################################
    def background_transcription(task_id: str, url: str, method: str, model_name: str):
        """Background task for handling transcription."""
        try:
            logger.info(f"Starting transcription task {task_id}")
            
            # Create a progress callback that uses the application context
            def progress_callback(data):
                with app.app_context():
                    # Ensure data has task_id
                    if isinstance(data, dict):
                        data['task_id'] = task_id
                    else:
                        data = {'task_id': task_id, 'data': data}
                    
                    # Emit the progress update
                    socketio.emit('progress_update', data, room=task_id, namespace='/')
                    logger.debug(f"Emitted progress update for task {task_id}: {data}")
            
            # Send initial join request once
            with app.app_context():
                socketio.emit('join_request', {'task_id': task_id}, namespace='/')
                # Small delay to ensure client has time to join
                time.sleep(0.1)
            
            manager.process_transcription(
                task_id=task_id,
                url=url,
                method=method,
                model_name=model_name,
                progress_callback=progress_callback
            )
            logger.info(f"Transcription task {task_id} completed successfully.")
        except Exception as e:
            logger.exception(f"Error in background transcription task {task_id}: {str(e)}")
            with app.app_context():
                socketio.emit('progress_update', {
                    'task_id': task_id,
                    'progress': 100,
                    'complete': True,
                    'success': False,
                    'error': str(e)
                }, room=task_id, namespace='/')

    @api.route('/transcribe', methods=['POST'])
    def start_transcription():
        """
        Initiates a transcription task.
        Expects JSON payload with 'url', 'method', and 'model_name'.
        """
        try:
            data = request.get_json()
            if not data:
                logger.warning("Transcription request received with no data.")
                return jsonify({'success': False, 'error': 'No data provided'}), 400

            url = data.get('url')
            if not url:
                logger.warning("Transcription request missing URL.")
                return jsonify({'success': False, 'error': 'No URL provided'}), 400

            method = data.get('method', 'Both')  # Options: "YouTube", "Whisper", "Both"
            model_name = data.get('model_name', 'base')  # Default Whisper model

            task_id = str(uuid.uuid4())
            logger.info(f"Starting transcription task {task_id} for URL: {url}, Method: {method}, Model: {model_name}")

            # Start background task
            socketio.start_background_task(
                background_transcription, 
                task_id, 
                url, 
                method, 
                model_name
            )

            return jsonify({
                'success': True,
                'task_id': task_id,
                'message': 'Transcription started'
            }), 202

        except Exception as e:
            logger.exception(f"Error starting transcription: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @api.route('/transcribe-file', methods=['POST'])
    def transcribe_file():
        """
        Handles file upload and initiates transcription.
        Expects multipart/form-data with 'file' and 'model_name'.
        """
        try:
            if 'file' not in request.files:
                logger.warning("File upload request received with no file.")
                return jsonify({'success': False, 'error': 'No file provided'}), 400

            file = request.files['file']
            if not file or not file.filename:
                logger.warning("File upload request received with empty file.")
                return jsonify({'success': False, 'error': 'No file selected'}), 400

            model_name = request.form.get('model_name', 'base')
            task_id = str(uuid.uuid4())

            # Create temp directory if it doesn't exist
            temp_dir = Path('temp_audio')
            temp_dir.mkdir(exist_ok=True)

            # Save the uploaded file
            file_ext = Path(file.filename).suffix
            temp_path = temp_dir / f"{task_id}{file_ext}"
            file.save(temp_path)

            logger.info(f"Starting file transcription task {task_id} for file: {file.filename}, Model: {model_name}")

            # Start background task
            def background_file_transcription(task_id: str, file_path: Path, model_name: str):
                try:
                    logger.info(f"Starting file transcription task {task_id}")
                    
                    def progress_callback(data):
                        with app.app_context():
                            if isinstance(data, dict):
                                data['task_id'] = task_id
                            else:
                                data = {'task_id': task_id, 'data': data}
                            socketio.emit('progress_update', data, room=task_id, namespace='/')
                            logger.debug(f"Emitted progress update for task {task_id}: {data}")
                    
                    with app.app_context():
                        socketio.emit('join_request', {'task_id': task_id}, namespace='/')
                        time.sleep(0.1)
                    
                    manager.process_file_transcription(
                        task_id=task_id,
                        file_path=file_path,
                        model_name=model_name,
                        progress_callback=progress_callback
                    )
                    logger.info(f"File transcription task {task_id} completed successfully.")
                except Exception as e:
                    logger.exception(f"Error in background file transcription task {task_id}: {str(e)}")
                    with app.app_context():
                        socketio.emit('progress_update', {
                            'task_id': task_id,
                            'progress': 100,
                            'complete': True,
                            'success': False,
                            'error': str(e)
                        }, room=task_id, namespace='/')
                finally:
                    # Clean up the temporary file
                    try:
                        temp_path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete temporary file {temp_path}: {str(e)}")

            socketio.start_background_task(
                background_file_transcription,
                task_id,
                temp_path,
                model_name
            )

            return jsonify({
                'success': True,
                'task_id': task_id,
                'message': 'File transcription started'
            }), 202

        except Exception as e:
            logger.exception(f"Error starting file transcription: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    ######################################
    # PDF Conversion Endpoint
    ######################################
    @api.route('/convert-to-pdf', methods=['POST'])
    def convert_to_pdf():
        """
        Converts a webpage to PDF using a Node.js script.
        Expects JSON payload with 'url', 'orientation', 'zoom', and 'exclude'.
        """
        try:
            data = request.get_json()
            if not data:
                logger.warning("PDF conversion request received with no data.")
                return jsonify({'success': False, 'error': 'No data provided'}), 400

            url = data.get('url')
            orientation = data.get('orientation', 'auto')
            zoom = float(data.get('zoom', 100)) / 100
            exclude = data.get('exclude', '')

            if not url:
                logger.warning("PDF conversion request missing URL.")
                return jsonify({'success': False, 'error': 'No URL provided'}), 400

            # Generate unique filename
            filename = f"{uuid.uuid4()}.pdf"
            current_dir = Path(__file__).resolve().parent
            base_dir = current_dir.parent  # Go up one level from src/
            output_dir = current_dir / 'output'
            output_path = output_dir / filename
            script_dir = base_dir / 'scripts' / 'website-to-pdf'
            script_path = script_dir / 'convert.js'

            # Ensure directories exist
            output_dir.mkdir(parents=True, exist_ok=True)

            # Verify script exists
            if not script_path.exists():
                logger.error(f"PDF conversion script not found at {script_path}")
                return jsonify({'success': False, 'error': f"Script not found at {script_path}"}), 500

            # Verify node_modules exists
            node_modules_path = script_dir / 'node_modules'
            if not node_modules_path.exists():
                logger.error(f"Node modules not installed. Please run 'npm install' in {script_dir}")
                return jsonify({'success': False, 'error': f"Node modules not installed in {script_dir}"}), 500

            # Build command
            cmd = [
                'node',
                str(script_path),
                '--url', url,
                '--output', str(output_path),
                '--scale', str(zoom)
            ]

            if orientation == 'landscape':
                cmd.extend(['--landscape'])

            if exclude:
                cmd.extend(['--exclude', exclude])

            logger.info(f"Running PDF conversion command: {' '.join(cmd)}")

            # Function to run subprocess in executor
            def run_subprocess():
                process = subprocess.run(
                    cmd,
                    cwd=str(script_dir),
                    capture_output=True,
                    text=True,
                    check=True
                )
                return process

            # Offload subprocess.run to ThreadPoolExecutor
            future = executor.submit(run_subprocess)
            process = future.result()

            if process.returncode != 0:
                error_msg = process.stderr
                if "Cannot find module 'puppeteer'" in error_msg:
                    error_msg = f"Puppeteer not installed. Please run 'npm install puppeteer' in {script_dir}"
                logger.error(f"PDF conversion failed: {error_msg}")
                return jsonify({'success': False, 'error': f"Conversion failed: {error_msg}"}), 500

            # Verify the PDF was created
            if not output_path.exists():
                logger.error(f"PDF file was not created at {output_path}")
                return jsonify({'success': False, 'error': f"PDF file was not created at {output_path}"}), 500
            if output_path.stat().st_size == 0:
                logger.error("Downloaded PDF file is empty.")
                return jsonify({'success': False, 'error': "Downloaded PDF file is empty."}), 500

            logger.info(f"PDF conversion successful. File created at {output_path}")

            return jsonify({
                'success': True,
                'filename': filename,
                'path': str(output_path.relative_to(base_dir))
            }), 200

        except subprocess.CalledProcessError as e:
            logger.exception(f"Subprocess error during PDF conversion: {str(e)}")
            return jsonify({
                'success': False,
                'error': f"Conversion failed: {e.stderr}"
            }), 500
        except Exception as e:
            logger.exception(f"Error during PDF conversion: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    ######################################
    # Fetch Source Endpoint
    ######################################
    @api.route('/fetch-source', methods=['POST'])
    def fetch_source():
        """
        Fetches the source code of a webpage using a Node.js script.
        Expects JSON payload with 'url'.
        """
        try:
            data = request.get_json()
            if not data:
                logger.warning("Fetch source request received with no data.")
                return jsonify({'error': 'No data provided'}), 400

            url = data.get('url')
            if not url:
                logger.warning("Fetch source request missing URL.")
                return jsonify({'error': 'URL is required'}), 400

            # Generate unique filename
            filename = f"{uuid.uuid4()}.html"
            current_dir = Path(__file__).resolve().parent
            output_dir = current_dir / 'output'
            output_path = output_dir / filename
            script_dir = current_dir.parent / 'scripts' / 'website-to-src'
            script_path = script_dir / 'page-downloader.js'

            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            # Verify script exists
            if not script_path.exists():
                logger.error(f"Source downloader script not found at {script_path}")
                return jsonify({'error': f"Script not found at {script_path}"}), 500

            # Execute the page downloader script
            cmd = [
                'node',
                str(script_path),
                url,
                '--output', str(output_path)
            ]

            logger.info(f"Running source download command: {' '.join(cmd)}")

            # Function to run subprocess in executor
            def run_subprocess():
                process = subprocess.run(
                    cmd,
                    cwd=str(script_dir),
                    capture_output=True,
                    text=True
                )
                return process

            # Offload subprocess.run to ThreadPoolExecutor
            future = executor.submit(run_subprocess)
            process = future.result()

            if process.returncode != 0:
                logger.error(f"Source download failed: {process.stderr}")
                return jsonify({'error': f"Failed to download source: {process.stderr}"}), 500

            # Read the downloaded source code
            with open(output_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Clean up the file
            output_path.unlink()
            logger.info(f"Source code fetched successfully for URL: {url}")

            return jsonify({
                'success': True,
                'source': source_code
            }), 200

        except Exception as e:
            logger.exception(f"Error fetching source: {str(e)}")
            return jsonify({'error': str(e)}), 500

    ######################################
    # Serve PDF Endpoint
    ######################################
    @api.route('/output/<filename>', methods=['GET'])
    def serve_pdf(filename):
        """
        Serves the generated PDF file.
        """
        current_dir = Path(__file__).resolve().parent
        output_dir = current_dir / 'output'
        file_path = output_dir / filename

        try:
            # Prevent directory traversal attacks
            file_path = file_path.resolve()
            if not file_path.is_file() or not str(file_path).startswith(str(output_dir.resolve())):
                logger.warning(f"Attempted to access invalid file: {filename}")
                return jsonify({'error': 'Invalid filename'}), 400

            logger.info(f"Serving PDF file: {file_path}")
            return send_file(str(file_path), mimetype='application/pdf')

        except Exception as e:
            logger.exception(f"Error serving PDF file {filename}: {str(e)}")
            return jsonify({'error': 'File not found'}), 404

    ######################################
    # Compare Transcripts Endpoint
    ######################################
    @api.route('/compare-transcripts', methods=['POST'])
    def compare_transcripts():
        """
        Compares YouTube and Whisper transcripts.
        Expects JSON payload with 'youtube_transcript', 'whisper_transcript', and 'mode'.
        """
        try:
            data = request.get_json()
            if not data:
                logger.warning("Compare transcripts request received with no data.")
                return jsonify({'success': False, 'error': 'No data provided'}), 400

            youtube_transcript = data.get('youtube_transcript')
            whisper_transcript = data.get('whisper_transcript')
            mode = data.get('mode', 'inline')  # Modes could be 'inline', 'side-by-side', etc.

            if not youtube_transcript or not whisper_transcript:
                logger.warning("Compare transcripts request missing transcripts.")
                return jsonify({'success': False, 'error': 'Both transcripts are required'}), 400

            # Compare the texts using the specified mode
            comparison = compare_texts(youtube_transcript, whisper_transcript, mode=mode)
            logger.info("Transcripts compared successfully.")

            return jsonify({
                'success': True,
                'comparison': comparison
            }), 200

        except Exception as e:
            logger.exception(f"Error comparing transcripts: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    ######################################
    # Compare Texts Endpoint
    ######################################
    @api.route('/compare-texts', methods=['POST'])
    def compare_texts_api():
        """
        Compares two arbitrary texts.
        Expects JSON payload with 'text1', 'text2', and 'mode'.
        """
        try:
            data = request.get_json()
            if not data:
                logger.warning("Compare texts request received with no data.")
                return jsonify({'success': False, 'error': 'No data provided'}), 400

            text1 = data.get('text1', '')
            text2 = data.get('text2', '')
            mode = data.get('mode', 'side-by-side')  # Modes could be 'side-by-side', 'diff', etc.

            if not text1 or not text2:
                logger.warning("Compare texts request missing texts.")
                return jsonify({'success': False, 'error': 'Both texts are required'}), 400

            # Compare the texts using the specified mode
            comparison = compare_texts(text1, text2, mode=mode)
            logger.info("Texts compared successfully.")

            return jsonify({
                'success': True,
                'comparison': comparison
            }), 200

        except Exception as e:
            logger.exception(f"Error comparing texts: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    ######################################
    # SocketIO Event Handlers
    ######################################
    @socketio.on('join')
    def handle_join(data):
        """
        Handles client joining a specific room to receive progress updates.
        Expects 'task_id' in the data.
        """
        task_id = data.get('task_id')
        if task_id:
            join_room(task_id)
            emit('joined', {'message': f'Joined room for task {task_id}'})
            logger.debug(f"Client joined room: {task_id}")
        else:
            emit('error', {'error': 'task_id is required to join a room'})
            logger.warning("Client attempted to join room without task_id.")

    @socketio.on('leave')
    def handle_leave(data):
        """
        Handles client leaving a specific room.
        Expects 'task_id' in the data.
        """
        task_id = data.get('task_id')
        if task_id:
            leave_room(task_id)
            emit('left', {'message': f'Left room for task {task_id}'})
            logger.debug(f"Client left room: {task_id}")
        else:
            emit('error', {'error': 'task_id is required to leave a room'})
            logger.warning("Client attempted to leave room without task_id.")

    # Register the Blueprint
    app.register_blueprint(api, url_prefix='/api')
