// Placeholder (stream C replaces): KindIcon and Logo, as named in docs/design-tokens.md.
import logo from "./logo.svg";

export function KindIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true" data-kind={kind}>
    <rect x="2.5" y="3.5" width="11" height="9" rx="2" /></svg>;
}

export function Logo({ size = 24 }: { size?: number }) {
  return <img src={logo} width={size} height={size} alt="schemagen" />;
}
