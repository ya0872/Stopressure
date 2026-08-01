import type { ChartSeries } from '../../types/weather';

/**
 * 気圧の推移をSVGで描く。mockup/index.html の drawChart をそのまま React へ移したもの。
 * グラフライブラリを足さず依存をゼロに保つ（表示だけなので判定ロジックは含まない）。
 */
const W = 720;
const H = 240;
const PAD_L = 46;
const PAD_R = 16;
const PAD_T = 16;
const PAD_B = 30;

export const PressureChart = ({ chart }: { chart: ChartSeries }) => {
  const p = chart.pressure;
  const now = chart.now_index;

  if (!p || p.length < 2) {
    return <p className="widget-note">気圧の系列を取得できませんでした。</p>;
  }

  // 上下に2hPaの余白を取る。線が枠に貼り付くと変化量が読み取りにくいため
  const min = Math.min(...p) - 2;
  const max = Math.max(...p) + 2;
  const x = (i: number) => PAD_L + (i / (p.length - 1)) * (W - PAD_L - PAD_R);
  const y = (v: number) => PAD_T + (1 - (v - min) / (max - min)) * (H - PAD_T - PAD_B);

  const path = (idxs: number[]) =>
    idxs.map((i, k) => `${k === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p[i]).toFixed(1)}`).join(' ');

  const pastIdx = Array.from({ length: now + 1 }, (_, i) => i);
  const futureIdx = Array.from({ length: p.length - now }, (_, k) => k + now);

  // 下降している区間だけアクセント色で上書きする。低下が身体負荷に直結するため
  const declines = p
    .map((v, i) => ({ v, i }))
    .filter(({ i }) => i > 0 && p[i] < p[i - 1]);

  const hhmm = (i: number) => (chart.times[i] ?? '').slice(11, 16);
  // 系列の長さは固定ではないため、目盛りの位置を割合で決めて実時刻を出す
  const ticks = [
    ...new Set([0, Math.round(now / 2), now, Math.round((now + p.length - 1) / 2), p.length - 1]),
  ];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      role="img"
      aria-label={`気圧の推移。現在 ${p[now].toFixed(1)} hPa`}
    >
      {/* 横罫線と気圧の目盛り */}
      {[0, 1, 2, 3].map((k) => {
        const v = min + ((max - min) * k) / 3;
        return (
          <g key={`grid-${k}`}>
            <line x1={PAD_L} y1={y(v)} x2={W - PAD_R} y2={y(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={PAD_L - 8} y={y(v) + 4} textAnchor="end" fontSize={10} fill="var(--text-faint)">
              {v.toFixed(0)}
            </text>
          </g>
        );
      })}

      {/* 実測（0〜現在）と予報（現在〜末尾）を線種で分ける */}
      <path d={path(pastIdx)} fill="none" stroke="var(--text-dim)" strokeWidth={1.5} />
      <path
        d={path(futureIdx)}
        fill="none"
        stroke="var(--text-faint)"
        strokeWidth={1.5}
        strokeDasharray="4 4"
      />

      {declines.map(({ i }) => (
        <line
          key={`dec-${i}`}
          x1={x(i - 1)}
          y1={y(p[i - 1])}
          x2={x(i)}
          y2={y(p[i])}
          stroke="var(--accent)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />
      ))}

      {/* 現在時刻の縦線と値 */}
      <line x1={x(now)} y1={PAD_T} x2={x(now)} y2={H - PAD_B} stroke="var(--accent-dim)" strokeWidth={1} />
      <circle cx={x(now)} cy={y(p[now])} r={4} fill="var(--accent)" />
      <text x={x(now)} y={PAD_T - 4} textAnchor="middle" fontSize={10} fill="var(--text-dim)">
        現在 {p[now].toFixed(1)}hPa
      </text>

      {ticks.map((i) => {
        const label = i === now ? '現在' : hhmm(i);
        if (!label) return null;
        return (
          <text
            key={`tick-${i}`}
            x={x(i)}
            y={H - 10}
            textAnchor="middle"
            fontSize={10}
            fill="var(--text-faint)"
          >
            {label}
          </text>
        );
      })}
    </svg>
  );
};
