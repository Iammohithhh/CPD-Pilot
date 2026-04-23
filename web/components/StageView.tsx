'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { api, Session, Stage5Result, approvedStages } from '@/lib/api';
import { STAGE_NAMES, STAGE_DESCS, STAGE_COLORS, EXAMPLE_INPUT, MAX_REFINEMENTS } from '@/lib/constants';
import { Btn } from '@/components/ui/Btn';
import { Equipment } from '@/components/ui/Equipment';
import { ChatPanel } from '@/components/ChatPanel';
import { StageGate } from '@/components/StageGate';
import { DownloadCard } from '@/components/DownloadCard';
import { BFDDiagram } from '@/components/BFDDiagram';
import { PFDViewer } from '@/components/PFDViewer';

interface StageViewProps {
  session: Session;
  stageNum: number;
  onSessionUpdate: (s: Session) => void;
  onApprove: (s: Session) => void;
}

export function StageView({ session, stageNum, onSessionUpdate, onApprove }: StageViewProps) {
  const [streamed, setStreamed] = useState('');
  const [isDone, setIsDone] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState('');
  const [input, setInput] = useState('');
  const [hasRun, setHasRun] = useState(false);
  const [pfdResult, setPfdResult] = useState<Stage5Result | null>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  const approved = approvedStages(session);
  const isApproved = approved.includes(stageNum);
  const color = STAGE_COLORS[stageNum] ?? 'var(--navy)';
  const existingArtifact = session.stage_data?.[String(stageNum)]?.artifact;
  const existingRaw = (existingArtifact as { raw?: string } | null)?.raw ?? '';
  const refinements = session.stage_data?.[String(stageNum)]?.feedback ? 1 : 0;

  // Restore previous run output if artifact exists
  useEffect(() => {
    if (existingRaw) {
      setStreamed(existingRaw);
      setIsDone(true);
      setHasRun(true);
    }
    if (stageNum === 5 && existingArtifact && 'dwxmz_path' in existingArtifact) {
      setPfdResult(existingArtifact as unknown as Stage5Result);
      setHasRun(true);
      setIsDone(true);
    }
  }, [stageNum]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll while streaming
  useEffect(() => {
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [streamed]);

  const run = useCallback(async () => {
    setError('');
    setHasRun(true);
    setIsRunning(true);
    setStreamed('');
    setIsDone(false);

    if (stageNum === 5) {
      try {
        const result = await api.runStage5(session.session_id);
        setPfdResult(result);
        setIsDone(true);
        // Refresh session state from server so gate/download sees updated artifact
        const updated = await api.getSession(session.session_id);
        onSessionUpdate(updated);
      } catch (e) {
        setError(String(e));
      } finally {
        setIsRunning(false);
      }
      return;
    }

    try {
      const body = stageNum === 1 ? { user_input: input } : {};
      const chunks: string[] = [];
      for await (const token of api.runStage(session.session_id, stageNum, body)) {
        chunks.push(token);
        setStreamed(chunks.join(''));
      }
      setIsDone(true);
      const updated = await api.getSession(session.session_id);
      onSessionUpdate(updated);
    } catch (e) {
      setError(String(e));
      setIsDone(true);
    } finally {
      setIsRunning(false);
    }
  }, [session.session_id, stageNum, input, onSessionUpdate]);

  const handleRefine = useCallback(async (feedback: string) => {
    setError('');
    try {
      const updated = await api.refineStage(session.session_id, stageNum, feedback);
      onSessionUpdate(updated);
      // Re-run after storing feedback
      setTimeout(() => run(), 100);
    } catch (e) {
      setError(String(e));
    }
  }, [session.session_id, stageNum, onSessionUpdate, run]);

  const handleApprove = useCallback(async () => {
    setError('');
    try {
      const { session: updated } = await api.approveStage(session.session_id, stageNum);
      onApprove(updated);
    } catch (e) {
      setError(String(e));
    }
  }, [session.session_id, stageNum, onApprove]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }} className="animate-fade-in">
      {/* Stage header */}
      <div style={{ padding: '20px 28px 16px', borderBottom: '1px solid var(--border)', background: 'white', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: color, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ color: 'white', fontSize: 13, fontFamily: 'var(--font-mono, monospace)', fontWeight: 700 }}>{stageNum}</span>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--navy)' }}>{STAGE_NAMES[stageNum - 1]}</h2>
              <span style={{ fontSize: 10, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)', background: 'var(--surface2)', padding: '2px 8px', borderRadius: 10, border: '1px solid var(--border)' }}>STAGE {stageNum}/5</span>
              {isApproved && <span style={{ fontSize: 10, fontFamily: 'var(--font-mono, monospace)', background: 'var(--teal-light)', color: 'var(--teal)', padding: '2px 8px', borderRadius: 10, border: '1px solid rgba(11,122,106,0.2)' }}>✓ APPROVED</span>}
            </div>
            <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>{STAGE_DESCS[stageNum - 1]}</p>
          </div>
        </div>
      </div>

      <div ref={outputRef} style={{ flex: 1, overflow: 'auto', padding: '24px 28px' }}>
        {error && (
          <div style={{ marginBottom: 16, padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 7, fontSize: 13, color: 'var(--red)' }}>
            {error}
          </div>
        )}

        {/* Stage 1 — text input */}
        {stageNum === 1 && !hasRun && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ padding: 20, background: 'white', border: '1px solid var(--border)', borderRadius: 10, boxShadow: 'var(--shadow)', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Equipment.Reactor size={22} color="var(--navy2)" />
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)' }}>Describe your process</span>
              </div>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={`e.g. "${EXAMPLE_INPUT}"`}
                style={{ width: '100%', height: 100, background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 14px', color: 'var(--text)', fontFamily: 'var(--font-mono, monospace)', fontSize: 13, resize: 'none', lineHeight: 1.6 }}
                onFocus={(e) => (e.target.style.borderColor = 'var(--teal)')}
                onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
              />
              <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <Btn variant="navy" onClick={run} disabled={!input.trim() || isRunning}>▶ Generate Brief</Btn>
                <button
                  onClick={() => setInput(EXAMPLE_INPUT)}
                  style={{ background: 'none', border: '1px dashed var(--border2)', borderRadius: 6, padding: '9px 14px', fontSize: 12, color: 'var(--text3)', cursor: 'pointer', fontFamily: 'var(--font-mono, monospace)' }}
                >
                  Use example
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Stages 2–4 — run button with prior stage chips */}
        {stageNum > 1 && stageNum < 5 && !hasRun && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ padding: 18, background: 'white', border: '1px solid var(--border)', borderRadius: 10, boxShadow: 'var(--shadow)', marginBottom: 14 }}>
              <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 12, fontWeight: 500 }}>Inputs from approved stages:</p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
                {approved.filter((s) => s < stageNum).map((s) => (
                  <span key={s} style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)', background: 'var(--teal-light)', color: 'var(--teal)', padding: '3px 10px', borderRadius: 10, border: '1px solid rgba(11,122,106,0.2)' }}>
                    Stage {s} — {STAGE_NAMES[s - 1]} ✓
                  </span>
                ))}
              </div>
              <Btn variant="navy" onClick={run} disabled={isRunning}>▶ Run {STAGE_NAMES[stageNum - 1]}</Btn>
            </div>
          </div>
        )}

        {/* Stage 5 — DWSIM build card */}
        {stageNum === 5 && !hasRun && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ padding: 20, background: 'white', border: '1px solid var(--border)', borderRadius: 10, boxShadow: 'var(--shadow)', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                <div style={{ flexShrink: 0, marginTop: 2 }}><Equipment.Column size={32} color="var(--navy)" /></div>
                <div>
                  <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--navy)', marginBottom: 6 }}>Build DWSIM Flowsheet</p>
                  <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 8 }}>All 4 stages approved. Claude will build the .dwxmz flowsheet and export a PFD image. No DWSIM install required — it runs in the container.</p>
                  <p style={{ fontSize: 12, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>Estimated time: ~30s</p>
                </div>
              </div>
              <div style={{ marginTop: 14 }}>
                <Btn variant="navy" onClick={run} disabled={isRunning}>⚙ Build DWSIM Flowsheet</Btn>
              </div>
            </div>
          </div>
        )}

        {/* Streaming indicator */}
        {isRunning && stageNum < 5 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: 'var(--blue-light)', border: '1px solid rgba(30,111,181,0.2)', borderRadius: 7, marginBottom: 14 }}>
            <div style={{ width: 14, height: 14, border: '2px solid rgba(30,111,181,0.3)', borderTopColor: 'var(--blue)', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: 'var(--blue)', fontFamily: 'var(--font-mono, monospace)' }}>Streaming from Claude API…</span>
          </div>
        )}

        {/* BFD diagram — shown for Stage 4 after run */}
        {stageNum === 4 && hasRun && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <div style={{ width: 3, height: 16, background: 'var(--amber)', borderRadius: 2 }} />
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)', fontWeight: 600, letterSpacing: 0.5 }}>BLOCK FLOW DIAGRAM</span>
            </div>
            <div style={{ background: 'white', border: '1px solid var(--border)', borderRadius: 10, boxShadow: 'var(--shadow)', overflow: 'hidden' }}>
              <BFDDiagram />
            </div>
          </div>
        )}

        {/* PFD viewer — shown for Stage 5 after run */}
        {stageNum === 5 && hasRun && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <div style={{ width: 3, height: 16, background: 'var(--navy)', borderRadius: 2 }} />
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)', fontWeight: 600, letterSpacing: 0.5 }}>PROCESS FLOW DIAGRAM</span>
            </div>
            <PFDViewer status={isRunning ? 'running' : 'done'} result={pfdResult} />
          </div>
        )}

        {/* Streaming output text */}
        {hasRun && streamed && stageNum !== 4 && (
          <div style={{ padding: 20, background: 'white', border: '1px solid var(--border)', borderRadius: 10, boxShadow: 'var(--shadow)', marginBottom: 20, borderTop: `3px solid ${color}` }}>
            <ChatPanel text={streamed} isDone={isDone} accentColor={color} />
          </div>
        )}

        {/* Stage 4: show text summary below BFD */}
        {stageNum === 4 && hasRun && streamed && (
          <div style={{ padding: 20, background: 'white', border: '1px solid var(--border)', borderRadius: 10, boxShadow: 'var(--shadow)', marginBottom: 20, borderTop: `3px solid ${color}` }}>
            <ChatPanel text={streamed} isDone={isDone} accentColor={color} />
          </div>
        )}

        {/* Stage gate */}
        {isDone && !isApproved && !isRunning && (
          <StageGate
            stage={stageNum}
            refinements={refinements}
            maxRefinements={MAX_REFINEMENTS}
            onApprove={handleApprove}
            onRefine={handleRefine}
          />
        )}

        {/* Download card for Stage 5 */}
        {stageNum === 5 && isApproved && pfdResult && (
          <DownloadCard session={session} result={pfdResult} />
        )}

        {/* Approved re-run note for stages 1–4 */}
        {isApproved && stageNum < 5 && (
          <div style={{ marginTop: 8, padding: '10px 14px', background: 'var(--teal-light)', borderRadius: 6, border: '1px solid rgba(11,122,106,0.2)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--teal)' }}>✓ Approved — downstream stages use this output</span>
            <button
              onClick={() => { setHasRun(false); setStreamed(''); setIsDone(false); }}
              style={{ background: 'none', border: '1px solid rgba(11,122,106,0.3)', borderRadius: 5, padding: '4px 12px', fontSize: 11, color: 'var(--teal)', cursor: 'pointer', fontFamily: 'var(--font-mono, monospace)' }}
            >
              Re-run
            </button>
          </div>
        )}

        <div style={{ height: 40 }} />
      </div>
    </div>
  );
}
