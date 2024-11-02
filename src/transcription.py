from youtube_transcript_api import YouTubeTranscriptApi

from youtube_transcript_api.formatters import TextFormatter
import yt_dlp
import whisper
import os
import re
from pathlib import Path
import logging
from difflib import SequenceMatcher

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

def get_youtube_transcript(video_id, language='en'):
    """Get transcript from YouTube video."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        formatter = TextFormatter()
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
        output_path = Path(output_dir) / '%(id)s.%(ext)s'
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
            info = ydl.extract_info(url, download=True)
            audio_path = Path(output_dir) / f"{info['id']}.mp3"
            return str(audio_path)
    except Exception as e:
        logger.error(f"Error downloading audio: {str(e)}")
        raise

def transcribe_audio(audio_path, model_name="base"):
    """Transcribe audio using OpenAI Whisper."""
    try:
        # Load the Whisper model
        model = whisper.load_model(model_name)
        
        # Transcribe the audio
        result = model.transcribe(audio_path)
        
        # Clean up the audio file
        try:
            os.remove(audio_path)
        except Exception as e:
            logger.warning(f"Failed to delete audio file: {str(e)}")
        
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

def start_transcription(url, use_whisper=False, language='en', model_name="base"):
    """Main function to handle transcription process."""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return {
                'success': False, 
                'error': 'Invalid YouTube URL',
                'complete': True  # Add complete flag
            }

        result = {
            'success': True,
            'transcript': None,
            'youtube_transcript': None,
            'whisper_transcript': None,
            'complete': True,  # Add complete flag
            'message': 'Transcription complete!'  # Add completion message
        }

        # Get YouTube transcript if requested or if both methods are used
        if not use_whisper or use_whisper == "Both":
            yt_result = get_youtube_transcript(video_id, language)
            if yt_result['success']:
                result['youtube_transcript'] = yt_result['transcript']
                if not use_whisper:  # If only YouTube method was requested
                    result['transcript'] = yt_result['transcript']

        # Get Whisper transcript if requested
        if use_whisper:
            temp_dir = Path('temp_audio')
            temp_dir.mkdir(exist_ok=True)
            
            try:
                audio_path = download_audio(url, temp_dir)
                whisper_result = transcribe_audio(audio_path, model_name)
                if whisper_result['success']:
                    result['whisper_transcript'] = whisper_result['transcript']
                    if use_whisper == "Whisper":  # If only Whisper method was requested
                        result['transcript'] = whisper_result['transcript']
            except Exception as e:
                if not result['youtube_transcript']:  # Only fail if we don't have any transcript
                    return {'success': False, 'error': f"Whisper transcription failed: {str(e)}"}

        return result

    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return {
            'success': False,
            'error': f"Transcription failed: {str(e)}",
            'complete': True  # Add complete flag even for errors
        }

def highlight_differences(text1, text2, mode='inline'):
    def tokenize(text):
        return re.findall(r'\w+|[^\w\s]', text.lower())

    words1, words2 = tokenize(text1), tokenize(text2)
    matcher = SequenceMatcher(None, words1, words2)
    result = []

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            result.extend(words1[i1:i2])
        elif op == 'delete':
            result.append('<span class="bg-red-200">')
            result.extend(words1[i1:i2])
            result.append('</span>')
        elif op == 'insert':
            result.append('<span class="bg-green-200">')
            result.extend(words2[j1:j2])
            result.append('</span>')
        elif op == 'replace':
            result.append('<span class="bg-red-200">')
            result.extend(words1[i1:i2])
            result.append('</span>')
            result.append('<span class="bg-green-200">')
            result.extend(words2[j1:j2])
            result.append('</span>')

    def reconstruct(tokens):
        reconstructed = []
        capitalize_next = True
        for token in tokens:
            if token in ('.', '!', '?'):
                capitalize_next = True
            elif re.match(r'\w', token):
                if capitalize_next:
                    token = token.capitalize()
                    capitalize_next = False
                if reconstructed and reconstructed[-1] not in (' ', "'"):
                    reconstructed.append(' ')
            reconstructed.append(token)
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
                result1.append('<span class="bg-red-200">')
                result1.extend(words1[i1:i2])
                result1.append('</span>')
            elif op == 'insert':
                result2.append('<span class="bg-green-200">')
                result2.extend(words2[j1:j2])
                result2.append('</span>')
            elif op == 'replace':
                result1.append('<span class="bg-red-200">')
                result1.extend(words1[i1:i2])
                result1.append('</span>')
                result2.append('<span class="bg-green-200">')
                result2.extend(words2[j1:j2])
                result2.append('</span>')
        return reconstruct(result1), reconstruct(result2)
