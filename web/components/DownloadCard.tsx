'use client';

import { useState } from 'react';
import { api, Session, Stage5Result } from '@/lib/api';
import { Equipment } from '@/components/ui/Equipment';
import { Btn } from '@/components/ui/Btn';

interface DownloadCardProps {
  session: Session;
  result: Stage5Result;
}

export function DownloadCard({ session, result }: DownloadCardProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');

  const download = async () => {
    setDownloading(true);
    setError('');
    try {
      await api.downloadBundle(session.session_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(false);
    }
  };

  const files = [
    { name: session.project_name.toLowerCase().replace(/\s+/g, '_') + '.dwxmz', type: 'DWSIM Simulation' },
    { name: session.project_name.toLowerCase().replace(/\s+/g, '_') + '_pfd.png', type: 'Flowsheet Image' },
    { name: 'brief.json', type: 'Design Brief' },
  ];

  return (
    <div style={{ padding: 22, background: 'white', border: '1px solid rgba(11,122,106,0.35)', borderRadius: 10, boxShadow: 'var(--shadow-md)', borderTop: '4px solid var(--teal)', marginTop: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
        <div style={{ width: 44, height: 44, borderRadius: 10, background: 'var(--teal-light)', border: '1px solid rgba(11,122,106,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Equipment.Column size={28} color="var(--teal)" />
        </div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>Bundle ready to download</div>
          <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
            3 files · {result.connections_wired} connections wired · DWSIM 8.8.7 compatible
          </div>
        </div>
      </div>

      {files.map((f) => (
        <div key={f.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--surface2)', borderRadius: 6, marginBottom: 6, border: '1px solid var(--border)' }}>
          <span style={{ fontSize: 12, color: 'var(--navy)', fontFamily: 'var(--font-mono, monospace)', fontWeight: 500 }}>{f.name}</span>
          <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>{f.type}</span>
        </div>
      ))}

      {error && (
        <div style={{ marginBottom: 12, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, fontSize: 13, color: 'var(--red)' }}>
          {error}
        </div>
      )}

      <Btn variant="teal" full onClick={download} disabled={downloading}>
        <span style={{ fontSize: 16 }}>↓</span>
        {downloading ? 'Preparing download…' : 'Download Bundle (.zip)'}
      </Btn>
      <p style={{ fontSize: 11, color: 'var(--text3)', marginTop: 10, textAlign: 'center' }}>
        Open .dwxmz in DWSIM Desktop → press Solve to run the simulation
      </p>
    </div>
  );
}
