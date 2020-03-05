# -*- coding: utf-8 -*-
# import module snippets
import json
import boto3
import base64
import cfnresponse


def lambda_handler(event, context):
    print(json.dumps(event))
    try:
        params = dict([(k, v) for k, v in event['ResourceProperties'].items() if k != 'ServiceToken'])
        region = params.pop("region", "ap-northeast-1")
        client = boto3.client('kms', region_name=region)
        ret = client.encrypt(
            KeyId=params.get("KeyId"),
            Plaintext=params.get("Plaintext")
        )
        enc = ret["CiphertextBlob"]
        enc = base64.b64encode(enc).decode('utf-8')
        response_data = {
            "Value": enc
        }
        cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)
    except Exception as e:
        cfnresponse.send(event, context, cfnresponse.FAILED, {})
