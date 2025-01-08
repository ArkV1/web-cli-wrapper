# src/transcription_manager.py

"""
Transcription Manager Module (File-Based Progress + get_progress method)

Handles all aspects of transcription including:
- YouTube video processing
- Audio downloading
- Whisper transcription
- Progress tracking (via file-based polling)
- An optional get_progress() method that returns ephemeral task data
"""

import os
import json
import time
import tempfile
import shutil
import re
import threading
import multiprocessing
import logging
import warnings
from pathlib import Path
from typing import Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

import whisper
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

from src.loggers.yt_dlp_logger import YTDLPLogger

##############################################################################
# We'll create a spawn context for child processes, but avoid Manager-based IPC
##############################################################################
ctx = multiprocessing.get_context("spawn")

# Create a module-level logger
logger = logging.getLogger(__name__)

# Configure warning logging
logging.captureWarnings(True)
warnings_logger = logging.getLogger('py.warnings')

# Create a filter for torch warnings
class TorchWarningFilter(logging.Filter):
    def filter(self, record):
        return 'torch.load' in str(record.msg) or 'FP16' in str(record.msg)

# Add the filter to the warnings logger
warnings_logger.addFilter(TorchWarningFilter())

def get_yt_dlp_opts(output_path: str) -> dict:
    """Get yt-dlp options with proper logging configuration."""
    return {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': '%(id)s.%(ext)s',  # Use video ID as filename
        'paths': {'home': str(Path(output_path).parent)},  # Set download directory
        'quiet': False,
        'no_warnings': False,
        'logger': YTDLPLogger(),
        'progress_hooks': [],
        'verbose': True,
        'extract_flat': False,
        'retries': 3,
        'fragment_retries': 3,
        'skip_unavailable_fragments': False,
        'keepvideo': False,
        'writethumbnail': False,
        'postprocessor_args': [
            '-ar', '44100',
            '-ac', '2',
        ],
    }

def _transcribe_in_process(audio_path: str, model_name: str, verbose: bool,
                           progress_file: str) -> Dict:
    """
    Child process function to run Whisper. Writes JSON lines to progress_file
    for each progress update, leftover console output, or errors.
    """
    import io
    import sys
    import tqdm
    import builtins

    def write_update(update: Dict):
        with open(progress_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(update) + "\n")
            f.flush()  # Ensure it's written immediately

    # Create a custom stdout to capture all output
    class CustomStdout:
        def __init__(self):
            self.buffer = io.StringIO()
            self._last_text = None  # Track last text to prevent duplicates

        def write(self, text):
            if text.strip():  # Only process non-empty text
                # Only write if this is new text
                if text.strip() != self._last_text:
                    write_update({"type": "debug", "message": text.strip()})
                    self._last_text = text.strip()
            self.buffer.write(text)

        def flush(self):
            pass

        def getvalue(self):
            return self.buffer.getvalue()

        def truncate(self, *args, **kwargs):
            self.buffer.truncate(*args, **kwargs)

        def seek(self, *args, **kwargs):
            self.buffer.seek(*args, **kwargs)

    stdout_capture = CustomStdout()
    original_stdout = sys.stdout
    sys.stdout = stdout_capture

    try:
        try:
            write_update({"type": "debug", "message": "Loading Whisper model..."})
            model = whisper.load_model(model_name)
            write_update({"type": "debug", "message": "Model loaded, starting transcription..."})

            result = model.transcribe(
                audio_path,
                verbose=True,  # Force verbose to True
                condition_on_previous_text=False,  # Disable to ensure simpler output
                temperature=0  # Use greedy decoding for consistency
            )

            # Get any remaining output
            final_output = stdout_capture.getvalue()
            if final_output:
                write_update({"type": "debug", "message": f"Final captured output: {final_output}"})

            return {
                "success": True,
                "text": result["text"],
                "segments": [
                    {
                        "text": seg["text"],
                        "start": seg["start"],
                        "end": seg["end"]
                    }
                    for seg in result["segments"]
                ]
            }

        finally:
            # Restore original stdout
            sys.stdout = original_stdout

    except Exception as e:
        err_msg = str(e)
        write_update({"type": "debug", "message": f"Error in transcription: {err_msg}"})
        write_update({"type": "error", "error": err_msg})
        return {"success": False, "error": err_msg}


class TranscriptionManager:
    """
    Orchestrates YouTube downloads, Whisper transcriptions, and progress updates
    using a file-based approach to bypass manager-based queues.

    Also includes a ThreadPoolExecutor (`self._thread_pool`) so that external code
    (like api_routes.py) can do `manager._thread_pool.submit(...)` to run
    tasks in a background thread rather than blocking the request thread.

    We also keep a small in-memory `self.tasks` dict so we can store ephemeral
    progress, enabling a get_progress(task_id) method if needed.
    """
    def __init__(self, socketio=None):
        self._lock = threading.Lock()
        self.socketio = socketio

        # store ephemeral task states
        self.tasks: Dict[str, Dict] = {}

        # A thread pool so you can offload non-CPU-bound tasks:
        self._thread_pool = ThreadPoolExecutor(max_workers=4)

        # A process pool for CPU-bound tasks like Whisper transcription
        self._whisper_pool = ProcessPoolExecutor(max_workers=2, mp_context=ctx)

        # Ensure executors are shutdown gracefully
        import atexit
        atexit.register(self.shutdown)

    def shutdown(self):
        """Shutdown the executors gracefully."""
        self._whisper_pool.shutdown(wait=True)
        self._thread_pool.shutdown(wait=True)

    def update_progress(self, task_id: str, progress_data: dict):
        """Store ephemeral progress data in an in-memory dictionary."""
        with self._lock:
            self.tasks[task_id] = progress_data

    def get_progress(self, task_id: str) -> Optional[dict]:
        """
        Return ephemeral progress data if we want to support a 'check_progress' event.
        If not used, you can remove this method.
        """
        with self._lock:
            return self.tasks.get(task_id)

    def extract_video_id(self, url: str) -> Optional[str]:
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
        try:
            tx_list = YouTubeTranscriptApi.get_transcript(video_id)
            return {
                "success": True,
                "text": " ".join(item["text"] for item in tx_list),
                "segments": tx_list
            }
        except Exception as e:
            logger.warning("Could not retrieve YouTube transcript for video_id=%s: %s", video_id, e)
            return {"success": False, "error": str(e)}

    def process_file_transcription(
        self,
        task_id: str,
        file_path: Path,
        model_name: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Process a direct file upload for transcription.
        
        Args:
            task_id: Unique identifier for this transcription task
            file_path: Path to the uploaded file
            model_name: Name of the Whisper model to use
            progress_callback: Optional callback for progress updates
        
        Returns:
            Dict containing transcription results or error information
        """
        try:
            if progress_callback:
                progress_callback({
                    "progress": 0,
                    "message": "Starting transcription..."
                })

            # Create a temporary file for progress tracking
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as progress_file:
                progress_path = progress_file.name

                try:
                    # Run transcription in a separate process
                    future = self._whisper_pool.submit(
                        _transcribe_in_process,
                        str(file_path),
                        model_name,
                        True,  # verbose
                        progress_path
                    )

                    # Monitor progress file while transcription runs
                    last_progress = 0
                    while not future.done():
                        try:
                            with open(progress_path, 'r') as f:
                                lines = f.readlines()
                                for line in lines[last_progress:]:
                                    update = json.loads(line)
                                    if progress_callback:
                                        progress_callback(update)
                                last_progress = len(lines)
                        except Exception as e:
                            logger.warning(f"Error reading progress for task {task_id}: {e}")
                        time.sleep(0.1)

                    # Get the result
                    result = future.result()

                    if result.get("success"):
                        if progress_callback:
                            progress_callback({
                                "progress": 100,
                                "message": "Transcription complete",
                                "complete": True,
                                "success": True,
                                "whisper_result": result["text"],
                                "segments": result.get("segments", [])
                            })
                        return result
                    else:
                        error = result.get("error", "Unknown error during transcription")
                        if progress_callback:
                            progress_callback({
                                "progress": 100,
                                "message": f"Error: {error}",
                                "complete": True,
                                "success": False,
                                "error": error
                            })
                        return {"success": False, "error": error}

                finally:
                    # Clean up progress file
                    try:
                        os.unlink(progress_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete progress file {progress_path}: {e}")

        except Exception as e:
            error_msg = f"Error processing file transcription: {str(e)}"
            logger.exception(error_msg)
            if progress_callback:
                progress_callback({
                    "progress": 100,
                    "message": error_msg,
                    "complete": True,
                    "success": False,
                    "error": error_msg
                })
            return {"success": False, "error": error_msg}

    def download_audio(self, url: str, output_path: Path, progress_cb: Optional[Callable]):
        """
        Download audio using yt_dlp, reporting progress to progress_cb.
        """
        try:
            import yt_dlp
            import shlex
            import glob

            # Ensure URL is properly quoted
            safe_url = shlex.quote(url)
            
            ydl_opts = get_yt_dlp_opts(str(output_path))
            if progress_cb:
                ydl_opts['progress_hooks'] = [lambda d: self._yt_dlp_hook(d, progress_cb)]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug("Starting YouTube audio download: %s", safe_url)
                
                # First extract info to verify video is accessible
                try:
                    info = ydl.extract_info(url, download=True)  # Changed to download=True
                    if not info:
                        raise RuntimeError("Failed to extract video info")
                    
                    # The file will be named video_id.mp3 in the output directory
                    video_id = info['id']
                    expected_file = output_path.parent / f"{video_id}.mp3"
                    
                    # If the file exists, move it to the desired location
                    if expected_file.exists():
                        shutil.move(str(expected_file), str(output_path))
                    else:
                        # Look for any mp3 files in the directory
                        mp3_files = list(output_path.parent.glob("*.mp3"))
                        if mp3_files:
                            # Move the first mp3 file found to the desired location
                            shutil.move(str(mp3_files[0]), str(output_path))
                        else:
                            raise RuntimeError(f"Download completed but no MP3 file found in {output_path.parent}")
                    
                    # Final verification
                    if not output_path.exists():
                        raise RuntimeError(f"Failed to move audio file to {output_path}")
                    if output_path.stat().st_size == 0:
                        raise RuntimeError("Downloaded file is empty")
                    
                except yt_dlp.utils.DownloadError as e:
                    logger.error("yt-dlp download error: %s", str(e))
                    raise RuntimeError(f"Failed to download video: {str(e)}")
                
            if progress_cb:
                progress_cb({"progress": 100})
                
        except Exception as e:
            logger.exception("Error downloading audio from %s: %s", url, str(e))
            # Clean up any partially downloaded files
            try:
                if output_path.exists():
                    output_path.unlink()
                # Also clean up any intermediate files
                for f in output_path.parent.glob(f"*.mp3"):
                    f.unlink()
                for f in output_path.parent.glob(f"*.webm"):
                    f.unlink()
            except Exception as cleanup_error:
                logger.warning("Failed to clean up partial download: %s", str(cleanup_error))
            raise RuntimeError(f"Failed to download audio: {str(e)}")

    def _yt_dlp_hook(self, d: dict, cb: Optional[Callable]):
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            if total > 0:
                prog = (downloaded / total) * 100
                data = {"progress": prog}
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                if speed:
                    speed_mb = speed / (1024 * 1024)
                    data["download_speed"] = f"{speed_mb:.1f} MB/s"
                if eta:
                    data["eta"] = f"{eta}s"
                cb(data)

    def process_transcription(self, task_id: str, url: str, method: str,
                              model_name: str, progress_callback: Callable):
        """
        Main transcription logic:
          1) Optionally fetch YT transcript
          2) Download audio
          3) Spawn child process -> Whisper, writing progress to a file
          4) Poll that file for updates, pass them to progress_callback
        """
        temp_dir = None
        try:
            vid_id = self.extract_video_id(url)
            if not vid_id:
                logger.error("Invalid YouTube URL: %s", url)
                raise ValueError("Invalid YouTube URL")

            logger.debug("Started process_transcription, method=%s, task_id=%s", method, task_id)

            # Maybe fetch YouTube transcript
            youtube_result = None
            if method in ["YouTube", "Both"]:
                self._send_progress(task_id, progress_callback, 0, "Fetching YouTube transcript...")
                youtube_result = self.get_youtube_transcript(vid_id)
                if youtube_result["success"] and method == "YouTube":
                    # We can return early
                    logger.info("YouTube transcript only method complete for task_id=%s", task_id)
                    self._send_progress(task_id, progress_callback, 100, "Complete", 
                                      extra={"complete": True, "success": True, 
                                            "youtube_transcript": youtube_result["text"]})
                    return

            if method in ["Whisper", "Both"]:
                temp_dir = Path(tempfile.mkdtemp(prefix="transcription_"))
                audio_path = temp_dir / "audio.mp3"

                start_progress = 30 if (youtube_result and youtube_result["success"]) else 0

                def dl_cb(data):
                    p = data.get("progress", 0)
                    scaled = start_progress + (p * 0.3)
                    self._send_progress(task_id, progress_callback, scaled, "Downloading audio...",
                                      extra={"download_speed": data.get("download_speed"),
                                            "eta": data.get("eta")})

                # Download the audio
                logger.debug("Downloading audio to %s for task_id=%s", audio_path, task_id)
                self.download_audio(url, audio_path, dl_cb)

                self._send_progress(task_id, progress_callback, start_progress + 30, 
                                  "Starting transcription...")

                # We'll store the child's progress lines in this file
                progress_file = str(temp_dir / "progress.jsonl")

                # Submit transcription task to ProcessPoolExecutor
                logger.debug("Submitting transcription task to ProcessPoolExecutor, task_id=%s", task_id)
                future = self._whisper_pool.submit(
                    _transcribe_in_process,
                    str(audio_path),
                    model_name,
                    True,
                    progress_file
                )

                last_pos = 0
                last_progress_time = time.time()
                while not future.done():
                    # Read any new lines from progress_file
                    if os.path.exists(progress_file):
                        with open(progress_file, "r", encoding="utf-8") as f:
                            f.seek(last_pos)
                            for line in f:
                                if not line.strip():
                                    continue  # Skip empty lines
                                try:
                                    update = json.loads(line)
                                except json.JSONDecodeError as e:
                                    logger.warning("Malformed JSON line in progress_file: %s", line)
                                    continue

                                if update["type"] == "progress":
                                    pct = update["progress"]
                                    scaled_progress = start_progress + 30 + (pct * 0.4)
                                    
                                    # Send progress updates immediately
                                    extra_data = {
                                        "output": update.get("output", ""),
                                        "segments": update.get("segments", [])
                                    }
                                    self._send_progress(task_id, progress_callback, scaled_progress,
                                                      "Transcribing...", 
                                                      extra=extra_data)
                                        
                                elif update["type"] == "output":
                                    # Send output updates immediately
                                    self._send_progress(task_id, progress_callback, None, None,
                                                      extra={"output": update["output"]})
                                elif update["type"] == "debug":
                                    # Log debug messages immediately
                                    logger.debug("[Transcription Debug] %s", update["message"])
                                    # Also send to client immediately
                                    self._send_progress(task_id, progress_callback, None, None,
                                                      extra={"debug": update["message"]})
                                elif update["type"] == "error":
                                    logger.error("Child process error: %s", update["error"])
                                    self._send_progress(task_id, progress_callback, None, None,
                                                      extra={"error": update["error"]})
                            last_pos = f.tell()

                    # If using gevent, yield control
                    import gevent
                    gevent.sleep(0.5)  # Increased sleep time to reduce CPU usage

                # Retrieve final result
                result = future.result()
                if result["success"]:
                    logger.info("Transcription completed successfully, task_id=%s", task_id)
                    self._send_progress(task_id, progress_callback, 100, "Complete",
                                      extra={
                                          "complete": True,
                                          "success": True,
                                          "youtube_transcript": (
                                              youtube_result["text"] if (youtube_result and youtube_result["success"]) else None
                                          ),
                                          "whisper_transcript": result["text"],
                                          "segments": result["segments"]
                                      })
                else:
                    logger.error("Transcription failed for task_id=%s: %s", task_id, result.get("error"))
                    raise RuntimeError(result.get("error", "Transcription failed"))

        except Exception as e:
            logger.exception("Error in process_transcription (task_id=%s, url=%s)", task_id, url)
            self._send_progress(task_id, progress_callback, 100, "Error",
                              extra={"complete": True, "success": False, "error": str(e)})
        finally:
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as ex:
                    logger.warning("Error cleaning up temp files in %s: %s", temp_dir, ex)

    def _send_progress(self, task_id: str, callback: Callable, progress: Optional[float], 
                      message: Optional[str], extra: Optional[dict] = None):
        """Helper method to send progress updates with retry logic"""
        data = {"task_id": task_id}
        if progress is not None:
            data["progress"] = progress
        if message is not None:
            data["message"] = message
        if extra:
            data.update(extra)
            
        # Update in-memory state
        self.update_progress(task_id, data)
        
        # Log the progress data
        logger.debug("Sending progress update for task_id=%s: %s", task_id, data)
        
        # Try to send the update with retry logic
        max_retries = 3
        retry_delay = 1
        for attempt in range(max_retries):
            try:
                callback(data)
                logger.debug("Progress update sent successfully on attempt %d", attempt + 1)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("Failed to send progress update after %d attempts: %s", 
                               max_retries, str(e))
                else:
                    logger.warning("Failed to send progress update (attempt %d): %s", 
                                 attempt + 1, str(e))
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
