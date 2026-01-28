from modules.importHandler import asyncio, datetime, time
from modules.loggingHandler import logger
from modules.notificationManager import NotificationManager
from modules.connectionManager import CloudflareConnectionManager
from modules.configHandler import load_config, load_state, save_state
import modules.errorHandling  # noqa: F401 - hooks global exception handling


def parse_timestamp(value):
    """
    Parse Cloudflare timestamp fields into aware datetime objects.
    """
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(cleaned)
    except Exception:
        return None


def event_timestamp(event):
    """
    Try multiple keys used by Cloudflare for event time.
    """
    for key in ("occurred_at", "datetime", "timestamp", "time"):
        ts = parse_timestamp(event.get(key))
        if ts:
            return ts
    return None


def ts_to_string(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts.astimezone(datetime.timezone.utc).isoformat()


def build_notification(zone_name, event):
    """
    Create a title/body pair for toast notifications.
    """
    action = event.get("action") or event.get("outcome") or "Security event"
    source = event.get("source") or event.get("kind") or event.get("service") or "Cloudflare"
    client_ip = event.get("client_ip") or event.get("ip") or "Unknown IP"
    country = event.get("client_country_name") or event.get("country") or ""
    rule = event.get("rule_message") or event.get("rule_id") or ""
    ray_id = event.get("ray_id") or event.get("rayid") or ""

    body_parts = [f"{source} - {client_ip}"]
    if country:
        body_parts[-1] += f" ({country})"
    if rule:
        body_parts.append(rule)
    if ray_id:
        body_parts.append(f"Ray ID: {ray_id}")

    title = f"{zone_name}: {action}"
    body = " | ".join(body_parts)
    return title, body


async def poll_events():
    config = load_config()
    notifier = NotificationManager()
    state = load_state()
    last_seen = state.get("zones", {})

    initial_cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=config.get("lookback_minutes", 15)
    )

    async with CloudflareConnectionManager(
        api_token=config.get("api_token"),
        api_key=config.get("api_key"),
        email=config.get("email"),
        verify_ssl=config.get("verify_ssl", True),
    ) as client:
        zone_names = {}
        for zone in config["zone_ids"]:
            zone_names[zone] = await client.fetch_zone_name(zone)

        while True:
            any_updates = False
            for zone_id in config["zone_ids"]:
                since_str = last_seen.get(zone_id) or ts_to_string(initial_cutoff)
                since_dt = parse_timestamp(since_str) if since_str else None

                events = await client.fetch_security_events(zone_id, since=since_str)
                new_events = []
                for event in events:
                    ev_ts = event_timestamp(event)
                    if since_dt and ev_ts and ev_ts <= since_dt:
                        continue
                    new_events.append((ev_ts, event))

                if not new_events:
                    continue

                new_events.sort(key=lambda item: item[0] or datetime.datetime.now(datetime.timezone.utc))
                latest_ts = since_dt
                for ev_ts, event in new_events:
                    title, body = build_notification(zone_names.get(zone_id, zone_id), event)
                    notifier.send_notification(title, body)
                    any_updates = True
                    if ev_ts:
                        latest_ts = ev_ts if latest_ts is None else max(latest_ts, ev_ts)

                if latest_ts:
                    last_seen[zone_id] = ts_to_string(latest_ts)

            if any_updates:
                save_state({"zones": last_seen})

            await asyncio.sleep(config.get("poll_interval", 60))


def main():
    logger.info("CloudFlareNotifier starting up")
    try:
        asyncio.run(poll_events())
    except FileNotFoundError as missing_cfg:
        logger.error(missing_cfg)
    except ValueError as invalid_cfg:
        logger.error("Configuration error: %s", invalid_cfg)
    except KeyboardInterrupt:
        logger.info("Shutting down on user request.")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        time.sleep(1)


if __name__ == "__main__":
    main()
