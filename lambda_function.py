import json
import logging
import os
import time
from typing import Tuple, Union

import urllib3
from urllib3.filepost import encode_multipart_formdata

# Configure logging to see output in CloudWatch
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Best practice: load secrets and config from environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "<API-KEY-HERE>")
SONIOX_TOKEN = os.environ.get("SONIOX_TOKEN", "<API-KEY-HERE>")
ALLOW_LIST = os.environ.get("ALLOW_LIST", "delgod").split(",")

# Initialize a single PoolManager for connection pooling
http = urllib3.PoolManager()
soniox_headers = {"Authorization": f"Bearer {SONIOX_TOKEN}"}

# Constants for retry logic and message truncation
MAX_POLL_RETRIES = 24
POLL_RETRY_DELAY_S = 0.5
MAX_ERROR_LEN = 100


def send_reply(chat_id: int, message: str) -> bool:
    """Sends a reply message back to the user via the Telegram API."""
    logger.info(f"Sending reply to chat_id {chat_id}: '{message[:80]}...'")
    try:
        reply_payload = {"chat_id": chat_id, "text": message}
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        encoded_payload = json.dumps(reply_payload).encode("utf-8")
        response = http.request(
            "POST",
            url,
            body=encoded_payload,
            headers={"Content-Type": "application/json"},
        )
        return response.status < 400
    except Exception as e:
        logger.error(f"Failed to send reply to chat_id {chat_id}: {e}")
        return False


def poll_until_complete(transcription_id: str) -> str:
    """Polls Soniox API until transcription is complete, fails, or times out."""
    for _ in range(MAX_POLL_RETRIES):
        try:
            response = http.request(
                "GET",
                f"https://api.soniox.com/v1/transcriptions/{transcription_id}",
                headers=soniox_headers,
            )
            if response.status >= 400:
                logger.error(f"Polling failed with status {response.status}")
                return "Error polling transcription status"

            data = json.loads(response.data.decode("utf-8"))
            status = data.get("status")

            if status == "completed":
                return "completed"
            if status == "error":
                error_message = data.get("error_message", "Unknown transcription error")
                logger.error(f"Transcription failed: {error_message}")
                return error_message
        except urllib3.exceptions.MaxRetryError as e:
            logger.error(f"Network error during polling: {e}")
            return "Network error while polling transcription status"
        except Exception as e:
            logger.error(f"Unexpected error during polling: {e}")
            return "Failed to get transcription status"
        time.sleep(POLL_RETRY_DELAY_S)
    return "Transcription timed out"


def transcribe(file_content: bytes, file_type: str) -> str:
    """Orchestrates the file upload, transcription, and cleanup process."""
    file_id = None
    transcription_id = None

    try:
        # 1. Upload file to Soniox
        try:
            body, content_type = encode_multipart_formdata(
                {"file": ("file.dat", file_content, file_type)}
            )
            upload_headers = soniox_headers.copy()
            upload_headers["Content-Type"] = content_type
            response = http.request(
                "POST",
                "https://api.soniox.com/v1/files",
                body=body,
                headers=upload_headers,
            )
            if response.status >= 400:
                err = response.data.decode("utf-8")[:MAX_ERROR_LEN]
                return f"File upload failed with status {response.status}: {err}"
            file_id = json.loads(response.data.decode("utf-8")).get("id")
            if not file_id:
                return "Failed to get file_id from upload response"
        except (Exception, json.JSONDecodeError) as e:
            logger.error(f"Error during file upload: {e}")
            return f"File upload failed: {e}"

        # 2. Start transcription
        try:
            transcription_data = {
                "file_id": file_id,
                "model": "stt-async-preview",
                "language_hints": ["ru", "uk", "es", "en"],
            }
            json_headers = soniox_headers.copy()
            json_headers["Content-Type"] = "application/json"
            response = http.request(
                "POST",
                "https://api.soniox.com/v1/transcriptions",
                body=json.dumps(transcription_data),
                headers=json_headers,
            )
            if response.status >= 400:
                err = response.data.decode("utf-8")[:MAX_ERROR_LEN]
                return f"Transcription start failed with status {response.status}: {err}"
            transcription_id = json.loads(response.data.decode("utf-8")).get("id")
            if not transcription_id:
                return "Failed to get transcription_id from response"
        except (Exception, json.JSONDecodeError) as e:
            logger.error(f"Error starting transcription: {e}")
            return f"Transcription start failed: {e}"

        # 3. Poll for result
        poll_result = poll_until_complete(transcription_id)
        if poll_result != "completed":
            return f"Transcription failed: {poll_result}"

        # 4. Get transcript text
        try:
            response = http.request(
                "GET",
                f"https://api.soniox.com/v1/transcriptions/{transcription_id}/transcript",
                headers=soniox_headers,
            )
            if response.status >= 400:
                err = response.data.decode("utf-8")[:MAX_ERROR_LEN]
                return f"Transcript retrieval failed with status {response.status}: {err}"
            transcript_data = json.loads(response.data.decode("utf-8"))
            transcript_text = transcript_data.get("text", "")

            if not transcript_text:
                return "Transcription completed but no text was found"

            return f"Transcription: {transcript_text}"
        except Exception as e:
            logger.error(f"Error getting transcript text: {e}")
            return f"Transcript retrieval failed: {e}"

    finally:
        # 5. Clean up resources regardless of success or failure
        if transcription_id:
            try:
                http.request(
                    "DELETE",
                    f"https://api.soniox.com/v1/transcriptions/{transcription_id}",
                    headers=soniox_headers,
                )
                logger.info(f"Deleted transcription {transcription_id}")
            except Exception as e:
                logger.error(f"Failed to delete transcription {transcription_id}: {e}")
        if file_id:
            try:
                http.request(
                    "DELETE",
                    f"https://api.soniox.com/v1/files/{file_id}",
                    headers=soniox_headers,
                )
                logger.info(f"Deleted file {file_id}")
            except Exception as e:
                logger.error(f"Failed to delete file {file_id}: {e}")


def get_file(file_id: str) -> Tuple[int, Union[bytes, str]]:
    """Gets file path from Telegram and downloads the file content."""
    try:
        # First, get the file path from the file_id
        url1 = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
        response1 = http.request("GET", url1)
        if response1.status >= 400:
            return response1.status, response1.data.decode("utf-8")
        data = json.loads(response1.data.decode("utf-8"))
        remote_file_path = data.get("result", {}).get("file_path")
        if not remote_file_path:
            return 404, "File path not found in Telegram response"

        # Second, download the file from the path
        url2 = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{remote_file_path}"
        response2 = http.request("GET", url2)
        return response2.status, response2.data
    except (Exception, json.JSONDecodeError) as e:
        logger.error(f"Exception in get_file: {e}")
        return 500, f"An error occurred while getting the file: {e}"


def handle_media_message(message: dict) -> str:
    """Generic handler for voice, video, and video_note messages."""
    file_id = None
    file_type = "application/octet-stream"  # Default MIME type

    if "voice" in message:
        file_id = message.get("voice", {}).get("file_id")
        file_type = message.get("voice", {}).get("mime_type", "audio/ogg")
    elif "video" in message:
        file_id = message.get("video", {}).get("file_id")
        file_type = message.get("video", {}).get("mime_type", "video/mp4")
    elif "video_note" in message:
        file_id = message.get("video_note", {}).get("file_id")
        file_type = "video/mp4"  # video_note is always mp4
    else:
        return "Unsupported message type."

    if not file_id:
        return "Could not find a file_id in the message."

    response_code, file_content = get_file(file_id)
    if response_code != 200 or not isinstance(file_content, bytes):
        err = file_content if isinstance(file_content, str) else "Unknown error"
        return f"File download failed with code {response_code}: {err[:MAX_ERROR_LEN]}"

    return transcribe(file_content, file_type)


def lambda_handler(event, _):
    """Main AWS Lambda entry point."""
    chat_id = None
    try:
        logger.info("Received event")
        body = json.loads(event.get("body", "{}"))
        message = body.get("message")

        if not message:
            logger.warning("Event has no message body")
            return {"statusCode": 200, "body": "No message body"}

        chat_id = message.get("chat", {}).get("id")
        username = message.get("from", {}).get("username")

        if not chat_id or not username:
            logger.error(f"Missing chat_id or username in message: {message}")
            return {"statusCode": 400, "body": "Missing chat_id or username"}

        if username not in ALLOW_LIST:
            send_reply(chat_id, f"Sorry, user '{username}' is not authorized.")
            return {"statusCode": 200, "body": f"{username} is unauthorized"}

        reply_message = "Please send a voice, video, or video note for transcription."
        if "text" in message:
            reply_message = f"You sent text. {reply_message}"
        elif any(k in message for k in ["voice", "video", "video_note"]):
            reply_message = handle_media_message(message)

        success = send_reply(chat_id, reply_message)
        if not success:
            logger.warning("Failed to send reply message to user")

        return {"statusCode": 200, "body": json.dumps(reply_message)}

    except json.JSONDecodeError:
        logger.error("Received non-JSON event body")
        return {"statusCode": 400, "body": "Invalid JSON in request body"}
    except Exception as e:
        logger.error(f"Unhandled exception in lambda_handler: {e}", exc_info=True)
        if chat_id:
            send_reply(chat_id, "An unexpected error occurred. The administrator has been notified.")
        return {"statusCode": 500, "body": "Internal server error"}
