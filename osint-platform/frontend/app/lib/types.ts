// Mirrors the backend Pydantic / dataclass shapes (app/osint/verification.py +
// app/osint/correlation.py + app/schemas.py). Keep in sync when the API changes.

export type QueryKind = "name" | "email" | "phone" | "username";

export type FindingType =
  | "name" | "email" | "phone" | "username"
  | "social_profile" | "website" | "domain" | "person"
  | "image";  // perceptual-hash cluster of avatars seen across platforms

// User-spec'd identity-resolution tiers.
//   verified  ≥ 85
//   high      ≥ 70
//   possible  ≥ 50
//   unverified < 50
export type ConfidenceLabel = "verified" | "high" | "possible" | "unverified";

export interface Source {
  url: string;
  title?: string | null;
  source_type: string;
  extracted_at: string;
}

export interface Signal {
  kind: string;
  delta: number;
  reason: string;
  source_url?: string | null;
  at: string;
}

export interface Finding {
  key: string;
  type: FindingType;
  value: string;
  confidence: number;
  verified: boolean;
  label: ConfidenceLabel;
  signals: Signal[];
  match_reasons: string[];
  sources: Source[];
  related_to: string[];
  first_seen: string;
  last_seen: string;
}

export interface ProfileSnapshot {
  url: string;
  platform: string;
  handle?: string | null;
  display_name?: string | null;
  bio?: string | null;
  avatar_url?: string | null;
  title?: string | null;
  extracted_emails: string[];
  extracted_handles: string[];
  extracted_links: string[];
  is_blocked?: boolean;
  parser_confidence?: number;
}

export interface Dork {
  label: string;
  query: string;
  google: string;
  bing: string;
  duckduckgo: string;
}

export interface WhoisRecord {
  domain: string;
  found: boolean;
  registrar?: string | null;
  created?: string | null;
  updated?: string | null;
  expires?: string | null;
  nameservers: string[];
  status: string[];
  contacts: Array<Record<string, string>>;
  raw_url?: string | null;
  error?: string | null;
}

export interface TimelineEntry {
  timestamp: string;
  stage: string;
  detail: string;
}

// One row in the AUTHORITATIVE local DB block (Elasticsearch tc_index hit).
// Confidence is fixed at 100 per spec — `match_strength` carries the ES
// engine's per-match score for the audit trail. Top-level identity fields
// mirror the ES `_source` mapping (UPPERCASE).
export interface LocalDatabaseRecord {
  NAME: string;
  PHONE: string;
  EMAIL: string;
  TAGS: string[] | string;
  ASONDATE: string;
  confidence: 100;
  label: string;
  matched_field: string;
  matched_against: string;
  match_reason: string;
  match_strength: number;
  es_id: string;
  es_score: number;
  timestamp: string;
}

export interface LocalDatabaseBlock {
  display_label: string;
  display_label_banner: string;
  empty_message: string;
  source: string;
  trust_level: string;
  verdict: string;
  found: boolean;
  count: number;
  records: LocalDatabaseRecord[];
}

export interface ExternalOsintListing {
  platform: string;
  username: string;
  link: string;
  confidence: number;
  verified: boolean;
}

export interface ExternalOsintBlock {
  display_label: string;
  display_label_banner: string;
  empty_message: string;
  skipped?: boolean;
  skipped_reason?: string | null;
  source: string;
  trust_level: string;
  key_note: string;
  confidence: number;
  confidence_label: string;
  stats: {
    total_findings: number;
    verified_profiles: number;
    usernames: number;
    emails: number;
    confidence_score: number;
  };
  listings: ExternalOsintListing[];
  results: Record<string, unknown>;
}

export interface SearchResponse {
  id?: number;
  query_kind: QueryKind;
  query_value: string;
  started_at: string;
  finished_at?: string | null;
  summary: Record<string, unknown> & {
    finding_count?: number;
    verified_count?: number;
    high_confidence_count?: number;
    suppressed_count?: number;
    platforms_found?: string[];
    username_count?: number;
    email_count?: number;
    phone_count?: number;
    site_count?: number;
    domain_count?: number;
  };
  local_db?: LocalDatabaseBlock;
  external_osint?: ExternalOsintBlock;
  findings: Finding[];
  related_usernames: string[];
  related_emails: string[];
  related_phones: string[];
  related_websites: string[];
  related_domains: string[];
  social_profiles: Array<{ platform: string; url: string; handle: string }>;
  websites: Array<{ url: string; title: string }>;
  dorks: Dork[];
  metadata_snippets: Array<Record<string, unknown>>;
  profile_snapshots: ProfileSnapshot[];
  whois_records: WhoisRecord[];
  image_clusters: ImageCluster[];
  evidence_ledger: EvidenceRow[];
  timeline: TimelineEntry[];
  confidence_score: number;
  confidence_label: ConfidenceLabel;
  graph: {
    nodes: Array<{ id: string; label: string; group: string; confidence: number; verified: boolean }>;
    edges: Array<{ from: string; to: string; reason?: string; signal?: string }>;
    seed?: string;
  };
  email_report?: Record<string, unknown> | null;
  phone_report?: Record<string, unknown> | null;
}

export interface EvidenceRow {
  at: string;
  finding_key: string;
  type: string;
  value: string;
  signal: string;
  delta: number;
  reason: string;
  source_url: string | null;
}

export interface ImageClusterMember {
  avatar_url: string;
  platform: string;
  handle: string | null;
  profile_url: string | null;
  min_distance: number;
}

export interface ImageCluster {
  size: number;
  platforms: string[];
  representative_hash_hex: string;
  members: ImageClusterMember[];
}

export interface SearchBundleInput {
  name?: string;
  email?: string;
  phone?: string;
  username?: string;
}

export interface HistoryItem {
  id: number;
  created_at: string;
  query_kind: string;
  query_value: string;
  confidence: number;
  confidence_label: ConfidenceLabel;
  summary: Record<string, unknown>;
}

export interface HistoryList { items: HistoryItem[]; total: number; }

// SSE event payloads
export type StreamEvent =
  | { type: "stage";    stage: string; detail: string }
  | { type: "finding";  finding: Finding }
  | { type: "snapshot"; snapshot: ProfileSnapshot }
  | { type: "result";   payload: SearchResponse }
  | { type: "complete"; payload: SearchResponse }
  | { type: "error";    detail: string };
