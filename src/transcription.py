from youtube_transcript_api import YouTubeTranscriptApi

from youtube_transcript_api.formatters import Formatter
import yt_dlp
import whisper
import os
import re
from pathlib import Path
import logging
from difflib import SequenceMatcher
import tempfile
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_video_id(url):
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

class PlainTextFormatter(Formatter):
    def format_transcript(self, transcript, **kwargs):
        return ' '.join(line['text'] for line in transcript)


def get_youtube_transcript(video_id, language='en'):
    """Get transcript from YouTube video."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        formatter = PlainTextFormatter()
        return {
            'success': True,
            'transcript': formatter.format_transcript(transcript_list),
            'segments': transcript_list
        }
    except Exception as e:
        logger.error(f"Error getting YouTube transcript: {str(e)}")
        return {
            'success': False,
            'error': f"Failed to get YouTube transcript: {str(e)}"
        }

def download_audio(url, output_dir):
    """Download audio from YouTube video."""
    try:
        # Ensure output directory exists
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Downloading audio to directory: {output_dir}")
        
        output_path = output_dir / '%(id)s.%(ext)s'
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(output_path),
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Starting YouTube download")
            info = ydl.extract_info(url, download=True)
            audio_path = output_dir / f"{info['id']}.mp3"
            
            if not audio_path.exists():
                raise FileNotFoundError(f"Failed to download audio file to {audio_path}")
            
            logger.info(f"Successfully downloaded audio: {audio_path}")
            logger.info(f"Audio file size: {audio_path.stat().st_size} bytes")
                
            return str(audio_path)
    except Exception as e:
        logger.error(f"Error downloading audio: {str(e)}")
        raise

def transcribe_audio(audio_path, model_name="base"):
    """Transcribe audio using OpenAI Whisper."""
    try:
        logger.info(f"Loading Whisper model: {model_name}")
        model = whisper.load_model(model_name)
        
        # Verify file exists
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        logger.info(f"Starting transcription of: {audio_path}")
        logger.info(f"Audio file size: {audio_path.stat().st_size} bytes")
        
        # Transcribe the audio
        try:
            result = model.transcribe(str(audio_path))
        except Exception as e:
            logger.error(f"Whisper transcription error: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            raise
        
        return {
            'success': True,
            'transcript': result['text'],
            'segments': result['segments']
        }
    except Exception as e:
        logger.error(f"Error transcribing audio: {str(e)}")
        return {
            'success': False,
            'error': f"Failed to transcribe audio: {str(e)}"
        }

def start_transcription(url, use_youtube=False, use_whisper=False, language='en', model_name="base"):
    """Handles the transcription process based on selected methods."""
    temp_dir = None
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {
                'success': False, 
                'error': 'Invalid YouTube URL',
                'complete': True
            }

        result = {
            'success': True,
            'youtube_transcript': None,
            'whisper_transcript': None,
            'complete': False,
            'message': 'Transcription in progress...'
        }

        # YouTube Transcription
        if use_youtube:
            yt_result = get_youtube_transcript(video_id, language)
            if yt_result['success']:
                result['youtube_transcript'] = yt_result['transcript']
            else:
                # Only fail if YouTube was the only method requested
                if not use_whisper:
                    return {
                        'success': False,
                        'error': yt_result['error'],
                        'complete': True
                    }

        # Whisper Transcription
        if use_whisper:
            try:
                # Create a temporary directory that will be automatically cleaned up
                temp_dir = tempfile.mkdtemp(prefix='transcription_')
                
                # Download and transcribe
                audio_path = download_audio(url, temp_dir)
                whisper_result = transcribe_audio(audio_path, model_name)
                
                if whisper_result['success']:
                    result['whisper_transcript'] = whisper_result['transcript']
                else:
                    # Only fail if Whisper was the only method requested
                    if not use_youtube or not result['youtube_transcript']:
                        return {
                            'success': False,
                            'error': whisper_result['error'],
                            'complete': True
                        }
                    
            except Exception as e:
                logger.error(f"Error in Whisper transcription: {str(e)}")
                if not use_youtube or not result['youtube_transcript']:
                    return {
                        'success': False,
                        'error': f"Whisper transcription failed: {str(e)}",
                        'complete': True
                    }

        # Check if at least one method succeeded
        if not result['youtube_transcript'] and not result['whisper_transcript']:
            return {
                'success': False,
                'error': 'Both transcription methods failed',
                'complete': True
            }

        result['complete'] = True
        result['message'] = 'Transcription complete!'
        return result

    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return {
            'success': False,
            'error': f"Transcription failed: {str(e)}",
            'complete': True
        }
    finally:
        # Clean up temporary directory if it exists
        if temp_dir and Path(temp_dir).exists():
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to remove temporary directory {temp_dir}: {str(e)}")


def highlight_differences(text1, text2, mode='inline'):
    def preprocess_text(text):
        # Normalize whitespace and convert to lowercase
        text = ' '.join(text.split())
        # Split into words while preserving punctuation
        return re.findall(r'\w+\'?\w*|[^\w\s]', text.lower())

    def smart_tokenize(text):
        # Handle contractions and compound words better
        tokens = preprocess_text(text)
        # Merge certain split tokens (e.g., don't, isn't, etc.)
        merged = []
        i = 0
        while i < len(tokens):
            if i + 2 < len(tokens) and tokens[i+1] == "'" and tokens[i+2] in ['t', 'll', 've', 're', 's']:
                merged.append(tokens[i] + "'" + tokens[i+2])
                i += 3
            else:
                merged.append(tokens[i])
                i += 1
        return merged

    words1, words2 = smart_tokenize(text1), smart_tokenize(text2)
    matcher = SequenceMatcher(None, words1, words2)
    result = []

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            result.extend(words1[i1:i2])
        elif op == 'delete':
            result.append('<span class="bg-red-200 px-1 rounded">')
            result.extend(words1[i1:i2])
            result.append('</span>')
        elif op == 'insert':
            result.append('<span class="bg-green-200 px-1 rounded">')
            result.extend(words2[j1:j2])
            result.append('</span>')
        elif op == 'replace':
            result.append('<span class="bg-red-200 px-1 rounded">')
            result.extend(words1[i1:i2])
            result.append('</span>')
            result.append('<span class="bg-green-200 px-1 rounded">')
            result.extend(words2[j1:j2])
            result.append('</span>')

    def reconstruct(tokens):
        reconstructed = []
        capitalize_next = True
        skip_space = False

        for token in tokens:
            if token.startswith('<span'):
                reconstructed.append(token)
                skip_space = False
            elif token.endswith('</span>'):
                reconstructed.append(token)
                skip_space = False
            elif token in '.!?':
                reconstructed.append(token)
                capitalize_next = True
                skip_space = False
            elif re.match(r'\w', token):
                if capitalize_next:
                    token = token.capitalize()
                    capitalize_next = False
                if not skip_space and reconstructed and not reconstructed[-1].endswith(('</span>', "'", "-")):
                    reconstructed.append(' ')
                reconstructed.append(token)
                skip_space = False
            else:
                reconstructed.append(token)
                skip_space = token in ["'", "-"]

        return ''.join(reconstructed)

    if mode == 'inline':
        return reconstruct(result)
    else:  # side-by-side mode
        result1, result2 = [], []
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == 'equal':
                result1.extend(words1[i1:i2])
                result2.extend(words2[j1:j2])
            elif op == 'delete':
                result1.append('<span class="bg-red-200 px-1 rounded">')
                result1.extend(words1[i1:i2])
                result1.append('</span>')
            elif op == 'insert':
                result2.append('<span class="bg-green-200 px-1 rounded">')
                result2.extend(words2[j1:j2])
                result2.append('</span>')
            elif op == 'replace':
                result1.append('<span class="bg-red-200 px-1 rounded">')
                result1.extend(words1[i1:i2])
                result1.append('</span>')
                result2.append('<span class="bg-green-200 px-1 rounded">')
                result2.extend(words2[j1:j2])
                result2.append('</span>')
        return reconstruct(result1), reconstruct(result2)
