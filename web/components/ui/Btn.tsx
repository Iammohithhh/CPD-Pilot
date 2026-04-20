'use client';

import React from 'react';

type BtnVariant = 'teal' | 'amber' | 'ghost' | 'navy';
type BtnSize = 'sm' | 'md';

interface BtnProps {
  variant?: BtnVariant;
  size?: BtnSize;
  full?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit';
}

const variantStyles: Record<BtnVariant, React.CSSProperties> = {
  teal: { background: 'var(--teal)', color: 'white', border: 'none' },
  amber: { background: 'white', color: 'var(--amber)', border: '1px solid var(--amber)' },
  ghost: { background: 'white', color: 'var(--text2)', border: '1px solid var(--border)' },
  navy: { background: 'var(--navy)', color: 'white', border: 'none' },
};

export function Btn({ variant = 'teal', size = 'md', full, children, onClick, disabled, type = 'button' }: BtnProps) {
  const pad = size === 'sm' ? '7px 14px' : '10px 20px';
  const fs = size === 'sm' ? 12 : 13;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: pad,
        borderRadius: 6,
        fontSize: fs,
        fontFamily: 'var(--font-sans, sans-serif)',
        fontWeight: 500,
        cursor: 'pointer',
        transition: 'all 0.15s',
        width: full ? '100%' : undefined,
        justifyContent: full ? 'center' : undefined,
        ...variantStyles[variant],
      }}
    >
      {children}
    </button>
  );
}
