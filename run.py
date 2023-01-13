from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Optional

from telethon import TelegramClient
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import Channel, Chat, InputChannel

from tg_data_loader import load_group_data


# < < < < < < < < < settings section
_LOGLEVEL: int = logging.INFO
_API_ID: int = ...
_API_HASH: str = ...
_PHONE: str = ...
_OUTPUT_DIR: str = './data'
_MESSAGES_AFTER: datetime.datetime = datetime.datetime(2023, 1, 1, tzinfo=datetime.timezone.utc)
_CHATS_BATCH_SIZE: int = 10
# > > > > > > > > >


logging.basicConfig(
    level=_LOGLEVEL,
    format='[%(asctime)s] %(levelname)-8s| %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S %Z'
)
LOGGER = logging.getLogger(__name__)


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


async def run(
        phone: str,
        api_id: int,
        api_hash: str,
        outdir: str,
        messages_after: datetime.datetime,
        chats_batch_size: int = 10,
) -> None:
    client = TelegramClient(session=phone, api_id=api_id, api_hash=api_hash, request_retries=10)

    try:
        await client.connect()
        await client.start(phone=lambda: phone)

        raw_chats: list[Dialog] = []

        target_group_id: Optional[int] = None
        group_idx = 0

        async for dialog in client.iter_dialogs():  # type: Dialog
            LOGGER.debug(f'Processing dialog with entity type {type(dialog.entity)}: {dialog}')
            if not (dialog.is_group or dialog.is_channel):
                LOGGER.debug(f'Can not process chat: {dialog.title}')
                continue
            raw_chats.append(dialog)
            if len(raw_chats) % chats_batch_size == 0:
                group_idx, choice = _ask_group_idx(cur_idx=group_idx, groups=raw_chats[-chats_batch_size:])
                if choice is not None:
                    target_group_id = choice
                    break

        if unviewed_chats := len(raw_chats) - group_idx:
            group_idx, choice = _ask_group_idx(cur_idx=group_idx, groups=raw_chats[-unviewed_chats:])
            if choice is not None:
                target_group_id = choice

        if target_group_id is None:
            choice: Optional = None
            raw_input = input('\nNo more chats, choose one or press "Enter" again to finish: ')
            if raw_input.strip():
                choice = int(raw_input) - 1

            if choice is not None:
                target_group_id = choice
            else:
                return

        target_group: Channel | InputChannel | Chat = raw_chats[target_group_id].entity

        await load_group_data(client, target_group, outdir, messages_after)

    finally:
        if not await client.is_user_authorized():
            return

        log_out_choice = input('\n\nLog out? [y/n]\n')
        if log_out_choice.lower() == 'y':
            await client.log_out()


if __name__ == '__main__':
    asyncio.run(
        run(_PHONE, _API_ID, _API_HASH, _OUTPUT_DIR, _MESSAGES_AFTER, _CHATS_BATCH_SIZE)
    )
