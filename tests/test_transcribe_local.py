import os
import sys
import unittest
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import transcribe_local as tl


class TestTranscribeLocal(unittest.TestCase):
    def setUp(self):
        """Set up test files and patch environment variables."""
        self.test_dir = Path("test_data")
        self.test_dir.mkdir(exist_ok=True)
        self.input_file = self.test_dir / "audio.mp3"
        self.output_file = self.test_dir / "audio.txt"
        # Use write_bytes for binary content simulation
        self.input_file.write_bytes(b"fake_audio_content")

        self.env_patcher = patch.dict(os.environ, {"SONIOX_TOKEN": "fake_soniox_token"})
        self.env_patcher.start()
        # Reload module to apply patched env vars
        if "lambda_function" in sys.modules:
            importlib.reload(sys.modules["lambda_function"])
        self.addCleanup(self.env_patcher.stop)

    def tearDown(self):
        """Clean up created files."""
        if self.input_file.exists():
            self.input_file.unlink()
        if self.output_file.exists():
            self.output_file.unlink()
        # Check if test_dir is empty before removing
        if self.test_dir.exists() and not any(self.test_dir.iterdir()):
            self.test_dir.rmdir()
        # Also remove the test_dir if it's not removed
        if self.test_dir.exists():
            try:
                self.test_dir.rmdir()
            except OSError:
                pass

    def test_detect_mime_type(self):
        """Test MIME type detection for a known file type."""
        self.assertEqual(tl.detect_mime_type(Path("test.mp3")), "audio/mpeg")
        # Accommodate different system MIME type databases
        self.assertIn(tl.detect_mime_type(Path("test.wav")), ["audio/wav", "audio/x-wav"])
        self.assertEqual(tl.detect_mime_type(Path("unknown")), "application/octet-stream")

    @patch("transcribe_local.transcribe")
    @patch("sys.exit")
    def test_main_success(self, mock_exit, mock_transcribe):
        """Test the main function for a successful transcription."""
        transcript = "This is a test transcription."
        mock_transcribe.return_value = f"Transcription: {transcript}"

        with patch.object(
            sys, "argv", ["prog_name", str(self.input_file), "-o", str(self.output_file)]
        ):
            tl.main()

        mock_transcribe.assert_called_once_with(b"fake_audio_content", "audio/mpeg")
        self.assertTrue(self.output_file.exists())
        self.assertEqual(self.output_file.read_text(encoding="utf-8"), transcript)
        mock_exit.assert_not_called()

    @patch("transcribe_local.transcribe")
    @patch("sys.exit")
    def test_main_transcription_fails(self, mock_exit, mock_transcribe):
        """Test the main function when transcription returns an error."""
        error_message = "API Error"
        mock_transcribe.return_value = error_message
        mock_exit.side_effect = SystemExit  # Mock exit to stop execution

        with patch.object(
            sys, "argv", ["prog_name", str(self.input_file), "-o", str(self.output_file)]
        ):
            with self.assertRaises(SystemExit):
                tl.main()

        self.assertFalse(self.output_file.exists())
        mock_exit.assert_called_once_with(1)

    @patch("sys.exit")
    def test_main_file_not_found(self, mock_exit):
        """Test the main function with a non-existent input file."""
        mock_exit.side_effect = SystemExit

        with patch.object(sys, "argv", ["prog_name", "non_existent_file.mp3"]):
            with self.assertRaises(SystemExit):
                tl.main()
        mock_exit.assert_called_once_with(1)

    @patch("pathlib.Path.write_text")
    @patch("transcribe_local.transcribe")
    @patch("sys.exit")
    def test_main_output_write_fails(self, mock_exit, mock_transcribe, mock_write):
        """Test the main function when writing the output file fails."""
        mock_transcribe.return_value = "Transcription: success"
        mock_write.side_effect = IOError("Permission denied")
        mock_exit.side_effect = SystemExit

        with patch.object(
            sys, "argv", ["prog_name", str(self.input_file), "-o", str(self.output_file)]
        ):
            with self.assertRaises(SystemExit):
                tl.main()
        mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main() 