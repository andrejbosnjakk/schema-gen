// The one way to talk to the server: retries GETs, turns every failure into a plain sentence (docs/api.md, Errors).

export class ApiError extends Error {
  constructor(public code: string, message: string, public retry: boolean) { super(message); }
}

type Handler = (method: string, path: string, body: unknown) => Promise<{ status: number; json: unknown }>;
let mock: Handler | null = null, mockStep = 40;
/** Route every call to an in-memory server (the e2e and dev mock, `?mock=1`). */
export function useMock(h: Handler, step = 40) { mock = h; mockStep = step; }

const OFFLINE = "schemagen is not answering. It may have been closed, or it is still starting.";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The error a non-2xx answer carries, or a plain one when the body is not the contract's. */
function toError(status: number, body: unknown): ApiError {
  const e = (body as { error?: { code?: string; message?: string; retry?: boolean } } | null)?.error;
  if (e?.message) return new ApiError(e.code || "internal", e.message, !!e.retry);
  return new ApiError("internal", "Something went wrong inside schemagen. The details are in its log file.", status >= 500);
}

async function once<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (mock) {
    const r = await mock(method, path, body);
    if (r.status >= 400) throw toError(r.status, r.json);
    return r.json as T;
  }
  let r: Response;
  try {
    r = await fetch(path, { method, headers: body === undefined ? undefined : { "content-type": "application/json" },
                            body: body === undefined ? undefined : JSON.stringify(body) });
  } catch { throw new ApiError("offline", OFFLINE, true); }
  let j: unknown = null;
  try { j = await r.json(); } catch { /* not JSON */ }
  if (!r.ok) throw toError(r.status, j);
  return j as T;
}

/** GET with three tries and backoff (only for errors worth retrying). */
export async function get<T>(path: string): Promise<T> {
  for (let i = 0; ; i++) {
    try { return await once<T>("GET", path); } catch (e) {
      if (i >= 2 || !(e instanceof ApiError) || !e.retry) throw e;
      await sleep(300 * 3 ** i);
    }
  }
}
export const post = <T>(path: string, body: unknown = {}) => once<T>("POST", path, body);
export const del = <T>(path: string) => once<T>("DELETE", path);

/** Upload a file (multipart `file`) with progress 0..1 while sending; resolves with the answer once the server is done. */
export function upload<T>(path: string, file: File, onProgress: (f: number) => void): Promise<T> {
  if (mock) {
    const m = mock;
    return (async () => {
      for (let f = 0.2; f <= 1.01; f += 0.2) { onProgress(Math.min(f, 1)); await sleep(mockStep); }
      const r = await m("POST", path, file);
      if (r.status >= 400) throw toError(r.status, r.json);
      return r.json as T;
    })();
  }
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", path);
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    x.upload.onload = () => onProgress(1);
    x.onerror = () => reject(new ApiError("offline", OFFLINE, true));
    x.onload = () => {
      let j: unknown = null;
      try { j = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) resolve(j as T); else reject(toError(x.status, j));
    };
    const fd = new FormData(); fd.append("file", file);
    x.send(fd);
  });
}

/** A plain sentence for anything thrown. */
export const say = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
export const canRetry = (e: unknown) => !(e instanceof ApiError) || e.retry;

/** Tell the tour (docs/tour.md) what the user just did. */
export const act = (action: string) => window.dispatchEvent(new CustomEvent("schemagen:action", { detail: { action } }));
