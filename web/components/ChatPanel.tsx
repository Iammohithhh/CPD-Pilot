'use client';

interface ChatPanelProps {
  text: string;
  isDone: boolean;
  accentColor?: string;
}

export function ChatPanel({ text, isDone, accentColor = 'var(--navy)' }: ChatPanelProps) {
  const lines = text.split('\n');

  return (
    <div style={{ fontSize: 13, lineHeight: 1.75, color: 'var(--text)', wordBreak: 'break-word' }}>
      {lines.map((line, i) => {
        // h2
        if (line.startsWith('## ')) {
          return (
            <h3 key={i} style={{ fontSize: 15, fontWeight: 700, color: 'var(--navy)', marginBottom: 10, marginTop: i > 0 ? 18 : 0, fontFamily: 'inherit', borderBottom: '2px solid var(--border)', paddingBottom: 6 }}>
              {line.slice(3)}
            </h3>
          );
        }
        // h3
        if (line.startsWith('### ')) {
          return (
            <h4 key={i} style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy2)', marginBottom: 6, marginTop: 14, fontFamily: 'inherit' }}>
              {line.slice(4)}
            </h4>
          );
        }
        // hr
        if (line.startsWith('---')) {
          return <hr key={i} style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '14px 0' }} />;
        }
        // table row
        if (line.startsWith('|')) {
          const cells = line.split('|').filter(Boolean).map((c) => c.trim());
          const isSep = /^\|[-| ]+\|$/.test(line);
          const isHeader = !isSep && i + 1 < lines.length && /^\|[-| ]+\|$/.test(lines[i + 1] ?? '');
          if (isSep) return null;
          return (
            <div key={i} style={{ display: 'flex', background: isHeader ? 'var(--navy)' : i % 2 === 0 ? 'white' : 'var(--surface2)', borderBottom: '1px solid var(--border)' }}>
              {cells.map((c, j) => (
                <div
                  key={j}
                  style={{ flex: j === 0 ? '0 0 140px' : 1, padding: '6px 12px', fontSize: 12, color: isHeader ? 'white' : 'var(--text2)', fontFamily: 'var(--font-mono, monospace)', borderRight: j < cells.length - 1 ? '1px solid var(--border)' : '', fontWeight: isHeader ? 600 : 400 }}
                >
                  {c.replace(/\*\*/g, '')}
                </div>
              ))}
            </div>
          );
        }
        // bullet
        if (line.startsWith('- ') || line.startsWith('• ')) {
          return (
            <li key={i} style={{ marginLeft: 20, marginBottom: 4, color: 'var(--text2)', fontFamily: 'inherit', fontSize: 13 }}>
              {line.slice(2).replace(/\*\*/g, '')}
            </li>
          );
        }
        // bold inline + plain paragraph
        const withBold = line.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
        return line ? (
          <p key={i} style={{ color: 'var(--text2)', marginBottom: 4, fontFamily: 'inherit', fontSize: 13 }} dangerouslySetInnerHTML={{ __html: withBold }} />
        ) : (
          <div key={i} style={{ height: 7 }} />
        );
      })}
      {/* Blinking caret while streaming */}
      {!isDone && (
        <span
          style={{ display: 'inline-block', width: 8, height: 14, background: accentColor, borderRadius: 1, verticalAlign: 'middle', marginLeft: 2 }}
          className="animate-blink"
        />
      )}
    </div>
  );
}
