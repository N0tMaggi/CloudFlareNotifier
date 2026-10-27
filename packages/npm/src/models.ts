export interface SecurityEvent {
  zoneId: string;
  zoneName: string;
  action: string;
  source: string;
  clientIp: string;
  country: string;
  ruleId: string;
  /** Description of the rule that matched (GraphQL `description`) */
  ruleMessage: string;
  rayId: string;
  /** Requested host, if the API exposes it */
  host: string;
  /** HTTP method, if the API exposes it */
  method: string;
  /** Request path, if the API exposes it. Attacker-controlled: escape before rendering. */
  path: string;
  /** Query string, if the API exposes it. Attacker-controlled: escape before rendering. */
  query: string;
  /** User agent, if the API exposes it. Attacker-controlled: escape before rendering. */
  userAgent: string;
  /** Client ASN, if the API exposes it */
  asn: string;
  occurredAt: Date | null;
  /** Original GraphQL event object from Cloudflare */
  raw: Record<string, unknown>;
}

export interface WatcherConfig {
  /** Recommended: Cloudflare API token */
  apiToken?: string;
  /** Legacy: API key (requires email) */
  apiKey?: string;
  /** Required when using apiKey */
  email?: string;
  /** One or more Cloudflare zone IDs to monitor (32 hex characters each) */
  zoneIds: string[];
  /** Seconds between polls (default: 60) */
  pollInterval?: number;
  /** How far back to look on first poll, in minutes (default: 15, max: 44640 = 31 days) */
  lookbackMinutes?: number;
  /**
   * Seconds each poll re-reads before the newest event already seen, to catch
   * events Cloudflare ingests late. Duplicates are filtered out (default: 300)
   */
  overlap?: number;
  /** Events requested per zone and page (default: 1000) */
  pageSize?: number;
  /** Per-request timeout in seconds (default: 15) */
  requestTimeout?: number;
  /** Retries for network errors, timeouts, 429 and 5xx responses (default: 3) */
  maxRetries?: number;
  /** Custom fetch implementation, e.g. for proxies or tests */
  fetch?: typeof fetch;
}
