import csv
import datetime
import json
import logging
import os
from typing import Generator

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.custom.message import Message
from telethon.tl.functions.stats import GetMegagroupStatsRequest, LoadAsyncGraphRequest
from telethon.tl.patched import Message as BasicMessage
from telethon.tl.types import (
    Channel,
    ChatEmpty,
    InputChannel,
    MessageService,
    ReactionEmoji,
    StatsGraph,
    StatsGraphAsync,
    StatsGraphError,
    TypeChatFull,
    User,
)
from telethon.tl.types.messages import ChatFull
from telethon.tl.types.stats import MegagroupStats


LOGGER = logging.getLogger(__name__)


def bool_to_csv(val: bool) -> str:
    return '1' if val else '0'


def graph_data_generator(data: dict) -> Generator[tuple[int | str], None, None]:
    names = {
        'x': 'x',
        **data['names'],
    }
    header = (names[row[0]] for row in data['columns'])
    yield header
    for row in zip(*data['columns']):
        if isinstance(row[0], str):
            continue
        x = datetime.datetime.fromtimestamp(row[0] / 1000.0, tz=datetime.timezone.utc)
        yield (x,) + row[1:]


def write_graph(graph: StatsGraph, filename: str) -> None:
    graph_data = json.loads(graph.json.data)
    with open(filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        for row in graph_data_generator(graph_data):
            writer.writerow(row)


def write_overview(stats: MegagroupStats, filename: str):
    with open(filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerow([
            'min_date',
            'max_date',
            'members_current',
            'members_previous',
            'messages_current',
            'messages_previous',
            'viewers_current',
            'viewers_previous',
            'posters_current',
            'posters_previous',
        ])
        writer.writerow([
            stats.period.min_date,
            stats.period.max_date,
            stats.members.current,
            stats.members.previous,
            stats.messages.current,
            stats.messages.previous,
            stats.viewers.current,
            stats.viewers.previous,
            stats.posters.current,
            stats.posters.previous,
        ])


def write_top_admins(stats: MegagroupStats, filename: str):
    with open(filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerow(['user_id', 'deleted', 'kicked', 'banned'])
        for admin_stats in stats.top_admins:
            writer.writerow([
                admin_stats.user_id,
                admin_stats.deleted,
                admin_stats.kicked,
                admin_stats.banned,
            ])


async def write_megagroup_stats(client: TelegramClient, target_group: Channel | InputChannel, chat_outdir: str) -> None:
    stats: MegagroupStats = await client(GetMegagroupStatsRequest(
        channel=target_group,
        dark=False,
    ))

    overview_filename = os.path.join(chat_outdir, 'overview.csv')
    write_overview(stats, overview_filename)

    # there is also 'top_hours_graph', but it is useless since we have all messages
    sync_graph_names = ('growth_graph', 'members_graph')
    for sync_graph_name in sync_graph_names:
        sync_graph_obj = getattr(stats, sync_graph_name)
        assert isinstance(sync_graph_obj, StatsGraph)
        graph_filename = os.path.join(chat_outdir, sync_graph_name + '.csv')
        write_graph(sync_graph_obj, graph_filename)

    async_graph_names = ('new_members_by_source_graph', 'languages_graph', 'messages_graph', 'actions_graph')
    for async_graph_name in async_graph_names:
        async_graph_obj = getattr(stats, async_graph_name)
        assert isinstance(async_graph_obj, StatsGraphAsync)
        sync_graph_obj = await client(LoadAsyncGraphRequest(token=async_graph_obj.token))
        assert isinstance(sync_graph_obj, (StatsGraph, StatsGraphError))
        if isinstance(sync_graph_obj, StatsGraphError):
            LOGGER.error(f'Cannot load {async_graph_name}: {sync_graph_obj.error}')
        else:
            graph_filename = os.path.join(chat_outdir, async_graph_name + '.csv')
            write_graph(sync_graph_obj, graph_filename)

    top_admins_filename = os.path.join(chat_outdir, 'top_admins.csv')
    write_top_admins(stats, top_admins_filename)


def write_chat_info(channel_full: TypeChatFull, chat_outdir: str) -> None:
    info_filename = os.path.join(chat_outdir, 'info.csv')
    with open(info_filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerow(['about'])
        writer.writerow([channel_full.about])


def write_chats(chat_full: ChatFull, chat_outdir: str) -> None:
    chats_filename = os.path.join(chat_outdir, 'chats.csv')
    with open(chats_filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerow(['order', 'id', 'title'])
        for order, chat in enumerate(chat_full.chats):
            if not isinstance(chat, ChatEmpty):
                writer.writerow([order, chat.id, chat.title])


async def write_participants(client: TelegramClient, target_group: Channel | InputChannel, chat_outdir: str) -> None:
    participants_filename = os.path.join(chat_outdir, 'participants.csv')
    success = True
    with open(participants_filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerow(['user_id', 'username', 'name', 'bot', 'premium', 'verified'])
        try:
            async for participant in client.iter_participants(target_group):
                assert isinstance(participant, User)
                if not participant.deleted:
                    writer.writerow([
                        participant.id,
                        participant.username,
                        ' '.join((participant.first_name or '', participant.last_name or '')).strip(),
                        bool_to_csv(participant.bot),
                        bool_to_csv(participant.premium),
                        bool_to_csv(participant.verified),
                    ])
        except RPCError as e:
            LOGGER.warning(f'An error occurred while trying to load participants: {e}')
            success = False
    if not success:
        os.remove(participants_filename)


async def write_messages(
        client: TelegramClient,
        target_group: Channel | InputChannel,
        chat_outdir: str,
        messages_after: datetime.datetime
) -> None:
    messages_filename = os.path.join(chat_outdir, 'messages.csv')
    with open(messages_filename, 'w', encoding='UTF-8') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerow([
            'message_id',
            'dt',
            'user_id',
            'username_or_channel_title',
            'message_text',
            'is_forwarded',
            'reply_to_message',
            'media',
            'entities',
            'reactions',
            'replies',
            'forwards',
            'service_action',
        ])
        async for message in client.iter_messages(target_group, limit=None):  # type: Message
            if not isinstance(message, (BasicMessage, MessageService)):
                LOGGER.error(f'Message of type "{type(message)}" is not supported yet, it will not be saved')
                continue

            message_id: int = message.id
            dt: datetime.datetime = message.date

            if dt < messages_after:
                break

            user_id: str | int
            username_or_channel_title: str = ''
            message_text: str = '' if isinstance(message, MessageService) else message.message
            is_forwarded: str = (
                bool_to_csv(False)
                if isinstance(message, MessageService)
                else bool_to_csv(message.fwd_from is not None))
            reply_to_message = message.reply_to.reply_to_msg_id if message.reply_to is not None else ''
            media: str = ''
            entities: str = ''
            reactions: list[str] = []
            replies = message.replies.replies if message.replies is not None else 0
            forwards = message.forwards if message.forwards is not None else 0
            service_action: str = type(message.action).__name__ if isinstance(message, MessageService) else ''

            if message.reactions is not None:
                for reaction in message.reactions.results:
                    reactions.extend(
                        [reaction.reaction.emoticon] * reaction.count
                        if isinstance(reaction.reaction, ReactionEmoji)
                        else []
                    )
            reactions_str = ','.join(reactions)

            if isinstance(target_group, Channel) and target_group.broadcast and message.from_id is None:
                user_id = ''
                username_or_channel_title = target_group.title
            else:
                author: User | Channel = await client.get_entity(message.from_id)
                user_id = author.id
                if isinstance(author, User):
                    username_or_channel_title = author.username
                elif isinstance(author, Channel):
                    username_or_channel_title = author.title
                else:
                    LOGGER.error(f'Unsupported message author type: {type(author)}')

            if isinstance(message, BasicMessage):
                media = type(message.media).__name__ if message.media is not None else ''
                entities = str(message.entities) if message.entities is not None else ''

            writer.writerow([
                message_id,
                dt,
                user_id,
                username_or_channel_title,
                message_text,
                is_forwarded,
                reply_to_message,
                media,
                entities,
                reactions_str,
                replies,
                forwards,
                service_action,
            ])
