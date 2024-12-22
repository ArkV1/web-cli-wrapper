import unittest
import sys
import io
from pathlib import Path
import os
import yt_dlp
import whisper

class TestWhisperTranscription(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create test directory if it doesn't exist
        cls.test_dir = Path(__file__).parent
        cls.test_audio = str(cls.test_dir / "test_audio.mp3")
        cls.model = whisper.load_model("tiny")
        
        # Download test audio if it doesn't exist
        if not os.path.exists(cls.test_audio):
            cls._download_test_audio()
    
    @classmethod
    def _download_test_audio(cls):
        url = "https://www.youtube.com/watch?v=WsFOcu-yHTY"
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': cls.test_audio.replace('.mp3', ''),
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def setUp(self):
        # Create a fresh output capture for each test
        self.captured_output = io.StringIO()
        self.original_stdout = sys.stdout
        sys.stdout = self.captured_output

    def tearDown(self):
        # Restore stdout after each test
        sys.stdout = self.original_stdout

    def test_whisper_default_no_verbose_param(self):
        """Test without specifying verbose parameter (default behavior)"""
        try:
            # Direct whisper transcription without verbose parameter
            result = self.model.transcribe(self.test_audio)
            
            output = self.captured_output.getvalue()
            
            print("\nWhisper Output (no verbose parameter):")
            print("-" * 40)
            print(output)
            print("-" * 40)
            
            # Save the output
            with open(os.path.join(self.test_dir, 'whisper_default_output.txt'), 'w') as f:
                f.write(output)
                
            print("\nTranscription Result:")
            print(result['text'][:200] + "...")
            
        except Exception as e:
            print(f"Error during transcription: {str(e)}")
            raise

    def test_whisper_verbose_false(self):
        """Test with verbose=False - should show tqdm progress bar"""
        try:
            result = self.model.transcribe(self.test_audio, verbose=False)
            
            output = self.captured_output.getvalue()
            
            print("\nWhisper Output with verbose=False:")
            print("-" * 40)
            print(output)
            print("-" * 40)
            
            with open(os.path.join(self.test_dir, 'whisper_non_verbose_output.txt'), 'w') as f:
                f.write(output)
                
            print("\nTranscription Result:")
            print(result['text'][:200] + "...")
            
        except Exception as e:
            print(f"Error during transcription: {str(e)}")
            raise

    def test_whisper_verbose_true(self):
        """Test with verbose=True - should show detailed output but no tqdm"""
        try:
            result = self.model.transcribe(self.test_audio, verbose=True)
            
            output = self.captured_output.getvalue()
            
            print("\nWhisper Output with verbose=True:")
            print("-" * 40)
            print(output)
            print("-" * 40)
            
            with open(os.path.join(self.test_dir, 'whisper_verbose_output.txt'), 'w') as f:
                f.write(output)
                
            print("\nTranscription Result:")
            print(result['text'][:200] + "...")
            
        except Exception as e:
            print(f"Error during transcription: {str(e)}")
            raise

if __name__ == '__main__':
    unittest.main() 