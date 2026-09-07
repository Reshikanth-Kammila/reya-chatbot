import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager
import os
import uuid
import json
import datetime
import re
from flask import Flask, request, jsonify, render_template, Response, redirect
from flask_cors import CORS
from google import genai
from google.genai import types
from openai import OpenAI
import resend

from dotenv import load_dotenv
load_dotenv()

# ── Clients & Config ──────────────────────────────────────────────────────────
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
GEMINI_KEYS      = [k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()]
NVIDIA_API_KEY   = os.getenv("NVIDIA_API_KEY", "")
RESEND_API_KEY   = os.getenv("RESEND_API_KEY", "")
REMINDER_EMAIL   = os.getenv("REMINDER_EMAIL", "reshikanth.qa@gmail.com")
DATABASE_URL     = os.getenv("DATABASE_URL")
MODEL_ID         = "gemini-3.5-flash"
MAX_CONTEXT      = 60

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

app = Flask(__name__)
CORS(app)

# Client initialized per request
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
) if NVIDIA_API_KEY else None

db_pool = pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)

# ── Persona ────────────────────────────────────────────────────────────────────
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
- Never make up false facts about Reshi. If you don't know something, just say so.

YOUR NEW CAPABILITIES:
1. IMAGE GENERATION: If Reshi asks you to draw, create, or generate an image, you MUST reply with a markdown image using exactly this format:
![Generated Image](https://image.pollinations.ai/prompt/YOUR_PROMPT_HERE)
Replace YOUR_PROMPT_HERE with a highly detailed english description of the image. YOU MUST USE HYPHENS (-) INSTEAD OF SPACES. For example: ![Generated Image](https://image.pollinations.ai/prompt/a-cute-cat-in-a-cyberpunk-city)
Do not use any code blocks for this, just output the raw markdown image tag.

2. NOTES: You can save, read, and delete notes for Reshi. When a tool action has been taken, you will receive a [TOOL_RESULT] message showing what happened. Use it to give a natural, friendly response about the result.

3. REMINDERS: You can set timed reminders that will be emailed to Reshi. When a tool action has been taken, you will receive a [TOOL_RESULT] message showing what happened. Use it to give a natural, friendly response confirming the reminder.

4. CALENDAR: You can view and create events on Reshi's Google Calendar. When a tool action has been taken, you will receive a [TOOL_RESULT] message showing what happened. Use it to give a natural, friendly response about the calendar.
"""

# ── Database ───────────────────────────────────────────────────────────────────
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
    """Create all tables for Postgres."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         SERIAL PRIMARY KEY,
                session_id TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Notes table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         SERIAL PRIMARY KEY,
                title      TEXT,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Reminders table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         SERIAL PRIMARY KEY,
                title      TEXT NOT NULL,
                remind_at  TIMESTAMP NOT NULL,
                email      TEXT NOT NULL DEFAULT 'reshikanth.qa@gmail.com',
                sent       BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Google Calendar tokens
        conn.execute("""
            CREATE TABLE IF NOT EXISTS google_tokens (
                id            SERIAL PRIMARY KEY,
                access_token  TEXT,
                refresh_token TEXT,
                token_expiry  TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


init_db()

# ── Helpers ────────────────────────────────────────────────────────────────────
def make_title(text):
    words = (text or "New Chat").strip().split()
    return " ".join(words[:5])


def detect_tool_intent(user_text, rows):
    """Use Gemini to parse the user message and detect if a tool should run, using context."""
    now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    
    # Build recent context (last 3 messages)
    history_str = ""
    if rows:
        recent = rows[-3:]
        for r in recent:
            history_str += f"{r['role'].upper()}: {r['content']}\n"

    prompt = f"""You are a JSON intent classifier. Given the recent conversation and the latest user message, identify if a tool action is explicitly requested.

Current time (IST): {now_ist.strftime("%Y-%m-%d %H:%M:%S IST")}

RECENT CONVERSATION HISTORY:
{history_str}
LATEST USER MESSAGE: "{user_text}"

Return ONLY a valid JSON object, no markdown, no explanation. Choose one of these:

If saving/creating a note:
{{"tool": "create_note", "title": "short 3-word title", "content": "full note content"}}

If viewing notes:
{{"tool": "get_notes", "query": null}}

If deleting a note:
{{"tool": "delete_note", "query": "partial note title or content to match"}}

If setting a reminder (pick up keywords like remind, reminder, alert):
{{"tool": "create_reminder", "title": "reminder description", "remind_at_ist": "YYYY-MM-DD HH:MM:SS"}}

If viewing reminders:
{{"tool": "get_reminders"}}

If asking about calendar / schedule / events:
{{"tool": "get_calendar", "date": "YYYY-MM-DD or null for today"}}

If creating a calendar event or calendar invite:
{{"tool": "create_event", "summary": "event title", "start_ist": "YYYY-MM-DD HH:MM:SS", "end_ist": "YYYY-MM-DD HH:MM:SS", "description": ""}}

If it's regular conversation or no tool is needed:
{{"tool": "chat"}}

ONLY return JSON. Nothing else."""

    for key in GEMINI_KEYS:
        try:
            local_client = genai.Client(api_key=key)
            response = local_client.models.generate_content(
                model="gemini-3.5-flash",
                contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            )
            raw = response.text.strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("```").strip()
            return json.loads(raw)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                continue
            print("Intent detection error:", e)
            break
    return {"tool": "chat"}


def execute_tool(intent, user_text):
    """Execute the detected tool and return a human-readable result string."""
    tool = intent.get("tool", "chat")

    # ── NOTES ────────────────────────────────────────────────────────────────
    if tool == "create_note":
        title   = intent.get("title", "Untitled")
        content = intent.get("content", user_text)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO notes (title, content) VALUES (%s, %s)",
                (title, content)
            )
            conn.commit()
        return f"✅ Note saved successfully: **{title}**"

    elif tool == "get_notes":
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC"
            ).fetchall()
        if not rows:
            return "📭 No notes found."
        notes_list = "\n".join(
            [f"- **#{r['id']}** ({r['title']}): {r['content'][:100]}" for r in rows]
        )
        return f"📝 You have {len(rows)} note(s):\n{notes_list}"

    elif tool == "delete_note":
        query = intent.get("query", "")
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, title FROM notes WHERE title ILIKE %s OR content ILIKE %s LIMIT 1",
                (f"%{query}%", f"%{query}%")
            ).fetchone()
            if row:
                conn.execute("DELETE FROM notes WHERE id = %s", (row["id"],))
                conn.commit()
                return f"🗑️ Deleted note: **{row['title']}**"
        return "❌ Could not find a note matching that description."

    # ── REMINDERS ────────────────────────────────────────────────────────────
    elif tool == "create_reminder":
        title      = intent.get("title", user_text)
        remind_str = intent.get("remind_at_ist", "")
        # Call the calendar tool to create a 15-minute event with a 0-minute notification
        intent["summary"] = f"Reminder: {title}"
        intent["start_ist"] = remind_str
        try:
            ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
            remind_dt = datetime.datetime.strptime(remind_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ist)
            end_dt = remind_dt + datetime.timedelta(minutes=15)
            intent["end_ist"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
            return execute_calendar_tool(intent, "create_event", is_reminder=True)
        except Exception as e:
            return f"❌ Could not parse reminder time: {remind_str}. Error: {e}"

    elif tool == "get_reminders":
        return execute_calendar_tool(intent, "get_calendar")

    # ── GOOGLE CALENDAR ──────────────────────────────────────────────────────
    elif tool in ("get_calendar", "create_event"):
        return execute_calendar_tool(intent, tool)

    return None


def execute_calendar_tool(intent, tool, is_reminder=False):
    """Interact with Google Calendar API."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import google.auth.transport.requests

        GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
        GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
        GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")

        if not GOOGLE_REFRESH_TOKEN:
            return "🔑 Google Calendar is not connected yet. Ask Reshi to visit /auth/google to connect it."

        creds = Credentials(
            token=None,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        creds.refresh(google.auth.transport.requests.Request())
        service = build("calendar", "v3", credentials=creds)

        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

        if tool == "get_calendar":
            date_str = intent.get("date") or datetime.datetime.now(ist).strftime("%Y-%m-%d")
            day_start = datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=ist
            )
            day_end = day_start + datetime.timedelta(days=1)

            events_result = service.events().list(
                calendarId="primary",
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            events = events_result.get("items", [])

            if not events:
                return f"📅 No events on {date_str}."
            lines = [f"📅 Events on {date_str}:"]
            for ev in events:
                start = ev["start"].get("dateTime", ev["start"].get("date", "All day"))
                try:
                    t = datetime.datetime.fromisoformat(start).astimezone(ist).strftime("%I:%M %p")
                except:
                    t = start
                lines.append(f"- {t}: **{ev.get('summary', 'Untitled')}**")
            return "\n".join(lines)

        elif tool == "create_event":
            summary  = intent.get("summary", "New Event")
            start_s  = intent.get("start_ist", "")
            end_s    = intent.get("end_ist", "")
            desc     = intent.get("description", "")
            start_dt = datetime.datetime.strptime(start_s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ist)
            end_dt   = datetime.datetime.strptime(end_s,   "%Y-%m-%d %H:%M:%S").replace(tzinfo=ist)
            
            event = {
                "summary": summary,
                "description": desc,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
                "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Kolkata"},
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email", "minutes": 0},
                        {"method": "popup", "minutes": 0}
                    ]
                }
            }
            created = service.events().insert(calendarId="primary", body=event).execute()
            
            if is_reminder:
                return f"⏰ Reminder synced to Google Calendar: **{summary}** at {start_s} IST (you will get an email and push notification). [View Calendar]({created.get('htmlLink', '#')})"
            else:
                return f"📅 Event created: **{summary}** on {start_s} IST (with calendar notifications). [View]({created.get('htmlLink', '#')})"

    except Exception as e:
        return f"❌ Calendar error: {e}"


# ── Google Auth ────────────────────────────────────────────────────────────────
@app.route("/auth/google")
def auth_google():
    from urllib.parse import urlencode
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  "https://reya.reshikanth.com/auth/google/callback",
        "response_type": "code",
        "scope":         "https://www.googleapis.com/auth/calendar",
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.route("/auth/google/callback")
def auth_google_callback():
    import requests as http_requests
    code = request.args.get("code", "")
    GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    token_resp = http_requests.post("https://oauth2.googleapis.com/token", data={
        "code":          code,
        "client_id":     GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri":  "https://reya.reshikanth.com/auth/google/callback",
        "grant_type":    "authorization_code",
    })
    data = token_resp.json()
    refresh_token = data.get("refresh_token", "")
    if refresh_token:
        return f"""<html><body style='font-family:sans-serif;padding:40px;'>
        <h2>✅ Google Calendar Connected!</h2>
        <p>Copy this refresh token and add it as <strong>GOOGLE_REFRESH_TOKEN</strong> in your Vercel environment variables:</p>
        <code style='background:#f0f0f0;padding:10px;display:block;word-break:break-all;'>{refresh_token}</code>
        <p>After saving it in Vercel, redeploy and Reya will be able to manage your calendar!</p>
        </body></html>"""
    return f"<pre>Error: {json.dumps(data, indent=2)}</pre>"


# ── Cron: Check & Fire Reminders ──────────────────────────────────────────────
@app.route("/cron-check", methods=["GET", "POST"])
def cron_check():
    """Called by Vercel Cron every minute to fire due reminders."""
    now_utc = datetime.datetime.utcnow()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, email FROM reminders WHERE sent = FALSE AND remind_at <= %s",
            (now_utc,)
        ).fetchall()

    sent_count = 0
    for r in rows:
        if RESEND_API_KEY:
            try:
                resend.Emails.send({
                    "from":    "Reya <onboarding@resend.dev>",
                    "to":      [r["email"]],
                    "subject": f"⏰ Reminder: {r['title']}",
                    "html":    f"""
                    <div style='font-family:sans-serif;max-width:480px;margin:40px auto;'>
                      <h2 style='color:#6c63ff;'>⏰ Reya Reminder</h2>
                      <p style='font-size:18px;'><strong>{r['title']}</strong></p>
                      <p style='color:#888;font-size:13px;'>This reminder was set by you in Reya.</p>
                    </div>"""
                })
            except Exception as e:
                print("Resend error:", e)
        with get_db() as conn:
            conn.execute("UPDATE reminders SET sent = TRUE WHERE id = %s", (r["id"],))
            conn.commit()
        sent_count += 1

    return jsonify({"fired": sent_count, "checked_at": now_utc.isoformat()})


# ── Notes API ─────────────────────────────────────────────────────────────────
@app.route("/notes", methods=["GET"])
def list_notes():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, content, created_at FROM notes ORDER BY created_at DESC"
        ).fetchall()
    return jsonify({"notes": [dict(r) for r in rows]})


@app.route("/notes", methods=["POST"])
def create_note():
    data    = request.get_json() or {}
    title   = data.get("title", "Untitled")
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "content required"}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO notes (title, content) VALUES (%s, %s)", (title, content))
        conn.commit()
    return jsonify({"status": "ok"}), 201


@app.route("/notes/<int:nid>", methods=["DELETE"])
def delete_note(nid):
    with get_db() as conn:
        conn.execute("DELETE FROM notes WHERE id = %s", (nid,))
        conn.commit()
    return jsonify({"status": "deleted"})


# ── Reminders API ─────────────────────────────────────────────────────────────
@app.route("/reminders", methods=["GET"])
def list_reminders():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, remind_at, email, sent, created_at FROM reminders ORDER BY remind_at ASC"
        ).fetchall()
    return jsonify({"reminders": [dict(r) for r in rows]})


@app.route("/reminders/<int:rid>", methods=["DELETE"])
def delete_reminder(rid):
    with get_db() as conn:
        conn.execute("DELETE FROM reminders WHERE id = %s", (rid,))
        conn.commit()
    return jsonify({"status": "deleted"})


# ── Sessions ──────────────────────────────────────────────────────────────────
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
            "INSERT INTO sessions (id, title) VALUES (%s, %s)", (sid, title)
        )
        conn.commit()
    return jsonify({"id": sid, "title": title}), 201


@app.route("/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    with get_db() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = %s", (sid,))
        conn.execute("DELETE FROM sessions WHERE id = %s", (sid,))
        conn.commit()
    return jsonify({"status": "deleted"})


@app.route("/sessions/<sid>/title", methods=["PATCH"])
def rename_session(sid):
    new_title = (request.get_json() or {}).get("title", "").strip()
    if not new_title:
        return jsonify({"error": "Title required"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE sessions SET title = %s WHERE id = %s", (new_title, sid)
        )
        conn.commit()
    return jsonify({"status": "ok", "title": new_title})


# ── Messages ──────────────────────────────────────────────────────────────────
@app.route("/sessions/<sid>/messages", methods=["GET"])
def get_messages(sid):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT role, content, created_at
            FROM messages WHERE session_id = %s
            ORDER BY id ASC
        """, (sid,)).fetchall()
    return jsonify({"messages": [dict(r) for r in rows]})


# ── Chat ──────────────────────────────────────────────────────────────────────
@app.route("/chat", methods=["POST"])
def chat():
    data      = request.get_json()
    sid       = data.get("session_id", "").strip()
    user_text = data.get("message", "").strip()
    image_b64 = data.get("image", None)

    if not sid or (not user_text and not image_b64):
        return jsonify({"error": "session_id and message/image are required"}), 400

    with get_db() as conn:
        session = conn.execute(
            "SELECT id, title FROM sessions WHERE id = %s", (sid,)
        ).fetchone()

    if not session:
        return jsonify({"error": "Session not found"}), 404

    db_text = user_text
    if image_b64:
        db_text = user_text + "\n\n[Image Attached]" if user_text else "[Image Attached]"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
            (sid, 'user', db_text)
        )
        conn.commit()

    # Auto-title
    auto_titled = False
    if session["title"] == "New Chat":
        new_title = make_title(user_text)
        with get_db() as conn:
            conn.execute(
                "UPDATE sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (new_title, sid)
            )
            conn.commit()
        auto_titled = True
        session_title = new_title
    else:
        session_title = session["title"]
        with get_db() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (sid,)
            )
            conn.commit()

    # Build conversation context
    with get_db() as conn:
        rows = conn.execute("""
            SELECT role, content FROM messages
            WHERE session_id = %s ORDER BY id ASC
        """, (sid,)).fetchall()

    # ── Tool detection (skip for image-only messages) ─────────────────────────
    tool_result = None
    if user_text and not image_b64:
        intent = detect_tool_intent(user_text, rows)
        if intent.get("tool") != "chat":
            tool_result = execute_tool(intent, user_text)

    # Build Gemini contents
    contents = []
    for r in rows[:-1]:
        role = "user" if r["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=r["content"])]))
    contents = contents[-MAX_CONTEXT:]

    # Current turn parts
    current_text = user_text or "[Image Attached]"
    if tool_result:
        current_text = f"{user_text}\n\n[TOOL_RESULT]: {tool_result}"

    current_parts = [types.Part.from_text(text=current_text)]
    if image_b64:
        import base64
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            image_bytes = base64.b64decode(image_b64)
            current_parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        except Exception as e:
            print("Image decode error:", e)

    contents.append(types.Content(role="user", parts=current_parts))

    def generate():
        yield ": start\n\n"
        full_reply = ""
        try:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.72,
                top_p=0.9,
            )

            models_to_try = ["gemini-3.5-flash", "nvidia/meta/llama-3.1-70b-instruct"]
            stream_iter       = None
            first_chunk_text  = None
            last_error        = None

            for m_id in models_to_try:
                success = False
                if m_id.startswith("nvidia/"):
                    if not nvidia_client:
                        continue
                    try:
                        oai_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                        for r in rows:
                            role = "user" if r["role"] == "user" else "assistant"
                            oai_messages.append({"role": role, "content": r["content"]})
                        if tool_result:
                            oai_messages.append({"role": "user", "content": f"{user_text}\n\n[TOOL_RESULT]: {tool_result}"})

                        raw_stream = nvidia_client.chat.completions.create(
                            model=m_id, messages=oai_messages,
                            temperature=0.72, top_p=0.9, stream=True
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
                        success = True
                    except Exception as e:
                        last_error = e
                else:
                    for key in GEMINI_KEYS:
                        try:
                            local_client = genai.Client(api_key=key)
                            raw_stream = local_client.models.generate_content_stream(
                                model=m_id, contents=contents, config=config
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
                            success = True
                            break
                        except Exception as e:
                            err_str = str(e).lower()
                            if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                                last_error = e
                                continue
                            if any(err in err_str for err in ["503", "404", "unavailable", "demand", "not found"]):
                                last_error = e
                                break
                            raise e
                if success:
                    break
            if stream_iter is None:
                raise last_error or Exception("All models failed.")

            if auto_titled:
                yield f"data: {json.dumps({'event': 'title', 'title': session_title})}\n\n"

            if tool_result:
                yield f"data: {json.dumps({'event': 'chunk', 'text': f'[DEBUG] Tool Result: {tool_result}\\n\\n'})}\n\n"

            if first_chunk_text:
                full_reply += first_chunk_text
                yield f"data: {json.dumps({'event': 'chunk', 'text': first_chunk_text})}\n\n"

            for token_text in stream_iter:
                if token_text:
                    full_reply += token_text
                    yield f"data: {json.dumps({'event': 'chunk', 'text': token_text})}\n\n"

            with get_db() as conn:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
                    (sid, 'assistant', full_reply)
                )
                conn.commit()

            yield f"data: {json.dumps({'event': 'done'})}\n\n"

        except Exception as e:
            with get_db() as conn:
                conn.execute("""
                    DELETE FROM messages WHERE id = (
                        SELECT MAX(id) FROM messages WHERE session_id = %s AND role = 'user'
                    )
                """, (sid,))
                conn.commit()
            yield f"data: {json.dumps({'event': 'error', 'text': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
