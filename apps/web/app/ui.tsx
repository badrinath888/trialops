import type { ReactNode } from "react";

export function Icon({
  name = "spark",
  size = 20,
}: {
  name?: string;
  size?: number;
}) {
  const paths: Record<string, ReactNode> = {
    spark: (
      <>
        <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" />
        <path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5Z" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </>
    ),
    plus: (
      <>
        <path d="M12 5v14M5 12h14" />
      </>
    ),
    history: (
      <>
        <path d="M3 11a9 9 0 1 1 2.6 7M3 4v7h7" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    chart: (
      <>
        <path d="M4 3v17h17M8 15v-4M13 15V7M18 15V4" />
      </>
    ),
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    shield: (
      <>
        <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    folder: (
      <path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    file: (
      <>
        <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
        <path d="M14 3v6h6M8 13h8M8 17h5" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.spark}
    </svg>
  );
}

export function Hero({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-hero">
      <div className="hero-contours" aria-hidden="true">
        <svg viewBox="0 0 680 320" preserveAspectRatio="xMidYMid slice">
          {Array.from({ length: 12 }, (_, i) => (
            <path
              key={i}
              d={`M ${-90 + i * 18} 340 C ${130 + i * 9} ${40 - i * 10}, ${300 + i * 12} ${370 - i * 14}, ${430 + i * 13} ${110 - i * 15} S ${660 + i * 10} ${-40 - i * 10}, 780 -80`}
            />
          ))}
        </svg>
      </div>
      <div className="hero-copy">
        <p className="eyebrow">
          <span className="eyebrow-line" />
          {eyebrow}
        </p>
        <h1>{title}</h1>
        <p className="hero-description">{description}</p>
      </div>
      <div className="hero-aside">
        {children || (
          <div className="hero-label">
            <Icon name="shield" />
            <span>
              Evidence first.
              <br />
              <b>Human reviewed.</b>
            </span>
          </div>
        )}
      </div>
    </header>
  );
}

export function Status({ value }: { value: string }) {
  const safe = [
    "approved",
    "rejected",
    "pending",
    "supported",
    "insufficient_evidence",
  ].includes(value)
    ? value
    : "pending";
  return (
    <span className={`status status-${safe}`}>
      <i />
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function EmptyState({
  title,
  description,
  icon = "folder",
}: {
  title: string;
  description: string;
  icon?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name={icon} size={30} />
      </span>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

export function Metric({
  label,
  value,
  icon,
  note,
}: {
  label: string;
  value: ReactNode;
  icon: string;
  note: string;
}) {
  return (
    <article className="metric">
      <div className="metric-top">
        <small>{label}</small>
        <Icon name={icon} size={18} />
      </div>
      <strong>{value}</strong>
      <span className="metric-note">{note}</span>
    </article>
  );
}
