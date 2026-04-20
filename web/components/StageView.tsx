'use client';

// Full implementation in Task 4.
// Stub exported here so Task 3 studio page type-checks.

import { Session } from '@/lib/api';

interface StageViewProps {
  session: Session;
  stageNum: number;
  onSessionUpdate: (s: Session) => void;
  onApprove: (s: Session) => void;
}

export function StageView(_props: StageViewProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text3)', fontSize: 13 }}>
      Stage {_props.stageNum} — loading…
    </div>
  );
}
