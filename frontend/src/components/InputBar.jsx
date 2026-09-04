import React, { useState, useRef, useEffect } from 'react';

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
      <div style={{ maxWidth: '840px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
        {imagePreview && (
          <div className="image-preview" style={{ marginBottom: '12px', marginLeft: '48px', position: 'relative', display: 'inline-block' }}>
            <img src={imagePreview} alt="Preview" style={{ height: '64px', borderRadius: '8px', border: '1px solid var(--border)', objectFit: 'cover' }} />
            <button onClick={clearImage} style={{ position: 'absolute', top: '-8px', right: '-8px', background: 'var(--text)', color: 'var(--bg)', borderRadius: '50%', width: '20px', height: '20px', fontSize: '10px', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold' }}>✕</button>
          </div>
        )}
        <div className="input-box" style={{ width: '100%', margin: '0' }}>
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
      </div>
      <div className="input-hint">Enter to send  /  Shift+Enter for new line</div>
    </div>
  );
}
