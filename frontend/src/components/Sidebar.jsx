import React from 'react';

export default function Sidebar({ sessions, currentSid, onSelect, onNewChat, onDelete, isOpen, onClose }) {
  return (
    <>
      <div className={`sidebar-overlay ${isOpen ? 'active' : ''}`} onClick={onClose} />
      <aside className={`sidebar ${isOpen ? 'mobile-open' : 'collapsed'}`}>
      <div className="sidebar-top">
        <div className="sidebar-brand">
          <img src="/logo.png" alt="Reya" className="sb-logo" />
          <span className="sb-name">Reya</span>
        </div>
        <button className="new-chat-btn" onClick={onNewChat}>
          <span className="plus">+</span> New Chat
        </button>
      </div>
      <div className="sessions-label">Conversations</div>
      <div className="sessions-list">
        {sessions.length === 0 && (
          <div style={{ padding: '16px 10px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center' }}>
            No conversations yet
          </div>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`session-item${s.id === currentSid ? ' active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <div className="session-dot" />
            <div className="session-info">
              <div className="session-title">{s.title}</div>
              <div className="session-date">{new Date(s.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
            </div>
            <button className="session-del" onClick={(e) => onDelete(e, s.id)} title="Delete">x</button>
          </div>
        ))}
      </div>
      <div className="sidebar-footer">Reya - Personal Assistant</div>
    </aside>
    </>
  );
}
