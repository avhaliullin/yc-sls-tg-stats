import datetime
import logging

import clickhouse_connect
from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError
from telethon.tl.custom.message import Message
from telethon.tl.patched import Message as BasicMessage
from telethon.tl.types import (
    Channel,
    InputChannel,
    MessageService,
    User, PeerUser,
)

_MESSAGES_BATCH = 1000
_PARTICIPANTS_BATCH = 1000
_LOGGER = logging.getLogger(__name__)


class CHDataWriter:
    def __init__(self, hostname, login, password, database, ca_cert=None):
        self.ch_client = clickhouse_connect.get_client(host=hostname, port=8443, username=login, password=password,
                                                       database=database, ca_cert=ca_cert)

    def _flush_participants(self, group_id, participants):
        users_csv = ','.join([str(p.id) for p in participants])
        known_users_rs = self.ch_client.query(
            f'SELECT user_id FROM participants WHERE group_id = {{g:UInt64}} AND user_id IN({users_csv})',
            parameters={
                'g': group_id,
            })
        known_users = set([row[0] for row in known_users_rs.result_set])
        data = [[group_id, p.id, p.username or '', p.first_name or '', p.last_name or '', p.bot, p.premium, p.verified]
                for p in participants if p.id not in known_users]
        if len(data) > 0:
            self.ch_client.insert('participants', data,
                                  ['group_id', 'user_id', 'username', 'first_name', 'last_name', 'is_bot', 'is_premium',
                                   'is_verified'])
            _LOGGER.info(f'Updated {len(data)} participants')

    async def write_participants(self, client: TelegramClient, target_group: Channel | InputChannel,
                                 deadline: datetime.datetime) -> None:
        group_name = target_group.title
        _LOGGER.info(f'Updating participants for group {group_name}')
        try:
            participants = list()
            async for participant in client.iter_participants(target_group):
                if datetime.datetime.now() > deadline:
                    _LOGGER.warning("Timeout exceeded, will continue in next function run")
                    break
                assert isinstance(participant, User)
                if not participant.deleted:
                    participants.append(participant)
                if len(participants) >= _PARTICIPANTS_BATCH:
                    self._flush_participants(target_group.id, participants)
                    participants = list()
            if len(participants) > 0:
                self._flush_participants(target_group.id, participants)
        except ChatAdminRequiredError as e:
            _LOGGER.warning(f'An error occurred while trying to load participants of "{group_name}": {e}')
        finally:
            _LOGGER.info(f'Done participants for group {group_name}')

    async def write_groups(self, groups):
        _LOGGER.info('Updating groups table')
        data = list()
        groups_rs = self.ch_client.query("SELECT group_id, name FROM groups")
        current_groups = {}
        for row in groups_rs.result_set:
            current_groups[row[0]] = row[1]

        for group in groups:
            cur_name = current_groups.get(group.id)
            if cur_name == group.title:
                continue
            if cur_name is not None:
                _LOGGER.warning(f'Group {group.id} title was changed: "{cur_name}"->"{group.title}". '
                                f'Keeping old title in DB')
                continue
            data.append([group.id, group.title])
            _LOGGER.info(f'Added group {group.id} "{group.title}"')
        if len(data) > 0:
            self.ch_client.insert('groups', data, column_names=['group_id', 'name'])
        _LOGGER.info('Done updating groups table')

    def _flush_messages(self, group_name, data):
        _LOGGER.info(f'Flushing {len(data)} messages of "{group_name}"')
        self.ch_client.insert('messages', data,
                              column_names=['group_id', 'message_id', 'dt', 'user_id', 'message_text', 'is_forwarded',
                                            'reply_to'])

    async def write_messages(self, client: TelegramClient, target_group: Channel | InputChannel,
                             messages_after: datetime.datetime, deadline: datetime.datetime) -> None:
        group_name = target_group.title
        max_id_rs = self.ch_client.query(
            query='SELECT message_id FROM messages WHERE group_id = {g:UInt64} ORDER BY dt DESC, message_id DESC LIMIT 1',
            parameters={'g': target_group.id}
        )
        max_id = 0
        if len(max_id_rs.result_set) > 0:
            max_id = max_id_rs.result_set[0][0]
        _LOGGER.info(f'Scanning group "{group_name}" from message {max_id}')
        data = list()
        async for message in client.iter_messages(target_group, limit=None, reverse=True,
                                                  offset_id=max_id, offset_date=messages_after):  # type: Message
            if datetime.datetime.now() > deadline:
                _LOGGER.warning("Timeout exceeded, will continue in next function run")
                break
            if not isinstance(message, (BasicMessage, MessageService)):
                _LOGGER.error(f'Message of type "{type(message)}" is not supported yet, it will not be saved')
                continue

            group_id = target_group.id
            message_id: int = message.id
            dt: datetime.datetime = message.date

            message_text: str = '' if isinstance(message, MessageService) else message.message
            is_forwarded = message.fwd_from is not None
            reply_to_message = message.reply_to.reply_to_msg_id if message.reply_to is not None else 0

            user_id = 0
            if message.from_id is not None and isinstance(message.from_id, PeerUser):
                user_id = message.from_id.user_id

            data.append([group_id, message_id, dt, user_id, message_text, is_forwarded, reply_to_message])

            if len(data) >= 100:
                self._flush_messages(group_name, data)
                data = list()
        if len(data) > 0:
            self._flush_messages(group_name, data)
        _LOGGER.info(f'Done processing "{group_name}" messages')
