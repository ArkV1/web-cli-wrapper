"""
Transcription Manager Module

Handles all aspects of transcription including:
- YouTube video processing
- Audio downloading
- Whisper transcription
- Progress tracking
"""

import threading
from typing import Dict, Optional, Callable
import whisper
from pathlib import Path
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import time
import tempfile
import shutil
import re
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import gevent
import multiprocessing

logger = logging.getLogger(__name__)

def _transcribe_in_process(audio_path: str, model_name: str) -> Dict:
    """Process running in ProcessPoolExecutor - NO socket.io here"""
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(audio_path)
        return {
            'success': True,
            'text': result['text'],
            'segments': [{
                'text': segment['text'],
                'start': segment['start'],
                'end': segment['end']
            } for segment in result['segments']]
        }
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

class TranscriptionManager:
    def __init__(self):
        self.tasks = {}  # Store task status
        self._lock = threading.Lock()
        self._thread_pool = ThreadPoolExecutor(max_workers=4)

    def extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats."""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/shorts\/([^&\n?#]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_youtube_transcript(self, video_id: str) -> Dict:
        """Fetch transcript directly from YouTube's transcript API."""
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            return {
                'success': True,
                'text': ' '.join(item['text'] for item in transcript_list),
                'segments': transcript_list
            }
        except Exception as e:
            error_msg = f"Failed to get YouTube transcript: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def download_audio(self, url: str, output_path: Path, progress_callback: Optional[Callable] = None):
        """Download audio from a YouTube video with progress tracking."""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': str(output_path).replace('.mp3', ''),
                'progress_hooks': [lambda d: self._yt_dlp_progress_hook(d, progress_callback) 
                                 if progress_callback else None],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            if progress_callback:
                progress_callback({
                    'progress': 100,
                    'download_speed': None,
                    'eta': None
                })
                
        except Exception as e:
            logger.error(f"Error downloading audio: {str(e)}")
            raise

    def _yt_dlp_progress_hook(self, d: dict, progress_callback: Optional[Callable] = None):
        """Process progress updates from yt-dlp."""
        if d['status'] == 'downloading':
            try:
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                
                if total > 0:
                    progress = (downloaded / total) * 100
                    speed = d.get('speed', 0)
                    if speed:
                        speed_mb = speed / (1024 * 1024)
                        eta = d.get('eta', 0)
                        
                        progress_callback({
                            'progress': progress,
                            'download_speed': f"{speed_mb:.1f} MB/s",
                            'eta': f"{eta}s" if eta else None
                        })
                    else:
                        progress_callback({
                            'progress': progress,
                            'download_speed': None,
                            'eta': None
                        })
            except Exception as e:
                logger.warning(f"Error in progress hook: {str(e)}")

    def process_transcription(self, task_id: str, url: str, method: str, 
                            model_name: str, progress_callback: Callable):
        """Main transcription processing function."""
        temp_dir = None
        try:
            video_id = self.extract_video_id(url)
            if not video_id:
                raise ValueError("Invalid YouTube URL")

            # Try YouTube transcript if requested
            youtube_result = None
            if method in ['YouTube', 'Both']:
                progress_callback({
                    'task_id': task_id,
                    'progress': 0,
                    'message': 'Fetching YouTube transcript...'
                })
                
                youtube_result = self.get_youtube_transcript(video_id)
                if youtube_result['success']:
                    if method == 'YouTube':
                        progress_callback({
                            'task_id': task_id,
                            'progress': 100,
                            'complete': True,
                            'success': True,
                            'youtube_transcript': youtube_result['text']
                        })
                        return

            # Proceed with Whisper transcription if needed
            if method in ['Whisper', 'Both']:
                # Create temp directory
                temp_dir = Path(tempfile.mkdtemp(prefix='transcription_'))
                audio_path = temp_dir / 'audio.mp3'
                
                # Download audio with progress updates
                start_progress = 30 if youtube_result and youtube_result['success'] else 0
                
                def download_progress(progress_data):
                    progress = progress_data.get('progress', 0)
                    scaled_progress = start_progress + (progress * 0.3)
                    progress_callback({
                        'task_id': task_id,
                        'progress': scaled_progress,
                        'message': 'Downloading audio...',
                        'download_speed': progress_data.get('download_speed'),
                        'eta': progress_data.get('eta')
                    })

                self.download_audio(url, audio_path, download_progress)

                # Start Whisper transcription
                progress_callback({
                    'task_id': task_id,
                    'progress': start_progress + 30,
                    'message': 'Starting transcription...'
                })

                # Create a new process pool for this transcription
                with ProcessPoolExecutor(max_workers=1, 
                                      mp_context=multiprocessing.get_context('spawn')) as process_pool:
                    future = process_pool.submit(_transcribe_in_process, str(audio_path), model_name)

                    # Monitor transcription progress
                    while not future.done():
                        progress_callback({
                            'task_id': task_id,
                            'progress': start_progress + 50,
                            'message': 'Transcribing...'
                        })
                        gevent.sleep(3)

                    result = future.result()
                
                if result['success']:
                    progress_callback({
                        'task_id': task_id,
                        'progress': 100,
                        'complete': True,
                        'success': True,
                        'youtube_transcript': youtube_result['text'] if youtube_result and youtube_result['success'] else None,
                        'whisper_transcript': result['text']
                    })
                else:
                    raise Exception(result.get('error', 'Transcription failed'))

        except Exception as e:
            logger.error(f"Error in transcription process: {str(e)}", exc_info=True)
            progress_callback({
                'task_id': task_id,
                'progress': 100,
                'complete': True,
                'success': False,
                'error': str(e)
            })
        finally:
            # Cleanup
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.error(f"Error cleaning up temp files: {str(e)}")

    def update_progress(self, task_id: str, progress: dict):
        """Thread-safe progress update"""
        with self._lock:
            self.tasks[task_id] = progress
            
    def get_progress(self, task_id: str) -> Optional[dict]:
        """Thread-safe progress retrieval"""
        with self._lock:
            return self.tasks.get(task_id)

    def cleanup_task(self, task_id: str):
        """Remove task from tracking"""
        with self._lock:
            self.tasks.pop(task_id, None)

    def shutdown(self):
        """Cleanup resources"""
        self._thread_pool.shutdown(wait=True)

# Create a global instance
manager = TranscriptionManager()