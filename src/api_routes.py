from flask import jsonify, request, send_file
import subprocess
import os
from pathlib import Path
import uuid

def register_api_routes(app):
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
