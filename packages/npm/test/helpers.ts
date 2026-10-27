export const ZONE_A = "a".repeat(32);
export const ZONE_B = "b".repeat(32);

export interface GraphQLCall {
  query: string;
  variables: Record<string, unknown>;
}

export interface FakeApiOptions {
  /** Field names of the firewallEventsAdaptive type, or an Error to fail introspection. */
  eventFields?: string[] | Error;
  /** Answer an events query; default returns no events. */
  events?: (call: GraphQLCall) => Response | Promise<Response>;
  zoneName?: (zoneId: string) => string;
}

export const DEFAULT_FIELDS = [
  "action",
  "source",
  "clientIP",
  "clientCountryName",
  "datetime",
  "ruleId",
  "rayName",
  "description",
  "clientRequestPath",
  "userAgent",
];

export function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

/** Wrap per-alias event lists in the GraphQL response shape. */
export function eventsResponse(byAlias: Record<string, Record<string, unknown>[]>): Response {
  const viewer: Record<string, unknown> = {};
  for (const [alias, events] of Object.entries(byAlias)) {
    viewer[alias] = [{ firewallEventsAdaptive: events }];
  }
  return json({ data: { viewer }, errors: null });
}

/** Map zone ID → alias for a batched events query. */
export function aliases(call: GraphQLCall): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(call.variables)) {
    if (key.startsWith("z")) out[value as string] = key;
  }
  return out;
}

const TYPE_FIELDS: Record<string, { name: string; type: unknown }[]> = {
  Query: [{ name: "viewer", type: { name: "viewer" } }],
  viewer: [{ name: "zones", type: { name: null, ofType: { name: null, ofType: { name: "zone" } } } }],
  zone: [{ name: "firewallEventsAdaptive", type: { name: null, ofType: { name: "ZoneFirewallEventsAdaptive" } } }],
};

/** A fetch stand-in for the Cloudflare API that records every call. */
export function fakeApi(options: FakeApiOptions = {}) {
  const graphqlCalls: GraphQLCall[] = [];
  const eventCalls: GraphQLCall[] = [];
  const fields = options.eventFields ?? DEFAULT_FIELDS;

  const fetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url.endsWith("/graphql")) {
      const call = JSON.parse(String(init?.body)) as GraphQLCall;
      graphqlCalls.push(call);
      if (call.query.includes("__schema")) {
        if (fields instanceof Error) return json({ data: null, errors: [{ message: fields.message }] });
        return json({ data: { __schema: { queryType: { name: "Query" } } } });
      }
      if (call.query.includes("__type")) {
        const name = call.variables["name"] as string;
        const typeFields =
          name === "ZoneFirewallEventsAdaptive" && Array.isArray(fields)
            ? fields.map((f) => ({ name: f, type: { name: "string" } }))
            : TYPE_FIELDS[name];
        return json({ data: { __type: typeFields ? { fields: typeFields } : null } });
      }
      eventCalls.push(call);
      return options.events ? options.events(call) : eventsResponse({});
    }
    const zoneId = url.split("/zones/")[1];
    return json({ success: true, result: { name: options.zoneName?.(zoneId) ?? `${zoneId.slice(0, 4)}.example` } });
  };

  return { fetch: fetch as typeof globalThis.fetch, graphqlCalls, eventCalls };
}

/** ISO timestamp `seconds` before now. */
export function ago(seconds: number): string {
  return new Date(Date.now() - seconds * 1000).toISOString();
}

/** Answer events queries for one zone like the API would: time window, ascending order, limit. */
export function serveWindow(events: () => Record<string, unknown>[]) {
  return (call: GraphQLCall): Response => {
    const limit = Number(/limit: (\d+)/.exec(call.query)?.[1]);
    const f = call.variables["f0"] as { datetime_geq: string; datetime_leq: string };
    const from = Date.parse(f.datetime_geq);
    const to = Date.parse(f.datetime_leq);
    const page = events()
      .filter((e) => Date.parse(String(e.datetime)) >= from && Date.parse(String(e.datetime)) <= to)
      .sort((a, b) => Date.parse(String(a.datetime)) - Date.parse(String(b.datetime)))
      .slice(0, limit);
    return eventsResponse({ z0: page });
  };
}

export function event(datetime: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    action: "block",
    source: "firewallManaged",
    clientIP: "203.0.113.7",
    clientCountryName: "DE",
    ruleId: "rule-1",
    rayName: `ray-${datetime}`,
    description: "SQLi attempt",
    datetime,
    ...overrides,
  };
}
