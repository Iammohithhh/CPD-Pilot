// Static BFD diagram ported from design prototype.
// Shows a generic methanol-style SMR block flow as a placeholder;
// a future version can drive this from the Stage 4 artifact JSON.
export function BFDDiagram() {
  return (
    <div style={{ overflowX: 'auto', padding: '20px 8px 8px' }}>
      <svg width="1080" height="300" style={{ fontFamily: 'var(--font-mono, monospace)', display: 'block' }}>
        <defs>
          <marker id="arrowB" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0,7 2.5,0 5" fill="#1a3554" opacity="0.7" />
          </marker>
          <marker id="arrowR" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0,7 2.5,0 5" fill="#c4690a" opacity="0.7" />
          </marker>
        </defs>

        {/* Feed */}
        <rect x="20" y="110" width="80" height="44" rx="4" fill="#e8f1fb" stroke="#1e6fb5" strokeWidth="1.5" />
        <text x="60" y="128" fill="#1a3554" fontSize="10" fontWeight="700" textAnchor="middle">FEED</text>
        <text x="60" y="142" fill="#3d5168" fontSize="8" textAnchor="middle">CH₄ + H₂O</text>
        <line x1="100" y1="132" x2="140" y2="132" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* R-101 Reformer */}
        <circle cx="175" cy="100" r="32" fill="#fef9f0" stroke="#c4690a" strokeWidth="1.8" />
        <path d="M158 100 Q175 84 192 100 Q175 116 158 100Z" fill="none" stroke="#c4690a" strokeWidth="1.2" />
        <text x="175" y="96" fill="#1a3554" fontSize="9" fontWeight="700" textAnchor="middle">R-101</text>
        <text x="175" y="108" fill="#3d5168" fontSize="7.5" textAnchor="middle">Reformer</text>
        <text x="175" y="118" fill="#7a92a8" fontSize="7" textAnchor="middle">850°C</text>
        <line x1="175" y1="68" x2="175" y2="50" stroke="#1a3554" strokeWidth="1.2" />
        <text x="180" y="46" fill="#7a92a8" fontSize="7.5">steam</text>
        <line x1="207" y1="100" x2="247" y2="100" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* R-102 WGS */}
        <circle cx="282" cy="100" r="28" fill="#f0f8ff" stroke="#1e6fb5" strokeWidth="1.8" />
        <path d="M265 100 Q282 87 299 100 Q282 113 265 100Z" fill="none" stroke="#1e6fb5" strokeWidth="1.2" />
        <text x="282" y="96" fill="#1a3554" fontSize="9" fontWeight="700" textAnchor="middle">R-102</text>
        <text x="282" y="108" fill="#3d5168" fontSize="7.5" textAnchor="middle">WGS</text>
        <line x1="310" y1="100" x2="350" y2="100" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* A-101 Absorber */}
        <rect x="350" y="60" width="36" height="80" rx="4" fill="#e6f4f1" stroke="#0b7a6a" strokeWidth="1.8" />
        {[80, 98, 116].map((y) => <line key={y} x1="350" y1={y} x2="386" y2={y} stroke="#0b7a6a" strokeWidth="0.7" opacity="0.5" />)}
        <text x="368" y="97" fill="#1a3554" fontSize="9" fontWeight="700" textAnchor="middle">A-101</text>
        <text x="368" y="108" fill="#3d5168" fontSize="7" textAnchor="middle">CO₂ Abs</text>
        <line x1="350" y1="80" x2="330" y2="80" stroke="#0b7a6a" strokeWidth="1.2" />
        <text x="310" y="78" fill="#0b7a6a" fontSize="7">MEA in</text>
        <line x1="368" y1="60" x2="368" y2="40" stroke="#7a92a8" strokeWidth="1.2" strokeDasharray="3,2" />
        <text x="373" y="36" fill="#7a92a8" fontSize="7.5">CO₂</text>
        <line x1="386" y1="100" x2="420" y2="100" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* C-101 Compressor */}
        <circle cx="455" cy="100" r="26" fill="#f5f0fb" stroke="#7c3aed" strokeWidth="1.8" />
        <path d="M440 112 L455 80 L470 112 Z" fill="none" stroke="#7c3aed" strokeWidth="1.2" />
        <text x="455" y="97" fill="#1a3554" fontSize="9" fontWeight="700" textAnchor="middle">C-101</text>
        <text x="455" y="108" fill="#3d5168" fontSize="7" textAnchor="middle">50 bar</text>
        <line x1="481" y1="100" x2="515" y2="100" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* R-103 MeOH Reactor */}
        <circle cx="550" cy="100" r="32" fill="#fef9f0" stroke="#c4690a" strokeWidth="1.8" />
        <path d="M533 100 Q550 84 567 100 Q550 116 533 100Z" fill="none" stroke="#c4690a" strokeWidth="1.2" />
        <text x="550" y="96" fill="#1a3554" fontSize="9" fontWeight="700" textAnchor="middle">R-103</text>
        <text x="550" y="108" fill="#3d5168" fontSize="7.5" textAnchor="middle">MeOH Rx</text>
        <text x="550" y="118" fill="#7a92a8" fontSize="7" textAnchor="middle">260°C</text>
        <line x1="582" y1="100" x2="618" y2="100" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* V-101 Flash */}
        <rect x="620" y="80" width="32" height="48" rx="14" fill="#f8f9fc" stroke="#1a3554" strokeWidth="1.8" />
        <text x="636" y="100" fill="#1a3554" fontSize="8" fontWeight="700" textAnchor="middle">V-101</text>
        <text x="636" y="112" fill="#7a92a8" fontSize="7" textAnchor="middle">Flash</text>
        <line x1="636" y1="80" x2="636" y2="62" stroke="#1a3554" strokeWidth="1.2" />
        <text x="641" y="58" fill="#7a92a8" fontSize="7">vapor</text>
        <line x1="652" y1="104" x2="686" y2="104" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* T-101 Distillation Column */}
        <rect x="688" y="50" width="40" height="100" rx="4" fill="#e6f4f1" stroke="#0b7a6a" strokeWidth="1.8" />
        {[75, 95, 115, 135].map((y) => (
          <g key={y}>
            <line x1="688" y1={y} x2="728" y2={y} stroke="#0b7a6a" strokeWidth="0.7" opacity="0.4" />
            <path d={`M688,${y} L708,${y - 6} L728,${y}`} fill="none" stroke="#0b7a6a" strokeWidth="0.9" opacity="0.5" />
          </g>
        ))}
        <text x="708" y="97" fill="#1a3554" fontSize="9" fontWeight="700" textAnchor="middle">T-101</text>
        <text x="708" y="109" fill="#3d5168" fontSize="7" textAnchor="middle">Distillation</text>
        <line x1="708" y1="50" x2="708" y2="32" stroke="#1a3554" strokeWidth="1.2" />
        <text x="713" y="28" fill="#7a92a8" fontSize="7">lights</text>
        <line x1="708" y1="150" x2="708" y2="168" stroke="#1a3554" strokeWidth="1.5" markerEnd="url(#arrowB)" />

        {/* Product */}
        <rect x="660" y="168" width="96" height="44" rx="4" fill="#e6f4f1" stroke="#0b7a6a" strokeWidth="1.8" />
        <text x="708" y="186" fill="#0b7a6a" fontSize="10" fontWeight="700" textAnchor="middle">PRODUCT</text>
        <text x="708" y="200" fill="#1a3554" fontSize="8" textAnchor="middle">MeOH 99.5%</text>

        {/* Recycle dashed arc */}
        <path d="M550 132 Q550 230 280 230 Q175 230 175 132" fill="none" stroke="#c4690a" strokeWidth="1.5" strokeDasharray="5,3" markerEnd="url(#arrowR)" />
        <text x="355" y="244" fill="#c4690a" fontSize="8" textAnchor="middle">recycle loop (H₂ + unreacted syngas)</text>

        {/* Purge */}
        <line x1="455" y1="74" x2="455" y2="48" stroke="#7a92a8" strokeWidth="1.2" strokeDasharray="3,2" />
        <circle cx="455" cy="44" r="4" fill="none" stroke="#7a92a8" strokeWidth="1" />
        <text x="462" y="43" fill="#7a92a8" fontSize="7.5">purge</text>

        {/* Title block */}
        <rect x="10" y="258" width="420" height="32" fill="white" stroke="#d0d9e6" strokeWidth="1" />
        <line x1="10" y1="270" x2="430" y2="270" stroke="#d0d9e6" strokeWidth="0.5" />
        <text x="18" y="266" fill="#7a92a8" fontSize="7">DRAWING NO.</text>
        <text x="18" y="284" fill="#1a3554" fontSize="9" fontWeight="600">BFD-001 — Block Flow Diagram</text>
        <text x="300" y="266" fill="#7a92a8" fontSize="7">DATE</text>
        <text x="300" y="284" fill="#3d5168" fontSize="9">CPD-Pilot · AI-generated</text>
      </svg>
    </div>
  );
}
