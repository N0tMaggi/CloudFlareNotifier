export interface SecurityEvent {
  zoneId: string;
  zoneName: string;
  action: string;
  source: string;
  clientIp: string;
  country: string;
  ruleId: string;
  ruleMessage: string;
  rayId: string;
  occurredAt: Date | null;
  /** Original raw event dict from Cloudflare */
  raw: Record<string, unknown>;
}

export interface WatcherConfig {
  /** Recommended: Cloudflare API token */
  apiToken?: string;
  /** Legacy: API key (requires email) */
  apiKey?: string;
  /** Required when using apiKey */
  email?: string;
  /** One or more Cloudflare zone IDs to monitor */
  zoneIds: string[];
  /** Seconds between polls (default: 60) */
  pollInterval?: number;
  /** How far back to look on first poll, in minutes (default: 15) */
  lookbackMinutes?: number;
}
