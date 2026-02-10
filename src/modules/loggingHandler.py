from modules.importHandler import logging, os
from modules.paths import LOG_DIR
from logging.handlers import RotatingFileHandler

# Setup logging configuration in local logs directory
log_dir = str(LOG_DIR)
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

logger = logging.getLogger("CloudFlareNotifier")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    try:
        rotating_handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
        rotating_handler.setFormatter(formatter)
        
        rotating_handler.setLevel(logging.WARNING)
        logger.addHandler(rotating_handler)
    except Exception:
        print("[ ! ] Failed to set up file logging. Logs will only be output to the console.")
        pass


def get_logger():
    """
    Returns the configured logger for use in other modules.
    """
    return logger
