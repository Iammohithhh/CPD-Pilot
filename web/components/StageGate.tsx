'use client';
// Full implementation in Task 5. Stub to satisfy type-check.
interface StageGateProps {
  stage: number;
  refinements: number;
  maxRefinements: number;
  onApprove: () => void;
  onRefine: (feedback: string) => void;
}
export function StageGate(_: StageGateProps) { return null; }
