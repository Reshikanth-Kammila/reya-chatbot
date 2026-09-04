import re

with open("api/index.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add OpenAI import and client setup
imports_to_add = """from google.genai import types
from openai import OpenAI

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
) if NVIDIA_API_KEY else None
"""
code = code.replace("from google.genai import types", imports_to_add)

# 2. Replace the `def generate():` block
generate_new = """    def generate():
        yield ": start\\n\\n"
        full_reply = ""
        try:
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.72,
                top_p=0.9,
            )

            models_to_try = ["gemini-3.5-flash", "gemini-1.5-flash", "nvidia/meta/llama-3.1-70b-instruct"]
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
                yield f"data: {json.dumps({'event': 'title', 'title': session_title})}\\n\\n"

            if first_chunk_text:
                full_reply += first_chunk_text
                yield f"data: {json.dumps({'event': 'chunk', 'text': first_chunk_text})}\\n\\n"

            for token_text in stream_iter:
                if token_text:
                    full_reply += token_text
                    yield f"data: {json.dumps({'event': 'chunk', 'text': token_text})}\\n\\n"

            # Persist assistant reply
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                    (sid, full_reply)
                )
                conn.commit()

            yield f"data: {json.dumps({'event': 'done'})}\\n\\n"

        except Exception as e:
            # Roll back orphaned user message
            with get_db() as conn:
                conn.execute(\"\"\"
                    DELETE FROM messages WHERE id = (
                        SELECT MAX(id) FROM messages WHERE session_id = ? AND role = 'user'
                    )
                \"\"\", (sid,))
                conn.commit()
            yield f"data: {json.dumps({'event': 'error', 'text': str(e)})}\\n\\n"
"""

# Extract the part before `def generate():` and after it
match = re.search(r'    def generate\(\):.*?(?=    return Response)', code, flags=re.DOTALL)
if match:
    code = code[:match.start()] + generate_new + "\n" + code[match.end():]
else:
    print("Could not find generate function")

with open("api/index.py", "w", encoding="utf-8") as f:
    f.write(code)
print("done")
