import { describe, expect, it } from "vitest";
import { CloudflareApiError, CloudflareClient } from "../src/connection.js";
import { ZONE_A, ZONE_B, aliases, event, eventsResponse, fakeApi, json } from "./helpers.js";

const since = new Date("2026-01-01T00:00:00Z");
const until = new Date("2026-01-01T01:00:00Z");

function client(fetch: typeof globalThis.fetch, extra: Partial<ConstructorParameters<typeof CloudflareClient>[0]> = {}) {
  return new CloudflareClient({ apiToken: "tok", fetch, retryBaseMs: 1, ...extra });
}

describe("field discovery", () => {
  it("requests optional fields the schema exposes and skips the rest", async () => {
    const api = fakeApi();
    await client(api.fetch).fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    const query = api.eventCalls[0].query;
    expect(query).toContain("description");
    expect(query).toContain("clientRequestPath");
    expect(query).not.toContain("clientRequestHTTPHost");
    expect(query).not.toContain("ruleMessage");
  });

  it("falls back to the known-safe field set when introspection fails", async () => {
    const api = fakeApi({ eventFields: new Error("introspection disabled") });
    const c = client(api.fetch);
    await c.fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    await c.fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    expect(api.eventCalls[0].query).toMatch(/action source clientIP clientCountryName datetime ruleId rayName \}/);
    expect(api.graphqlCalls.filter((c) => c.query.includes("__schema"))).toHaveLength(1);
  });

  it("introspects only once per client", async () => {
    const api = fakeApi();
    const c = client(api.fetch);
    await c.fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    await c.fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    expect(api.graphqlCalls.length - api.eventCalls.length).toBe(5);
  });
});

describe("fetchEvents", () => {
  it("queries several zones in one request, oldest first, and maps results back by alias", async () => {
    const api = fakeApi({
      events: (call) => {
        const a = aliases(call);
        return eventsResponse({ [a[ZONE_A]]: [event("2026-01-01T00:10:00Z")], [a[ZONE_B]]: [] });
      },
    });
    const results = await client(api.fetch).fetchEvents(
      [{ zoneId: ZONE_A, since }, { zoneId: ZONE_B, since }],
      until,
      25,
    );

    expect(api.eventCalls).toHaveLength(1);
    const call = api.eventCalls[0];
    expect(call.query).toContain("orderBy: [datetime_ASC]");
    expect(call.query).toContain("limit: 25");
    expect(call.variables["f0"]).toEqual({ datetime_geq: since.toISOString(), datetime_leq: until.toISOString() });
    expect(results.get(ZONE_A)).toEqual({ events: [event("2026-01-01T00:10:00Z")] });
    expect(results.get(ZONE_B)).toEqual({ events: [] });
  });

  it("isolates errors scoped to one zone", async () => {
    const api = fakeApi({
      events: (call) => {
        const a = aliases(call);
        return json({
          data: { viewer: { [a[ZONE_A]]: [{ firewallEventsAdaptive: [] }], [a[ZONE_B]]: null } },
          errors: [{ message: "zone not authorized", path: ["viewer", a[ZONE_B]] }],
        });
      },
    });
    const results = await client(api.fetch).fetchEvents(
      [{ zoneId: ZONE_A, since }, { zoneId: ZONE_B, since }],
      until,
      10,
    );
    expect(results.get(ZONE_A)).toEqual({ events: [] });
    const b = results.get(ZONE_B);
    expect(b && "error" in b && b.error.message).toMatch(/zone not authorized/);
  });

  it("throws on query-wide GraphQL errors", async () => {
    const api = fakeApi({ events: () => json({ data: null, errors: [{ message: "bad query" }] }) });
    await expect(client(api.fetch).fetchEvents([{ zoneId: ZONE_A, since }], until, 10)).rejects.toThrow(
      /bad query/,
    );
  });

  it("rejects more than 10 zones per query", async () => {
    const zones = Array.from({ length: 11 }, (_, i) => ({ zoneId: String(i).padStart(32, "0"), since }));
    await expect(client(fakeApi().fetch).fetchEvents(zones, until, 10)).rejects.toThrow(RangeError);
  });
});

describe("retries and timeouts", () => {
  /** Fails the first `failures` events queries with `response`, then succeeds. */
  function flaky(failures: number, response: () => Response | Promise<Response>) {
    let calls = 0;
    const api = fakeApi({
      events: () => (++calls <= failures ? response() : eventsResponse({ z0: [event("2026-01-01T00:10:00Z")] })),
    });
    return { api, calls: () => calls };
  }

  it("retries 5xx responses", async () => {
    const { api, calls } = flaky(2, () => json({ errors: [{ code: 10000, message: "oops" }] }, { status: 502 }));
    const res = await client(api.fetch).fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    expect(calls()).toBe(3);
    expect(res.get(ZONE_A)).toEqual({ events: [event("2026-01-01T00:10:00Z")] });
  });

  it("honours Retry-After on 429", async () => {
    const { api, calls } = flaky(1, () => json({}, { status: 429, headers: { "Retry-After": "0" } }));
    await client(api.fetch, { retryBaseMs: 60_000 }).fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    expect(calls()).toBe(2);
  });

  it("retries network errors", async () => {
    const { api, calls } = flaky(1, () => Promise.reject(new TypeError("fetch failed")));
    await client(api.fetch).fetchEvents([{ zoneId: ZONE_A, since }], until, 10);
    expect(calls()).toBe(2);
  });

  it("does not retry other 4xx responses and exposes status and Cloudflare errors", async () => {
    const { api, calls } = flaky(1, () =>
      json({ success: false, errors: [{ code: 10000, message: "Authentication error" }] }, { status: 403 }),
    );
    const err = await client(api.fetch)
      .fetchEvents([{ zoneId: ZONE_A, since }], until, 10)
      .catch((e: unknown) => e);
    expect(calls()).toBe(1);
    expect(err).toBeInstanceOf(CloudflareApiError);
    expect(err).toMatchObject({ status: 403, endpoint: "/graphql", errors: [{ code: 10000 }] });
    expect((err as Error).message).toContain("[10000] Authentication error");
  });

  it("gives up after maxRetries", async () => {
    const { api, calls } = flaky(10, () => json({}, { status: 503 }));
    await expect(
      client(api.fetch, { maxRetries: 2 }).fetchEvents([{ zoneId: ZONE_A, since }], until, 10),
    ).rejects.toThrow(/HTTP 503/);
    expect(calls()).toBe(3);
  });

  it("times out hanging requests", async () => {
    const hanging = (_: unknown, init?: RequestInit) =>
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      });
    const c = client(hanging as typeof globalThis.fetch, { timeoutMs: 20, maxRetries: 1 });
    const started = Date.now();
    await expect(c.fetchZoneName(ZONE_A)).resolves.toBe(ZONE_A);
    expect(Date.now() - started).toBeLessThan(1000);

    await expect(c.fetchEvents([{ zoneId: ZONE_A, since }], until, 10)).rejects.toThrow(/timed out after 20ms/);
  });

  it("stops retrying immediately when the caller aborts", async () => {
    const { api } = flaky(10, () => json({}, { status: 503 }));
    const abort = new AbortController();
    const pending = client(api.fetch, { retryBaseMs: 60_000 }).fetchEvents(
      [{ zoneId: ZONE_A, since }],
      until,
      10,
      abort.signal,
    );
    setTimeout(() => abort.abort(), 20);
    await expect(pending).rejects.toBeDefined();
  });
});
