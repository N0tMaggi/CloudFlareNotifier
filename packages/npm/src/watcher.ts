import { EventEmitter } from "events";
import { CloudflareClient } from "./connection.js";
import { SecurityEvent, WatcherConfig } from "./models.js";

type EventHandler = (event: SecurityEvent) => void | Promise<void>;

/**
 * Poll Cloudflare security events and emit them as Node.js events.
 *
 * @example
 * ```ts
 * import { CloudFlareWatcher } from "cloudflare-notifier";
 *
 * const watcher = new CloudFlareWatcher({
 *   apiToken: process.env.CF_TOKEN!,
 *   zoneIds: ["your-zone-id"],
 * });
 *
 * watcher.on("event", (event) => {
 *   console.log(event.action, event.clientIp);
 * });
 *
 * watcher.start();
 * ```
 */
export class CloudFlareWatcher extends EventEmitter {
  private client: CloudflareClient;
  private config: Required<WatcherConfig>;
  private lastSeen = new Map<string, Date>();
  private running = false;
  private timer: NodeJS.Timeout | null = null;

  constructor(config: WatcherConfig) {
    super();
    if (!config.apiToken && !(config.apiKey && config.email)) {
      throw new Error("Provide apiToken or both apiKey and email.");
    }
    if (!config.zoneIds || config.zoneIds.length === 0) {
      throw new Error("Provide at least one zoneId.");
    }
    this.config = {
      apiToken: config.apiToken ?? "",
      apiKey: config.apiKey ?? "",
      email: config.email ?? "",
      zoneIds: config.zoneIds,
      pollInterval: config.pollInterval ?? 60,
      lookbackMinutes: config.lookbackMinutes ?? 15,
    };
    this.client = new CloudflareClient({
      apiToken: this.config.apiToken || undefined,
      apiKey: this.config.apiKey || undefined,
      email: this.config.email || undefined,
    });
  }

  /** Register a handler for security events. */
  onEvent(handler: EventHandler): this {
    return super.on("event", handler as (...args: unknown[]) => void);
  }

  /** Start polling. Resolves when stop() is called. */
  async start(): Promise<void> {
    this.running = true;
    const cutoff = new Date(Date.now() - this.config.lookbackMinutes * 60 * 1000);

    const zoneNames = new Map<string, string>();
    for (const zoneId of this.config.zoneIds) {
      zoneNames.set(zoneId, await this.client.fetchZoneName(zoneId));
      if (!this.lastSeen.has(zoneId)) this.lastSeen.set(zoneId, cutoff);
    }

    return new Promise((resolve) => {
      const tick = async (): Promise<void> => {
        if (!this.running) {
          resolve();
          return;
        }
        await this.poll(zoneNames);
        this.timer = setTimeout(tick, this.config.pollInterval * 1000);
      };
      void tick();
    });
  }

  /** Stop polling after the current cycle completes. */
  stop(): void {
    this.running = false;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private async poll(zoneNames: Map<string, string>): Promise<void> {
    for (const zoneId of this.config.zoneIds) {
      const since = this.lastSeen.get(zoneId);
      const rawEvents = await this.client.fetchSecurityEvents(
        zoneId,
        since ? toIsoZ(since) : undefined,
      );
      if (!rawEvents) continue;

      const newEvents: [Date | null, Record<string, unknown>][] = [];
      for (const raw of rawEvents) {
        const evTs = parseTs(raw);
        if (since && evTs && evTs <= since) continue;
        newEvents.push([evTs, raw]);
      }
      if (!newEvents.length) continue;

      newEvents.sort(([a], [b]) => (a?.getTime() ?? 0) - (b?.getTime() ?? 0));

      let latest = since ?? null;
      for (const [evTs, raw] of newEvents) {
        const event = toEvent(zoneId, zoneNames.get(zoneId) ?? zoneId, raw, evTs);
        this.emit("event", event);
        if (evTs) latest = latest ? (evTs > latest ? evTs : latest) : evTs;
      }
      if (latest) this.lastSeen.set(zoneId, latest);
    }
  }
}

// ------------------------------------------------------------------ helpers

function parseTs(raw: Record<string, unknown>): Date | null {
  for (const key of ["occurred_at", "datetime", "timestamp", "time"]) {
    const val = raw[key];
    if (!val) continue;
    const d = new Date(String(val));
    if (!isNaN(d.getTime())) return d;
  }
  return null;
}

function toIsoZ(d: Date): string {
  return d.toISOString().replace("+00:00", "Z");
}

function toEvent(
  zoneId: string,
  zoneName: string,
  raw: Record<string, unknown>,
  occurredAt: Date | null,
): SecurityEvent {
  return {
    zoneId,
    zoneName,
    action: String(raw["action"] ?? raw["outcome"] ?? ""),
    source: String(raw["source"] ?? raw["kind"] ?? raw["service"] ?? ""),
    clientIp: String(raw["client_ip"] ?? raw["ip"] ?? ""),
    country: String(raw["client_country_name"] ?? raw["country"] ?? ""),
    ruleId: String(raw["rule_id"] ?? ""),
    ruleMessage: String(raw["rule_message"] ?? ""),
    rayId: String(raw["ray_id"] ?? raw["rayid"] ?? ""),
    occurredAt,
    raw,
  };
}
