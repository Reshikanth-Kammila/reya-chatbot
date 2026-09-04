import re

with open("app.py", "r", encoding="utf-8") as f:
    code = f.read()

init_db_new = """def init_db():
    \"\"\"Create tables.\"\"\"
    with get_db() as conn:
        # Sessions table
        conn.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        \"\"\")

        # Messages table
        conn.execute(\"\"\"
            CREATE TABLE IF NOT EXISTS messages (
                id         SERIAL PRIMARY KEY,
                session_id TEXT,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        \"\"\")
        conn.commit()"""

code = re.sub(r'def init_db\(\):.*?(?=\n\n# â”€â”€)', init_db_new, code, flags=re.DOTALL)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(code)
