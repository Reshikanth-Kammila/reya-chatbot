import re
import os

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Imports
code = code.replace("import sqlite3", "import psycopg2\nimport psycopg2.extras\nfrom psycopg2 import pool\nfrom contextlib import contextmanager")

# 2. Config
code = code.replace(
    'DB_PATH   = os.path.join(os.path.dirname(__file__), "memory.db")',
    'DATABASE_URL = os.getenv("DATABASE_URL")\nif not DATABASE_URL:\n    raise ValueError("DATABASE_URL is not set")\ndb_pool = pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)'
)

# 3. get_db
get_db_old = """def get_db():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn"""

get_db_new = """@contextmanager
def get_db():
    class DBWrapper:
        def __init__(self, conn):
            self.conn = conn
        def execute(self, query, params=()):
            query = query.replace('?', '%s')
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            return cursor
        def commit(self):
            self.conn.commit()
        def close(self):
            self.conn.close()
    
    conn = db_pool.getconn()
    try:
        yield DBWrapper(conn)
    finally:
        db_pool.putconn(conn)"""

code = code.replace(get_db_old, get_db_new)

# 4. Table schema changes
code = code.replace("DATETIME DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
code = code.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Conversion complete.")
