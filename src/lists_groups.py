from __future__ import annotations

import argparse
import asyncio
from typing import Optional

import yandexcloud
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import Channel, Chat
from yandex.cloud.lockbox.v1.payload_pb2 import Payload
from yandex.cloud.lockbox.v1.payload_service_pb2 import GetPayloadRequest
from yandex.cloud.lockbox.v1.payload_service_pb2_grpc import PayloadServiceStub

flag_parser = argparse.ArgumentParser()

flag_parser.add_argument("--tg-secret-id", type=str, required=True)
flag_parser.add_argument("--yc-oauth", type=str, required=True)

yc_sdk: yandexcloud.SDK = None


def _ask_group_idx(cur_idx: int, groups: list[Dialog]) -> tuple[int, Optional[int]]:
    choice: Optional = None
    for g in groups:
        cur_idx += 1
        chat: Channel | Chat = g.entity
        print(f'{cur_idx} - {chat.title}')
    raw_input = input('\nChoose a group by typing in its number or press "Enter" to load more: ')
    if raw_input.strip():
        choice = int(raw_input) - 1

    return cur_idx, choice


async def list_groups() -> None:
    args = flag_parser.parse_args()
    yc_sdk = yandexcloud.SDK(token=args.yc_oauth)
    secret_id = args.tg_secret_id
    lb_client: PayloadServiceStub = yc_sdk.client(PayloadServiceStub)
    secret: Payload = lb_client.Get(GetPayloadRequest(
        secret_id=secret_id
    ))
    api_hash = None
    api_id = None
    session = None
    for entry in secret.entries:
        if entry.key == 'api-id':
            api_id = entry.text_value
        elif entry.key == 'api-hash':
            api_hash = entry.text_value
        elif entry.key == 'session':
            session = entry.text_value

    async with TelegramClient(session=StringSession(session), api_id=api_id, api_hash=api_hash,
                              request_retries=10) as client:

        async for dialog in client.iter_dialogs():  # type: Dialog
            if not (dialog.is_group or dialog.is_channel):
                continue
            group = dialog.entity
            print(f'{group.title}: {group.id}')


if __name__ == '__main__':
    asyncio.run(
        list_groups()
    )
