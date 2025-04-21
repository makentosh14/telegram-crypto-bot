import aiohttp
import asyncio
import time
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# === CONFIG ===
BYBIT_API_KEY = "UiYisqj7VuDzDjKQjo"  # RSA API key ID from Bybit
BYBIT_API_URL = "https://api.bybit.com"
PRIVATE_KEY_PATH = "bybit_private_key.pem"  # Make sure this file exists

# === RSA UTILITIES ===
def load_rsa_private_key(path: str):
    with open(path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
        )
    return private_key

def generate_rsa_signature(private_key, message: str) -> str:
    signature = private_key.sign(
        message.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode()

# === API CALL ===
async def rsa_signed_request():
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    query = f"timestamp={timestamp}&recvWindow={recv_window}&accountType=UNIFIED"

    private_key = load_rsa_private_key(PRIVATE_KEY_PATH)
    signature = generate_rsa_signature(private_key, query)

    headers = {
        "X-BYBIT-API-KEY": BYBIT_API_KEY,
        "X-BYBIT-SIGN": signature,
        "X-BYBIT-SIGN-TYPE": "RSA",
        "X-BYBIT-TIMESTAMP": timestamp,
        "X-BYBIT-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }

    url = f"{BYBIT_API_URL}/v5/account/wallet-balance?{query}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            print(f"🔐 Status Code: {resp.status}")
            print("📦 Response:", await resp.text())

# === RUN TEST ===
if __name__ == "__main__":
    asyncio.run(rsa_signed_request())
