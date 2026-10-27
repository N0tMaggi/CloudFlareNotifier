/**
 * Internal Cloudflare API client. Not part of the public API.
 *
 * Security events are read from the GraphQL Analytics API
 * (`firewallEventsAdaptive`), the only supported source on all plans.
 */

const BASE_URL = "https://api.cloudflare.com/client/v4";
const GRAPHQL_URL = `${BASE_URL}/graphql`;

/** Cloudflare allows up to 10 zones per zone-scoped GraphQL query. */
export const MAX_ZONES_PER_QUERY = 10;

/** Fields documented for `firewallEventsAdaptive`; always requested. */
const BASE_FIELDS = ["action", "source", "clientIP", "clientCountryName", "datetime"];

/** Requested only when the schema exposes them. */
const OPTIONAL_FIELDS = [
  "ruleId",
  "rayName",
  "description",
  "clientRequestHTTPHost",
  "clientRequestHTTPMethodName",
  "clientRequestPath",
  "clientRequestQuery",
  "userAgent",
  "clientAsn",
];

/** Used when introspection is unavailable; known to work on all plans. */
const FALLBACK_OPTIONAL_FIELDS = ["ruleId", "rayName"];

export type RawEvent = Record<string, unknown>;

export interface ClientConfig {
  apiToken?: string;
  apiKey?: string;
  email?: string;
  /** Per-request timeout in milliseconds. */
  timeoutMs?: number;
  /** Retries for network errors, timeouts, 429 and 5xx responses. */
  maxRetries?: number;
  /** Base delay for exponential backoff in milliseconds. */
  retryBaseMs?: number;
  fetch?: typeof fetch;
}

export interface ZoneQuery {
  zoneId: string;
  since: Date;
}

export type ZoneResult = { events: RawEvent[] } | { error: Error };

interface GraphQLError {
  message?: string;
  path?: (string | number)[];
  extensions?: Record<string, unknown>;
}

interface GraphQLResponse<T> {
  data?: T | null;
  errors?: GraphQLError[] | null;
}

/** Error raised for failed Cloudflare API calls. */
export class CloudflareApiError extends Error {
  readonly status: number;
  readonly endpoint: string;
  readonly errors: readonly { code?: number; message?: string }[];

  constructor(
    message: string,
    status: number,
    endpoint: string,
    errors: readonly { code?: number; message?: string }[] = [],
  ) {
    super(message);
    this.name = "CloudflareApiError";
    this.status = status;
    this.endpoint = endpoint;
    this.errors = errors;
  }
}

export class CloudflareClient {
  private config: Required<Omit<ClientConfig, "apiToken" | "apiKey" | "email">> &
    Pick<ClientConfig, "apiToken" | "apiKey" | "email">;
  private zoneCache = new Map<string, string>();
  private fieldsPromise: Promise<string[]> | null = null;

  constructor(config: ClientConfig) {
    this.config = {
      ...config,
      timeoutMs: config.timeoutMs ?? 15_000,
      maxRetries: config.maxRetries ?? 3,
      retryBaseMs: config.retryBaseMs ?? 500,
      fetch: config.fetch ?? globalThis.fetch.bind(globalThis),
    };
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.config.apiToken) {
      h["Authorization"] = `Bearer ${this.config.apiToken}`;
    } else if (this.config.apiKey && this.config.email) {
      h["X-Auth-Key"] = this.config.apiKey;
      h["X-Auth-Email"] = this.config.email;
    }
    return h;
  }

  /** Resolve zone names in parallel; falls back to the zone ID on failure. */
  async fetchZoneNames(zoneIds: string[], signal?: AbortSignal): Promise<Map<string, string>> {
    const entries = await Promise.all(
      zoneIds.map(async (id) => [id, await this.fetchZoneName(id, signal)] as const),
    );
    return new Map(entries);
  }

  async fetchZoneName(zoneId: string, signal?: AbortSignal): Promise<string> {
    const cached = this.zoneCache.get(zoneId);
    if (cached) return cached;
    let name = zoneId;
    try {
      const data = (await this.request(`${BASE_URL}/zones/${zoneId}`, { method: "GET" }, signal)) as {
        success?: boolean;
        result?: { name?: string };
      };
      if (data.success && data.result?.name) name = data.result.name;
    } catch (err) {
      if (signal?.aborted) throw err;
    }
    this.zoneCache.set(zoneId, name);
    return name;
  }

  /**
   * Fetch one page of events for up to {@link MAX_ZONES_PER_QUERY} zones in a
   * single GraphQL request, ordered oldest first. Errors scoped to a single
   * zone are returned per zone instead of failing the whole batch.
   */
  async fetchEvents(
    queries: ZoneQuery[],
    until: Date,
    limit: number,
    signal?: AbortSignal,
  ): Promise<Map<string, ZoneResult>> {
    if (queries.length === 0) return new Map();
    if (queries.length > MAX_ZONES_PER_QUERY) {
      throw new RangeError(`At most ${MAX_ZONES_PER_QUERY} zones per query.`);
    }
    if (!Number.isInteger(limit) || limit < 1) throw new RangeError("limit must be a positive integer.");

    const fields = (await this.resolveFields(signal)).join(" ");
    const declarations: string[] = [];
    const selections: string[] = [];
    const variables: Record<string, unknown> = {};

    queries.forEach(({ zoneId, since }, i) => {
      declarations.push(`$z${i}: string, $f${i}: FirewallEventsAdaptiveFilter_InputObject`);
      selections.push(
        `z${i}: zones(filter: { zoneTag: $z${i} }) {
          firewallEventsAdaptive(filter: $f${i}, limit: ${limit}, orderBy: [datetime_ASC]) { ${fields} }
        }`,
      );
      variables[`z${i}`] = zoneId;
      variables[`f${i}`] = { datetime_geq: since.toISOString(), datetime_leq: until.toISOString() };
    });

    const query = `query FirewallEvents(${declarations.join(", ")}) { viewer { ${selections.join("\n")} } }`;
    const res = await this.graphql<{ viewer?: Record<string, { firewallEventsAdaptive?: RawEvent[] }[]> }>(
      query,
      variables,
      signal,
    );

    const errorsByAlias = new Map<string, GraphQLError[]>();
    const globalErrors: GraphQLError[] = [];
    for (const err of res.errors ?? []) {
      const alias = err.path?.[0] === "viewer" ? err.path[1] : undefined;
      if (typeof alias === "string") {
        errorsByAlias.set(alias, [...(errorsByAlias.get(alias) ?? []), err]);
      } else {
        globalErrors.push(err);
      }
    }
    if (globalErrors.length || !res.data?.viewer) {
      throw graphqlError(globalErrors.length ? globalErrors : res.errors ?? []);
    }

    const results = new Map<string, ZoneResult>();
    queries.forEach(({ zoneId }, i) => {
      const zoneErrors = errorsByAlias.get(`z${i}`);
      if (zoneErrors) {
        results.set(zoneId, { error: graphqlError(zoneErrors, zoneId) });
        return;
      }
      const events = res.data?.viewer?.[`z${i}`]?.[0]?.firewallEventsAdaptive ?? [];
      results.set(zoneId, { events });
    });
    return results;
  }

  /**
   * Discover which optional event fields the schema exposes, so the query
   * never asks for a field the API rejects. Cached for the client lifetime.
   */
  resolveFields(signal?: AbortSignal): Promise<string[]> {
    this.fieldsPromise ??= this.introspectFields(signal).then(
      (available) => [...BASE_FIELDS, ...OPTIONAL_FIELDS.filter((f) => available.has(f))],
      (err: unknown) => {
        if (signal?.aborted) {
          this.fieldsPromise = null;
          throw err;
        }
        // Transient failures retry introspection next time; anything else
        // (e.g. introspection disabled) settles on the fallback for good.
        if (err instanceof CloudflareApiError && (err.status === 0 || err.status === 429 || err.status >= 500)) {
          this.fieldsPromise = null;
        }
        return [...BASE_FIELDS, ...FALLBACK_OPTIONAL_FIELDS];
      },
    );
    return this.fieldsPromise;
  }

  private async introspectFields(signal?: AbortSignal): Promise<Set<string>> {
    const root = await this.graphql<{ __schema: { queryType: { name: string } } }>(
      "{ __schema { queryType { name } } }",
      {},
      signal,
    );
    let typeName = root.data?.__schema.queryType.name;
    for (const fieldName of ["viewer", "zones", "firewallEventsAdaptive"]) {
      const fields = await this.typeFields(typeName, signal);
      typeName = unwrapTypeName(fields.find((f) => f.name === fieldName)?.type);
      if (!typeName) throw new Error(`Introspection: field ${fieldName} not found.`);
    }
    return new Set((await this.typeFields(typeName, signal)).map((f) => f.name));
  }

  private async typeFields(name: string | undefined, signal?: AbortSignal): Promise<IntrospectionField[]> {
    if (!name) throw new Error("Introspection: missing type name.");
    const res = await this.graphql<{ __type: { fields: IntrospectionField[] | null } | null }>(
      `query($name: String!) { __type(name: $name) { fields { name type { ...T } } } }
       fragment T on __Type { name ofType { name ofType { name ofType { name } } } }`,
      { name },
      signal,
    );
    if (res.errors?.length) throw graphqlError(res.errors);
    return res.data?.__type?.fields ?? [];
  }

  private async graphql<T>(
    query: string,
    variables: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<GraphQLResponse<T>> {
    return (await this.request(
      GRAPHQL_URL,
      { method: "POST", body: JSON.stringify({ query, variables }) },
      signal,
    )) as GraphQLResponse<T>;
  }

  /** JSON request with timeout and retries (network errors, timeouts, 429, 5xx). */
  private async request(url: string, init: RequestInit, signal?: AbortSignal): Promise<unknown> {
    const endpoint = new URL(url).pathname.replace(/^\/client\/v4/, "");
    for (let attempt = 0; ; attempt++) {
      signal?.throwIfAborted();
      let retryAfterMs: number | undefined;
      let failure: Error;
      const { signal: requestSignal, cleanup } = withTimeout(this.config.timeoutMs, signal);
      try {
        // Race against the signal too, in case a custom fetch ignores it.
        const res = await abortable(
          this.config.fetch(url, { ...init, headers: this.headers(), signal: requestSignal }),
          requestSignal,
        );
        const body = (await abortable(res.json().catch(() => null), requestSignal)) as {
          errors?: { code?: number; message?: string }[];
        } | null;
        if (res.ok) return body ?? {};

        const errors = body?.errors ?? [];
        const detail = errors.map((e) => (e.code ? `[${e.code}] ` : "") + (e.message ?? "")).join(", ");
        failure = new CloudflareApiError(
          `Cloudflare API ${endpoint} returned HTTP ${res.status}${detail ? ` – ${detail}` : ""}`,
          res.status,
          endpoint,
          errors,
        );
        if (res.status !== 429 && res.status < 500) throw failure;
        retryAfterMs = parseRetryAfter(res.headers.get("retry-after"));
      } catch (err) {
        if (signal?.aborted) throw err;
        if (err instanceof CloudflareApiError && err.status !== 429 && err.status < 500) throw err;
        failure =
          err instanceof CloudflareApiError
            ? err
            : new CloudflareApiError(
                `Cloudflare API ${endpoint} request failed: ${isTimeout(err) ? `timed out after ${this.config.timeoutMs}ms` : String(err)}`,
                0,
                endpoint,
              );
      } finally {
        cleanup();
      }

      if (attempt >= this.config.maxRetries) throw failure;
      const backoff = this.config.retryBaseMs * 2 ** attempt;
      await sleep(retryAfterMs ?? backoff + Math.random() * backoff * 0.2, signal);
    }
  }
}

// ------------------------------------------------------------------ helpers

interface IntrospectionType {
  name: string | null;
  ofType?: IntrospectionType | null;
}

interface IntrospectionField {
  name: string;
  type: IntrospectionType;
}

function unwrapTypeName(type: IntrospectionType | undefined): string | undefined {
  let t = type;
  while (t && !t.name) t = t.ofType ?? undefined;
  return t?.name ?? undefined;
}

function graphqlError(errors: GraphQLError[], zoneId?: string): CloudflareApiError {
  const detail = errors.map((e) => e.message ?? "").filter(Boolean).join(", ") || "unknown error";
  return new CloudflareApiError(
    `Cloudflare GraphQL query failed${zoneId ? ` for zone ${zoneId}` : ""}: ${detail}`,
    200,
    "/graphql",
    errors.map((e) => ({ message: e.message })),
  );
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(value);
  return Number.isNaN(date) ? undefined : Math.max(0, date - Date.now());
}

function isTimeout(err: unknown): boolean {
  return err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
}

/** Combine a per-request timeout with an optional outer abort signal. */
function withTimeout(ms: number, outer?: AbortSignal): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new DOMException("The operation timed out.", "TimeoutError")),
    ms,
  );
  const onAbort = () => controller.abort(outer?.reason);
  outer?.addEventListener("abort", onAbort, { once: true });
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onAbort);
    },
  };
}

function abortable<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) return Promise.reject(signal.reason);
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(signal.reason);
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
  });
}

/** Resolves after `ms`, or rejects as soon as `signal` aborts. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
