import json
import lambda_tools
import Box
import io
import urllib
import logging
import hashlib
from lambda_tools import invoke
from lambda_tools import print_json
from lambda_tools import kms_decrypted
from lambda_tools import get_lambda_info


logging.getLogger('boxsdk').setLevel(logging.CRITICAL)
box_setting = {
    "client_id": kms_decrypted("BOX_CLIENT_ID"),
    "client_secret": kms_decrypted("BOX_CLIENT_SECRET"),
    "enterprise_id": kms_decrypted("BOX_ENTERPRISE_ID"),
    "jwt_key_id": kms_decrypted("BOX_JWT_KEY_ID") ,
    "rsa_private_key_data": kms_decrypted("BOX_PRIVATE_KEY")
}
box_folder_id = kms_decrypted("BOX_FOLDER_ID")
box_user = kms_decrypted("BOX_USER")
box_file = Box.File(**box_setting)
box_file.login(box_user)


def uploader(stream, length, name):
    try:
        if length <= 20000000:
            uploaded_file = box_file.upload(
                folder_id=box_folder_id, stream=io.BytesIO(stream.read()),
                name=name, overwrite=True
            )
            return uploaded_file.id, uploaded_file.name
        # Chunk upload
        session = box_file.client.folder(
            folder_id=box_folder_id
        ).create_upload_session(file_size=length, file_name=name)
        parts = []
        sha1 = hashlib.sha1()
        for part_index in range(session.total_parts):
            copied_length = 0
            chunk = b''
            while copied_length < session.part_size:
                buffer = stream.read(session.part_size - copied_length)
                if buffer is None:
                    continue
                if len(buffer) == 0:
                    break
                chunk += buffer
                copied_length += len(buffer)
                uploaded_part = session.upload_part_bytes(
                    chunk, part_index*session.part_size, length)
                parts.append(uploaded_part)
                updated_sha1 = sha1.update(chunk)
        content_sha1 = sha1.digest()
        uploaded_file = session.commit(
            content_sha1=content_sha1, parts=parts)
        return uploaded_file.id, uploaded_file.name
    except Exception as e:
        raise e


def downloader(url, headers):
    args = locals()
    req = urllib.request.Request(**args)
    try:
        res = urllib.request.urlopen(req)
        headers = res.headers
        contentLength = int(headers["Content-Length"])
        return res, contentLength
    except Exception as e:
        raise e


def transfer(file):
    nm = "{host}-{time}[{topic}({meeting_id})]_{recording_type}.{file_type}"
    name = nm.format(**file)
    url = file["download_url"]
    token = file["download_token"]
    headers = {"Authorization": "Bearer {}".format(token)}
    stream, length = downloader(url, headers)
    try:
        response = box_file.preflight(name, box_folder_id, length)
    except Exception as e:
        if e.code == "item_name_in_use":
            print_json({
                "type": "Box",
                "level": "warning",
                "message": "ファイルが既に存在します。",
                "name": name
            })
            return
        else:
            raise e
    print_json({
        "type": "lambda",
        "message": "Zoom Recording FileをBoxにアップロードします",
        "name": name,
        "size": length
    })
    id, filename = uploader(stream, length, name)
    print_json({
        "type": "lambda",
        "message": "Zoom Recording FileをBoxにアップロードしました",
        "name": filename,
        "id": id
    })


def main_function(data, context):
    payload = data["Payload"]
    del data["Payload"]
    event = payload["event"]
    if event != "recording.completed":
        return
    obj = payload["payload"]["object"]
    files = obj["recording_files"]

    for file in files:
        if file["file_type"] == "TIMELINE":
            continue
        file["meeting_uuid"] = file["meeting_id"]
        file["meeting_id"] = obj["id"]
        file["host"] = obj["host_email"]
        file["topic"] = obj["topic"]
        file["download_token"] = payload["download_token"]
        file["time"] = obj["start_time"]
        data["recording_file"] = file
        if lambda_tools.aws_request_id == "debug":
            lambda_handler(data, context)
        else:
            invoke(data)


def lambda_handler(event, context):
    get_lambda_info(context, "zoom-app-transfer_box")
    print_json({
        "type": "lambda",
        "message": "イベント受信",
        "payload": event,
    })
    try:
        lambda_tools.zoom_verification(event)
        if 'body' in event:
            event["Payload"] = json.loads(event['body'])
            del event["body"]
            print_json({
                "type": "lambda",
                "message": "Lambdaを再帰呼出しします",
            })
            if lambda_tools.aws_request_id == "debug":
                lambda_handler(event, context)
            else:
                invoke(event)
        elif "Payload" in event:
            main_function(event, context)
        elif "recording_file" in event:
            transfer(event["recording_file"])
        return {
            "isBase64Encoded": False,
            "statusCode": 200,
            "headers": {},
            "body": json.dumps({
                "message": "OK"
            }),
        }
    except Exception as e:
        print_json({
            "type": "lambda",
            "level": "error",
            "request-id": lambda_tools.aws_request_id,
            "message": str(e),
            "reason": lambda_tools.exception_fail(e)
        })
        return {
            "isBase64Encoded": False,
            "statusCode": 500,
            "headers": {},
            "body": json.dumps({
                "message": str(e)
            })
        }
