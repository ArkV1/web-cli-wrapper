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

from .yt_dlp_logger import YTDLPLogger

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
        }],
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'logger': YTDLPLogger()
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

    def write_update(update: Dict):
        with open(progress_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(update) + "\n")

    stdout_capture = io.StringIO()
    sys.stdout = stdout_capture

    try:
        try:
            model = whisper.load_model(model_name)
            original_tqdm = tqdm.tqdm

            def progress_callback(num_frames: int, total_frames: int):
                output = stdout_capture.getvalue()
                stdout_capture.truncate(0)
                stdout_capture.seek(0)
                pct = (num_frames / total_frames * 100) if total_frames else 0
                write_update({
                    "type": "progress",
                    "progress": pct,
                    "output": output
                })

            def custom_tqdm(*args, **kwargs):
                if args and hasattr(args[0], "__iter__"):
                    iterable = args[0]
                    total = len(iterable) if hasattr(iterable, "__len__") else None

                    def generator():
                        for i, item in enumerate(iterable):
                            progress_callback(i, total)
                            yield item
                    return generator()
                else:
                    return original_tqdm(*args, **kwargs)

            # Patch tqdm so we intercept progress
            tqdm.tqdm = custom_tqdm

            # Do the transcription
            result = model.transcribe(audio_path, verbose=verbose)

            # Restore original tqdm
            tqdm.tqdm = original_tqdm

            # Any leftover console output
            final_output = stdout_capture.getvalue()
            if final_output:
                write_update({"type": "output", "output": final_output})

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
            sys.stdout = sys.__stdout__

    except Exception as e:
        err_msg = str(e)
        # Log the error with stack trace
        logger.exception("Error in child transcription process")
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

        # A thread pool so you can offload process_transcription calls:
        self._thread_pool = ThreadPoolExecutor(max_workers=4)

        # A process pool for CPU-bound tasks
        self._process_pool = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

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

    def download_audio(self, url: str, output_path: Path, progress_cb: Optional[Callable]):
        """
        Download audio using yt_dlp, reporting progress to progress_cb.
        """
        try:
            import yt_dlp

            ydl_opts = get_yt_dlp_opts(str(output_path))
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug("Starting YouTube audio download: %s", url)
                ydl.download([url])
            if progress_cb:
                progress_cb({"progress": 100})
        except Exception as e:
            logger.exception("Error downloading audio from %s", url)
            raise

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
                progress_callback({"task_id": task_id, "progress": 0,
                                   "message": "Fetching YouTube transcript..."})
                youtube_result = self.get_youtube_transcript(vid_id)
                if youtube_result["success"] and method == "YouTube":
                    # We can return early
                    logger.info("YouTube transcript only method complete for task_id=%s", task_id)
                    progress_callback({
                        "task_id": task_id,
                        "progress": 100,
                        "complete": True,
                        "success": True,
                        "youtube_transcript": youtube_result["text"]
                    })
                    return

            if method in ["Whisper", "Both"]:
                temp_dir = Path(tempfile.mkdtemp(prefix="transcription_"))
                audio_path = temp_dir / "audio.mp3"

                start_progress = 30 if (youtube_result and youtube_result["success"]) else 0

                def dl_cb(data):
                    p = data.get("progress", 0)
                    scaled = start_progress + (p * 0.3)
                    # ephemeral in-memory update
                    self.update_progress(task_id, {
                        "progress": scaled, "message": "Downloading audio..."
                    })
                    progress_callback({
                        "task_id": task_id,
                        "progress": scaled,
                        "message": "Downloading audio...",
                        "download_speed": data.get("download_speed"),
                        "eta": data.get("eta")
                    })

                # Download the audio
                logger.debug("Downloading audio to %s for task_id=%s", audio_path, task_id)
                self.download_audio(url, audio_path, dl_cb)

                progress_callback({
                    "task_id": task_id,
                    "progress": start_progress + 30,
                    "message": "Starting transcription..."
                })
                self.update_progress(task_id, {
                    "progress": start_progress + 30,
                    "message": "Starting transcription..."
                })

                # We'll store the child's progress lines in this file
                progress_file = str(temp_dir / "progress.jsonl")

                # Spawn child process
                logger.debug("Spawning child process for Whisper transcription, task_id=%s", task_id)
                future = self._process_pool.submit(
                    _transcribe_in_process,
                    str(audio_path),
                    model_name,
                    False,
                    progress_file
                )

                last_pos = 0
                while not future.done():
                    # Read any new lines from progress_file
                    if os.path.exists(progress_file):
                        with open(progress_file, "r", encoding="utf-8") as f:
                            f.seek(last_pos)
                            for line in f:
                                update = json.loads(line)
                                if update["type"] == "progress":
                                    pct = update["progress"]
                                    scaled_progress = start_progress + 30 + (pct * 0.4)

                                    # ephemeral in-memory update
                                    self.update_progress(task_id, {
                                        "progress": scaled_progress, "message": "Transcribing..."
                                    })

                                    progress_callback({
                                        "task_id": task_id,
                                        "progress": scaled_progress,
                                        "message": "Transcribing...",
                                        "output": update.get("output", "")
                                    })
                                elif update["type"] == "output":
                                    progress_callback({
                                        "task_id": task_id,
                                        "output": update["output"]
                                    })
                                elif update["type"] == "error":
                                    logger.error("Child process error: %s", update["error"])
                                    progress_callback({
                                        "task_id": task_id,
                                        "error": update["error"]
                                    })
                            last_pos = f.tell()

                    # If using gevent, yield control
                    import gevent
                    gevent.sleep(0.1)

                # Retrieve final result
                result = future.result()
                if result["success"]:
                    logger.info("Transcription completed successfully, task_id=%s", task_id)
                    self.update_progress(task_id, {
                        "progress": 100, "message": "Complete"
                    })
                    progress_callback({
                        "task_id": task_id,
                        "progress": 100,
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
            self.update_progress(task_id, {
                "progress": 100, "message": "Error", "error": str(e)
            })
            progress_callback({
                "task_id": task_id,
                "progress": 100,
                "complete": True,
                "success": False,
                "error": str(e)
            })
        finally:
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as ex:
                    logger.warning("Error cleaning up temp files in %s: %s", temp_dir, ex)


manager = TranscriptionManager()
