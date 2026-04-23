'use client';

import { Stage5Result } from '@/lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface PFDViewerProps {
  status: 'running' | 'done';
  result: Stage5Result | null;
}

export function PFDViewer({ status, result }: PFDViewerProps) {
  if (status === 'running') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 320, gap: 16, background: 'white', borderRadius: 8, border: '1px solid var(--border)' }}>
        <div style={{ position: 'relative', width: 56, height: 56 }}>
          <div style={{ width: 56, height: 56, border: '3px solid var(--border)', borderTopColor: 'var(--teal)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
          <div style={{ position: 'absolute', inset: 10, border: '2px solid var(--border)', borderBottomColor: 'var(--amber)', borderRadius: '50%', animation: 'spin 0.7s linear infinite reverse' }} />
        </div>
        <p style={{ fontSize: 13, color: 'var(--text2)', fontFamily: 'var(--font-mono, monospace)' }}>Running DWSIM simulation…</p>
        <p style={{ fontSize: 11, color: 'var(--text3)' }}>Building flowsheet · wiring connections</p>
      </div>
    );
  }

  // No image yet (stage 5 ran but image_path is null)
  if (!result?.image_path) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, gap: 12, background: 'white', borderRadius: 8, border: '1px solid var(--border)', color: 'var(--text3)' }}>
        <p style={{ fontSize: 13 }}>PFD image not available.</p>
        {result?.connections_failed !== undefined && result.connections_failed > 0 && (
          <p style={{ fontSize: 12, color: 'var(--amber)' }}>⚠ {result.connections_failed} connection(s) failed</p>
        )}
      </div>
    );
  }

  // Construct the image URL — image_path is a filesystem path like /app/outputs/xxx.png
  // Serve it via the API's /outputs static route (or directly via API URL prefix)
  const imageName = result.image_path.split('/').pop();
  const imgSrc = `${API_URL}/outputs/${imageName}`;

  return (
    <div style={{ position: 'relative', borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', background: '#f8fbfe' }}>
      {/* Connection stats badge */}
      <div style={{ position: 'absolute', top: 8, right: 8, zIndex: 10, background: result.connections_failed > 0 ? 'rgba(196,105,10,0.1)' : 'rgba(11,122,106,0.1)', border: `1px solid ${result.connections_failed > 0 ? 'rgba(196,105,10,0.35)' : 'rgba(11,122,106,0.35)'}`, borderRadius: 4, padding: '4px 10px', fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: result.connections_failed > 0 ? 'var(--amber)' : 'var(--teal)' }}>
        {result.connections_failed > 0
          ? `⚠ ${result.connections_wired}/${result.connections_wired + result.connections_failed} connections`
          : `✓ ${result.connections_wired}/${result.connections_wired} connections`}
      </div>

      {/* PFD image from DWSIM */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={imgSrc}
        alt="DWSIM Process Flow Diagram"
        style={{ width: '100%', display: 'block', maxHeight: 600, objectFit: 'contain' }}
        onError={(e) => {
          // Fallback: hide broken image and show message
          (e.target as HTMLImageElement).style.display = 'none';
          (e.target as HTMLImageElement).nextElementSibling?.removeAttribute('hidden');
        }}
      />
      <p hidden style={{ padding: 20, fontSize: 13, color: 'var(--text3)', textAlign: 'center' }}>
        Could not load PFD image — check that the API container is running.
      </p>

      {/* Engineering title block */}
      <div style={{ borderTop: '1px solid var(--border)', background: 'white', padding: '8px 16px', display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)' }}>
        <span>PFD-001 Rev.A · AI-generated</span>
        <span>CPD-Pilot v1.0 · DWSIM 8.8.7</span>
      </div>
    </div>
  );
}
