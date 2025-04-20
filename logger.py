import logging

# === Basic Logging Setup ===
logging.basicConfig(
    filename='logs/bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log(message, level="info"):
    if level == "info":
        logging.info(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "error":
        logging.error(message)
    else:
        logging.debug(message)

    # Optional: also print to console
    print(message)
