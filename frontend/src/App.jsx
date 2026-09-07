import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { marked } from 'marked';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import InputBar from './components/InputBar';
import Welcome from './components/Welcome';

function App() {
  const [sessions, setSessions] = useState([]);
  const [currentSid, setCurrentSid] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typing, setTyping] = useState(false);
  const [headerTitle, setHeaderTitle] = useState('Reya');
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
  const chatEndRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  useEffect(() => {
    const initLoad = async () => {
      try {
        const res = await axios.get('/sessions');
        const data = res.data.sessions || [];
        setSessions(data);
        if (data.length > 0) {
          await switchSession(data[0].id, data);
        } else {
          setLoading(false);
        }
      } catch (e) {
        console.error('Failed to load initial sessions', e);
        setLoading(false);
      }
    };
    initLoad();
  }, []);

  const switchSession = async (sid, sessionsList = sessions) => {
    setLoading(true);
    setCurrentSid(sid);
    const sess = sessionsList.find((s) => s.id === sid);
    if (sess) setHeaderTitle(sess.title);
    try {
      const res = await axios.get(`/sessions/${sid}/messages`);
      setMessages(res.data.messages || []);
    } catch (e) {
      console.error('Failed to load messages', e);
    }
    setLoading(false);
  };

  const createNewChat = async () => {
    try {
      const res = await axios.post('/sessions', { title: 'New Chat' });
      const newSid = res.data.id;
      setHeaderTitle('New Chat');
      setCurrentSid(newSid);
      setMessages([]);
      axios.get('/sessions').then(r => setSessions(r.data.sessions || []));
      return newSid;
    } catch (e) {
      console.error('Failed to create session', e);
    }
  };

  const deleteSession = async (e, sid) => {
    e.stopPropagation();
    if (!window.confirm('Delete this conversation?')) return;
    try {
      await axios.delete(`/sessions/${sid}`);
      if (currentSid === sid) {
        setCurrentSid(null);
        setMessages([]);
        setHeaderTitle('Reya');
      }
      axios.get('/sessions').then(r => {
        const data = r.data.sessions || [];
        setSessions(data);
        if (currentSid === sid && data.length > 0) {
          switchSession(data[0].id, data);
        }
      });
    } catch (e) {
      console.error('Failed to delete session', e);
    }
  };

  const sendMessage = async (text, image = null) => {
    let activeSid = currentSid;
    if (!activeSid) {
      activeSid = await createNewChat();
    }
    if ((!text && !image) || !activeSid) return;
    
    // Display the image in the user's message bubble
    let displayContent = text;
    if (image) {
      displayContent = text ? text + "\n\n![User Image](" + image + ")" : "![User Image](" + image + ")";
    }
    
    const userMsg = { role: 'user', content: displayContent, created_at: new Date().toISOString() };
    const botMsg = { role: 'assistant', content: '', created_at: new Date().toISOString() };
    
    setMessages((prev) => [...prev, userMsg, botMsg]);
    setTyping(true);
    
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: activeSid, message: text, image: image })
      });
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let done = false;
      let buffer = '';
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          let newlineIdx;
          while ((newlineIdx = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, newlineIdx);
            buffer = buffer.slice(newlineIdx + 2);
            
            const lines = block.split('\n');
            for (let line of lines) {
              if (line.startsWith('data: ')) {
                const dataStr = line.slice(6);
                try {
                  const data = JSON.parse(dataStr);
                  if (data.event === 'title') {
                    setHeaderTitle(data.title);
                    axios.get('/sessions').then(r => setSessions(r.data.sessions || []));
                  } else if (data.event === 'chunk') {
                    setTyping(false);
                    setMessages(prev => {
                       const newMsgs = [...prev];
                       newMsgs[newMsgs.length - 1].content += data.text;
                       return newMsgs;
                    });
                  } else if (data.event === 'error') {
                     setTyping(false);
                     setMessages(prev => {
                       const newMsgs = [...prev];
                       newMsgs[newMsgs.length - 1].content += "\n\n**Error:** " + data.text;
                       return newMsgs;
                    });
                  } else if (data.event === 'done') {
                     setTyping(false);
                  }
                } catch (e) {
                  console.error("Failed to parse stream event", e, line);
                }
              }
            }
          }
        }
      }
    } catch (err) {
      console.error('Chat error', err);
    } finally {
      setMessages(prev => {
        const newMsgs = [...prev];
        if (newMsgs.length > 0 && newMsgs[newMsgs.length - 1].role === 'assistant' && !newMsgs[newMsgs.length - 1].content) {
          newMsgs[newMsgs.length - 1].content = "**Error:** The AI service timed out or is overloaded (API limits reached). Please try again.";
        }
        return newMsgs;
      });
      setTyping(false);
    }
  };

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, typing]);

  return (
    <div className="layout">
      <Sidebar
        sessions={sessions}
        currentSid={currentSid}
        onSelect={(id) => { switchSession(id); if (window.innerWidth <= 768) setSidebarOpen(false); }}
        onNewChat={() => { createNewChat(); if (window.innerWidth <= 768) setSidebarOpen(false); }}
        onDelete={deleteSession}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="main">
        <Header 
          title={headerTitle} 
          onMenuClick={() => setSidebarOpen(!sidebarOpen)} 
          theme={theme} 
          toggleTheme={toggleTheme} 
        />
        <div className="chat-area" id="chatArea">
          {loading ? (
            <div className="loading-history">
              <div className="spinner" />
              <span>Loading...</span>
            </div>
          ) : messages.length ? (
            messages.map((msg, idx) => (
              <Message key={idx} role={msg.role} content={msg.content} time={msg.created_at} />
            ))
          ) : (
            <Welcome onStart={sendMessage} />
          )}
          <div ref={chatEndRef} />
        </div>
        <InputBar onSend={sendMessage} />
      </div>
    </div>
  );
}

const THINKING_MESSAGES = [
  "Rolling my virtual eyes... 🙄",
  "Brewing some premium sarcasm... ☕",
  "Judging your life choices... just a sec... 🦦",
  "Finding the perfect comeback... 💅",
  "Waking up the brain cells... 🧠",
  "Calculating the exact amount of sass required... 🧮",
  "Pretending to think deeply... 🪩"
];

function Message({ role, content }) {
  const isUser = role === 'user';
  const [thinkingText] = useState(() => THINKING_MESSAGES[Math.floor(Math.random() * THINKING_MESSAGES.length)]);
  
  const isThinking = !isUser && !content;
  const __html = isThinking ? '' : marked.parse(content);

  return (
    <div className={`message ${isUser ? 'user' : 'bot'}`}>
      {!isUser && (
        <div className="bot-avatar-wrap">
          <img src="/logo.png" alt="Reya" className="bot-avatar" />
        </div>
      )}
      <div className="bubble-content">
        {isThinking ? (
          <div className="bubble" style={{ color: 'var(--text-muted)', fontStyle: 'italic', animation: 'pulse 1.5s infinite' }}>
            {thinkingText}
          </div>
        ) : (
          <div className="bubble" dangerouslySetInnerHTML={{ __html }} />
        )}
      </div>
    </div>
  );
}

export default App;
