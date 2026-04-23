'use client';

import { useState } from 'react';
import { STAGE_NAMES } from '@/lib/constants';
import { Btn } from '@/components/ui/Btn';

interface StageGateProps {
  stage: number;
  refinements: number;
  maxRefinements: number;
  onApprove: () => void;
  onRefine: (feedback: string) => void;
}

export function StageGate({ stage, refinements, maxRefinements, onApprove, onRefine }: StageGateProps) {
  const [feedback, setFeedback] = useState('');
  const [showRefine, setShowRefine] = useState(false);
  const remaining = maxRefinements - refinements;

  return (
    <div style={{ marginTop: 20, padding: 18, background: '#f8fbfe', border: '1px solid var(--border)', borderRadius: 8, borderLeft: '4px solid var(--navy)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--amber)' }} />
        <span style={{ fontSize: 12, fontFamily: 'var(--font-mono, monospace)', color: 'var(--text3)' }}>
          GATE {stage}/{STAGE_NAMES.length} — AWAITING REVIEW
        </span>
      </div>

      {!showRefine ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 13, color: 'var(--text2)' }}>
            Stage {stage} ({STAGE_NAMES[stage - 1]}) output generated. Approve to advance, or refine with feedback.
          </p>
          <div style={{ display: 'flex', gap: 10 }}>
            <Btn variant="teal" onClick={onApprove}>✓ Approve &amp; Continue</Btn>
            {remaining > 0 && (
              <Btn variant="amber" onClick={() => setShowRefine(true)}>
                ↺ Refine
                {refinements > 0 && <span style={{ fontSize: 11, opacity: 0.7 }}> ({remaining} left)</span>}
              </Btn>
            )}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <p style={{ fontSize: 13, color: 'var(--text2)' }}>Describe what to change:</p>
            <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono, monospace)' }}>
              {remaining} refinements left
            </span>
          </div>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="e.g. Use 99.9% purity target, add nitrogen as inert component…"
            style={{ width: '100%', height: 80, background: 'white', border: '1px solid var(--border2)', borderRadius: 6, padding: '10px 12px', color: 'var(--text)', fontFamily: 'var(--font-mono, monospace)', fontSize: 12, resize: 'vertical' }}
            onFocus={(e) => (e.target.style.borderColor = 'var(--teal)')}
            onBlur={(e) => (e.target.style.borderColor = 'var(--border2)')}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn
              variant="amber"
              onClick={() => { onRefine(feedback); setFeedback(''); setShowRefine(false); }}
              disabled={!feedback.trim()}
            >
              Submit &amp; Re-run
            </Btn>
            <Btn variant="ghost" onClick={() => setShowRefine(false)}>Cancel</Btn>
          </div>
        </div>
      )}
    </div>
  );
}
