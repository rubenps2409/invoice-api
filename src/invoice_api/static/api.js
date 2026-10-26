// The only place that talks to the server. Same origin, so there is no CORS to configure.

import { text } from "./strings.js";
import { waitText } from "./format.js";

const TOKEN_KEY = "invoice-api.token";
// A request that takes longer than this is probably waiting for the server to wake up.
const SLOW_AFTER_MS = 2500;
const TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  constructor(status, detail, retryAfter = null) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

// The token lives in sessionStorage: it disappears with the tab. Storage can be blocked,
// so every access is guarded and the page also works with the token in memory only.
let memoryToken = null;
export const session = {
  get token() {
    try {
      return sessionStorage.getItem(TOKEN_KEY) ?? memoryToken;
    } catch {
      return memoryToken;
    }
  },
  save(token) {
    memoryToken = token;
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* in-memory only */
    }
  },
  clear() {
    memoryToken = null;
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* nothing to clear */
    }
  },
};

let onUnauthorized = () => {};
let onSlowChange = () => {};
let slowRequests = 0;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

export function setSlowHandler(handler) {
  onSlowChange = handler;
}

function describe(body, status) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    // Pydantic validation errors: [{loc: ["body", "email"], msg: "..."}]
    const first = detail[0];
    const field = Array.isArray(first.loc) ? first.loc.filter((p) => p !== "body").join(".") : "";
    return field ? `${field}: ${first.msg}` : String(first.msg);
  }
  return status >= 500 ? text.errors.generic : `HTTP ${status}`;
}

export async function request(method, path, { json, form, query, auth = true } = {}) {
  const url = new URL(`/api${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }

  const headers = { Accept: "application/json" };
  const token = session.token;
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    body = new URLSearchParams(form);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let slow = false;
  const slowTimer = setTimeout(() => {
    slow = true;
    slowRequests += 1;
    onSlowChange(true);
  }, SLOW_AFTER_MS);

  try {
    let response;
    try {
      response = await fetch(url, { method, headers, body, signal: controller.signal });
    } catch {
      throw new ApiError(0, text.errors.network);
    }

    const retryHeader = Number(response.headers.get("Retry-After"));
    const retryAfter = Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : null;
    let payload = null;
    if (response.status !== 204) {
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      if (response.status === 401 && auth && token) {
        session.clear();
        onUnauthorized();
      }
      throw new ApiError(response.status, describe(payload, response.status), retryAfter);
    }
    return payload;
  } finally {
    clearTimeout(timeout);
    clearTimeout(slowTimer);
    if (slow) {
      slowRequests -= 1;
      if (slowRequests === 0) onSlowChange(false);
    }
  }
}

// Reads every page of a list endpoint (the API caps a page at 100 items).
export async function listAll(path, query = {}) {
  const items = [];
  const pageSize = 100;
  for (let skip = 0; skip < 5000; skip += pageSize) {
    const page = await request("GET", path, { query: { ...query, skip, limit: pageSize } });
    items.push(...page);
    if (page.length < pageSize) break;
  }
  return items;
}

// A message a person can act on, for an error thrown by `request`.
export function explain(error, { action } = {}) {
  if (!(error instanceof ApiError)) return text.errors.generic;
  const retry = error.retryAfter ? ` ${text.errors.tryAgainIn(waitText(error.retryAfter))}` : "";

  if (error.status === 0) return error.detail;
  if (action === "extract") {
    if (error.status === 422) return `${text.errors.extraction422} ${error.detail}`.trim();
    if (error.status === 502) return text.errors.extraction502;
    if (error.status === 504) return text.errors.extraction504;
    if (error.status === 503) return `${text.errors.extraction503}${retry}`;
  }
  if (action === "login" && error.status === 401) return text.errors.credentials;
  if (error.status === 401) return text.errors.session;
  if (error.status === 429 && (action === "login" || action === "register")) {
    return `${text.errors.tooMany}${retry}`;
  }
  const sentence = /[.!?]$/.test(error.detail) ? error.detail : `${error.detail}.`;
  return `${sentence}${retry}`;
}
