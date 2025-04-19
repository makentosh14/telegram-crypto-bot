# logger.py

import logging
from datetime import datetime

def log(message):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp} UTC] {message}"
    print(formatted_message)
    with open("logs/bot_log.txt", "a") as f:
        f.write(formatted_message + "\n")


def setup_logger():
    log_file = f"logs/bot_{datetime.utcnow().strftime('%Y-%m-%d')}.log"
    logging.basicConfig(
        filename=log_file,
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S',
        level=logging.INFO
    )
    return logging.getLogger()

log = setup_logger()

def log_info(message):
    print(message)
    log.info(message)

def log_error(message):
    print(f"ERROR: {message}")
    log.error(message)
