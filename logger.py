# logger.py

import logging
from datetime import datetime

log_file = f"logs/bot_log_{datetime.utcnow().strftime('%Y%m%d')}.log"

logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def log(message: str, level: str = "info"):
    console_msg = f"[{datetime.utcnow().strftime('%H:%M:%S')}] {message}"
    print(console_msg)
    if level == "info":
        logging.info(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "error":
        logging.error(message)
    elif level == "debug":
        logging.debug(message)
