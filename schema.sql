create table messages
(
    dt           DATETIME,
    group_id     UInt64,
    message_id   UInt64,
    user_id      UInt64,
    message_text String,
    is_forwarded Boolean,
    reply_to     UInt64,
    topic_id     UInt64
) ENGINE = MergeTree()
      ORDER BY (group_id, dt, message_id);

create table groups
(
    group_id UInt64,
    name     String
) ENGINE = MergeTree()
      ORDER BY group_id;

create table participants
(
    group_id    UInt64,
    user_id     UInt64,
    username    String,
    first_name  String,
    last_name   String,
    is_bot      Boolean,
    is_premium  Boolean,
    is_verified Boolean
) ENGINE = MergeTree()
      ORDER BY (group_id, user_id);

create table topics
(
    group_id UInt64,
    topic_id UInt64,
    title    String
) ENGINE = MergeTree()
      ORDER BY (group_id, topic_id);
