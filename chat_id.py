"""Retrieve your private chat ID, after sending /start to your bot.
No secrets are printed. Run on a trusted computer.
"""
import os
import requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN environment variable")
data = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", timeout=20).json()
chats = [(item.get("message") or {}).get("chat", {}) for item in data.get("result", [])]
ids = sorted({str(chat["id"]) for chat in chats if chat.get("type") == "private" and "id" in chat})
print("Private chat IDs:", ", ".join(ids) if ids else "None. Send /start to your bot first.")
