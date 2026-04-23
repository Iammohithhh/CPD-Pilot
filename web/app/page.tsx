'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, Session, approvedStages } from '@/lib/api';
import { STAGE_NAMES, STAGE_DESCS } from '@/lib/constants';
import { EngrPaper } from '@/components/ui/EngrPaper';
import { Equipment } from '@/components/ui/Equipment';
import { Btn } from '@/components/ui/Btn';

function stageStatusColor(sess: Session): string {
  const n = approvedStages(sess).length;
  if (n === 5) return 'var(--teal)';
  if (n >= 2) return 'var(--amber)';
  return 'var(--blue)';
}

function ApprovalRings({ session }: { session: Session }) {
  const approved = approvedStages(session);
  return (
    <div style={{ display: 'flex', gap: 3 }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <div
          key={n}
          style={{
            width: 22,
            height: 22,
            borderRadius: '50%',
            background: approved.includes(n) ? 'var(--teal)' : 'var(--surface2)',
            border: `1.5px solid ${approved.includes(n) ? 'var(--teal)' : 'var(--border)'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 9,
            color: approved.includes(n) ? 'white' : 'var(--text3)',
            fontFamily: 'var(--font-mono, monospace)',
            fontWeight: 700,
          }}
        >
          {approved.includes(n) ? '✓' : n}
        </div>
      ))}
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const list = await api.listSessions();
      setSessions(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const sess = await api.createSession(name.trim());
      router.push(`/sessions/${sess.session_id}`);
    } catch (e) {
      setError(String(e));
      setCreating(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', position: 'relative', overflowX: 'hidden' }}>
      <EngrPaper />

      {/* Decorative equipment background */}
      <div style={{ position: 'fixed', right: -40, top: 60, opacity: 0.06, pointerEvents: 'none', zIndex: 0 }}>
        <Equipment.Column size={200} color="var(--navy)" />
      </div>
      <div style={{ position: 'fixed', right: 160, bottom: 40, opacity: 0.05, pointerEvents: 'none', zIndex: 0 }}>
        <Equipment.Reactor size={160} color="var(--navy)" />
      </div>
      <div style={{ position: 'fixed', left: 20, bottom: 80, opacity: 0.05, pointerEvents: 'none', zIndex: 0 }}>
        <Equipment.HeatExchanger size={180} color="var(--navy)" />
      </div>
      <div style={{ position: 'fixed', left: 120, top: 100, opacity: 0.04, pointerEvents: 'none', zIndex: 0 }}>
        <Equipment.Vessel size={100} color="var(--navy)" />
      </div>

      <div style={{ position: 'relative', zIndex: 1 }}>
        {/* Header */}
        <div style={{ background: 'white', borderBottom: '1px solid var(--border)', padding: '0 48px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: 'var(--shadow)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 34, height: 34, borderRadius: 9, background: 'var(--navy)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Equipment.Column size={18} color="rgba(0,201,167,0.9)" />
            </div>
            <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--navy)', letterSpacing: '-0.4px' }}>CPD-Pilot</span>
            <span style={{ fontSize: 10, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)', background: 'var(--surface2)', padding: '2px 7px', borderRadius: 8, border: '1px solid var(--border)' }}>v1.0</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 5px #22c55e' }} />
            <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>API healthy</span>
          </div>
        </div>

        <div style={{ maxWidth: 860, margin: '0 auto', padding: '48px 24px 0' }}>
          {/* Hero */}
          <div style={{ marginBottom: 44 }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 14px', background: 'white', border: '1px solid rgba(11,122,106,0.3)', borderRadius: 20, marginBottom: 18, boxShadow: '0 1px 4px rgba(11,122,106,0.1)' }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--teal)' }} />
              <span style={{ fontSize: 11, color: 'var(--teal)', fontFamily: 'var(--font-mono, monospace)', fontWeight: 500 }}>AI-ASSISTED CHEMICAL PROCESS DESIGN</span>
            </div>
            <h1 style={{ fontSize: 38, fontWeight: 700, letterSpacing: '-1px', marginBottom: 14, lineHeight: 1.1, color: 'var(--navy)' }}>
              From brief to flowsheet,<br />
              <span style={{ color: 'var(--teal)' }}>in 5 gated stages.</span>
            </h1>
            <p style={{ fontSize: 15, color: 'var(--text2)', maxWidth: 500, lineHeight: 1.75 }}>
              Brief → Routes → Thermo → BFD → DWSIM PFD. Claude designs, you approve.
              Download .dwxmz + PFD image when done.
            </p>
            {/* Mini pipeline */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 20, flexWrap: 'wrap' }}>
              {STAGE_NAMES.map((n, i) => (
                <span key={n} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <div style={{ padding: '5px 14px', background: 'white', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, color: 'var(--navy)', fontFamily: 'var(--font-mono, monospace)', fontWeight: 500, boxShadow: 'var(--shadow)' }}>
                    {i + 1}. {n}
                  </div>
                  {i < 4 && <div style={{ width: 20, height: 1.5, background: 'var(--border)', borderRadius: 1 }} />}
                </span>
              ))}
            </div>
          </div>

          {/* New project */}
          <div style={{ padding: 24, background: 'white', border: '1px solid var(--border)', borderRadius: 12, boxShadow: 'var(--shadow-md)', marginBottom: 36 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <div style={{ width: 3, height: 18, background: 'var(--navy)', borderRadius: 2 }} />
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--navy)' }}>New Project</h3>
            </div>
            {error && (
              <div style={{ marginBottom: 12, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, fontSize: 13, color: 'var(--red)' }}>
                {error}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && create()}
                placeholder="e.g. Methanol Synthesis, Ammonia Loop, Ethylene Glycol…"
                style={{ flex: 1, height: 42, background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 7, padding: '0 14px', color: 'var(--text)', fontFamily: 'inherit', fontSize: 13 }}
                onFocus={(e) => (e.target.style.borderColor = 'var(--teal)')}
                onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
              />
              <Btn variant="navy" onClick={create} disabled={!name.trim() || creating}>
                {creating ? '…' : '+ New Project'}
              </Btn>
            </div>
          </div>

          {/* Session list */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 3, height: 16, background: 'var(--text3)', borderRadius: 2 }} />
                <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text2)' }}>Recent Projects</h3>
              </div>
              <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>
                {loading ? '…' : `${sessions.length} sessions`}
              </span>
            </div>

            {loading ? (
              <div style={{ textAlign: 'center', padding: 40, color: 'var(--text3)', fontSize: 13 }}>Loading…</div>
            ) : sessions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: 'var(--text3)', fontSize: 13, background: 'white', borderRadius: 10, border: '1px dashed var(--border)' }}>
                No projects yet — create one above.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {sessions.map((s) => (
                  <div
                    key={s.session_id}
                    onClick={() => router.push(`/sessions/${s.session_id}`)}
                    style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '16px 20px', background: 'white', border: '1px solid var(--border)', borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s', boxShadow: 'var(--shadow)' }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--navy)'; e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = 'var(--shadow-md)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'var(--shadow)'; }}
                  >
                    <div style={{ width: 42, height: 42, borderRadius: 10, background: 'var(--navy)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Equipment.Column size={22} color="rgba(0,201,167,0.9)" />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--navy)', marginBottom: 3 }}>{s.project_name || 'Untitled'}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: stageStatusColor(s) }}>
                          {STAGE_NAMES[s.current_stage - 1]} — Stage {s.current_stage}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text3)' }}>·</span>
                        <span style={{ fontSize: 11, color: 'var(--text3)' }}>
                          {new Date(s.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </span>
                      </div>
                    </div>
                    <ApprovalRings session={s} />
                    <span style={{ color: 'var(--text3)', fontSize: 16 }}>›</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={{ height: 60 }} />
        </div>
      </div>

      {/* Bottom bar */}
      <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 44, background: 'rgba(248,249,252,0.92)', backdropFilter: 'blur(10px)', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, zIndex: 10 }}>
        {STAGE_NAMES.map((n, i) => (
          <span key={n} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 16, height: 16, borderRadius: '50%', background: 'var(--surface2)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)', fontWeight: 700 }}>{i + 1}</div>
              <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>{n}</span>
            </div>
            {i < 4 && <span style={{ color: 'var(--border2)', fontSize: 11, fontFamily: 'var(--font-mono, monospace)' }}>→</span>}
          </span>
        ))}
      </div>
    </div>
  );
}
