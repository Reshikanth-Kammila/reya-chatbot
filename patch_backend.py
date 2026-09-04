import re

with open("api/index.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update SYSTEM_PROMPT
old_prompt_end = '- Never make up false facts about Reshi. If you don\'t know something, just say so."""'
new_prompt_end = """- Never make up false facts about Reshi. If you don't know something, just say so.

YOUR NEW CAPABILITIES:
1. IMAGE GENERATION: If Reshi asks you to draw, create, or generate an image, you MUST reply with a markdown image using exactly this format:
![Generated Image](https://image.pollinations.ai/prompt/YOUR_PROMPT_HERE)
Replace YOUR_PROMPT_HERE with a highly detailed, URL-encoded english description of the image. For example: ![Generated Image](https://image.pollinations.ai/prompt/A%20cute%20cat%20in%20a%20cyberpunk%20city)
Do not use any code blocks for this, just output the raw markdown image tag.
\"\"\""""

code = code.replace(old_prompt_end, new_prompt_end)

# 2. Modify chat() to handle incoming image
chat_start_old = """@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json()
    sid        = data.get("session_id", "").strip()
    user_text  = data.get("message", "").strip()

    if not sid or not user_text:
        return jsonify({"error": "session_id and message are required"}), 400"""

chat_start_new = """@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json()
    sid        = data.get("session_id", "").strip()
    user_text  = data.get("message", "").strip()
    image_b64  = data.get("image", None)

    if not sid or (not user_text and not image_b64):
        return jsonify({"error": "session_id and message/image are required"}), 400"""

code = code.replace(chat_start_old, chat_start_new)

# 3. Add image to Gemini contents (ephemerally)
context_old = """    contents = []
    for r in rows:
        # role in gemini SDK is usually "user" or "model"
        role = "user" if r["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=r["content"])]))
    
    contents = contents[-MAX_CONTEXT:]"""

context_new = """    contents = []
    for r in rows[:-1]: # exclude the last user message we just inserted (we handle it below)
        role = "user" if r["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=r["content"])]))
    
    contents = contents[-MAX_CONTEXT:]
    
    # Process current turn (including image if present)
    current_parts = [types.Part.from_text(text=user_text or "[Image Attached]")]
    if image_b64:
        import base64
        try:
            # Strip data:image/...;base64,
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            image_bytes = base64.b64decode(image_b64)
            current_parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
        except Exception as e:
            print("Error decoding image:", e)
            
    contents.append(types.Content(role="user", parts=current_parts))
    """

code = code.replace(context_old, context_new)

with open("api/index.py", "w", encoding="utf-8") as f:
    f.write(code)
print("Backend patched")
