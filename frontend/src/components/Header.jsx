import React from 'react';
import axios from 'axios';

function Header({ title, onMenuClick, theme, toggleTheme }) {
  return (
    <header>
      <img 
        src="/logo.png" 
        alt="Reya" 
        className="h-logo clickable" 
        onClick={onMenuClick}
        title="Open menu"
      />
      <div className="h-info">
        <h1>{title}</h1>
        <p>Reshi's Personal Assistant</p>
      </div>
      
      <button 
        className="theme-toggle" 
        onClick={toggleTheme} 
        title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
      >
        {theme === 'light' ? '🌙' : '☀️'}
      </button>

      <div className="status-pill">
        <div className="status-led" />
        <span>Online</span>
      </div>
    </header>
  );
}

export default Header;
