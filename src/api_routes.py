from flask import request, send_file, jsonify
import subprocess
import os
from pathlib import Path
import uuid
from threading import Thread, Lock
import time
import logging
from .transcription import start_transcription

# Configure the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def register_api_routes(app, socketio):
    # Store for tracking tasks with thread safety
    tasks_lock = Lock()

    # Initialize the transcription tasks dictionary
    transcription_tasks = {}

    def send_progress_update(task_id, progress, message, complete=False, success=True, error=None, transcript=None, youtube_transcript=None, whisper_transcript=None):
        socketio.emit('transcription_progress', {
            'task_id': task_id,
            'progress': progress,
            'message': message,
            'complete': complete,
            'success': success,
            'error': error,
            'transcript': transcript,
            'youtube_transcript': youtube_transcript,
            'whisper_transcript': whisper_transcript
        })

    def process_transcription(task_id, url, method, use_whisper, model_name):
        logger = logging.getLogger('websocket')
        try:
            with tasks_lock:
                transcription_tasks[task_id] = {
                    'progress': 0,
                    'message': 'Starting transcription...'
                }
            
            logger.info(f"Processing transcription: method={method}, use_whisper={use_whisper}")
            
            result = start_transcription(url, use_whisper=use_whisper, model_name=model_name)
            
            logger.info(f"Transcription result: {result}")  # Add debugging
            
            with tasks_lock:
                if result['success']:
                    task_data = {
                        'progress': 100,
                        'message': 'Transcription complete!',
                        'complete': True,
                        'success': True,
                        'youtube_transcript': result.get('youtube_transcript'),
                        'whisper_transcript': result.get('whisper_transcript')
                    }
                    transcription_tasks[task_id] = task_data
                    
                    # Send only one update
                    send_progress_update(
                        task_id=task_id,
                        progress=100,
                        message="Transcription complete!",
                        complete=True,
                        success=True,
                        youtube_transcript=result.get('youtube_transcript'),
                        whisper_transcript=result.get('whisper_transcript')
                    )
                else:
                    error_msg = result.get('error', 'Unknown error')
                    transcription_tasks[task_id] = {
                        'progress': 100,
                        'message': 'Transcription failed',
                        'complete': True,
                        'success': False,
                        'error': error_msg
                    }
                    send_progress_update(
                        task_id=task_id,
                        progress=100,
                        message="Transcription failed",
                        complete=True,
                        success=False,
                        error=error_msg
                    )
            
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}", exc_info=True)
            error_msg = str(e)
            with tasks_lock:
                transcription_tasks[task_id] = {
                    'progress': 100,
                    'message': f'Error: {error_msg}',
                    'complete': True,
                    'success': False,
                    'error': error_msg
                }
            send_progress_update(
                task_id=task_id,
                progress=100,
                message="Transcription failed",
                complete=True,
                success=False,
                error=error_msg
            )

    @app.route('/api/convert-to-pdf', methods=['POST'])
    def convert_to_pdf():
        try:
            data = request.json
            url = data.get('url')
            orientation = data.get('orientation', 'auto')
            zoom = float(data.get('zoom', 100)) / 100
            exclude = data.get('exclude', '')

            # Generate unique filename
            filename = f"{uuid.uuid4()}.pdf"
            
            # Get absolute paths using the current file's location
            current_dir = Path(__file__).resolve().parent
            base_dir = current_dir.parent  # Go up one level from src/
            output_dir = current_dir / 'output'
            output_path = output_dir / filename
            script_dir = base_dir / 'scripts' / 'website-to-pdf'
            script_path = script_dir / 'convert.js'

            print(f"Script path: {script_path}")  # Debug print
            print(f"Output path: {output_path}")  # Debug print

            # Ensure directories exist
            output_dir.mkdir(parents=True, exist_ok=True)

            # Verify script exists
            if not script_path.exists():
                raise FileNotFoundError(f"Script not found at {script_path}")

            # Verify node_modules exists
            node_modules_path = script_dir / 'node_modules'
            if not node_modules_path.exists():
                raise EnvironmentError(f"Node modules not installed. Please run 'npm install' in {script_dir}")

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

            # Execute conversion script from the script directory
            process = subprocess.run(
                cmd,
                cwd=str(script_dir),
                capture_output=True,
                text=True,
                check=True
            )

            if process.returncode != 0:
                error_msg = process.stderr
                if "Cannot find module 'puppeteer'" in error_msg:
                    error_msg = f"Puppeteer not installed. Please run 'npm install puppeteer' in {script_dir}"
                raise Exception(f"Conversion failed: {error_msg}")

            # Verify the PDF was created
            if not output_path.exists():
                raise FileNotFoundError(f"PDF file was not created at {output_path}")

            return jsonify({
                'success': True,
                'filename': filename,
                'path': str(output_path.relative_to(base_dir))
            })

        except subprocess.CalledProcessError as e:
            return jsonify({
                'success': False,
                'error': f"Conversion failed: {e.stderr}"
            }), 500
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/fetch-source', methods=['POST'])
    def fetch_source():
        try:
            data = request.json
            url = data.get('url')
            if not url:
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

            # Execute the page downloader script
            cmd = [
                'node',
                str(script_path),
                url,
                '--output', str(output_path)
            ]

            process = subprocess.run(
                cmd,
                cwd=str(script_dir),
                capture_output=True,
                text=True
            )

            if process.returncode != 0:
                return jsonify({
                    'error': f"Failed to download source: {process.stderr}"
                }), 500

            # Read the downloaded source code
            with open(output_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Clean up the file
            output_path.unlink()

            return jsonify({
                'success': True,
                'source': source_code
            })

        except Exception as e:
            return jsonify({
                'error': str(e)
            }), 500

    @app.route('/output/<filename>', methods=['GET'])
    def serve_pdf(filename):
        # Get absolute path to output directory
        current_dir = Path(__file__).resolve().parent
        output_dir = current_dir / 'output'
        file_path = output_dir / filename

        # Verify file exists and is within output directory
        try:
            file_path.resolve().relative_to(output_dir.resolve())
            if not file_path.exists():
                return jsonify({'error': 'File not found'}), 404
            return send_file(str(file_path), mimetype='application/pdf')
        except ValueError:
            return jsonify({'error': 'Invalid filename'}), 400

    @app.route('/api/transcribe', methods=['POST'])
    def transcribe():
        try:
            data = request.get_json()
            
            # Extract parameters
            url = data.get('url')
            method = data.get('method', 'YouTube')  # Get the method
            use_whisper = data.get('use_whisper', False)
            model_name = data.get('model_name', 'large')
            
            if not url:
                raise ValueError("URL is required")
                
            task_id = str(uuid.uuid4())
            
            # Log the received parameters
            logger.info(f"Starting transcription task {task_id}")
            logger.info(f"Parameters: method={method}, use_whisper={use_whisper}, model_name={model_name}")
            
            # Start transcription in background thread
            thread = Thread(
                target=process_transcription,
                args=(task_id, url, method, use_whisper, model_name)
            )
            thread.start()
            
            return jsonify({
                'success': True,
                'task_id': task_id
            })
            
        except Exception as e:
            logger.error(f"Failed to start transcription: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @socketio.on('check_progress')
    def handle_progress_check(data, sid=None):
        with tasks_lock:
            task_id = data.get('task_id')
            if task_id in transcription_tasks:
                task = transcription_tasks[task_id]
                socketio.emit('transcription_progress', {
                    'task_id': task_id,
                    'progress': task['progress'],
                    'message': task['message'],
                    'complete': task.get('complete', False),
                    'success': task.get('success', True),
                    'error': task.get('error'),
                    'transcript': task.get('transcript'),
                    'youtube_transcript': task.get('youtube_transcript'),
                    'whisper_transcript': task.get('whisper_transcript')
                }, room=sid)

