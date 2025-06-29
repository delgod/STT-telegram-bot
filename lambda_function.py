import json
import time

import urllib3
from urllib3.filepost import encode_multipart_formdata

TELEGRAM_TOKEN = "<API-KEY-HERE>"
SONIOX_TOKEN = "<API-KEY-HERE>"
ALLOW_LIST = ["delgod"]

http = urllib3.PoolManager()
headers = {"Authorization": f"Bearer {SONIOX_TOKEN}"}


def poll_until_complete(transcription_id):
    retries = 24
    while retries > 0:
        response = http.request(
            "GET",
            f"https://api.soniox.com/v1/transcriptions/{transcription_id}",
            headers=headers,
        )
        data = json.loads(response.data.decode("utf-8"))
        if data["status"] == "completed":
            return "completed"
        if data["status"] == "error":
            return data.get("error_message", "Unknown error")
        retries -= 1
        time.sleep(0.5)
    return "Transcription timeout"


def transcribe(file_content, file_type):
    # Upload voice file
    body, content_type = encode_multipart_formdata(
        {
            "file": (
                "file",
                file_content,
                file_type,
            )
        }
    )
    upload_headers = headers.copy()
    upload_headers["Content-Type"] = content_type
    response = http.request(
        "POST", "https://api.soniox.com/v1/files", body=body, headers=upload_headers
    )
    if response.status >= 400:
        return f"HTTP {response.status} Error: {response.data.decode('utf-8')}"
    file_id = json.loads(response.data.decode("utf-8"))["id"]

    # Start transcription
    transcription_data = {
        "file_id": file_id,
        "model": "stt-async-preview",
        "language_hints": ["ru", "uk", "es", "en"],
    }
    json_headers = headers.copy()
    json_headers["Content-Type"] = "application/json"
    response = http.request(
        "POST",
        "https://api.soniox.com/v1/transcriptions",
        body=json.dumps(transcription_data),
        headers=json_headers,
    )
    if response.status >= 400:
        return f"HTTP {response.status} Error: {response.data.decode('utf-8')}"
    transcription_id = json.loads(response.data.decode("utf-8"))["id"]
    pool_result = poll_until_complete(transcription_id)
    if pool_result != "completed":
        return pool_result

    # Get the transcript text
    response = http.request(
        "GET",
        f"https://api.soniox.com/v1/transcriptions/{transcription_id}/transcript",
        headers=headers,
    )
    if response.status >= 400:
        return f"HTTP {response.status} Error: {response.data.decode('utf-8')}"
    result = "Transcription: " + json.loads(response.data.decode("utf-8"))["text"]

    # Delete the transcription
    http.request(
        "DELETE",
        f"https://api.soniox.com/v1/transcriptions/{transcription_id}",
        headers=headers,
    )

    # Delete the file
    http.request(
        "DELETE", f"https://api.soniox.com/v1/files/{file_id}", headers=headers
    )

    return result


def get_file(file_id):
    http = urllib3.PoolManager()
    url1 = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
    response1 = http.request("GET", url1)
    data = json.loads(response1.data.decode("utf-8"))
    if response1.status >= 400:
        return response1.status, response1.data.decode("utf-8")
    remote_file_path = data["result"]["file_path"]

    url2 = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{remote_file_path}"
    response2 = http.request("GET", url2)
    return response2.status, response2.data


def send_reply(chat_id, message):
    reply = {"chat_id": chat_id, "text": message}
    http = urllib3.PoolManager()
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    encoded_data = json.dumps(reply).encode("utf-8")
    http.request(
        "POST", url, body=encoded_data, headers={"Content-Type": "application/json"}
    )
    print(f"*** Reply : {encoded_data}")


def lambda_handler(event, _):
    print("*** Received event")
    body = json.loads(event["body"])
    chat_id = body["message"]["chat"]["id"]
    user_id = body["message"]["from"]["username"]

    if user_id not in ALLOW_LIST:
        return {"statusCode": 200, "body": json.dumps(f"{user_id} is unauthorized")}

    reply_message = "Reply to empty: " + json.dumps(body["message"])
    if "text" in body["message"]:
        message_text = body["message"]["text"]
        reply_message = f"Reply to text: {message_text}"

    if "voice" in body["message"]:
        file_id = body["message"]["voice"]["file_id"]
        file_type = body["message"]["voice"]["mime_type"]
        response_code, file_content = get_file(file_id)
        reply_message = f"HTTP {response_code} Error: {file_content[0:100]}"
        if response_code == 200:
            reply_message = transcribe(file_content, file_type)

    if "video" in body["message"]:
        file_id = body["message"]["video"]["file_id"]
        file_type = body["message"]["video"]["mime_type"]
        response_code, file_content = get_file(file_id)
        reply_message = f"HTTP {response_code} Error: {file_content[0:100]}"
        if response_code == 200:
            reply_message = transcribe(file_content, file_type)

    if "video_note" in body["message"]:
        file_id = body["message"]["video_note"]["file_id"]
        file_type = "video/mp4"
        response_code, file_content = get_file(file_id)
        reply_message = f"HTTP {response_code} Error: {file_content[0:100]}"
        if response_code == 200:
            reply_message = transcribe(file_content, file_type)

    send_reply(chat_id, reply_message)
    return {"statusCode": 200, "body": json.dumps(reply_message)}
