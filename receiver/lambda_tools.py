# -*- coding: utf-8 -*-
import json
import boto3
import botocore
import base64
import re
import os
import sys
import traceback

aws_request_id = None
function_name = None


kms = boto3.client(
    'kms',
    region_name=os.environ.get("REGION", "ap-northeast-1")
)
ssm = boto3.client(
    'ssm',
    region_name=os.environ.get("REGION", "ap-northeast-1")
)
lambda_client = boto3.client(
    'lambda',
    region_name=os.environ.get("REGION", "ap-northeast-1")
)

def exception_fail(e):
    info = sys.exc_info()
    tbinfo = traceback.format_tb(info[2])
    exception_name = str(info[1])
    result = {}
    result["msg"] = exception_name
    result["trace"] = []
    for info in tbinfo:
        message = info.split("\n")
        temp = message[0].split(", ")
        del message[0]
        places = {
            "file": temp[0].replace("  File", ""),
            "line": temp[1].replace("line ", ""),
            "func": temp[2].replace("in ", ""),
            "trac": message
        }
        result["trace"].append(places)
    return result



def get_lambda_info(context, funcname_default):
    global function_name
    global aws_request_id
    if context is not None:
        if context.function_name == "test":
            aws_request_id = "debug"
            function_name = os.environ.get("FUNCTION_NAME", funcname_default)
        else:
            aws_request_id = context.aws_request_id
            function_name = context.function_name
    else:
        aws_request_id = "debug"
        function_name = os.environ.get("FUNCTION_NAME", funcname_default)


def print_json(message):
    if isinstance(message, str) or isinstance(message, list):
        message = {
            "level": "info",
            "message": message
        }
    if isinstance(message, dict):
        if "level" not in message:
            message["level"] = "info"

    message["request-id"] = aws_request_id
    if aws_request_id == "debug":
        print(json.dumps(message, ensure_ascii=False, indent=4))
    else:
        if message["level"] == "debug":
            return
        print(json.dumps(message, ensure_ascii=False))


def get_ssm_path(path_name: str, to_snake: bool = True):
    def key_replace(s):
        tmp = s.replace(path_name, "")
        if to_snake:
            tmp = re.sub("([A-Z])", lambda x: "_" + x.group(1).lower(), tmp)
            return tmp[1:]
        return tmp

    def decrypt(encrypted):
        try:
            blob = base64.b64decode(encrypted)
            decrypted = kms.decrypt(CiphertextBlob=blob)['Plaintext']
            return decrypted.decode('utf-8')
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidCiphertextException":
                return encrypted
            raise e
        except base64.binascii.Error as e:
            return encrypted
        except ValueError as e:
            return encrypted
        except Exception as e:
            return default

    data = ssm.get_parameters_by_path(Path=path_name)
    ret = dict()
    tree = objectpath.Tree(data)
    query = "$..Parameters.Name"
    keys = list(tree.execute(query))
    keys = list(map(key_replace, keys))

    query = "$..Parameters.Value"
    values = list(tree.execute(query))
    values = list(map(decrypt, values))

    for idx in range(len(keys)):
        key = keys[idx]
        value = values[idx]
        ret[key] = value
    return ret


def kms_decrypted(key, default=None):
    if key not in os.environ:
        return default
    ENCRYPTED = os.environ[key]
    try:
        blob = base64.b64decode(ENCRYPTED)
        DECRYPTED = kms.decrypt(CiphertextBlob=blob)['Plaintext']
        return DECRYPTED.decode('utf-8')
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "InvalidCiphertextException":
            return ENCRYPTED
        raise e
    except base64.binascii.Error as e:
        return ENCRYPTED
    except ValueError as e:
        return ENCRYPTED
    except Exception as e:
        return default


def invoke(payload: dict):
    """
    @brief      Lambdaの再帰処理
    """
    global function_name
    try:
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event',
            Payload=json.dumps(payload)
        )
    except Exception as e:
        raise e

def zoom_verification(event: dict):
    if "headers" not in event:
        raise Exception("header not found")
    if "Authorization" not in event["headers"]:
        raise Exception("Authorization header not found")

    authoriztion = event["headers"]["Authorization"]
    token = kms_decrypted("ZOOM_VERIFICATION_TOKEN")
    if authoriztion != token:
        raise Exception("Verification token was not match")
