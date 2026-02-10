from modules.importHandler import logging, os, json
from modules.paths import ENV_FILE, STATE_FILE
logger = logging.getLogger(__name__)

def _load_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as exc:
        logger.warning("Failed to read .env file (%s): %s", path, exc)
    return env


def _env_int(env, key, fallback):
    raw = env.get(key, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid int for %s in .env, using default.", key)
        return fallback


def _ensure_env_file():
    if not os.path.exists(ENV_FILE):
        sample = (
            "# CloudFlareNotifier configuration\n"
            "# You can use either an API token (recommended) or API key + email.\n"
            "CLOUDFLARE_API_TOKEN=\n"
            "CLOUDFLARE_API_KEY=\n"
            "CLOUDFLARE_EMAIL=\n"
            "CLOUDFLARE_ZONE_IDS=\n"
            "POLL_INTERVAL=60\n"
            "LOOKBACK_MINUTES=15\n"
            "VERIFY_SSL=true\n"
            "\n"
            "WEBHOOK_URL=\n"
            "NO_WINDOWS_SERVER=false\n"
            "SEND_WINDOWS_TOAST=true\n"
        )
        with open(ENV_FILE, "w", encoding="utf-8") as handle:
            handle.write(sample)
        logger.info("Created .env template at %s. Please fill it in and run again.", ENV_FILE)
        raise FileNotFoundError(f".env created at {ENV_FILE}. Fill it in and run again.")


def load_config():
    """
    Load and validate configuration from disk.
    """
    _ensure_env_file()
    env = _load_env(ENV_FILE)

    api_token = (env.get("CLOUDFLARE_API_TOKEN") or "").strip()
    api_key = (env.get("CLOUDFLARE_API_KEY") or "").strip()
    email = (env.get("CLOUDFLARE_EMAIL") or "").strip()
    zone_ids_raw = env.get("CLOUDFLARE_ZONE_IDS") or ""
    poll_interval = _env_int(env, "POLL_INTERVAL", 60)
    lookback_minutes = _env_int(env, "LOOKBACK_MINUTES", 15)
    verify_ssl = str(env.get("VERIFY_SSL", "")).strip().lower()
    if verify_ssl in {"0", "false", "no", "off"}:
        verify_ssl = False
    elif verify_ssl in {"1", "true", "yes", "on"}:
        verify_ssl = True
    else:
        verify_ssl = parser.getboolean("cloudflare", "verify_ssl", fallback=True)

    webhook_url = (env.get("WEBHOOK_URL") or "").strip()

    raw_no_windows = env.get("NO_WINDOWS_SERVER") or env.get("NO_WINDOWS_SERVER") or ""
    no_windows_server = raw_no_windows.strip().lower() in {"1", "true", "yes", "on"}

    raw_send_toast = env.get("SEND_WINDOWS_TOAST", "")
    if raw_send_toast:
        send_windows_toast = raw_send_toast.strip().lower() in {"1", "true", "yes", "on"}
    else:
        send_windows_toast = True

    zone_ids = [z.strip() for z in zone_ids_raw.split(",") if z.strip()]

    if not api_token and not (api_key and email):
        raise ValueError("Configure either CLOUDFLARE_API_TOKEN or CLOUDFLARE_API_KEY + CLOUDFLARE_EMAIL in .env")
    if not zone_ids:
        raise ValueError("Configure at least one zone ID in .env (CLOUDFLARE_ZONE_IDS)")

    return {
        "api_token": api_token,
        "api_key": api_key,
        "email": email,
        "zone_ids": zone_ids,
        "poll_interval": poll_interval,
        "lookback_minutes": lookback_minutes,
        "verify_ssl": verify_ssl,
        "webhook_url": webhook_url,
        "no_windows_server": no_windows_server,
        "send_windows_toast": send_windows_toast,
    }


def load_state():
    """
    Loads persisted state for last seen events.
    """
    if not os.path.exists(STATE_FILE):
        return {"zones": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Failed to read state file (%s), starting fresh: %s", STATE_FILE, exc)
        return {"zones": {}}


def save_state(state):
    """
    Persists state to disk.
    """
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
