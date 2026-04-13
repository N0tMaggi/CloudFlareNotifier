from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SecurityEvent:
    """A single Cloudflare security event."""

    zone_id: str
    zone_name: str
    action: str
    source: str
    client_ip: str
    country: str
    rule_id: str
    rule_message: str
    ray_id: str
    occurred_at: datetime | None
    raw: dict[str, object] = field(repr=False)
