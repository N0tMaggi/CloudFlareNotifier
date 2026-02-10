from modules.importHandler import datetime


ATTACK_VECTORS = [
    ("managed_challenge", "Managed Challenge", "Cloudflare issued an adaptive challenge to verify the client is not automated."),
    ("js_challenge", "JavaScript Challenge", "Browser must execute JavaScript to pass; blocks many basic bots."),
    ("captcha", "CAPTCHA Challenge", "User-facing CAPTCHA was required to proceed."),
    ("botfight", "Bot Fight Mode", "Cloudflare detected bot-like traffic and applied bot mitigation."),
    ("bot_fight_mode", "Bot Fight Mode", "Cloudflare detected bot-like traffic and applied bot mitigation."),
    ("link_maze", "Link Maze", "Hidden links were injected to slow down scrapers and bots."),
    ("rate", "Rate Limit", "Traffic exceeded a rate-limiting threshold."),
    ("firewallmanaged", "Managed Firewall Rule", "Cloudflare managed rules triggered a block or challenge."),
    ("waf", "WAF Rule", "Web Application Firewall rule matched the request."),
    ("block", "Block", "Request was blocked by a firewall or security rule."),
]


def _normalize(text):
    return (text or "").strip().lower()


def classify_attack(event):
    action = _normalize(event.get("action") or event.get("outcome"))
    source = _normalize(event.get("source") or event.get("kind") or event.get("service"))
    rule_message = _normalize(event.get("rule_message") or event.get("rule_id"))

    haystack = " ".join([action, source, rule_message])

    for key, label, description in ATTACK_VECTORS:
        if key in haystack:
            return label, description

    return "General Security Event", "Cloudflare detected a security event. Review the rule message and Ray ID for details."


def build_embed(zone_name, event, event_ts=None):
    action = event.get("action") or event.get("outcome") or "Security event"
    source = event.get("source") or event.get("kind") or event.get("service") or "Cloudflare"
    client_ip = event.get("client_ip") or event.get("ip") or "Unknown IP"
    country = event.get("client_country_name") or event.get("country") or "Unknown"
    rule = event.get("rule_message") or event.get("rule_id") or "n/a"
    ray_id = event.get("ray_id") or event.get("rayid") or "n/a"

    vector_label, vector_desc = classify_attack(event)

    color = 15158332 if str(action).lower() in {"block", "deny"} else 15105570
    if "challenge" in str(action).lower():
        color = 16753920

    embed = {
        "title": f"{zone_name}: {action}",
        "description": f"{source} security event",
        "color": color,
        "fields": [
            {"name": "Client IP", "value": client_ip, "inline": True},
            {"name": "Country", "value": country, "inline": True},
            {"name": "Rule", "value": rule, "inline": False},
            {"name": "Ray ID", "value": ray_id, "inline": True},
            {"name": "Attack Vector", "value": vector_label, "inline": True},
            {"name": "Vector Description", "value": vector_desc, "inline": False},
        ],
    }

    if event_ts:
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=datetime.timezone.utc)
        embed["timestamp"] = event_ts.astimezone(datetime.timezone.utc).isoformat()

    return embed
