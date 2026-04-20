interface StageIconProps {
  active: boolean;
}

const A = '#0b7a6a';
const I = '#7a92a8';
const AL = '#0b7a6a';
const IL = '#b8c5d6';

export const StageIcons: Array<(props: StageIconProps) => React.ReactElement> = [
  ({ active }) => (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <rect x="2" y="3" width="14" height="13" rx="2" fill="none" stroke={active ? A : I} strokeWidth="1.5" />
      <line x1="5" y1="7" x2="13" y2="7" stroke={active ? AL : IL} strokeWidth="1.2" />
      <line x1="5" y1="10" x2="11" y2="10" stroke={active ? AL : IL} strokeWidth="1.2" />
      <rect x="6" y="1" width="6" height="4" rx="1" fill="none" stroke={active ? A : I} strokeWidth="1.3" />
    </svg>
  ),
  ({ active }) => (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <circle cx="9" cy="5" r="2.5" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <circle cx="4" cy="14" r="2" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <circle cx="14" cy="14" r="2" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <line x1="9" y1="7.5" x2="5.5" y2="12" stroke={active ? AL : IL} strokeWidth="1.2" />
      <line x1="9" y1="7.5" x2="12.5" y2="12" stroke={active ? AL : IL} strokeWidth="1.2" />
    </svg>
  ),
  ({ active }) => (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <circle cx="9" cy="9" r="2.5" fill={active ? '#e6f4f1' : '#f3f5f9'} stroke={active ? A : I} strokeWidth="1.4" />
      <ellipse cx="9" cy="9" rx="7" ry="3" fill="none" stroke={active ? AL : IL} strokeWidth="1.1" />
      <ellipse cx="9" cy="9" rx="7" ry="3" fill="none" stroke={active ? AL : IL} strokeWidth="1.1" transform="rotate(60 9 9)" />
      <ellipse cx="9" cy="9" rx="7" ry="3" fill="none" stroke={active ? AL : IL} strokeWidth="1.1" transform="rotate(120 9 9)" />
    </svg>
  ),
  ({ active }) => (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <rect x="1" y="6" width="5" height="6" rx="1" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <rect x="7" y="4" width="4" height="10" rx="1" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <rect x="13" y="6" width="4" height="6" rx="1" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <line x1="6" y1="9" x2="7" y2="9" stroke={active ? AL : IL} strokeWidth="1.2" />
      <line x1="11" y1="9" x2="13" y2="9" stroke={active ? AL : IL} strokeWidth="1.2" />
    </svg>
  ),
  ({ active }) => (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <circle cx="9" cy="9" r="6" fill="none" stroke={active ? A : I} strokeWidth="1.4" />
      <path d="M6 9 Q9 5 12 9 Q9 13 6 9Z" fill={active ? 'rgba(11,122,106,0.15)' : 'none'} stroke={active ? A : IL} strokeWidth="1.1" />
      <line x1="1" y1="9" x2="3" y2="9" stroke={active ? AL : IL} strokeWidth="1.2" />
      <line x1="15" y1="9" x2="17" y2="9" stroke={active ? AL : IL} strokeWidth="1.2" />
    </svg>
  ),
];
