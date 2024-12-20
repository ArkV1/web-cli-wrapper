import logging
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

import whisper
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    """Simple container for transcription results."""
    success: bool
    transcript: Optional[str] = None
    segments: Optional[List[Dict]] = None
    error: Optional[str] = None

def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
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
    """Get transcript directly from YouTube."""
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

def download_audio(url: str, output_path: Path) -> None:
    """Download audio from YouTube video."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': str(output_path),
        'quiet': True,
        'no_warnings': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"Downloading audio from: {url}")
        ydl.download([url])
        logger.info(f"Successfully downloaded audio to: {output_path}")

# Cache Whisper models to avoid reloading
_whisper_models: Dict[str, whisper.Whisper] = {}

def get_whisper_model(model_name: str) -> whisper.Whisper:
    """Get or load a Whisper model."""
    if model_name not in _whisper_models:
        logger.info(f"Loading Whisper model: {model_name}")
        _whisper_models[model_name] = whisper.load_model(model_name)
        logger.info(f"Successfully loaded Whisper model: {model_name}")
    return _whisper_models[model_name]

def transcribe_with_whisper(video_id: str, language: str = 'en', model_name: str = 'base') -> TranscriptionResult:
    """Transcribe video using Whisper."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    temp_dir = None
    
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix='transcription_')
        audio_path = Path(temp_dir) / 'audio.mp3'
        
        # Download audio
        download_audio(url, audio_path)
        
        # Load model and transcribe
        model = get_whisper_model(model_name)
        logger.info(f"Starting Whisper transcription of {video_id}")
        
        result = model.transcribe(
            str(audio_path),
            language=language,
            task='transcribe'
        )
        
        # Convert segments to common format
        segments = [{
            'text': segment['text'],
            'start': segment['start'],
            'duration': segment['end'] - segment['start']
        } for segment in result['segments']]
        
        logger.info(f"Successfully transcribed video {video_id} with Whisper")
        return TranscriptionResult(
            success=True,
            transcript=result['text'],
            segments=segments
        )
        
    except Exception as e:
        error_msg = f"Failed to transcribe with Whisper: {str(e)}"
        logger.error(error_msg)
        return TranscriptionResult(success=False, error=error_msg)
        
    finally:
        # Clean up temporary directory
        if temp_dir and Path(temp_dir).exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to remove temporary directory {temp_dir}: {str(e)}")

def transcribe(url: str, method: str = 'youtube', language: str = 'en', model_name: str = 'base') -> TranscriptionResult:
    """
    Main transcription function that handles both YouTube and Whisper methods.
    
    Args:
        url: YouTube video URL
        method: 'youtube', 'whisper', or 'both'
        language: Target language code
        model_name: Whisper model name (only used if method includes Whisper)
    """
    video_id = extract_video_id(url)
    if not video_id:
        return TranscriptionResult(success=False, error="Invalid YouTube URL")

    if method == 'youtube':
        return get_youtube_transcript(video_id, language)
    elif method == 'whisper':
        return transcribe_with_whisper(video_id, language, model_name)
    elif method == 'both':
        # Get both transcripts
        yt_result = get_youtube_transcript(video_id, language)
        whisper_result = transcribe_with_whisper(video_id, language, model_name)
        
        # If both succeed, combine them
        if yt_result.success and whisper_result.success:
            return TranscriptionResult(
                success=True,
                transcript=whisper_result.transcript,  # Prefer Whisper's transcript
                segments=[
                    {'youtube': yt_result.segments, 'whisper': whisper_result.segments}
                ]
            )
        # If YouTube fails but Whisper succeeds, return Whisper
        elif whisper_result.success:
            return whisper_result
        # If YouTube succeeds but Whisper fails, return YouTube
        elif yt_result.success:
            return yt_result
        # If both fail, return error
        else:
            return TranscriptionResult(
                success=False,
                error=f"Both methods failed. YouTube: {yt_result.error}, Whisper: {whisper_result.error}"
            )
    else:
        return TranscriptionResult(success=False, error=f"Invalid method: {method}")
