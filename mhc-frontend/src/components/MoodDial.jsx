import React from "react";

/**
 * MoodDial — half-circle gauge with a needle.
 * Props:
 *  - mood: "anger" | "distress" | "sadness" | "neutral" | "optimism" | "joy"
 *  - confidence?: number  (0..1)
 *  - size?: number        (px)
 */
export default function MoodDial({ mood = "neutral", confidence, size = 200 }) {
  const MOODS = ["anger", "distress", "sadness", "neutral", "optimism", "joy"]; // left -> right
  const COLORS = {
    anger: "#f97316",
    distress: "#f43f5e",
    sadness: "#3b82f6",
    neutral: "#64748b",
    optimism: "#14b8a6",
    joy: "#10b981",
  };
  const EMOJI = { anger: "😠", distress: "😥", sadness: "😢", neutral: "😐", optimism: "🙂", joy: "😊" };

  const idx = Math.max(0, MOODS.indexOf(mood));
  const w = size;
  const h = Math.round(size * 0.7);     // canvas height
  const cx = w / 2;
  const cy = Math.round(h * 0.95);      // gauge center near bottom
  const r  = Math.round(h * 0.62);

  const start = 180, end = 0;           // degrees across the TOP half
  const seg = (start - end) / MOODS.length;

  // --- IMPORTANT: SVG y-axis increases downward, so subtract the sin term ---
  const polar = (angle) => {
    const rad = (Math.PI / 180) * angle;
    return [cx + r * Math.cos(rad), cy - r * Math.sin(rad)];
  };

  const arcPath = (a0, a1) => {
    const [x0, y0] = polar(a0);
    const [x1, y1] = polar(a1);
    const largeArc = (a1 - a0) <= 180 ? 0 : 1;
    return `M ${x0} ${y0} A ${r} ${r} 0 ${largeArc} 1 ${x1} ${y1}`;
  };

  // Needle angle points into the middle of the chosen segment.
  const needleAngle = start - idx * seg - seg / 2;

  const pct = confidence != null ? Math.round(confidence * 100) : null;
  const unsure = pct != null && pct < 55;

  return (
    <div className="select-none">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-sm font-medium text-slate-700">Mood</span>
        <span className="text-sm">{EMOJI[mood] ?? "🙂"}</span>
        <span className="text-sm text-slate-600">{mood}</span>
        {pct != null && (
          <span
            className={`ml-2 text-xs rounded px-1.5 py-0.5 border ${
              unsure ? "border-amber-300 text-amber-700 bg-amber-50" : "border-slate-200 text-slate-600"
            }`}
          >
            {pct}%
          </span>
        )}
      </div>

      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        {/* colored segments */}
        {MOODS.map((m, i) => {
          const a0 = start - i * seg;
          const a1 = start - (i + 1) * seg;
          return (
            <path
              key={m}
              d={arcPath(a0, a1)}
              stroke={COLORS[m]}
              strokeWidth={Math.max(6, size * 0.07)}
              strokeLinecap="round"
              fill="none"
              opacity={i === idx ? 1 : 0.35}
            />
          );
        })}

        {/* tick marks */}
        {MOODS.map((_, i) => {
          const a = start - i * seg;
          const rad = (Math.PI / 180) * a;
          const x0 = cx + (r - size * 0.08) * Math.cos(rad);
          const y0 = cy - (r - size * 0.08) * Math.sin(rad); // subtract!
          const x1 = cx + (r + size * 0.02) * Math.cos(rad);
          const y1 = cy - (r + size * 0.02) * Math.sin(rad); // subtract!
          return <line key={i} x1={x0} y1={y0} x2={x1} y2={y1} stroke="#cbd5e1" strokeWidth="2" />;
        })}

        {/* needle — start pointing right, then rotate COUNTERCLOCKWISE */}
        <g style={{ transformOrigin: `${cx}px ${cy}px`, transform: `rotate(${-needleAngle}deg)` }}>
          <line x1={cx} y1={cy} x2={cx + r * 0.96} y2={cy} stroke="#0f172a" strokeWidth="3" />
          <circle cx={cx} cy={cy} r={Math.max(4, size * 0.03)} fill="#0f172a" />
        </g>
      </svg>

      <div className="mt-1 grid grid-cols-6 gap-1 text-[10px] text-slate-600">
        {MOODS.map((m) => (
          <div key={m} className="flex items-center gap-1 justify-center">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ background: COLORS[m], opacity: m === mood ? 1 : 0.6 }}
            />
            <span className={m === mood ? "font-medium" : ""}>{m}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
