import { EventEmitter } from "events";
import { CloudflareClient, MAX_ZONES_PER_QUERY, RawEvent, sleep } from "./connection.js";
import { SecurityEvent, WatcherConfig } from "./models.js";

type EventHandler = (event: SecurityEvent) => void | Promise<void>;
type ErrorHandler = (error: unknown) => void;

const ZONE_ID_PATTERN = /^[0-9a-f]{32}$/i;
/** firewallEventsAdaptive keeps at least 31 days of data on every plan. */
const MAX_LOOKBACK_MINUTES = 31 * 24 * 60;
/** Safety cap on pages fetched per zone in a single poll. */
const MAX_PAGES_PER_POLL = 100;

interface ResolvedConfig {
  zoneIds: string[];
  pollInterval: number;
  lookbackMinutes: number;
  overlap: number;
  pageSize: number;
}

/**
 * Poll Cloudflare security events and emit them as Node.js events.
 *
 * @example
 * ```ts
 * import { CloudFlareWatcher } from "@maggidev/cloudflare-notifier";
 *
 * const watcher = new CloudFlareWatcher({
 *   apiToken: process.env.CLOUDFLARE_API_TOKEN!,
 *   zoneIds: ["your-zone-id"],
 * });
 *
 * watcher.onEvent((event) => {
 *   console.log(event.action, event.clientIp);
 * });
 *
 * watcher.start();
 * ```
 */
export class CloudFlareWatcher extends EventEmitter {
  private client: CloudflareClient;
  private config: ResolvedConfig;
  /** Per zone: end of the last fully read time window. */
  private watermark = new Map<string, Date>();
  /** Dedupe keys of dispatched events → zone and event time (ms). */
  private seen = new Map<string, { zoneId: string; ts: number }>();
  private abort: AbortController | null = null;
  private runPromise: Promise<void> | null = null;

  constructor(config: WatcherConfig) {
    super();
    if (!config.apiToken && !(config.apiKey && config.email)) {
      throw new Error("Provide apiToken or both apiKey and email.");
    }
    if (!config.zoneIds || config.zoneIds.length === 0) {
      throw new Error("Provide at least one zoneId.");
    }
    const invalid = config.zoneIds.filter((id) => !ZONE_ID_PATTERN.test(id));
    if (invalid.length) {
      throw new Error(`Invalid zoneId(s): ${invalid.join(", ")}. Expected 32 hex characters.`);
    }

    this.config = {
      zoneIds: [...new Set(config.zoneIds.map((id) => id.toLowerCase()))],
      pollInterval: positive("pollInterval", config.pollInterval ?? 60),
      lookbackMinutes: positive("lookbackMinutes", config.lookbackMinutes ?? 15),
      overlap: nonNegative("overlap", config.overlap ?? 300),
      pageSize: positiveInt("pageSize", config.pageSize ?? 1000),
    };
    if (this.config.lookbackMinutes > MAX_LOOKBACK_MINUTES) {
      throw new Error(`lookbackMinutes must be at most ${MAX_LOOKBACK_MINUTES} (31 days).`);
    }

    this.client = new CloudflareClient({
      apiToken: config.apiToken || undefined,
      apiKey: config.apiKey || undefined,
      email: config.email || undefined,
      timeoutMs: positive("requestTimeout", config.requestTimeout ?? 15) * 1000,
      maxRetries: nonNegativeInt("maxRetries", config.maxRetries ?? 3),
      fetch: config.fetch,
    });
  }

  /** Register a handler for security events. */
  onEvent(handler: EventHandler): this {
    return super.on("event", handler as (...args: unknown[]) => void);
  }

  /** Register a handler for polling and event handler errors. */
  onError(handler: ErrorHandler): this {
    return super.on("error", handler as (...args: unknown[]) => void);
  }

  /** Start polling. Resolves when stop() is called. Calling it again while running returns the same promise. */
  start(): Promise<void> {
    if (this.runPromise) return this.runPromise;
    const abort = new AbortController();
    this.abort = abort;
    this.runPromise = this.run(abort.signal).finally(() => {
      this.abort = null;
      this.runPromise = null;
    });
    return this.runPromise;
  }

  /** Stop polling, cancelling in-flight requests. Resolves once the loop has exited. */
  async stop(): Promise<void> {
    const running = this.runPromise;
    this.abort?.abort();
    await running;
  }

  private async run(signal: AbortSignal): Promise<void> {
    const cutoff = new Date(Date.now() - this.config.lookbackMinutes * 60 * 1000);
    try {
      const zoneNames = await this.client.fetchZoneNames(this.config.zoneIds, signal);
      while (!signal.aborted) {
        await this.poll(zoneNames, cutoff, signal);
        await sleep(this.config.pollInterval * 1000, signal);
      }
    } catch (err) {
      if (!signal.aborted) throw err;
    }
  }

  private async poll(zoneNames: Map<string, string>, cutoff: Date, signal: AbortSignal): Promise<void> {
    const until = new Date();
    const overlapMs = this.config.overlap * 1000;
    const pending = new Map<string, Date>();
    for (const zoneId of this.config.zoneIds) {
      const mark = this.watermark.get(zoneId);
      pending.set(zoneId, mark ? new Date(mark.getTime() - overlapMs) : cutoff);
    }

    for (let page = 0; pending.size > 0; page++) {
      if (page >= MAX_PAGES_PER_POLL) {
        for (const zoneId of pending.keys()) {
          this.emitError(new Error(`Zone ${zoneId}: more than ${MAX_PAGES_PER_POLL} pages in one poll; continuing next poll.`));
        }
        return;
      }
      for (const batch of chunk([...pending.keys()], MAX_ZONES_PER_QUERY)) {
        let results;
        try {
          results = await this.client.fetchEvents(
            batch.map((zoneId) => ({ zoneId, since: pending.get(zoneId)! })),
            until,
            this.config.pageSize,
            signal,
          );
        } catch (err) {
          if (signal.aborted) throw err;
          this.emitError(err);
          batch.forEach((zoneId) => pending.delete(zoneId));
          continue;
        }

        for (const zoneId of batch) {
          const since = pending.get(zoneId)!;
          const result = results.get(zoneId);
          if (!result || "error" in result) {
            this.emitError(result?.error ?? new Error(`No result for zone ${zoneId}.`));
            pending.delete(zoneId);
            continue;
          }

          for (const raw of result.events) {
            if (signal.aborted) return;
            await this.handleRaw(zoneId, zoneNames.get(zoneId) ?? zoneId, raw);
          }

          if (result.events.length < this.config.pageSize) {
            this.watermark.set(zoneId, until);
            pending.delete(zoneId);
            continue;
          }
          // Full page: continue from the newest timestamp. Events sharing it are deduped.
          const next = parseTs(result.events[result.events.length - 1]);
          if (!next || next <= since) {
            this.emitError(
              new Error(`Zone ${zoneId}: more than ${this.config.pageSize} events share one timestamp; raise pageSize.`),
            );
            if (next) this.watermark.set(zoneId, next);
            pending.delete(zoneId);
            continue;
          }
          this.watermark.set(zoneId, next);
          pending.set(zoneId, next);
        }
      }
    }
    this.pruneSeen(overlapMs);
  }

  private async handleRaw(zoneId: string, zoneName: string, raw: RawEvent): Promise<void> {
    const occurredAt = parseTs(raw);
    const key = dedupeKey(zoneId, raw);
    if (this.seen.has(key)) return;
    this.seen.set(key, { zoneId, ts: occurredAt?.getTime() ?? Date.now() });
    await this.dispatchEvent(toEvent(zoneId, zoneName, raw, occurredAt));
  }

  /** Forget keys that can no longer reappear in a future overlap window. */
  private pruneSeen(overlapMs: number): void {
    for (const [key, { zoneId, ts }] of this.seen) {
      const mark = this.watermark.get(zoneId);
      if (mark && ts < mark.getTime() - overlapMs) this.seen.delete(key);
    }
  }

  private async dispatchEvent(event: SecurityEvent): Promise<void> {
    const handlers = this.listeners("event") as EventHandler[];
    for (const handler of handlers) {
      try {
        await handler(event);
      } catch (error) {
        this.emitError(error);
      }
    }
  }

  private emitError(error: unknown): void {
    if (this.listenerCount("error") > 0) {
      super.emit("error", error);
    }
  }
}

// ------------------------------------------------------------------ helpers

function positive(name: string, value: number): number {
  if (!Number.isFinite(value) || value <= 0) throw new Error(`${name} must be a positive number.`);
  return value;
}

function nonNegative(name: string, value: number): number {
  if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must not be negative.`);
  return value;
}

function positiveInt(name: string, value: number): number {
  if (!Number.isInteger(value) || value < 1) throw new Error(`${name} must be a positive integer.`);
  return value;
}

function nonNegativeInt(name: string, value: number): number {
  if (!Number.isInteger(value) || value < 0) throw new Error(`${name} must be a non-negative integer.`);
  return value;
}

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

function parseTs(raw: RawEvent | undefined): Date | null {
  const val = raw?.["datetime"];
  if (!val) return null;
  const d = new Date(String(val));
  return isNaN(d.getTime()) ? null : d;
}

/** One request can trigger several events, so the Ray ID alone is not unique. */
function dedupeKey(zoneId: string, raw: RawEvent): string {
  return [zoneId, raw["rayName"], raw["ruleId"], raw["source"], raw["action"], raw["datetime"], raw["clientIP"]]
    .map((v) => String(v ?? ""))
    .join("|");
}

function str(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function toEvent(
  zoneId: string,
  zoneName: string,
  raw: RawEvent,
  occurredAt: Date | null,
): SecurityEvent {
  return {
    zoneId,
    zoneName,
    action: str(raw["action"]),
    source: str(raw["source"]),
    clientIp: str(raw["clientIP"]),
    country: str(raw["clientCountryName"]),
    ruleId: str(raw["ruleId"]),
    ruleMessage: str(raw["description"]),
    rayId: str(raw["rayName"]),
    host: str(raw["clientRequestHTTPHost"]),
    method: str(raw["clientRequestHTTPMethodName"]),
    path: str(raw["clientRequestPath"]),
    query: str(raw["clientRequestQuery"]),
    userAgent: str(raw["userAgent"]),
    asn: str(raw["clientAsn"]),
    occurredAt,
    raw,
  };
}
