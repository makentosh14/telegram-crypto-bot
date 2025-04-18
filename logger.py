import logging
from datetime import datetime
import os

log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = os.path.join(log_dir, f"bot_log_{timestamp}.log")

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def log_info(message):
    print(f"[INFO] {message}")
    logging.info(message)

def log_warning(message):
    print(f"[WARNING] {message}")
    logging.warning(message)

def log_error(message):
    print(f"[ERROR] {message}")
    logging.error(message)
