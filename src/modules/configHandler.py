from modules.importHandler import logging, os, configparser, json

config_dir = os.path.join(os.getenv('APPDATA'), 'CloudFlareNotifier')
os.makedirs(config_dir, exist_ok=True)
config_file = os.path.join(config_dir, 'config.cfg')
state_file = os.path.join(config_dir, 'state.json')
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = """# CloudFlareNotifier configuration
# You can use either an API token (recommended) or API key + email.
[cloudflare]
api_token =
api_key =
email =
# Comma-separated list of zone IDs to monitor.
zone_ids =
# Seconds between polls to Cloudflare.
poll_interval = 60
# Minutes to look back for events on the very first run.
lookback_minutes = 15
# Set to false to skip TLS validation (not recommended).
verify_ssl = true
"""


def _open_config_for_edit():
    """
    Try to open the config file in the user's default editor (Windows startfile).
    """
    try:
        if hasattr(os, "startfile"):
            os.startfile(config_file)
            return True
    except Exception as exc:
        logger.warning("Could not auto-open config file: %s", exc)
    return False


def ensure_config_file():
    """
    Ensures the config file exists. If missing, write a template and raise.
    """
    if not os.path.exists(config_file):
        with open(config_file, "w", encoding="utf-8") as cfg:
            cfg.write(DEFAULT_CONFIG)
        opened = _open_config_for_edit()
        logger.info("Created config template at %s. Please fill in your Cloudflare credentials and zone IDs.", config_file)
        raise FileNotFoundError(
            f"Config file created at {config_file}. "
            f"{'Opened it for editing.' if opened else 'Open it in your editor, then run again.'}"
        )


def load_config():
    """
    Load and validate configuration from disk.
    """
    ensure_config_file()

    parser = configparser.ConfigParser()
    parser.read(config_file)

    api_token = parser.get("cloudflare", "api_token", fallback="").strip()
    api_key = parser.get("cloudflare", "api_key", fallback="").strip()
    email = parser.get("cloudflare", "email", fallback="").strip()
    zone_ids_raw = parser.get("cloudflare", "zone_ids", fallback="")
    poll_interval = parser.getint("cloudflare", "poll_interval", fallback=60)
    lookback_minutes = parser.getint("cloudflare", "lookback_minutes", fallback=15)
    verify_ssl = parser.getboolean("cloudflare", "verify_ssl", fallback=True)

    zone_ids = [z.strip() for z in zone_ids_raw.split(",") if z.strip()]

    if not api_token and not (api_key and email):
        raise ValueError("Configure either api_token or api_key + email in config.cfg")
    if not zone_ids:
        raise ValueError("Configure at least one zone_id in config.cfg")

    return {
        "api_token": api_token,
        "api_key": api_key,
        "email": email,
        "zone_ids": zone_ids,
        "poll_interval": poll_interval,
        "lookback_minutes": lookback_minutes,
        "verify_ssl": verify_ssl,
    }


def load_state():
    """
    Loads persisted state for last seen events.
    """
    if not os.path.exists(state_file):
        return {"zones": {}}
    try:
        with open(state_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Failed to read state file (%s), starting fresh: %s", state_file, exc)
        return {"zones": {}}


def save_state(state):
    """
    Persists state to disk.
    """
    os.makedirs(config_dir, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)

