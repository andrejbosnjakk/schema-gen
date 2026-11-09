// Icons (docs/design-tokens.md): hand-drawn 16 x 16 stroke icons in currentColor, 1.5 px at 16 px; no icon library.
import type { ReactNode } from "react";
import logoSvg from "./logo.svg?raw";

const Dot = ({ x, y, r = 0.9 }: { x: number; y: number; r?: number }) => <circle cx={x} cy={y} r={r} fill="currentColor" stroke="none" />;

function Svg({ size, children, ...rest }: { size: number; children: ReactNode; [k: string]: unknown }) {
  return <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...rest}>{children}</svg>;
}

const KINDS: Record<string, ReactNode> = {
  battery: <><rect x="1.75" y="4.75" width="11" height="7.5" rx="1.5" /><path d="M14.5 7v3M4.5 8.5h3M6 7v3" /></>,
  dcdc: <><rect x="2" y="2" width="12" height="12" rx="1.5" /><path d="M2.5 13.5l11-11M4.5 5h3M4.5 7h3M8.5 9h3M8.5 11h1M10.5 11h1" /></>,
  source: <><circle cx="8" cy="8" r="6" /><path d="M8 4.5v3M6.5 6h3M6.5 10.5h3" /></>,
  breaker: <path d="M1.5 11.5h3M11.5 11.5h3M4.5 11.5l6.25-5M10.5 10.5l2 2M12.5 10.5l-2 2" />,
  fuse: <><rect x="3.5" y="5.5" width="9" height="5" rx="1.25" /><path d="M1.25 8h13.5" /></>,
  bus: <><path d="M1.75 4.5h12.5M4.5 4.5v7M8 4.5v7M11.5 4.5v7" /><Dot x={4.5} y={12} r={1.1} /><Dot x={8} y={12} r={1.1} /><Dot x={11.5} y={12} r={1.1} /></>,
  ground: <path d="M8 2v5.5M2.75 7.5h10.5M5 10.25h6M7 13h2" />,
  splice: <><path d="M1.75 4c3.5 0 3.5 4 6.25 4M1.75 12c3.5 0 3.5-4 6.25-4h6.25" /><Dot x={8} y={8} r={1.6} /></>,
  harness: <><path d="M1.5 4.5c2 0 2.5 2.25 4 2.25M1.5 8h4M1.5 11.5c2 0 2.5-2.25 4-2.25M14.5 4.5c-2 0-2.5 2.25-4 2.25M14.5 8h-4M14.5 11.5c-2 0-2.5-2.25-4-2.25" /><rect x="5.5" y="5.25" width="5" height="5.5" rx="1.5" /></>,
  connector: <><rect x="1.75" y="2.75" width="8.5" height="10.5" rx="1.5" /><path d="M10.25 5.75h4M10.25 10.25h4" /><Dot x={5} y={5.75} /><Dot x={5} y={10.25} /></>,
  switch: <><path d="M1.5 11.5h2M12.5 11.5h2M5.1 10.6L11 6.25" /><circle cx="4.5" cy="11.5" r="1" /><circle cx="11.5" cy="11.5" r="1" /></>,
  relay: <><rect x="1.75" y="5" width="4.5" height="6" rx="1" /><path d="M1.75 11l4.5-6M9.7 10.8L14 6.75" /><circle cx="9" cy="11.5" r="1" /><circle cx="13.75" cy="11.5" r="1" /><path d="M6.25 8h4.75" strokeDasharray="1 1.5" /></>,
  device: <><rect x="2" y="2.75" width="12" height="10.5" rx="1.5" /><path d="M2 6h12" /></>,
  avionics: <><rect x="1.75" y="2.25" width="12.5" height="11.5" rx="1.5" /><circle cx="8" cy="8" r="3.25" /><path d="M8 8l1.75-1.75" /></>,
  light: <><circle cx="8" cy="8" r="5.75" /><path d="M3.95 3.95l8.1 8.1M12.05 3.95l-8.1 8.1" /></>,
  motor: <><circle cx="8" cy="8" r="6" /><path d="M5.25 10.5V5.5L8 8.75l2.75-3.25v5" /></>,
  can: <path d="M1.5 5c3.25 0 3.25 6 6.5 6s3.25-6 6.5-6M1.5 11c3.25 0 3.25-6 6.5-6s3.25 6 6.5 6" />,
  sensor: <><circle cx="5" cy="11" r="2" /><path d="M5 6.25A4.75 4.75 0 0 1 9.75 11M5 2.75A8.25 8.25 0 0 1 13.25 11" /></>,
};
export const KIND_NAMES = Object.keys(KINDS);

/** The icon for a component kind (model kinds); unknown kinds get the device icon. */
export function KindIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  return <Svg size={size} data-kind={kind}>{KINDS[kind] ?? KINDS.device}</Svg>;
}

const tray = "M2.5 10.25v2.25a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2.25";
const UI = {
  import: <path d={`${tray}M8 2.5v7.75M5 7.25l3 3 3-3`} />,
  export: <path d={`${tray}M8 10.25V2.5M5 5.5l3-3 3 3`} />,
  play: <path d="M4.75 3.25v9.5a.5.5 0 0 0 .76.43l7.6-4.75a.5.5 0 0 0 0-.86l-7.6-4.75a.5.5 0 0 0-.76.43z" />,
  sun: <><circle cx="8" cy="8" r="2.75" /><path d="M8 1.5v1.25M8 13.25v1.25M1.5 8h1.25M13.25 8h1.25M3.4 3.4l.9.9M11.7 11.7l.9.9M3.4 12.6l.9-.9M11.7 4.3l.9-.9" /></>,
  moon: <path d="M13.5 9.75A5.75 5.75 0 1 1 6.25 2.5a4.5 4.5 0 0 0 7.25 7.25z" />,
  plus: <path d="M8 3v10M3 8h10" />,
  fit: <path d="M2.5 5.5v-2a1 1 0 0 1 1-1h2M10.5 2.5h2a1 1 0 0 1 1 1v2M13.5 10.5v2a1 1 0 0 1-1 1h-2M5.5 13.5h-2a1 1 0 0 1-1-1v-2" />,
  "zoom-in": <><circle cx="7" cy="7" r="4.75" /><path d="M10.5 10.5l3 3M5 7h4M7 5v4" /></>,
  "zoom-out": <><circle cx="7" cy="7" r="4.75" /><path d="M10.5 10.5l3 3M5 7h4" /></>,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  "chevron-down": <path d="M4.5 6.25L8 9.75l3.5-3.5" />,
  "chevron-up": <path d="M4.5 9.75L8 6.25l3.5 3.5" />,
  "chevron-left": <path d="M9.75 4.5L6.25 8l3.5 3.5" />,
  "chevron-right": <path d="M6.25 4.5L9.75 8l-3.5 3.5" />,
  help: <><circle cx="8" cy="8" r="6.25" /><path d="M6.25 6.25a1.75 1.75 0 1 1 2.6 1.53c-.5.28-.85.67-.85 1.22v.25" /><Dot x={8} y={11.25} /></>,
  alert: <><circle cx="8" cy="8" r="6.25" /><path d="M8 4.75v3.75" /><Dot x={8} y={11} /></>,
  warning: <><path d="M7.13 2.5a1 1 0 0 1 1.74 0l5.4 9.5a1 1 0 0 1-.87 1.5H2.6a1 1 0 0 1-.87-1.5z" /><path d="M8 6.25v3" /><Dot x={8} y={11.4} /></>,
  check: <path d="M3 8.5l3.25 3.25L13 5" />,
  info: <><circle cx="8" cy="8" r="6.25" /><path d="M8 7.5v3.75" /><Dot x={8} y={5} /></>,
  search: <><circle cx="7" cy="7" r="4.75" /><path d="M10.5 10.5l3 3" /></>,
  "x-circle": <><circle cx="8" cy="8" r="6.25" /><path d="M6 6l4 4M10 6l-4 4" /></>,
  refresh: <path d="M13.5 8a5.5 5.5 0 1 1-1.61-3.89l1.61 1.64M13.5 2.5v3.25h-3.25" />,
  folder: <path d="M2 4.5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" />,
  file: <path d="M4 1.75h5l3.5 3.5V13.25a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2.75a1 1 0 0 1 1-1zM9 1.75v3.5h3.5" />,
  grip: <><Dot x={6} y={4} r={1} /><Dot x={10} y={4} r={1} /><Dot x={6} y={8} r={1} /><Dot x={10} y={8} r={1} /><Dot x={6} y={12} r={1} /><Dot x={10} y={12} r={1} /></>,
} satisfies Record<string, ReactNode>;
export type IconName = keyof typeof UI;
export const ICON_NAMES = Object.keys(UI) as IconName[];

/** A UI icon by name (see IconName). */
export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return <Svg size={size} data-icon={name}>{UI[name]}</Svg>;
}

/** The logo, inlined so its currentColor follows `--logo` (near-black on light, white on dark). logo.svg is the single
 *  source; the app icons are generated from it by make_icons.py. */
export function Logo({ size = 24 }: { size?: number }) {
  return <span className="sg-logo" role="img" aria-label="schemagen" style={{ width: size, height: size }}
    dangerouslySetInnerHTML={{ __html: logoSvg }} />;
}
