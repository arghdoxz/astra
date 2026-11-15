import type {
  Annotation,
  AnnotationList,
  CrossMatch,
  ExplainRequest,
  Explanation,
  Health,
  HistoryItem,
  Investigation,
  InvestigationRequest,
  ObservationsResponse,
  ResolveResult,
  ReviewItem,
  Status,
} from "@/lib/types";

export const API_BASE: string = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiFailure extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status = 0) {
    super(message);
    this.name = "ApiFailure";
    this.code = code;
    this.status = status;
  }
}

/** True when the investigation was computed live by the backend (frames served from the API). */
export function isLive(inv: Investigation): boolean {
  return inv.generated_from === "live";
}

/** Resolve a relative frame/thumbnail URL for an investigation (live API vs static demo bundle). */
export function assetUrl(inv: Investigation, relUrl: string): string {
  if (/^https?:\/\//i.test(relUrl)) return relUrl;
  if (isLive(inv)) return API_BASE + (relUrl.startsWith("/") ? relUrl : "/" + relUrl);
  const slug = inv.id.replace(/^demo_/, "");
  return `/demo/${slug}/${relUrl.replace(/^\/+/, "")}`;
}

interface ReqOpts {
  method?: "GET" | "POST";
  body?: unknown;
  timeoutMs?: number;
}

async function request<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const { method = "GET", body, timeoutMs = 15000 } = opts;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    if ((e as { name?: string })?.name === "AbortError") {
      throw new ApiFailure("timeout", `The ASTRA service did not respond within ${Math.round(timeoutMs / 1000)} s.`, 0);
    }
    throw new ApiFailure("network", "Could not reach the ASTRA service.", 0);
  }
  clearTimeout(timer);
  let data: unknown = null;
  const text = await res.text().catch(() => "");
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string }; detail?: unknown } | null) ?? null;
    const code = err?.error?.code ?? `http_${res.status}`;
    let message = err?.error?.message;
    if (!message && typeof err?.detail === "string") message = err.detail;
    throw new ApiFailure(code, message ?? `Request failed (HTTP ${res.status}).`, res.status);
  }
  if (data === null) throw new ApiFailure("bad_response", "The service returned an unreadable response.", res.status);
  return data as T;
}

export function getHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export function resolveTarget(q: string): Promise<ResolveResult> {
  return request<ResolveResult>(`/api/resolve?q=${encodeURIComponent(q)}`);
}

export function getObservations(ra: number, dec: number): Promise<ObservationsResponse> {
  return request<ObservationsResponse>(`/api/observations?ra=${ra}&dec=${dec}&collections=spherex_dr1,spherex_qr3`, { timeoutMs: 30000 });
}

export function startInvestigation(req: InvestigationRequest): Promise<{ id: string; status: Status }> {
  return request("/api/investigations", { method: "POST", body: req });
}

export function getInvestigation(id: string): Promise<Investigation> {
  return request<Investigation>(`/api/investigations/${encodeURIComponent(id)}`, { timeoutMs: 10000 }).then(normalizeInvestigation);
}

export function listInvestigations(limit = 20): Promise<{ items: HistoryItem[] }> {
  return request(`/api/investigations?limit=${limit}`);
}

export function crossmatch(ra: number, dec: number, radiusArcsec: number, mjd?: number): Promise<CrossMatch> {
  const q = new URLSearchParams({ ra: String(ra), dec: String(dec), radius_arcsec: String(radiusArcsec) });
  if (mjd !== undefined) q.set("mjd", String(mjd));
  return request<CrossMatch>(`/api/crossmatch?${q.toString()}`, { timeoutMs: 30000 });
}

export function explain(id: string, req: ExplainRequest): Promise<Explanation> {
  return request<Explanation>(`/api/investigations/${encodeURIComponent(id)}/explain`, {
    method: "POST",
    body: req,
    timeoutMs: 60000,
  });
}

export function getAnnotations(candidateId: string): Promise<AnnotationList> {
  return request<AnnotationList>(`/api/candidates/${encodeURIComponent(candidateId)}/annotations`);
}

export function postAnnotation(
  candidateId: string,
  body: { verdict: Annotation["verdict"]; note: string; author?: string },
): Promise<AnnotationList> {
  return request<AnnotationList>(`/api/candidates/${encodeURIComponent(candidateId)}/annotations`, { method: "POST", body });
}

export function listReviewQueue(limit = 50): Promise<{ items: ReviewItem[] }> {
  return request(`/api/candidates?limit=${limit}`);
}

export function reportUrl(id: string, fmt: "json" | "csv" | "md"): string {
  return `${API_BASE}/api/investigations/${encodeURIComponent(id)}/report.${fmt}`;
}

/** Fill array fields that may be absent in partial results so UI code can iterate safely. */
export function normalizeInvestigation(inv: Investigation): Investigation {
  const o = inv as Investigation;
  return {
    ...o,
    visits: o.visits ?? [],
    exposures: o.exposures ?? [],
    frames: o.frames ?? [],
    track: o.track ?? [],
    photometry: o.photometry ?? [],
    candidates: o.candidates ?? [],
    warnings: o.warnings ?? [],
    methods: o.methods ?? [],
    astrometry: { ...(o.astrometry ?? {}), measured: o.astrometry?.measured ?? [] },
  };
}
