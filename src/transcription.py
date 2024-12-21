"""
YouTube Video Transcription Module

This module provides functionality to transcribe YouTube videos using two methods:
1. YouTube's built-in transcript API
2. OpenAI's Whisper speech-to-text model

The module supports various features including:
- Downloading audio from YouTube videos
- Extracting video IDs from different YouTube URL formats
- Progress tracking during transcription
- Temporary file management
- Multiple Whisper model options
"""

import logging
import tempfile
import shutil
from pathlib import Path
import os
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass
import random
import string
import time

import whisper
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import re

import sys
import io
from contextlib import contextmanager
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

# Set up logging configuration for tracking operations and debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize a process pool executor for transcription tasks
_process_pool = ProcessPoolExecutor(max_workers=1)

# Create a dedicated process pool for Whisper transcription
_whisper_process_pool = ProcessPoolExecutor(
    max_workers=1,  # Use a single worker to avoid memory issues
    mp_context=multiprocessing.get_context('spawn')  # Use spawn for better stability
)

def get_random_string(length: int) -> str:
    """Generate a random string of fixed length."""
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

# Create a temporary directory for storing downloaded audio files
# This directory will be used for all temporary operations
TEMP_DIR = Path(tempfile.gettempdir()) / 'transcriptions'
TEMP_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class TranscriptionResult:
    """
    Data class to store transcription results and metadata.
    
    Attributes:
        success (bool): Whether the transcription was successful
        transcript (Optional[str]): The full text transcript if successful
        segments (Optional[List[Dict]]): Time-aligned segments of the transcript
        error (Optional[str]): Error message if transcription failed
        in_progress (bool): Whether the transcription is still in progress
    """
    success: bool
    transcript: str = ""
    segments: List[Dict] = None
    error: str = None
    in_progress: bool = False

    def __post_init__(self):
        if self.segments is None:
            self.segments = []

def extract_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.
    
    Supports multiple YouTube URL formats including:
    - Standard watch URLs (youtube.com/watch?v=...)
    - Short URLs (youtu.be/...)
    - Embed URLs (youtube.com/embed/...)
    - Shorts URLs (youtube.com/shorts/...)
    
    Args:
        url: The YouTube URL to extract the ID from
        
    Returns:
        Optional[str]: The video ID if found, None otherwise
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/shorts\/([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_transcript(video_id: str, language: str = 'en') -> TranscriptionResult:
    """
    Fetch transcript directly from YouTube's transcript API.
    
    This method attempts to retrieve the official transcript if available on YouTube.
    It's faster and more accurate than speech-to-text when available.
    
    Args:
        video_id: YouTube video identifier
        language: Desired transcript language code (default: 'en')
        
    Returns:
        TranscriptionResult: Contains transcript text and segments if successful
    """
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        transcript_text = ' '.join(line['text'] for line in transcript_list)
        
        logger.info(f"Successfully got YouTube transcript for video {video_id}")
        return TranscriptionResult(
            success=True,
            transcript=transcript_text,
            segments=transcript_list
        )
    except Exception as e:
        error_msg = f"Failed to get YouTube transcript: {str(e)}"
        logger.error(error_msg)
        return TranscriptionResult(success=False, error=error_msg)

def download_audio(url: str, output_path: Path, progress_callback=None):
    """Download audio from a YouTube video with progress tracking."""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(output_path).replace('.mp3', ''),  # yt-dlp will add extension
            'progress_hooks': [lambda d: _yt_dlp_progress_hook(d, progress_callback) if progress_callback else None],
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

def _yt_dlp_progress_hook(d: Dict, progress_callback: Optional[Callable] = None):
    """Process progress updates from yt-dlp and convert them to our format."""
    if d['status'] == 'downloading':
        try:
            # Extract progress information
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            
            if total > 0:
                progress = (downloaded / total) * 100
                speed = d.get('speed', 0)
                if speed:
                    speed_mb = speed / (1024 * 1024)  # Convert to MB/s
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
            # Continue even if progress reporting fails

# Cache to store loaded Whisper models to avoid reloading
_whisper_models: Dict[str, whisper.Whisper] = {}

@contextmanager
def capture_stdout():
    """Capture stdout while still allowing writes to the terminal."""
    stdout = sys.stdout
    stderr = sys.stderr
    output = io.StringIO()
    try:
        sys.stdout = CaptureOutput(output, stdout, 'stdout')
        sys.stderr = CaptureOutput(output, stderr, 'stderr')
        yield output
    finally:
        sys.stdout = stdout
        sys.stderr = stderr

class CaptureOutput:
    """Custom output capture that writes to both a string buffer and terminal."""
    def __init__(self, string_buffer, terminal, name='unknown'):
        self.string_buffer = string_buffer
        self.terminal = terminal
        self.name = name
        
    def write(self, text):
        if text.strip():
            logger.debug(f"[{self.name}] Captured output: {text.strip()}")
        self.string_buffer.write(text)
        self.terminal.write(text)
        
    def flush(self):
        self.string_buffer.flush()
        self.terminal.flush()

def parse_whisper_progress(text: str) -> Optional[Dict]:
    """
    Parse Whisper's download progress output.
    Handles various progress formats including tqdm progress bars.
    """
    if not text:
        return None
        
    # Look for tqdm-style progress bar
    # Example: " 25%|#########4            | 731M/2.88G [00:13<00:37, 61.5MiB/s]"
    tqdm_pattern = r'(\d+)%\|[█▏▎▍▌▋▊▉#\s]+\|\s*([0-9.]+[KMGT]?)(?:iB)?/([0-9.]+[KMGT]?)(?:iB)?\s*\[([0-9:]+)<([0-9:]+),\s*([0-9.]+[KMGT]?[i]?B/s)\]'
    match = re.search(tqdm_pattern, text)
    if match:
        percent, current, total, elapsed, remaining, speed = match.groups()
        return {
            'percent': float(percent),
            'downloaded': current,
            'total': total,
            'speed': speed,
            'elapsed': elapsed,
            'eta': remaining,
            'download_speed': speed
        }
    
    # Look for completed tqdm progress bar
    completed_pattern = r'100%\|[█#]+\|\s*([0-9.]+[KMGT]?)(?:iB)?/([0-9.]+[KMGT]?)(?:iB)?\s*\[([0-9:]+)<[0-9:]+,\s*([0-9.]+[KMGT]?[i]?B/s)\]'
    match = re.search(completed_pattern, text)
    if match:
        total, total_again, elapsed, speed = match.groups()
        return {
            'percent': 100.0,
            'downloaded': total,
            'total': total_again,
            'speed': speed,
            'elapsed': elapsed,
            'eta': '0',
            'download_speed': speed
        }
    
    return None

def format_progress_message(model_name: str, progress_info: Dict) -> str:
    """Format a user-friendly progress message for model downloads."""
    if not progress_info:
        return "Preparing model..."
        
    percent = progress_info.get('percent', 0)
    downloaded = progress_info.get('downloaded', '')
    total = progress_info.get('total', '')
    speed = progress_info.get('speed', '')
    
    if percent == 100:
        return "Loading model into memory..."
    elif percent > 0:
        # Format a clean progress message with all available information
        message = f"Downloading model... {percent:.0f}%"
        if speed:
            message += f" at {speed}"
        return message
    
    return "Preparing model..."

def get_whisper_model(model_name: str, progress_callback: Optional[Callable] = None) -> whisper.Whisper:
    """Get or download a Whisper model, with progress tracking."""
    if model_name in _whisper_models:
        return _whisper_models[model_name]

    latest_progress = {'percent': 0}
    
    with capture_stdout() as output:
        try:
            _whisper_models[model_name] = whisper.load_model(
                model_name,
                download_root=os.path.expanduser("~/.cache/whisper"),
                in_memory=True
            )
            
            # Process captured output for progress updates
            captured = output.getvalue()
            logger.debug(f"Captured output: {captured}")
            
            progress_lines = captured.split('\n')
            for line in progress_lines:
                if line.strip():
                    logger.debug(f"Processing line: {line.strip()}")
                    progress_info = parse_whisper_progress(line)
                    if progress_info:
                        logger.debug(f"Parsed progress info: {progress_info}")
                        # Update our tracking info
                        latest_progress.update(progress_info)
                        
                        # Scale progress to 30-60% range (model download phase)
                        scaled_progress = 30 + (latest_progress['percent'] * 0.3)
                        
                        # Construct progress message
                        message = format_progress_message(model_name, latest_progress)
                        
                        if progress_callback:
                            progress_callback({
                                'progress': scaled_progress,
                                'message': message,
                                'download_speed': latest_progress.get('download_speed'),
                                'eta': latest_progress.get('eta')
                            })
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {str(e)}")
            raise
    
    return _whisper_models[model_name]

def _load_whisper_model(model_name: str) -> Dict:
    """Helper function to load Whisper model in a separate process."""
    try:
        model = whisper.load_model(model_name)
        return {'success': True, 'model': model}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def _transcribe_in_process(audio_path: str, model_name: str, language: str) -> Dict:
    """Helper function to run transcription in a separate process."""
    try:
        # Load model in this process
        model_result = _load_whisper_model(model_name)
        if not model_result['success']:
            return {
                'success': False,
                'error': f"Failed to load Whisper model: {model_result['error']}"
            }
        
        model = model_result['model']
        
        # Run transcription with error handling
        try:
            result = model.transcribe(
                audio_path,
                language=language,
                task='transcribe'
            )
            return {
                'success': True,
                'text': result['text'],
                'segments': [{
                    'text': segment['text'],
                    'start': segment['start'],
                    'duration': segment['end'] - segment['start']
                } for segment in result['segments']]
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Whisper transcription error: {str(e)}"
            }
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to load Whisper model: {str(e)}"
        }

def transcribe_with_whisper(video_id: str, language: str = 'en', model_name: str = 'base', progress_callback=None) -> TranscriptionResult:
    """
    Transcribe a video using Whisper.
    """
    temp_dir = None
    try:
        # Create a temporary directory for this transcription
        temp_dir = TEMP_DIR / f"transcription_{get_random_string(8)}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created temporary directory: {temp_dir}")
        
        # Set up audio file path
        audio_path = temp_dir / "audio.mp3"
        logger.info(f"Will save audio to: {audio_path}")
        
        # Phase 1: Download audio (0-30%)
        if progress_callback:
            progress_callback({
                'progress': 0,
                'message': 'Downloading audio...',
                'download_speed': None,
                'eta': None
            })
            
        def audio_progress_callback(p):
            if progress_callback:
                progress_callback({
                    'progress': p['progress'] * 0.3,  # Scale to 0-30%
                    'message': f"Downloading audio... {p['progress']:.0f}%",
                    'download_speed': p.get('download_speed'),
                    'eta': p.get('eta')
                })

        # Get the video URL from video_id
        url = f"https://www.youtube.com/watch?v={video_id}"
        download_audio(url, audio_path, audio_progress_callback)
        
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found at {audio_path}")
        
        logger.info(f"Audio file exists and has size: {audio_path.stat().st_size} bytes")
        
        # Phase 2: Load/download model (30-60%)
        if progress_callback:
            progress_callback({
                'progress': 30,
                'message': 'Preparing model...',
                'download_speed': None,
                'eta': None
            })
        
        logger.info(f"Starting Whisper transcription of {video_id}")
        
        # Phase 3: Transcribe (60-100%)
        if progress_callback:
            progress_callback({
                'progress': 60,
                'message': 'Transcribing audio...',
                'download_speed': None,
                'eta': None
            })
        
        try:
            # Run transcription in a separate process without blocking
            future = _whisper_process_pool.submit(_transcribe_in_process, str(audio_path), model_name, language)
            
            # Create a monitoring thread to check progress and keep connection alive
            def monitor_transcription():
                try:
                    result = future.result(timeout=600)  # 10 minute timeout
                    if not result['success']:
                        raise Exception(result['error'])
                    
                    if progress_callback:
                        progress_callback({
                            'progress': 100,
                            'message': 'Transcription complete!',
                            'download_speed': None,
                            'eta': None
                        })
                    
                    logger.info(f"Successfully transcribed video {video_id} with Whisper")
                    return TranscriptionResult(
                        success=True,
                        transcript=result['text'],
                        segments=result['segments']
                    )
                except TimeoutError:
                    raise Exception("Transcription timed out after 10 minutes")
                except Exception as e:
                    raise Exception(f"Transcription failed: {str(e)}")
                finally:
                    # Clean up temporary files after transcription is complete
                    if temp_dir and temp_dir.exists():
                        try:
                            logger.info(f"Cleaning up temporary directory: {temp_dir}")
                            shutil.rmtree(temp_dir)
                            logger.info("Cleanup successful")
                        except Exception as e:
                            logger.warning(f"Failed to remove temporary directory {temp_dir}: {str(e)}")
            
            # Start monitoring in a separate thread
            from threading import Thread
            monitor_thread = Thread(target=monitor_transcription)
            monitor_thread.start()
            
            # Return immediately to not block the main thread
            return TranscriptionResult(
                success=True,
                transcript="",  # Will be updated when complete
                segments=[],
                in_progress=True
            )
            
        except Exception as e:
            raise Exception(f"Failed to start transcription: {str(e)}")

    except Exception as e:
        error_msg = f"Failed to transcribe with Whisper: {str(e)}"
        logger.error(error_msg)
        return TranscriptionResult(success=False, error=error_msg)

def transcribe(url: str, use_youtube: bool = True, use_whisper: bool = False, model_name: str = 'base', language: str = 'en', progress_callback=None) -> Dict:
    """
    Main transcription function that orchestrates the transcription process.
    
    This function can use either or both transcription methods:
    1. YouTube's built-in transcript API (faster, when available)
    2. Whisper speech-to-text (more reliable, works on all videos)
    
    The function will attempt the selected methods in order and return
    results from all successful transcriptions.
    
    Args:
        url: YouTube video URL
        use_youtube: Whether to try YouTube's transcript API (default: True)
        use_whisper: Whether to use Whisper transcription (default: False)
        model_name: Which Whisper model to use (default: 'base')
        language: Target language code (default: 'en')
        progress_callback: Optional function for progress updates
        
    Returns:
        Dict containing:
        - success: Whether any transcription method succeeded
        - youtube_transcript: YouTube transcript if available
        - whisper_transcript: Whisper transcript if requested
        - error: Error message if all methods failed
    """
    video_id = extract_video_id(url)
    if not video_id:
        return {'success': False, 'error': "Invalid YouTube URL"}

    youtube_result = None
    whisper_result = None
    error_messages = []
    methods_attempted = 0
    methods_succeeded = 0

    # Try YouTube's transcript API if requested
    if use_youtube:
        methods_attempted += 1
        if progress_callback:
            progress_callback({
                'progress': 0,
                'message': 'Checking for YouTube transcript...',
                'download_speed': None,
                'eta': None
            })
        yt_result = get_youtube_transcript(video_id, language)
        if yt_result.success:
            youtube_result = yt_result.transcript
            methods_succeeded += 1
        else:
            error_messages.append(yt_result.error)

    # Try Whisper transcription if requested
    if use_whisper:
        methods_attempted += 1
        if progress_callback:
            progress_callback({
                'progress': use_youtube and 30 or 0,
                'message': 'Starting Whisper transcription...',
                'download_speed': None,
                'eta': None
            })
        whisper_result_obj = transcribe_with_whisper(video_id, language, model_name, progress_callback)
        if whisper_result_obj.success:
            whisper_result = whisper_result_obj.transcript
            methods_succeeded += 1
        else:
            error_messages.append(whisper_result_obj.error)

    # Only mark as success if all attempted methods succeeded
    success = methods_succeeded == methods_attempted and (
        (use_youtube and youtube_result is not None) or not use_youtube
    ) and (
        (use_whisper and whisper_result is not None) or not use_whisper
    )

    if not success:
        return {
            'success': False,
            'error': ' | '.join(error_messages) or 'Not all requested transcription methods completed successfully'
        }

    # Return successful results
    return {
        'success': True,
        'youtube_transcript': youtube_result,
        'whisper_transcript': whisper_result
    }
