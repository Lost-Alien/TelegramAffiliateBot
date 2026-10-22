#!/usr/bin/env python3
"""
send_amazon_deal_whatsapp.py — Standalone Educational Amazon Deal Sender for WhatsApp.

Architecture & References (Educational Open-Source Patterns):
  * Based on multi-platform deal broadcasting patterns from TechyShahid/sasta_maal
  * Bulk messaging & rate-limiting loops inspired by BaseMax/whatsapp-bulk
  * Link sanitization & affiliate injection inspired by gabrieldamasse-01/bot-de-automacao

This script dispatches any deal text with Amazon links to your cloud-hosted
WhatsApp Bot (running on AWS Mumbai at http://13.201.98.82:3000). The bot:
  1. Resolves Amazon deep links (e.g., https://link.amazon/B0dEtDKaV)
  2. Extracts the true product ASIN
  3. Injects your official affiliate tracking ID
  4. Sequentially messages each recipient with humanized delays to protect account health
"""

import sys
import json
import argparse
import requests

# Default WhatsApp Bot Server on AWS Mumbai
DEFAULT_WA_BOT_URL = "http://13.201.98.82:3000/api/send-deal"

# Target phone numbers
DEFAULT_RECIPIENTS = [
    "+919202876921",
    "+918115814535",
    "8770520395",
    "+91 79993 31686"
]

SAMPLE_DEAL = """Samsung 24-inch (60.46cm) FHD Flat 1,920 x 1,080 Monitor at ₹1401

₹250 cashback with Amazon Pay Later

https://link.amazon/B0dEtDKaV"""


def send_deal(text: str, recipients: list[str] = None, endpoint: str = DEFAULT_WA_BOT_URL) -> dict:
    if recipients is None:
        recipients = DEFAULT_RECIPIENTS

    payload = {
        "text": text,
        "recipients": recipients
    }
    
    print("\n" + "=" * 60)
    print("🚀 DISPATCHING DEAL TO WHATSAPP RECIPIENTS")
    print("=" * 60)
    print(f"📡 API Endpoint : {endpoint}")
    print(f"👥 Recipients   : {', '.join(recipients)}")
    print(f"📝 Deal Text:\n{text}\n")
    print("-" * 60)
    print("⏳ Resolving Amazon short links & sending...")

    try:
        # 60s timeout allows link resolution + 2.5s safe delay between 4 numbers
        response = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ Successfully processed by WhatsApp Bot!")
            print("\n📦 Converted Message with Your Affiliate Link:")
            print("-" * 60)
            print(data.get("message", ""))
            print("-" * 60)
            print("\n📊 Delivery Results:")
            for res in data.get("results", []):
                icon = "✅" if res.get("status") == "sent" else "❌"
                print(f"  {icon} {res.get('recipient')} ({res.get('chatId')}) -> {res.get('status').upper()}")
            return data
        else:
            print(f"\n❌ Error from Bot API [HTTP {response.status_code}]:")
            print(response.text)
            return {"error": response.text}
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Send Amazon Deal to WhatsApp broadcast list")
    parser.add_argument("--text", "-t", type=str, default=None, help="The deal text to broadcast")
    parser.add_argument("--recipients", "-r", nargs="+", default=DEFAULT_RECIPIENTS, help="List of phone numbers")
    parser.add_argument("--url", "-u", type=str, default=DEFAULT_WA_BOT_URL, help="WhatsApp bot endpoint URL")
    
    args = parser.parse_args()
    
    deal_text = args.text
    if not deal_text:
        # If no arguments provided, use the user's sample Samsung Monitor deal
        print("💡 No deal text provided via CLI argument. Using sample Samsung Monitor deal:")
        deal_text = SAMPLE_DEAL
        
    send_deal(deal_text, args.recipients, args.url)


if __name__ == "__main__":
    main()
