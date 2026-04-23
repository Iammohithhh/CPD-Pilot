interface EquipProps {
  size?: number;
  color?: string;
}

export const Equipment = {
  Vessel: ({ size = 40, color = '#1a3554' }: EquipProps) => (
    <svg width={size} height={size * 1.5} viewBox="0 0 40 60">
      <rect x="8" y="10" width="24" height="36" rx="12" fill="none" stroke={color} strokeWidth="1.8" />
      <path d="M8 22 h24 M8 36 h24" stroke={color} strokeWidth="0.8" strokeDasharray="2,2" opacity="0.4" />
      <line x1="20" y1="1" x2="20" y2="10" stroke={color} strokeWidth="1.5" />
      <line x1="20" y1="46" x2="20" y2="55" stroke={color} strokeWidth="1.5" />
      <circle cx="20" cy="1" r="2" fill={color} />
    </svg>
  ),
  Reactor: ({ size = 44, color = '#1a3554' }: EquipProps) => (
    <svg width={size} height={size} viewBox="0 0 44 44">
      <circle cx="22" cy="22" r="18" fill="none" stroke={color} strokeWidth="1.8" />
      <path d="M14 22 Q22 14 30 22 Q22 30 14 22Z" fill="none" stroke={color} strokeWidth="1.2" />
      <line x1="22" y1="4" x2="22" y2="0" stroke={color} strokeWidth="1.5" />
      <line x1="22" y1="40" x2="22" y2="44" stroke={color} strokeWidth="1.5" />
      <line x1="4" y1="22" x2="0" y2="22" stroke={color} strokeWidth="1.5" />
    </svg>
  ),
  HeatExchanger: ({ size = 48, color = '#1a3554' }: EquipProps) => (
    <svg width={size} height={size * 0.6} viewBox="0 0 48 28">
      <rect x="4" y="6" width="40" height="16" rx="8" fill="none" stroke={color} strokeWidth="1.8" />
      <path d="M14 6 Q14 14 20 14 Q26 14 26 6" fill="none" stroke={color} strokeWidth="1.2" />
      <path d="M22 22 Q22 14 28 14 Q34 14 34 22" fill="none" stroke={color} strokeWidth="1.2" />
      <line x1="0" y1="10" x2="4" y2="10" stroke={color} strokeWidth="1.5" />
      <line x1="44" y1="18" x2="48" y2="18" stroke={color} strokeWidth="1.5" />
      <line x1="0" y1="18" x2="4" y2="18" stroke={color} strokeWidth="1.5" />
      <line x1="44" y1="10" x2="48" y2="10" stroke={color} strokeWidth="1.5" />
    </svg>
  ),
  Column: ({ size = 36, color = '#1a3554' }: EquipProps) => (
    <svg width={size} height={size * 2.2} viewBox="0 0 36 80">
      <rect x="6" y="8" width="24" height="64" rx="4" fill="none" stroke={color} strokeWidth="1.8" />
      {[20, 32, 44, 56].map((y) => (
        <g key={y}>
          <line x1="6" y1={y} x2="30" y2={y} stroke={color} strokeWidth="0.8" />
          <path d={`M6,${y} L18,${y - 5} L30,${y}`} fill="none" stroke={color} strokeWidth="1" />
        </g>
      ))}
      <line x1="18" y1="0" x2="18" y2="8" stroke={color} strokeWidth="1.5" />
      <line x1="18" y1="72" x2="18" y2="80" stroke={color} strokeWidth="1.5" />
      <line x1="6" y1="36" x2="0" y2="36" stroke={color} strokeWidth="1.5" />
    </svg>
  ),
  Compressor: ({ size = 40, color = '#1a3554' }: EquipProps) => (
    <svg width={size} height={size} viewBox="0 0 40 40">
      <circle cx="20" cy="20" r="15" fill="none" stroke={color} strokeWidth="1.8" />
      <path d="M20 8 L28 20 L20 32 L12 20 Z" fill="none" stroke={color} strokeWidth="1.2" />
      <line x1="0" y1="20" x2="5" y2="20" stroke={color} strokeWidth="1.5" />
      <line x1="35" y1="20" x2="40" y2="20" stroke={color} strokeWidth="1.5" />
    </svg>
  ),
  Pump: ({ size = 32, color = '#1a3554' }: EquipProps) => (
    <svg width={size} height={size} viewBox="0 0 32 32">
      <circle cx="16" cy="16" r="12" fill="none" stroke={color} strokeWidth="1.8" />
      <path d="M10 20 L16 8 L22 20 Z" fill="none" stroke={color} strokeWidth="1.2" />
      <line x1="4" y1="20" x2="0" y2="20" stroke={color} strokeWidth="1.5" />
      <line x1="28" y1="16" x2="32" y2="16" stroke={color} strokeWidth="1.5" />
    </svg>
  ),
};
