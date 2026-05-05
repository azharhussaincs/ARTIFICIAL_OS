import type {
  HistoryList,
  QueryKind,
  SearchBundleInput,
  SearchResponse,
} from "./types";

// All requests are relative — Next.js rewrites /api/* to the backend.
async function http<T>(input: RequestInfo, init: RequestInit = {}): Promise<T> {
  const r = await fetch(input, {
    ...init,
    headers: { "content-type": "application/json", ...(init.headers || {}) },
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 240)}`);
  return r.json() as Promise<T>;
}

export const api = {
  search: (kind: QueryKind, value: string) =>
    http<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify({ kind, value }),
    }),

  searchBundle: (bundle: SearchBundleInput) =>
    http<SearchResponse>("/api/search/bundle", {
      method: "POST",
      body: JSON.stringify(bundle),
    }),

  dorks: (kind: QueryKind, value: string) =>
    http<{ count: number; dorks: SearchResponse["dorks"] }>("/api/dorks", {
      method: "POST",
      body: JSON.stringify({ kind, value }),
    }),

  history: (limit = 20, offset = 0) =>
    http<HistoryList>(`/api/history?limit=${limit}&offset=${offset}`),

  historyOne: (id: number) =>
    http<SearchResponse>(`/api/history/${id}`),

  exportCsvUrl: (id: number) => `/api/export/${id}/csv`,
  exportPdfUrl: (id: number) => `/api/export/${id}/pdf`,

  health: () => http<{ status: string }>("/api/health"),
};

export function streamSearch(
  kind: QueryKind,
  value: string,
): EventSource {
  const url = `/api/search/stream?kind=${encodeURIComponent(kind)}&value=${encodeURIComponent(value)}`;
  return new EventSource(url);
}
