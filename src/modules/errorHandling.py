# Hook every error and exception to log it properly
from modules.importHandler import sys, threading
from modules.loggingHandler import logger

def log_exceptions(exc_type, exc_value, exc_traceback):
    """
    Handles uncaught exceptions in the main thread.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        # Call the default excepthook for KeyboardInterrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def log_thread_exceptions(args):
    """
    Handles uncaught exceptions in threads (Python 3.8+).
    """
    if issubclass(args.exc_type, KeyboardInterrupt):
        return
    logger.error("Uncaught exception in thread", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

# Hook main thread exceptions
sys.excepthook = log_exceptions

# Hook thread exceptions
if hasattr(threading, 'excepthook'):
    threading.excepthook = log_thread_exceptions
    
# Function to handle asyncio exceptions (optional usage in main)
def handle_async_exception(loop, context):
    msg = context.get("exception", context.get("message"))
    logger.error(f"Caught exception in asyncio loop: {msg}")