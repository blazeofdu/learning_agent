import sqlite3
from venv import create

connection = sqlite3.connect("agent.db")
cursor = connection.cursor() # 用来执行sql的对象

cursor.execute(
#多行字符串 “”“
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

cursor.execute(
    """
    insert into chat_messages (session_id, role, content) values (?, ?, ?) 
    """,
        (
        "session-001",
        "user",
        "什么是 AI Agent?",
    ),
)

connection.commit()
#表示提交事务，把此前对数据库的修改正式保存到数据库文件中。 后面才能查到 connection.rollback() 撤销

cursor.execute(
    """
     SELECT id, session_id, role, content, created_at
    FROM chat_messages
    ORDER BY id
    """
)


rows = cursor.fetchall() #来获取上一条查询语句返回的所有剩余记录。  list

for row in rows:
    print(row)


connection.close()

