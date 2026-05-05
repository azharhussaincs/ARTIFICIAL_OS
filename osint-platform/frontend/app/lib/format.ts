import type { FindingType, ConfidenceLabel } from "./types";

export function shortHost(url: string): string {
  try { return new URL(url).host.replace(/^www\./, ""); }
  catch { return url; }
}

export function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

export function tsShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return iso; }
}

export const TYPE_COLOR: Record<FindingType, string> = {
  name:           "#22d3ee",
  username:       "#a78bfa",
  email:          "#34d399",
  phone:          "#fbbf24",
  social_profile: "#f43f5e",
  website:        "#94a3b8",
  domain:         "#60a5fa",
  person:         "#22d3ee",
  image:          "#f0abfc",
};

export const TYPE_LABEL: Record<FindingType, string> = {
  name: "Name",
  username: "Username",
  email: "Email",
  phone: "Phone",
  social_profile: "Profile",
  website: "Website",
  domain: "Domain",
  person: "Person",
  image: "Image",
};

export function confClass(label: ConfidenceLabel): string {
  return ({
    verified:   "conf-verified",
    high:       "conf-high",
    possible:   "conf-possible",
    unverified: "conf-unverified",
  } as const)[label] || "conf-unverified";
}
