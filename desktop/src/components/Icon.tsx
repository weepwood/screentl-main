import type { PageKey } from "../types";

const paths: Record<PageKey | "play" | "pause" | "stop" | "folder" | "search" | "refresh" | "trash" | "check" | "archive", string> = {
  dashboard: "M3 13h8V3H3v10Zm0 8h8v-6H3v6Zm10 0h8V11h-8v10Zm0-18v6h8V3h-8Z",
  sessions: "M4 4h16v4H4V4Zm0 6h16v10H4V10Zm3 3v4h4v-4H7Z",
  timeline: "M4 5h2v14H4V5Zm5 3h11v2H9V8Zm0 6h8v2H9v-2Z",
  render: "M4 4h16v16H4V4Zm5 4v8l7-4-7-4Z",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm9 4-2.1-1.2.1-2.4-2.4-1.4-2 1.3L12.5 6 12 3H9l-.5 3-2.1.9-2-1.3L2 7l.1 2.4L0 10.6v2.8l2.1 1.2L2 17l2.4 1.4 2-1.3 2.1.9.5 3h3l.5-3 2.1-.9 2 1.3L19 17l-.1-2.4 2.1-1.2V12Z",
  play: "M8 5v14l11-7L8 5Z",
  pause: "M7 5h4v14H7V5Zm6 0h4v14h-4V5Z",
  stop: "M6 6h12v12H6V6Z",
  folder: "M3 5h7l2 2h9v12H3V5Z",
  search: "m20 20-4.3-4.3m2.3-5.2a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6",
  trash: "M5 7h14M9 7V4h6v3m2 0-1 13H8L7 7m3 4v5m4-5v5",
  check: "m5 12 4 4L19 6",
  archive: "M4 5h16v4H4V5Zm2 4h12v11H6V9Zm4 4h4",
};

interface IconProps {
  name: keyof typeof paths;
  size?: number;
  stroke?: boolean;
}

export function Icon({ name, size = 20, stroke = false }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={stroke ? "none" : "currentColor"}
      stroke={stroke ? "currentColor" : "none"}
      strokeWidth={stroke ? 2 : undefined}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name]} />
    </svg>
  );
}
