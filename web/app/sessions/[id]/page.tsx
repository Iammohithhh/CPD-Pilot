'use client';

import { useState, useEffect, useCallback, use } from 'react';
import { api, Session, HealthStatus } from '@/lib/api';
import { STAGE_NAMES } from '@/lib/constants';
import { EngrPaper } from '@/components/ui/EngrPaper';
import { Sidebar } from '@/components/Sidebar';
import { StageView } from '@/components/StageView';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function StudioPage({ params }: PageProps) {
  const { id } = use(params);
  const [session, setSession] = useState<Session | null>(null);
  const [activeStage, setActiveStage] = useState(1);
  const [health, setHealth] = useState<HealthStatus>({ status: 'checking' });
  const [notFound, setNotFound] = useState(false);

  const loadSession = useCallback(async () => {
    try {
      const sess = await api.getSession(id);
      setSession(sess);
      setActiveStage(sess.current_stage);
    } catch {
      setNotFound(true);
    }
  }, [id]);

  useEffect(() => { loadSession(); }, [loadSession]);

  useEffect(() => {
    const poll = async () => {
      const h = await api.checkHealth();
      setHealth(h);
    };
    poll();
    const iv = setInterval(poll, 10_000);
    return () => clearInterval(iv);
  }, []);

  const handleSessionUpdate = useCallback((updated: Session) => {
    setSession(updated);
  }, []);

  const handleApprove = useCallback((updated: Session) => {
    setSession(updated);
    // Auto-advance to next stage after approve
    setActiveStage((prev) => Math.min(prev + 1, 5));
  }, []);

  if (notFound) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)', color: 'var(--text2)' }}>
        Session not found.
      </div>
    );
  }

  if (!session) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 32, height: 32, border: '3px solid var(--border)', borderTopColor: 'var(--teal)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
          <span style={{ fontSize: 13, color: 'var(--text3)' }}>Loading session…</span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', position: 'relative' }}>
      <EngrPaper />
      <div style={{ display: 'flex', width: '100%', height: '100%', position: 'relative', zIndex: 1 }}>
        <Sidebar
          session={session}
          activeStage={activeStage}
          onSelectStage={setActiveStage}
        />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--paper)' }}>
          {/* Top bar */}
          <div style={{ height: 46, background: 'white', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', padding: '0 24px', justifyContent: 'space-between', flexShrink: 0, boxShadow: '0 1px 3px rgba(26,53,84,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              {STAGE_NAMES.map((n, i) => {
                const stageNum = i + 1;
                const available = stageNum <= session.current_stage;
                return (
                  <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <button
                      onClick={() => available && setActiveStage(stageNum)}
                      style={{
                        background: activeStage === stageNum ? 'var(--surface2)' : 'transparent',
                        border: 'none',
                        cursor: available ? 'pointer' : 'default',
                        color: activeStage === stageNum ? 'var(--navy)' : 'var(--text3)',
                        fontSize: 12,
                        fontFamily: 'inherit',
                        fontWeight: activeStage === stageNum ? 600 : 400,
                        padding: '3px 6px',
                        borderRadius: 4,
                        opacity: !available ? 0.35 : 1,
                      }}
                    >
                      {n}
                    </button>
                    {i < 4 && <span style={{ color: 'var(--border2)', fontSize: 10 }}>›</span>}
                  </span>
                );
              })}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <HealthPill label="API" ok={health.status === 'ok'} />
              <HealthPill label="DWSIM" ok={health.status === 'ok'} />
            </div>
          </div>

          {/* Stage content */}
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <StageView
              key={activeStage}
              session={session}
              stageNum={activeStage}
              onSessionUpdate={handleSessionUpdate}
              onApprove={handleApprove}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function HealthPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 7, height: 7, borderRadius: '50%', background: ok ? '#22c55e' : '#ef4444', boxShadow: ok ? '0 0 5px rgba(34,197,94,0.5)' : 'none' }} />
      <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>
        {label} {ok ? 'ready' : 'offline'}
      </span>
    </div>
  );
}
