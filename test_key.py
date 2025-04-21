import os
from dotenv import load_dotenv

load_dotenv()

print("🔑 BYBIT_API_KEY:", repr(os.getenv("BYBIT_API_KEY")))
print("🔐 BYBIT_API_SECRET:", repr(os.getenv("BYBIT_API_SECRET")))
