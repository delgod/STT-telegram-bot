import json
import os
import unittest
import importlib
from unittest.mock import MagicMock, call, patch

import lambda_function as lf


class TestLambdaFunction(unittest.TestCase):
    def setUp(self):
        """Set up common test data and mock environment variables."""
        self.chat_id = 12345
        self.username = "testuser"
        self.file_id = "file_id_123"
        self.file_content = b"fake_audio_data"
        self.file_type = "audio/ogg"
        self.transcription_id = "trans_id_abc"
        self.soniox_file_id = "soniox_file_id_xyz"
        self.reply_message = "This is a reply."

        # Patch environment variables
        self.env_patcher = patch.dict(
            os.environ,
            {
                "TELEGRAM_TOKEN": "fake_telegram_token",
                "SONIOX_TOKEN": "fake_soniox_token",
                "ALLOW_LIST": self.username,
            },
        )
        self.env_patcher.start()
        # Reload the module to ensure it picks up the patched environment variables
        importlib.reload(lf)
        self.addCleanup(self.env_patcher.stop)

    @patch("lambda_function.http.request")
    def test_send_reply_success(self, mock_request):
        """Test successful message sending."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_request.return_value = mock_response

        result = lf.send_reply(self.chat_id, self.reply_message)

        self.assertTrue(result)
        url = f"https://api.telegram.org/botfake_telegram_token/sendMessage"
        payload = {"chat_id": self.chat_id, "text": self.reply_message}
        mock_request.assert_called_once_with(
            "POST",
            url,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    @patch("lambda_function.http.request")
    def test_send_reply_failure(self, mock_request):
        """Test message sending failure."""
        mock_request.side_effect = Exception("Network Error")
        result = lf.send_reply(self.chat_id, self.reply_message)
        self.assertFalse(result)

    @patch("time.sleep", return_value=None)
    @patch("lambda_function.http.request")
    def test_poll_until_complete_success(self, mock_request, _):
        """Test polling succeeds when status becomes 'completed'."""
        mock_response_pending = MagicMock()
        mock_response_pending.status = 200
        mock_response_pending.data = json.dumps({"status": "pending"}).encode("utf-8")

        mock_response_completed = MagicMock()
        mock_response_completed.status = 200
        mock_response_completed.data = json.dumps({"status": "completed"}).encode(
            "utf-8"
        )

        mock_request.side_effect = [mock_response_pending, mock_response_completed]
        result = lf.poll_until_complete(self.transcription_id)
        self.assertEqual(result, "completed")
        self.assertEqual(mock_request.call_count, 2)

    @patch("time.sleep", return_value=None)
    @patch("lambda_function.http.request")
    def test_poll_until_complete_error(self, mock_request, _):
        """Test polling when transcription results in an error."""
        mock_response_error = MagicMock()
        mock_response_error.status = 200
        mock_response_error.data = json.dumps(
            {"status": "error", "error_message": "Bad audio"}
        ).encode("utf-8")
        mock_request.return_value = mock_response_error

        result = lf.poll_until_complete(self.transcription_id)
        self.assertEqual(result, "Bad audio")

    @patch("time.sleep", return_value=None)
    @patch("lambda_function.http.request")
    def test_poll_until_complete_timeout(self, mock_request, _):
        """Test polling timeout after MAX_POLL_RETRIES."""
        mock_response_pending = MagicMock()
        mock_response_pending.status = 200
        mock_response_pending.data = json.dumps({"status": "pending"}).encode("utf-8")
        mock_request.return_value = mock_response_pending

        result = lf.poll_until_complete(self.transcription_id)
        self.assertEqual(result, "Transcription timed out")
        self.assertEqual(mock_request.call_count, lf.MAX_POLL_RETRIES)

    @patch("lambda_function.http.request")
    def test_get_file_success(self, mock_request):
        """Test successfully getting a file from Telegram."""
        remote_path = "path/to/file.ogg"
        mock_response_path = MagicMock()
        mock_response_path.status = 200
        mock_response_path.data = json.dumps(
            {"result": {"file_path": remote_path}}
        ).encode("utf-8")

        mock_response_content = MagicMock()
        mock_response_content.status = 200
        mock_response_content.data = self.file_content

        mock_request.side_effect = [mock_response_path, mock_response_content]

        status, content = lf.get_file(self.file_id)

        self.assertEqual(status, 200)
        self.assertEqual(content, self.file_content)
        mock_request.assert_has_calls(
            [
                call("GET", f"https://api.telegram.org/botfake_telegram_token/getFile?file_id={self.file_id}"),
                call("GET", f"https://api.telegram.org/file/botfake_telegram_token/{remote_path}"),
            ]
        )

    @patch("lambda_function.http.request")
    def test_get_file_path_fails(self, mock_request):
        """Test failure when getting file path from Telegram."""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.data = b"Not Found"
        mock_request.return_value = mock_response

        status, content = lf.get_file(self.file_id)

        self.assertEqual(status, 404)
        self.assertEqual(content, "Not Found")

    @patch("lambda_function.http.request")
    def test_get_file_download_fails(self, mock_request):
        """Test failure when downloading the file content."""
        remote_path = "path/to/file.ogg"
        mock_response_path = MagicMock()
        mock_response_path.status = 200
        mock_response_path.data = json.dumps(
            {"result": {"file_path": remote_path}}
        ).encode("utf-8")

        mock_response_content = MagicMock()
        mock_response_content.status = 500
        mock_response_content.data = b"Server Error"

        mock_request.side_effect = [mock_response_path, mock_response_content]

        status, content = lf.get_file(self.file_id)

        self.assertEqual(status, 500)
        self.assertEqual(content, b"Server Error")

    @patch("lambda_function.poll_until_complete")
    @patch("lambda_function.encode_multipart_formdata")
    @patch("lambda_function.http.request")
    def test_transcribe_success_and_cleanup(
        self, mock_request, mock_encode, mock_poll
    ):
        """Test successful transcription and resource cleanup."""
        mock_encode.return_value = (b"form-data", "multipart/form-data")
        mock_poll.return_value = "completed"
        transcript_text = "Hello world."

        mock_upload_resp = MagicMock(status=200, data=json.dumps({"id": self.soniox_file_id}).encode())
        mock_start_resp = MagicMock(status=200, data=json.dumps({"id": self.transcription_id}).encode())
        mock_transcript_resp = MagicMock(status=200, data=json.dumps({"text": transcript_text}).encode())
        mock_delete_resp = MagicMock(status=204)

        mock_request.side_effect = [
            mock_upload_resp,
            mock_start_resp,
            mock_transcript_resp,
            mock_delete_resp,
            mock_delete_resp,
        ]

        result = lf.transcribe(self.file_content, self.file_type)

        self.assertEqual(result, f"Transcription: {transcript_text}")
        mock_encode.assert_called_once_with({"file": ("file.dat", self.file_content, self.file_type)})
        mock_poll.assert_called_once_with(self.transcription_id)
        
        self.assertEqual(mock_request.call_count, 5)
        delete_calls = [c for c in mock_request.call_args_list if c.args[0] == "DELETE"]
        self.assertEqual(len(delete_calls), 2)
        self.assertIn(f"transcriptions/{self.transcription_id}", delete_calls[0].args[1])
        self.assertIn(f"files/{self.soniox_file_id}", delete_calls[1].args[1])

    @patch("lambda_function.http.request")
    def test_transcribe_upload_fails(self, mock_request):
        """Test transcription failure at file upload stage."""
        mock_request.return_value = MagicMock(status=500, data=b"Upload error")
        result = lf.transcribe(self.file_content, self.file_type)
        self.assertTrue(result.startswith("File upload failed"))
        # Ensure no cleanup calls were made if upload fails
        self.assertEqual(mock_request.call_count, 1)

    @patch("lambda_function.http.request")
    def test_transcribe_start_fails(self, mock_request):
        """Test transcription failure at start stage with cleanup."""
        mock_upload_resp = MagicMock(status=200, data=json.dumps({"id": self.soniox_file_id}).encode())
        mock_start_fail_resp = MagicMock(status=400, data=b"Bad request")
        mock_delete_file_resp = MagicMock(status=204)
        mock_request.side_effect = [mock_upload_resp, mock_start_fail_resp, mock_delete_file_resp]

        result = lf.transcribe(self.file_content, self.file_type)

        self.assertTrue(result.startswith("Transcription start failed"))
        self.assertEqual(mock_request.call_count, 3)
        self.assertEqual(mock_request.call_args_list[-1], call('DELETE', f'https://api.soniox.com/v1/files/{self.soniox_file_id}', headers=lf.soniox_headers))

    @patch("lambda_function.poll_until_complete")
    @patch("lambda_function.http.request")
    def test_transcribe_poll_fails(self, mock_request, mock_poll):
        """Test transcription failure during polling with cleanup."""
        mock_upload_resp = MagicMock(status=200, data=json.dumps({"id": self.soniox_file_id}).encode())
        mock_start_resp = MagicMock(status=200, data=json.dumps({"id": self.transcription_id}).encode())
        mock_delete_resp = MagicMock(status=204)
        mock_request.side_effect = [mock_upload_resp, mock_start_resp, mock_delete_resp, mock_delete_resp]
        mock_poll.return_value = "Polling error"

        result = lf.transcribe(self.file_content, self.file_type)

        self.assertEqual(result, "Transcription failed: Polling error")
        self.assertEqual(mock_request.call_count, 4)
        delete_calls = [c for c in mock_request.call_args_list if c.args[0] == "DELETE"]
        self.assertEqual(len(delete_calls), 2)

    @patch("lambda_function.handle_media_message")
    @patch("lambda_function.send_reply")
    def test_lambda_handler_media_message(self, mock_send_reply, mock_handle_media):
        """Test lambda_handler with a media message."""
        mock_handle_media.return_value = self.reply_message
        message_data = {
            "chat": {"id": self.chat_id},
            "from": {"username": self.username},
            "voice": {"file_id": self.file_id},
        }
        event = {"body": json.dumps({"message": message_data})}

        response = lf.lambda_handler(event, None)

        mock_handle_media.assert_called_once_with(message_data)
        mock_send_reply.assert_called_with(self.chat_id, self.reply_message)
        self.assertEqual(response["statusCode"], 200)

    @patch("lambda_function.send_reply")
    def test_lambda_handler_unauthorized(self, mock_send_reply):
        """Test lambda_handler with an unauthorized user."""
        event = {
            "body": json.dumps(
                {
                    "message": {
                        "chat": {"id": self.chat_id},
                        "from": {"username": "unauthorized_user"},
                        "text": "hello",
                    }
                }
            )
        }
        response = lf.lambda_handler(event, None)
        mock_send_reply.assert_called_with(
            self.chat_id, "Sorry, user 'unauthorized_user' is not authorized."
        )
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], "unauthorized_user is unauthorized")

    def test_lambda_handler_invalid_json(self):
        """Test lambda_handler with invalid JSON body."""
        event = {"body": "this is not json"}
        response = lf.lambda_handler(event, None)
        self.assertEqual(response["statusCode"], 400)

    @patch("lambda_function.get_file")
    @patch("lambda_function.transcribe")
    def test_handle_media_message_voice(self, mock_transcribe, mock_get_file):
        """Test handle_media_message for a voice message."""
        mock_get_file.return_value = (200, self.file_content)
        mock_transcribe.return_value = "Transcription successful"
        message = {
            "voice": {"file_id": self.file_id, "mime_type": "audio/ogg"},
        }
        result = lf.handle_media_message(message)

        mock_get_file.assert_called_with(self.file_id)
        mock_transcribe.assert_called_with(self.file_content, "audio/ogg")
        self.assertEqual(result, "Transcription successful")

    @patch("lambda_function.get_file")
    def test_handle_media_message_download_fail(self, mock_get_file):
        """Test handle_media_message when file download fails."""
        mock_get_file.return_value = (500, "Server error")
        message = {"video": {"file_id": self.file_id}}
        result = lf.handle_media_message(message)
        self.assertTrue(result.startswith("File download failed"))


if __name__ == "__main__":
    unittest.main() 