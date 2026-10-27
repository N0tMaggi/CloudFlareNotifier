import { describe, expect, it } from "vitest";
import { CloudFlareWatcher, SecurityEvent, WatcherConfig } from "../src/index.js";
import {
  GraphQLCall,
  ZONE_A,
  ZONE_B,
  ago,
  aliases,
  event,
  eventsResponse,
  fakeApi,
  serveWindow,
} from "./helpers.js";

function watcher(fetch: typeof globalThis.fetch, extra: Partial<WatcherConfig> = {}) {
  return new CloudFlareWatcher({ apiToken: "tok", zoneIds: [ZONE_A], fetch, pollInterval: 0.01, ...extra });
}

/** Run until `done` returns true (checked after every poll), then stop. */
async function runUntil(w: CloudFlareWatcher, api: { eventCalls: GraphQLCall[] }, done: () => boolean) {
  const running = w.start();
  const deadline = Date.now() + 2000;
  while (!done()) {
    if (Date.now() > deadline) throw new Error(`timed out after ${api.eventCalls.length} event queries`);
    await new Promise((r) => setTimeout(r, 5));
  }
  await w.stop();
  await running;
}

function since(call: GraphQLCall, index = 0): string {
  return (call.variables[`f${index}`] as { datetime_geq: string }).datetime_geq;
}

describe("construction", () => {
  it("validates zone IDs", () => {
    expect(() => watcher(fakeApi().fetch, { zoneIds: ["../../user/tokens"] })).toThrow(/Invalid zoneId/);
    expect(() => watcher(fakeApi().fetch, { zoneIds: ["abc"] })).toThrow(/32 hex/);
  });

  it("validates numeric options", () => {
    expect(() => watcher(fakeApi().fetch, { pollInterval: 0 })).toThrow(/pollInterval/);
    expect(() => watcher(fakeApi().fetch, { pageSize: 1.5 })).toThrow(/pageSize/);
    expect(() => watcher(fakeApi().fetch, { lookbackMinutes: 50_000 })).toThrow(/31 days/);
    expect(() => watcher(fakeApi().fetch, { overlap: -1 })).toThrow(/overlap/);
  });

  it("requires credentials", () => {
    expect(() => new CloudFlareWatcher({ zoneIds: [ZONE_A] })).toThrow(/apiToken/);
  });
});

describe("polling", () => {
  it("maps GraphQL events to SecurityEvent", async () => {
    const api = fakeApi({
      events: () => eventsResponse({ z0: [event("2026-01-01T00:00:01Z", { clientRequestPath: "/login" })] }),
    });
    const w = watcher(api.fetch);
    const got: SecurityEvent[] = [];
    w.onEvent((e) => void got.push(e));
    await runUntil(w, api, () => got.length > 0);

    expect(got[0]).toMatchObject({
      zoneId: ZONE_A,
      zoneName: "aaaa.example",
      action: "block",
      clientIp: "203.0.113.7",
      country: "DE",
      ruleId: "rule-1",
      ruleMessage: "SQLi attempt",
      rayId: "ray-2026-01-01T00:00:01Z",
      path: "/login",
      host: "",
      occurredAt: new Date("2026-01-01T00:00:01Z"),
    });
  });

  it("pages through a full window without losing events", async () => {
    const all = [50, 40, 30, 20, 10].map((s) => event(ago(s)));
    const api = fakeApi({ events: serveWindow(() => all) });
    const w = watcher(api.fetch, { pageSize: 2 });
    const got: string[] = [];
    w.onEvent((e) => void got.push(e.rayId));
    await runUntil(w, api, () => api.eventCalls.length >= 6);

    expect(got).toEqual(all.map((e) => e.rayName));
    // Each page after the first continues from the newest timestamp of the previous one.
    expect(since(api.eventCalls[1])).toBe(all[1].datetime);
    expect(since(api.eventCalls[2])).toBe(all[2].datetime);
  });

  it("re-reads the overlap window and dispatches late events exactly once", async () => {
    const now = Date.now();
    const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();
    const early = event(iso(-60_000), { rayName: "early" });
    const late = event(iso(-30_000), { rayName: "late" }); // older than `early`'s poll, ingested later
    let polls = 0;
    const api = fakeApi({
      events: () => eventsResponse({ z0: ++polls === 1 ? [early] : [early, late] }),
    });
    const w = watcher(api.fetch, { overlap: 300 });
    const got: string[] = [];
    w.onEvent((e) => void got.push(e.rayId));
    await runUntil(w, api, () => polls >= 3);

    expect(got).toEqual(["early", "late"]);
    const secondSince = Date.parse(since(api.eventCalls[1]));
    expect(secondSince).toBeLessThan(now - 200_000);
  });

  it("treats events from one request with different rules as distinct", async () => {
    const at = ago(10);
    const both = [event(at, { rayName: "r1", ruleId: "a" }), event(at, { rayName: "r1", ruleId: "b" })];
    const api = fakeApi({ events: serveWindow(() => both) });
    const w = watcher(api.fetch);
    const got: string[] = [];
    w.onEvent((e) => void got.push(e.ruleId));
    await runUntil(w, api, () => api.eventCalls.length >= 2);
    expect(got).toEqual(["a", "b"]);
  });

  it("reports when a full page cannot advance and moves on", async () => {
    const at = ago(10);
    const same = [1, 2, 3].map((i) => event(at, { rayName: `r${i}` }));
    const api = fakeApi({ events: serveWindow(() => same) });
    const w = watcher(api.fetch, { pageSize: 2 });
    const errors: unknown[] = [];
    w.onError((e) => errors.push(e));
    await runUntil(w, api, () => errors.length > 0);
    expect(String(errors[0])).toMatch(/share one timestamp/);
  });

  it("batches up to 10 zones per request", async () => {
    const zones = Array.from({ length: 12 }, (_, i) => i.toString(16).padStart(32, "0"));
    const api = fakeApi();
    const w = watcher(api.fetch, { zoneIds: zones });
    await runUntil(w, api, () => api.eventCalls.length >= 2);
    expect(Object.keys(aliases(api.eventCalls[0]))).toHaveLength(10);
    expect(Object.keys(aliases(api.eventCalls[1]))).toHaveLength(2);
  });

  it("keeps polling other zones when one zone fails", async () => {
    const api = fakeApi({
      events: (call) => {
        const a = aliases(call);
        return new Response(
          JSON.stringify({
            data: { viewer: { [a[ZONE_A]]: null, [a[ZONE_B]]: [{ firewallEventsAdaptive: [event("2026-01-01T00:00:01Z")] }] } },
            errors: [{ message: "not authorized", path: ["viewer", a[ZONE_A]] }],
          }),
        );
      },
    });
    const w = watcher(api.fetch, { zoneIds: [ZONE_A, ZONE_B], lookbackMinutes: 60 * 24 * 31 });
    const got: string[] = [];
    const errors: unknown[] = [];
    w.onEvent((e) => void got.push(e.zoneId));
    w.onError((e) => errors.push(e));
    await runUntil(w, api, () => got.length > 0 && errors.length > 0);
    expect(got).toEqual([ZONE_B]);
    expect(String(errors[0])).toMatch(/not authorized/);
  });

  it("reports handler errors without stopping other handlers", async () => {
    const api = fakeApi({ events: () => eventsResponse({ z0: [event("2026-01-01T00:00:01Z")] }) });
    const w = watcher(api.fetch, { lookbackMinutes: 60 * 24 * 31 });
    const calls: string[] = [];
    const errors: unknown[] = [];
    w.onEvent(() => {
      throw new Error("boom");
    });
    w.onEvent(() => void calls.push("ok"));
    w.onError((e) => errors.push(e));
    await runUntil(w, api, () => calls.length > 0);
    expect(String(errors[0])).toMatch(/boom/);
  });
});

describe("lifecycle", () => {
  it("returns the same promise when started twice", async () => {
    const api = fakeApi();
    const w = watcher(api.fetch);
    const a = w.start();
    const b = w.start();
    expect(a).toBe(b);
    await w.stop();
    await a;
  });

  it("stop() interrupts the poll interval sleep and in-flight requests", async () => {
    const api = fakeApi({
      events: () => new Promise<Response>(() => {}), // never resolves
    });
    const w = watcher(api.fetch, { pollInterval: 3600, requestTimeout: 3600 });
    const running = w.start();
    while (api.eventCalls.length === 0) await new Promise((r) => setTimeout(r, 5));
    const started = Date.now();
    await w.stop();
    await running;
    expect(Date.now() - started).toBeLessThan(500);
  });

  it("can be restarted after stop()", async () => {
    const api = fakeApi();
    const w = watcher(api.fetch);
    await runUntil(w, api, () => api.eventCalls.length >= 1);
    const before = api.eventCalls.length;
    await runUntil(w, api, () => api.eventCalls.length > before);
  });
});
