import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager



DATA_DIR = Path(__file__).with_name("data")#获取与database.py同级的data目录：
# 测试或演示可设置独立路径；默认继续使用原有数据库。
DATABASE_PATH = Path(os.getenv("DATABASE_PATH") or DATA_DIR / "agent.db")


@contextmanager #@contextmanager 让普通函数可以管理 with 代码块进入前和退出后的操作。配合yiedld
def get_connection(): # FastAPI 会同时处理多个请求，而数据库连接本身带有事务状态。所有请求共享一个全局连接容易互相干扰。
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)

    # 让查询结果不仅能用数字下标读取，也能用数据库字段名读取
    connection.row_factory = sqlite3.Row
    try:
        yield connection # 会把 value 交给：with example() as value:
        connection.commit()
    except Exception :
        connection.rollback()
        raise
    finally:
        connection.close()



def init_db():
    with get_connection() as connection: #with = 获得数据库连接，并自动管理事务 as connection 把返回的数据库连接对象保存到变量：
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )




def save_chat_exchange(
    session_id: str,
    user_message: str,
    assistant_message: str,
):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO chat_messages (
                session_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                session_id,
                "user",
                user_message,
            ),
        )

        connection.execute(
            """
            INSERT INTO chat_messages (
                session_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                session_id,
                "assistant",
                assistant_message,
            ),
        )


def get_messages(session_id: str):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            SELECT
                id,
                session_id,
                role,
                content,
                created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        )

        rows = cursor.fetchall() #返回查询信息

        return [dict(row) for row in rows] # row 转换成字典再返回


# 导入模块不创建数据库，由应用启动时调用 init_db()。
