import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  trendTrust,
  type ClaimStatus,
  type SignalKind,
  type Stage,
  type Trend,
  type Trust,
} from "./data";

export function Button({
  to,
  kind = "primary",
  small,
  children,
  disabled,
  onClick,
}: {
  to?: string;
  kind?: "primary" | "dark" | "quiet";
  small?: boolean;
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const cls = `btn btn-${kind}${small ? " btn-sm" : ""}`;
  if (to) {
    return (
      <Link className={cls} to={to} onClick={onClick}>
        {children}
      </Link>
    );
  }
  return (
    <button className={cls} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone: "ok" | "bad" | "warn" | "bank";
  children: ReactNode;
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function kindBadge(kind: SignalKind) {
  if (kind === "хайп") return <Badge tone="bad">хайп</Badge>;
  if (kind === "на слуху") return <Badge tone="warn">на слуху</Badge>;
  return <Badge tone="ok">ранний сигнал</Badge>;
}

export function stageBadge(stage: Stage) {
  return <Badge tone="warn">{stage}</Badge>;
}

export function statusBadge(status: ClaimStatus) {
  if (status === "supported") return <Badge tone="ok">подтверждено</Badge>;
  if (status === "unsupported") return <Badge tone="bad">не подтверждено</Badge>;
  return <Badge tone="warn">гипотеза</Badge>;
}

export function trustBadge(trust: Trust) {
  if (trust === "высокий") return <Badge tone="ok">доверие высокое</Badge>;
  if (trust === "средний") return <Badge tone="warn">доверие среднее</Badge>;
  return <Badge tone="bad">доверие низкое</Badge>;
}

export function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  const w = 120;
  const h = 40;
  const step = w / (values.length - 1);
  const points = values
    .map((v, i) => `${i * step},${h - (v / max) * (h - 6) - 3}`)
    .join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        points={points}
        style={{ color: "var(--accent)" }}
      />
    </svg>
  );
}

export function Scene({
  variant,
}: {
  variant: "search" | "list" | "trend" | "compare" | "backtest" | "cabinet";
}) {
  const color = "var(--accent)";
  return (
    <svg className="scene" viewBox="0 0 420 360" role="img" aria-label="Объёмная сцена">
      <defs>
        <linearGradient id="g" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#7ea2ff" />
          <stop offset="1" stopColor="#2b61ec" />
        </linearGradient>
        <filter id="soft">
          <feDropShadow dx="0" dy="18" stdDeviation="12" floodColor="#0a0a0b" floodOpacity="0.12" />
        </filter>
      </defs>
      <ellipse cx="210" cy="300" rx="110" ry="18" fill="currentColor" opacity="0.08" />
      {variant === "search" && (
        <g filter="url(#soft)">
          <circle cx="168" cy="150" r="62" fill="url(#g)" />
          <circle cx="168" cy="150" r="34" fill="#fff" />
          <rect x="214" y="196" width="86" height="24" rx="12" transform="rotate(42 214 196)" fill="url(#g)" />
          <circle cx="300" cy="108" r="16" fill="#f4d7a8" />
          <circle cx="328" cy="168" r="12" fill="#c9d6ff" />
          <circle cx="112" cy="92" r="10" fill="#f4d7a8" />
        </g>
      )}
      {variant === "list" && (
        <g filter="url(#soft)">
          <rect x="110" y="150" width="200" height="120" rx="24" fill="#e8eeff" />
          <rect x="124" y="118" width="200" height="120" rx="24" fill="#c9d6ff" />
          <rect x="138" y="86" width="200" height="120" rx="24" fill="url(#g)" />
        </g>
      )}
      {variant === "trend" && (
        <g filter="url(#soft)">
          <rect x="90" y="90" width="240" height="170" rx="28" fill="#d6e4ff" />
          <path
            d="M120 210 C160 200 170 140 210 150 C250 160 260 110 310 96"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
          />
          <circle cx="310" cy="96" r="10" fill="#f4d7a8" />
        </g>
      )}
      {variant === "compare" && (
        <g filter="url(#soft)">
          <rect x="188" y="70" width="28" height="150" rx="10" fill="#c9d6ff" />
          <rect x="118" y="150" width="90" height="22" rx="11" fill="url(#g)" />
          <rect x="212" y="150" width="90" height="22" rx="11" fill="#f4d7a8" />
          <circle cx="140" cy="120" r="18" fill="#fff" />
          <circle cx="280" cy="188" r="18" fill="#fff" />
        </g>
      )}
      {variant === "backtest" && (
        <g filter="url(#soft)">
          <circle cx="210" cy="150" r="78" fill="url(#g)" />
          <path d="M210 92 v58 l38 22" fill="none" stroke="#fff" strokeWidth="10" strokeLinecap="round" />
          <rect x="186" y="64" width="48" height="18" rx="8" fill="#f4d7a8" />
        </g>
      )}
      {variant === "cabinet" && (
        <g filter="url(#soft)">
          <path d="M120 130 h70 l16 16 h94 v110 h-180 z" fill="url(#g)" />
          <path d="M120 146 h180" stroke="#fff" strokeWidth="8" />
          <polygon points="250,86 268,122 232,122" fill="#f4d7a8" />
        </g>
      )}
    </svg>
  );
}

export function TrendLine({ trend, index }: { trend: Trend; index: number }) {
  return (
    <Link className="card clickable" to={`/trends/${trend.id}`}>
      <div className="trend-row">
        <strong className="tiny" style={{ color: "var(--text)" } as CSSProperties}>
          {String(index + 1).padStart(2, "0")}
        </strong>
        <div>
          <h4>{trend.name}</h4>
          <p className="tiny" style={{ marginTop: 8 }}>
            {trend.definition}
          </p>
          <ul className="predictors">
            {trend.reasons.slice(0, 3).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <div className="badge-row" style={{ marginTop: 12 }}>
            {kindBadge(trend.kind)}
            {trustBadge(trendTrust(trend))}
          </div>
        </div>
        <div>
          <div className="score">{trend.signal}%</div>
          <div className="tiny">уверенность модели</div>
        </div>
      </div>
    </Link>
  );
}
