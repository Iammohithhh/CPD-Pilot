'use client';

import { useRouter } from 'next/navigation';
import { Session, approvedStages } from '@/lib/api';
import { STAGE_NAMES, STAGE_DESCS } from '@/lib/constants';
import { Equipment } from '@/components/ui/Equipment';
import { StageIcons } from '@/components/ui/StageIcons';

interface SidebarProps {
  session: Session;
  activeStage: number;
  onSelectStage: (n: number) => void;
}

export function Sidebar({ session, activeStage, onSelectStage }: SidebarProps) {
  const router = useRouter();
  const approved = approvedStages(session);

  return (
    <div style={{ width: 264, flexShrink: 0, background: 'white', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', height: '100%', boxShadow: '2px 0 8px rgba(26,53,84,0.06)' }}>
      {/* Logo bar */}
      <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={() => router.push('/')}
          style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14, color: 'var(--text3)', fontFamily: 'inherit' }}
        >
          <span style={{ fontSize: 13 }}>←</span>
          <span style={{ fontSize: 12 }}>All Projects</span>
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: 'var(--navy)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Equipment.Column size={18} color="rgba(0,201,167,0.9)" />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--navy)', lineHeight: 1.2, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {session.project_name || 'Untitled'}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)', marginTop: 2 }}>
              {session.session_id.slice(0, 16)}…
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline stepper */}
      <div style={{ flex: 1, overflow: 'auto', padding: '12px 10px' }}>
        <div style={{ fontSize: 10, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)', padding: '0 8px', marginBottom: 10, letterSpacing: 0.5 }}>
          WORKFLOW STAGES
        </div>
        {STAGE_NAMES.map((name, i) => {
          const n = i + 1;
          const isApproved = approved.includes(n);
          const isActive = activeStage === n;
          const available = n <= session.current_stage;
          const locked = !available;
          const Icon = StageIcons[i];
          return (
            <div key={n} style={{ position: 'relative' }}>
              {i < 4 && (
                <div style={{ position: 'absolute', left: 21, top: 42, width: 1.5, height: 24, background: isApproved ? 'var(--teal)' : 'var(--border)', zIndex: 0 }} />
              )}
              <div
                onClick={() => available && onSelectStage(n)}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  padding: '10px 10px',
                  borderRadius: 8,
                  cursor: available ? 'pointer' : 'default',
                  background: isActive ? '#e6f4f1' : 'transparent',
                  border: isActive ? '1px solid rgba(11,122,106,0.3)' : '1px solid transparent',
                  opacity: locked ? 0.4 : 1,
                  transition: 'all 0.12s',
                  marginBottom: 4,
                }}
              >
                <div style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  flexShrink: 0,
                  zIndex: 1,
                  marginTop: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: isApproved ? 'var(--teal)' : isActive ? 'white' : 'var(--surface2)',
                  border: isApproved ? 'none' : isActive ? '2px solid var(--teal)' : '2px solid var(--border)',
                  boxShadow: isActive ? '0 0 0 3px rgba(11,122,106,0.15)' : 'none',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono, monospace)',
                  color: isApproved ? 'white' : isActive ? 'var(--teal)' : 'var(--text3)',
                  fontWeight: 700,
                }}>
                  {isApproved ? '✓' : n}
                </div>
                <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: isActive ? 'var(--teal)' : isApproved ? 'var(--navy)' : 'var(--text2)' }}>
                      {name}
                    </span>
                    <Icon active={isActive || isApproved} />
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2, lineHeight: 1.4 }}>{STAGE_DESCS[i]}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar + decoration */}
      <div style={{ padding: '14px 18px', borderTop: '1px solid var(--border)', background: 'var(--surface2)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text3)' }}>Pipeline progress</span>
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: 'var(--teal)', fontWeight: 600 }}>
            {approved.length}/5
          </span>
        </div>
        <div style={{ height: 5, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${(approved.length / 5) * 100}%`, background: 'linear-gradient(90deg,var(--teal),var(--teal-mid))', borderRadius: 3, transition: 'width 0.5s ease' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 14, opacity: 0.25 }}>
          <Equipment.Reactor size={22} color="var(--navy)" />
          <Equipment.Column size={18} color="var(--navy)" />
          <Equipment.HeatExchanger size={26} color="var(--navy)" />
          <Equipment.Vessel size={16} color="var(--navy)" />
        </div>
      </div>
    </div>
  );
}
