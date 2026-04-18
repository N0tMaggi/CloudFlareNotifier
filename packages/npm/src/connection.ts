/**
 * Internal Cloudflare API client. Not part of the public API.
 *
 * Tries REST /security/events → /firewall/events → GraphQL analytics
 * to remain compatible across all Cloudflare plans.
 */

const BASE_URL = "https://api.cloudflare.com/client/v4";
const GRAPHQL_URL = `${BASE_URL}/graphql`;

type RawEvent = Record<string, unknown>;

interface ConnectionConfig {
  apiToken?: string;
  apiKey?: string;
  email?: string;
}

export class CloudflareClient {
  private config: ConnectionConfig;
  private zoneCache = new Map<string, string>();

  constructor(config: ConnectionConfig) {
    this.config = config;
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

  async fetchZoneName(zoneId: string): Promise<string> {
    if (this.zoneCache.has(zoneId)) return this.zoneCache.get(zoneId)!;
    try {
      const res = await fetch(`${BASE_URL}/zones/${zoneId}`, { headers: this.headers() });
      const data = (await res.json()) as { success: boolean; result?: { name: string } };
      const name = data?.result?.name ?? zoneId;
      this.zoneCache.set(zoneId, name);
      return name;
    } catch {
      this.zoneCache.set(zoneId, zoneId);
      return zoneId;
    }
  }

  async fetchSecurityEvents(
    zoneId: string,
    since?: string,
    perPage = 50,
  ): Promise<RawEvent[]> {
    const params = new URLSearchParams({ per_page: String(perPage), page: "1" });
    if (since) params.set("since", since);
    const failures: string[] = [];

    for (const path of [
      `/zones/${zoneId}/security/events`,
      `/zones/${zoneId}/firewall/events`,
    ]) {
      try {
        const res = await fetch(`${BASE_URL}${path}?${params}`, { headers: this.headers() });
        const data = (await res.json()) as {
          success: boolean;
          result?: unknown;
          errors?: { code: number; message?: string }[];
        };
        if (res.status === 404) continue;
        if (data.errors?.some((e) => [7000, 7003].includes(e.code))) continue;
        if (!res.ok || !data.success) {
          const detail = data.errors
            ?.map((e) => `[${e.code}] ${e.message ?? ""}`.trim())
            .join(", ");
          failures.push(`${path}: HTTP ${res.status}${detail ? ` – ${detail}` : ""}`);
          continue;
        }
        return this.extractEvents(data.result);
      } catch (err) {
        failures.push(`${path}: ${String(err)}`);
        continue;
      }
    }

    return this.fetchGraphQL(zoneId, since, perPage, failures);
  }

  private async fetchGraphQL(
    zoneId: string,
    since?: string,
    limit = 50,
    priorFailures: string[] = [],
  ): Promise<RawEvent[]> {
    const fallbackSince =
      since ?? new Date(Date.now() - 60 * 60 * 1000).toISOString().replace("+00:00", "Z");

    const query = `
      query($zone: String!, $limit: Int!, $since: Time!) {
        viewer {
          zones(filter: { zoneTag: $zone }) {
            firewallEventsAdaptive(
              limit: $limit
              orderBy: [datetime_DESC]
              filter: { datetime_geq: $since }
            ) {
              action source clientIP clientCountryName
              ruleId ruleMessage rayName datetime
            }
          }
        }
      }
    `;

    try {
      const res = await fetch(GRAPHQL_URL, {
        method: "POST",
        headers: this.headers(),
        body: JSON.stringify({ query, variables: { zone: zoneId, limit, since: fallbackSince } }),
      });
      const data = (await res.json()) as {
        errors?: { message?: string }[];
        data?: { viewer?: { zones?: { firewallEventsAdaptive?: RawEvent[] }[] } };
      };
      if (!res.ok || data.errors) {
        const detail = data.errors?.map((e) => e.message ?? "").join(", ");
        priorFailures.push(`graphql: HTTP ${res.status}${detail ? ` – ${detail}` : ""}`);
        throw new Error(
          `All Cloudflare endpoints failed for zone ${zoneId}:\n  ${priorFailures.join("\n  ")}`,
        );
      }

      const events = data?.data?.viewer?.zones?.[0]?.firewallEventsAdaptive ?? [];
      return events.map((ev) => ({
        action: ev["action"],
        source: ev["source"],
        client_ip: ev["clientIP"],
        client_country_name: ev["clientCountryName"],
        rule_id: ev["ruleId"],
        rule_message: ev["ruleMessage"] ?? "",
        ray_id: ev["rayName"],
        datetime: ev["datetime"],
      }));
    } catch (err) {
      if (err instanceof Error && err.message.startsWith("All Cloudflare endpoints failed")) throw err;
      priorFailures.push(`graphql: ${String(err)}`);
      throw new Error(
        `All Cloudflare endpoints failed for zone ${zoneId}:\n  ${priorFailures.join("\n  ")}`,
      );
    }
  }

  extractEvents(result: unknown): RawEvent[] {
    if (!result) return [];
    if (Array.isArray(result)) return result as RawEvent[];
    if (typeof result === "object" && result !== null) {
      const r = result as Record<string, unknown>;
      for (const key of ["security_events", "events", "result"]) {
        if (Array.isArray(r[key])) return r[key] as RawEvent[];
      }
    }
    return [];
  }
}
