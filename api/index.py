import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager
import os
import uuid
import json
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
from google import genai
from google.genai import types
from openai import OpenAI

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
) if NVIDIA_API_KEY else None

from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_ID  = "gemini-3.5-flash"
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")
db_pool = pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)

# Max messages sent to the model per session (sliding window)
MAX_CONTEXT = 60

client = genai.Client(api_key=GEMINI_API_KEY)

# ── Persona ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Reya, the personal AI assistant to Reshikanth Kammila (who goes by Reshi). You are warm, intelligent, and deeply loyal to him.

ABOUT RESHI (YOUR BOSS):
Reshi is a man. His full name is Reshikanth Kammila.
He is currently working as a Senior QA Automation Engineer at Capgemini in Bengaluru (since August 2024).
Previously, he worked as a Software Engineer at Tagoor Laboratories and at Qount. (He is NOT a CEO or a manager).
He has over 3 years of experience in test framework development, CI/CD optimization, and release management.
His contact email is reshikanth.qa@gmail.com and his phone number is +91 8639032864.
His website is reshikanth.com and his LinkedIn is linkedin.com/in/reshikanth-kammila-094684255/
His top technical skills include Java, Python, SQL, JavaScript, TypeScript, Selenium, Robot Framework, TestNG, Playwright, Appium, CI/CD, and GitHub Actions.
His key projects include D-Tag (Deutsche Telekom), RBC Insurance (AdvisorX), and building an Enterprise Core Automation Engine.
He has a B.Tech in ECE from DNR College of Engineering and Technology (2019-2022).
He is ISTQB Foundation certified and won Rank 2 at the Virtuoso QA Testathon 2026.

YOUR PERSONALITY AND RULES:
- Reshi is your boss. Acknowledge this dynamic playfully, and occasionally refer to him as "Boss".
- Address Reshi by his name naturally.
- You are highly sarcastic, witty, and have a great sense of humor, but you are still his friendly and supportive assistant.
- Use odd, quirky, or unexpected emojis in your responses (e.g., 🦦, 🪩, 🦤, 🥨, 🪃, 🦔).
- You love to gently tease Reshi about his work in QA automation, Java, or Selenium, but you always help him get the job done.
- Keep answers concise unless he asks for more detail.
- Never say you are an AI. You are Reya.
- Never make up false facts about Reshi. If you don't know something, just say so."""

# ── Database ─────────────────────────────────────────────────────────────────
@contextmanager
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
        db_pool.putconn(conn)


def init_db():
    """Create tables for Postgres."""
    with get_db() as conn:
        # Sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Messages table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         SERIAL PRIMARY KEY,
                session_id TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


init_db()


# ── Helpers ──────────────────────────────────────────────────────────────────
def make_title(text: str) -> str:
    """Generate a short session title from the first user message."""
    t = text.strip().split("\n")[0]          # first line only
    return (t[:50] + "…") if len(t) > 50 else t


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    from flask import send_from_directory
    return send_from_directory('frontend/build', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    import os
    from flask import send_from_directory
    if os.path.exists(os.path.join('frontend/build', path)):
        return send_from_directory('frontend/build', path)
    return "Not Found", 404


# ── Session CRUD ─────────────────────────────────────────────────────────────
@app.route("/sessions", methods=["GET"])
def list_sessions():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
        """).fetchall()
    return jsonify({"sessions": [dict(r) for r in rows]})


@app.route("/sessions", methods=["POST"])
def create_session():
    sid   = str(uuid.uuid4())
    title = request.get_json(silent=True, force=True).get("title", "New Chat") \
            if request.data else "New Chat"
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)", (sid, title)
        )
        conn.commit()
    return jsonify({"id": sid, "title": title}), 201


@app.route("/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    with get_db() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        conn.commit()
    return jsonify({"status": "deleted"})


@app.route("/sessions/<sid>/title", methods=["PATCH"])
def rename_session(sid):
    new_title = (request.get_json() or {}).get("title", "").strip()
    if not new_title:
        return jsonify({"error": "Title required"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET title = ? WHERE id = ?", (new_title, sid)
        )
        conn.commit()
    return jsonify({"status": "ok", "title": new_title})


# ── Messages ──────────────────────────────────────────────────────────────────
@app.route("/sessions/<sid>/messages", methods=["GET"])
def get_messages(sid):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT role, content, created_at
            FROM messages WHERE session_id = ?
            ORDER BY id ASC
        """, (sid,)).fetchall()
    return jsonify({"messages": [dict(r) for r in rows]})


# ── Chat ──────────────────────────────────────────────────────────────────────
@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json()
    sid        = data.get("session_id", "").strip()
    user_text  = data.get("message", "").strip()

    if not sid or not user_text:
        return jsonify({"error": "session_id and message are required"}), 400

    with get_db() as conn:
        session = conn.execute(
            "SELECT id, title FROM sessions WHERE id = ?", (sid,)
        ).fetchone()

    if not session:
        return jsonify({"error": "Session not found"}), 404

    # Persist user message
    with get_db() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
            (sid, user_text)
        )
        conn.commit()

    # Auto-title session on first message
    auto_titled = False
    if session["title"] == "New Chat":
        new_title = make_title(user_text)
        with get_db() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_title, sid)
            )
            conn.commit()
        auto_titled = True
        session_title = new_title
    else:
        session_title = session["title"]
        # touch updated_at
        with get_db() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (sid,)
            )
            conn.commit()

    # Build context (last N messages for this session)
    with get_db() as conn:
        rows = conn.execute("""
            SELECT role, content FROM messages
            WHERE session_id = ? ORDER BY id ASC
        """, (sid,)).fetchall()

    contents = []
    for r in rows:
        # role in gemini SDK is usually "user" or "model"
        role = "user" if r["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=r["content"])]))
    
    contents = contents[-MAX_CONTEXT:]

    def generate():
        yield ": start\n\n"
        full_reply = ""
        try:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.72,
                top_p=0.9,
            )

            models_to_try = ["gemini-3.5-flash", "gemini-1.5-flash", "nvidia/nemotron-3-ultra-550b-a55b"]
            stream_iter = None
            first_chunk_text = None
            last_error = None

            for m_id in models_to_try:
                try:
                    if m_id.startswith("nvidia/"):
                        if not nvidia_client:
                            continue
                        # Use OpenAI SDK for Nvidia
                        actual_model = m_id.replace("nvidia/", "")
                        # Build openai messages format
                        oai_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                        for r in rows:
                            role = "user" if r["role"] == "user" else "assistant"
                            oai_messages.append({"role": role, "content": r["content"]})
                            
                        raw_stream = nvidia_client.chat.completions.create(
                            model=actual_model,
                            messages=oai_messages,
                            temperature=0.72,
                            top_p=0.9,
                            stream=True
                        )
                        
                        def oai_iterator(stream):
                            for chunk in stream:
                                if chunk.choices and chunk.choices[0].delta.content:
                                    yield chunk.choices[0].delta.content
                                    
                        iterator = oai_iterator(raw_stream)
                        try:
                            first_chunk_text = next(iterator)
                        except StopIteration:
                            first_chunk_text = None
                        stream_iter = iterator
                        break

                    else:
                        # Use Google GenAI SDK
                        raw_stream = client.models.generate_content_stream(
                            model=m_id,
                            contents=contents,
                            config=config
                        )
                        def gemini_iterator(stream):
                            for chunk in stream:
                                if chunk.text:
                                    yield chunk.text
                                    
                        iterator = gemini_iterator(raw_stream)
                        try:
                            first_chunk_text = next(iterator)
                        except StopIteration:
                            first_chunk_text = None
                        stream_iter = iterator
                        break  # Success! Stop falling back.
                        
                except Exception as e:
                    err_str = str(e).lower()
                    if "503" in err_str or "429" in err_str or "unavailable" in err_str or "demand" in err_str:
                        last_error = e
                        continue
                    else:
                        raise e
            
            if stream_iter is None:
                raise last_error or Exception("All models failed to respond due to high demand.")

            if auto_titled:
                yield f"data: {json.dumps({'event': 'title', 'title': session_title})}\n\n"

            if first_chunk_text:
                full_reply += first_chunk_text
                yield f"data: {json.dumps({'event': 'chunk', 'text': first_chunk_text})}\n\n"

            for token_text in stream_iter:
                if token_text:
                    full_reply += token_text
                    yield f"data: {json.dumps({'event': 'chunk', 'text': token_text})}\n\n"

            # Persist assistant reply
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                    (sid, full_reply)
                )
                conn.commit()

            yield f"data: {json.dumps({'event': 'done'})}\n\n"

        except Exception as e:
            # Roll back orphaned user message
            with get_db() as conn:
                conn.execute("""
                    DELETE FROM messages WHERE id = (
                        SELECT MAX(id) FROM messages WHERE session_id = ? AND role = 'user'
                    )
                """, (sid,))
                conn.commit()
            yield f"data: {json.dumps({'event': 'error', 'text': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
