from flask import Blueprint, request, jsonify, send_file
from flask_socketio import SocketIO
import logging
import uuid
from pathlib import Path
import subprocess
import os
import tempfile
from .transcription_manager import manager
from .text_comparison import compare_texts

logger = logging.getLogger(__name__)

def register_api_routes(app, socketio):
    def background_transcription(task_id: str, url: str, method: str, model_name: str, sid: str):
        """Background task for handling transcription"""
        def progress_callback(data):
            data['task_id'] = task_id
            socketio.emit('transcription_progress', data, room=sid)
        
        try:
            manager.process_transcription(
                task_id=task_id,
                url=url,
                method=method,
                model_name=model_name,
                progress_callback=progress_callback
            )
        except Exception as e:
            logger.error(f"Error in background transcription: {str(e)}", exc_info=True)
            socketio.emit('transcription_progress', {
                'task_id': task_id,
                'progress': 100,
                'complete': True,
                'success': False,
                'error': str(e)
            }, room=sid)

    @app.route('/api/transcribe', methods=['POST'])
    def start_transcription():
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'error': 'No data provided'}), 400
                
            url = data.get('url')
            if not url:
                return jsonify({'success': False, 'error': 'No URL provided'}), 400
                
            method = data.get('method', 'YouTube')
            model_name = data.get('model_name', 'base')
            sid = data.get('sid')
            
            task_id = str(uuid.uuid4())
            
            # Submit transcription task to thread pool
            manager._thread_pool.submit(
                background_transcription, 
                task_id, 
                url, 
                method, 
                model_name, 
                sid
            )
            
            return jsonify({
                'success': True,
                'task_id': task_id,
                'message': 'Transcription started'
            })
            
        except Exception as e:
            logger.error(f"Error starting transcription: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

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
        current_dir = Path(__file__).resolve().parent
        output_dir = current_dir / 'output'
        file_path = output_dir / filename

        try:
            file_path.resolve().relative_to(output_dir.resolve())
            if not file_path.exists():
                return jsonify({'error': 'File not found'}), 404
            return send_file(str(file_path), mimetype='application/pdf')
        except ValueError:
            return jsonify({'error': 'Invalid filename'}), 400

    @app.route('/api/compare-transcripts', methods=['POST'])
    def compare_transcripts():
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No data provided'
                }), 400

            youtube_transcript = data.get('youtube_transcript')
            whisper_transcript = data.get('whisper_transcript')
            mode = data.get('mode', 'inline')

            if not youtube_transcript or not whisper_transcript:
                return jsonify({
                    'success': False,
                    'error': 'Both transcripts are required'
                }), 400

            # Compare the texts using the specified mode
            comparison = compare_texts(youtube_transcript, whisper_transcript, mode=mode)

            return jsonify({
                'success': True,
                'comparison': comparison
            })

        except Exception as e:
            logger.error(f"Error comparing transcripts: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/compare-texts', methods=['POST'])
    def compare_texts_api():
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'No data provided'
                }), 400

            text1 = data.get('text1', '')
            text2 = data.get('text2', '')
            mode = data.get('mode', 'side-by-side')

            if not text1 or not text2:
                return jsonify({
                    'success': False,
                    'error': 'Both texts are required'
                }), 400

            comparison = compare_texts(text1, text2, mode=mode)

            return jsonify({
                'success': True,
                'comparison': comparison
            })

        except Exception as e:
            logger.error(f"Error comparing texts: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    # Register socket handlers
    from .socket_handlers import init_socket_handlers
    init_socket_handlers(socketio, manager)