import React from 'react';

const QUICK_ACTIONS = [
  {
    label: 'Plan my day',
    prompt: 'Help me plan my day',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
    ),
  },
  {
    label: 'Write an email',
    prompt: 'Write an email for me',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
      </svg>
    ),
  },
  {
    label: 'Explain something',
    prompt: 'Explain a concept to me',
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    ),
  },
  {
    label: 'Just chat',
    prompt: "Let's just have a casual chat",
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
    ),
  },
];

export default function Welcome({ onStart }) {
  return (
    <div className="welcome">
      <img src="/logo.png" alt="Reya" className="w-logo" />
      <h2>Hi Reshi, I'm Reya</h2>
      <p className="tagline">Your personal assistant — always here, always ready.</p>
      <div className="quick-grid">
        {QUICK_ACTIONS.map(({ label, prompt, icon }) => (
          <button key={label} className="quick-card" onClick={() => onStart(prompt)}>
            <span className="qc-icon">{icon}</span>
            <span className="qc-label">{label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
