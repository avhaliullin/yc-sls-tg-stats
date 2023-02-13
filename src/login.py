from __future__ import annotations

import argparse

import yandexcloud
from telethon import TelegramClient
from telethon.sessions import StringSession
from yandex.cloud.lockbox.v1.secret_pb2 import Secret
from yandex.cloud.lockbox.v1.secret_service_pb2 import CreateSecretRequest, PayloadEntryChange, AddVersionRequest
from yandex.cloud.lockbox.v1.secret_service_pb2_grpc import SecretServiceStub

flag_parser = argparse.ArgumentParser()

flag_parser.add_argument("--tg-api-id", type=int, required=True)
flag_parser.add_argument("--tg-api-hash", type=str, required=True)
flag_parser.add_argument("--yc-folder-id", type=str, required=True)
flag_parser.add_argument("--yc-oauth", type=str, required=True)


def login():
    args = flag_parser.parse_args()
    yc_sdk = yandexcloud.SDK(token=args.yc_oauth)
    secret_id = create_secret(yc_sdk, args.yc_folder_id, args.tg_api_id, args.tg_api_hash)
    session = login_tg(args.tg_api_id, args.tg_api_hash)
    add_session_to_secret(yc_sdk, secret_id, session)
    print(f'Created secret id: {secret_id}')


def add_session_to_secret(yc_sdk, secret_id, session):
    client: SecretServiceStub = yc_sdk.client(SecretServiceStub)
    update_secret_op = client.AddVersion(AddVersionRequest(
        secret_id=secret_id,
        payload_entries=[PayloadEntryChange(
            key='session',
            text_value=session
        )]
    ))
    yc_sdk.wait_operation_and_get_result(update_secret_op)


def create_secret(yc_sdk, folder_id, api_id, api_hash):
    client: SecretServiceStub = yc_sdk.client(SecretServiceStub)
    create_secret_op = client.Create(CreateSecretRequest(
        folder_id=folder_id,
        name='tg-creds',
        version_payload_entries=[
            PayloadEntryChange(
                key='api-id',
                text_value=str(api_id)
            ),
            PayloadEntryChange(
                key='api-hash',
                text_value=api_hash
            ),
        ]
    ))
    create_secret_res = yc_sdk.wait_operation_and_get_result(
        create_secret_op,
        response_type=Secret
    )
    return create_secret_res.response.id


def login_tg(api_id, api_hash):
    with TelegramClient(session=StringSession(), api_id=api_id, api_hash=api_hash, request_retries=10) as client:
        return client.session.save()


if __name__ == '__main__':
    login()
