import re

# Patch InputBar.jsx
with open("frontend/src/components/InputBar.jsx", "r", encoding="utf-8") as f:
    input_code = f.read()

input_bar_new = """import React, { useState, useRef, useEffect } from 'react';

export default function InputBar({ onSend }) {
  const [text, setText] = useState('');
  const [image, setImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file && file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const img = new Image();
        img.onload = () => {
          // Resize image for API
          const canvas = document.createElement('canvas');
          const MAX_SIZE = 800;
          let width = img.width;
          let height = img.height;
          if (width > height && width > MAX_SIZE) {
            height *= MAX_SIZE / width;
            width = MAX_SIZE;
          } else if (height > MAX_SIZE) {
            width *= MAX_SIZE / height;
            height = MAX_SIZE;
          }
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);
          const base64 = canvas.toDataURL('image/jpeg', 0.8);
          setImage(base64);
          setImagePreview(base64);
        };
        img.src = event.target.result;
      };
      reader.readAsDataURL(file);
    }
  };

  const clearImage = () => {
    setImage(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSend = () => {
    if (text.trim() || image) {
      onSend(text.trim(), image);
      setText('');
      clearImage();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 100) + 'px';
    }
  }, [text]);

  return (
    <div className="input-wrapper">
      {imagePreview && (
        <div className="image-preview" style={{ marginBottom: '10px', position: 'relative', display: 'inline-block' }}>
          <img src={imagePreview} alt="Preview" style={{ height: '60px', borderRadius: '8px', border: '1px solid var(--border)' }} />
          <button onClick={clearImage} style={{ position: 'absolute', top: '-5px', right: '-5px', background: 'red', color: 'white', borderRadius: '50%', width: '20px', height: '20px', fontSize: '12px', border: 'none', cursor: 'pointer' }}>x</button>
        </div>
      )}
      <div className="input-box">
        <button className="attach-btn" title="Attach image" onClick={() => fileInputRef.current.click()}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
        </button>
        <input type="file" accept="image/*" ref={fileInputRef} style={{ display: 'none' }} onChange={handleFileChange} />
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message Reya..."
          rows="1"
          autoComplete="off"
          spellCheck="false"
        />
        <button className="send-btn" onClick={handleSend} disabled={!text.trim() && !image} title="Send">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
          </svg>
        </button>
      </div>
      <div className="input-hint">Enter to send  /  Shift+Enter for new line</div>
    </div>
  );
}
"""

with open("frontend/src/components/InputBar.jsx", "w", encoding="utf-8") as f:
    f.write(input_bar_new)


# Patch App.jsx
with open("frontend/src/App.jsx", "r", encoding="utf-8") as f:
    app_code = f.read()

old_send_start = """  const sendMessage = async (text) => {
    let activeSid = currentSid;
    if (!activeSid) {
      activeSid = await createNewChat();
    }
    if (!text || !activeSid) return;
    
    const userMsg = { role: 'user', content: text, created_at: new Date().toISOString() };"""

new_send_start = """  const sendMessage = async (text, image = null) => {
    let activeSid = currentSid;
    if (!activeSid) {
      activeSid = await createNewChat();
    }
    if ((!text && !image) || !activeSid) return;
    
    // Display the image in the user's message bubble
    let displayContent = text;
    if (image) {
      displayContent = text ? text + "\\n\\n![User Image](" + image + ")" : "![User Image](" + image + ")";
    }
    
    const userMsg = { role: 'user', content: displayContent, created_at: new Date().toISOString() };"""

app_code = app_code.replace(old_send_start, new_send_start)

old_fetch = """      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSid, message: text })
      });"""

new_fetch = """      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSid, message: text, image: image })
      });"""

app_code = app_code.replace(old_fetch, new_fetch)

with open("frontend/src/App.jsx", "w", encoding="utf-8") as f:
    f.write(app_code)

print("Frontend patched")
