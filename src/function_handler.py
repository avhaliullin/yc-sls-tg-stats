from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from logging.config import dictConfig

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import Channel, InputChannel

from ch_data_writer import CHDataWriter

_MESSAGES_AFTER: datetime.datetime = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
# > > > > > > > > >


with open('log-config.json') as f:
    dictConfig(json.loads(f.read()))

_LOGGER = logging.getLogger(__name__)


async def run(event, context) -> None:
    dialog_ids_str = os.environ.get('DIALOG_IDS')
    dialog_ids = set([int(dialog_id) for dialog_id in dialog_ids_str.split(',')])
    api_hash = os.environ.get('API_HASH')
    api_id = int(os.environ.get('API_ID'))
    session_str = os.environ.get('SESSION_STR')

    ch_writer = CHDataWriter(
        hostname=os.environ.get('CH_HOST'),
        login=os.environ.get('CH_USER'),
        password=os.environ.get('CH_PASS'),
        database=os.environ.get('CH_DB'),
        ca_cert=os.environ.get('CH_CA_CERT_PATH'),
    )

    async with TelegramClient(session=StringSession(session_str), api_id=api_id, api_hash=api_hash,
                              request_retries=10) as client:

        groups: list[Channel | InputChannel] = []

        async for dialog in client.iter_dialogs():  # type: Dialog
            _LOGGER.debug(f'Processing dialog with entity type {type(dialog.entity)}: {dialog}')
            if not (dialog.is_group or dialog.is_channel):
                _LOGGER.debug(f'Can not process chat: {dialog.title}')
                continue
            if dialog.entity.id in dialog_ids:
                groups.append(dialog.entity)

        tasks = list()
        for group in groups:
            tasks.append(ch_writer.write_messages(client, group, _MESSAGES_AFTER))
            tasks.append(ch_writer.write_participants(client, group))
        tasks.append(ch_writer.write_groups(groups))
        await asyncio.gather(*tasks)
        _LOGGER.info("Done updating tg stats")


if __name__ == '__main__':
    asyncio.run(
        run(None, None)
    )
