import sqlite3

import pytest

import database


def test_save_and_read_in_order():
    database.save_chat_exchange("session-a", "第一问", "第一答")
    database.save_chat_exchange("session-b", "另一会话", "另一回答")
    database.save_chat_exchange("session-a", "第二问", "第二答")
    rows = database.get_messages("session-a")
    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "第一问"), ("assistant", "第一答"),
        ("user", "第二问"), ("assistant", "第二答"),
    ]
    assert len(database.get_messages("session-b")) == 2


def test_failed_exchange_rolls_back_both_messages():
    # 第一条 INSERT 成功，第二条因 NOT NULL 失败，两条都必须回滚。
    with pytest.raises(sqlite3.IntegrityError):
        database.save_chat_exchange("rollback", "不能留下半条对话", None)
    assert database.get_messages("rollback") == []


def test_connection_is_closed_after_context():
    with database.get_connection() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_sql_values_are_parameters():
    text = "'); DROP TABLE chat_messages; --"
    database.save_chat_exchange(text, text, "ok")
    assert database.get_messages(text)[0]["content"] == text
    assert database.get_messages("another") == []
