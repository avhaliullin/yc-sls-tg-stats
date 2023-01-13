from __future__ import annotations

import datetime
import os
import re
import logging
import time
from typing import Any

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.functions.stats import GetBroadcastStatsRequest
from telethon.tl.types import Channel, Chat, InputChannel
from telethon.tl.types.messages import ChatFull

from writers import (
    write_chat_info,
    write_chats,
    write_megagroup_stats,
    write_messages,
    write_participants,
)


LOGGER = logging.getLogger(__name__)


class Profiler:
    def __init__(self, step: str, loglevel: int = logging.DEBUG) -> None:
        self.step = step
        self.loglevel = loglevel

    def __enter__(self) -> Profiler:
        self.start_t = time.monotonic()
        return self

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        elapsed = time.monotonic() - self.start_t
        LOGGER.log(self.loglevel, f'Step "{self.step}" took: {elapsed:.9f} s')


def clean_string(s: str) -> str:
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', '-', s)

    return s


async def load_group_data(
        client: TelegramClient,
        target_group: Channel | InputChannel | Chat,
        outdir: str,
        messages_after: datetime.datetime,
) -> None:
    LOGGER.info(f'Going to load data for chat "{target_group.title}"')
    LOGGER.debug('Target chat object: %s', target_group)

    os.makedirs(outdir, exist_ok=True)

    clean_title = clean_string(target_group.title)
    chat_outdir = os.path.join(outdir, clean_title)
    os.makedirs(chat_outdir, exist_ok=True)
    LOGGER.info(f'Results will be saved into {chat_outdir}')

    chat_full: ChatFull
    if isinstance(target_group, Chat):
        chat_full = await client(GetFullChatRequest(target_group.id))
    else:
        chat_full = await client(GetFullChannelRequest(target_group))

    with Profiler('chat_info'):
        write_chat_info(chat_full.full_chat, chat_outdir)

    with Profiler('chats'):
        write_chats(chat_full, chat_outdir)

    if isinstance(target_group, (Channel, InputChannel)) and target_group.megagroup:
        try:
            with Profiler('megagroup_stats'):
                await write_megagroup_stats(client, target_group, chat_outdir)
        except RPCError as e:
            LOGGER.warning(f'An error occurred while trying to load megagroup stats: {e}')

    if isinstance(target_group, (Channel, InputChannel)) and target_group.broadcast:
        try:
            with Profiler('broadcast_stats'):
                await client(GetBroadcastStatsRequest(
                    channel=target_group,
                    dark=False,
                ))
            LOGGER.warning('Broadcast stats are not supported')
        except RPCError as e:
            LOGGER.debug(f'An error occurred while trying to load broadcast stats: {e}')

    with Profiler('messages'):
        await write_messages(client, target_group, chat_outdir, messages_after)
    LOGGER.info(f'Successfully loaded messages starting from {messages_after}')

    with Profiler('participants'):
        await write_participants(client, target_group, chat_outdir)
