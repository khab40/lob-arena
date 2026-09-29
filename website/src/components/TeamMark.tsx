type TeamMarkProps = {
  team: "red" | "blue";
  label?: string;
};

export function TeamMark({ label, team }: TeamMarkProps) {
  const ariaLabel = label ?? (team === "red" ? "Red Team" : "Detection");

  return (
    <span className={`team-mark ${team}`} aria-label={ariaLabel} role="img">
      {team === "red" ? <RedTargetIcon /> : <BlueShieldIcon />}
    </span>
  );
}

function RedTargetIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4" />
      <path d="M16.9 7.1l2.4-2.4M7.1 16.9l-2.4 2.4" />
    </svg>
  );
}

function BlueShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.8l7 2.7v5.3c0 4.6-2.7 8.5-7 10.4-4.3-1.9-7-5.8-7-10.4V5.5l7-2.7Z" />
      <path d="M8.2 12.1l2.3 2.3 5.3-5.5" />
    </svg>
  );
}
