"""
login_helper.py — One-time local helper to capture session cookies for @techselect_blog.
Runs interactively on your local machine to generate cookies.json.

Instructions:
1. Run: python -m x_commenter.login_helper
2. Enter your X username/email and password.
3. If 2FA or confirmation (email/SMS) is prompted, follow the terminal instructions.
4. cookies.json will be saved locally.
5. The script will output the base64-encoded string to copy into your GitHub Secret: TWITTER_COOKIES_B64
"""

import asyncio
import base64
import getpass
from pathlib import Path
from twikit import Client


async def main():
    print("=" * 60)
    print("TechSelect X Auto-Commenter — Cookie Authentication Setup")
    print("=" * 60)
    print("This script logs into X/Twitter once and saves your browser session cookies.")
    print("You can then store them in GitHub Secrets without sharing your password.\n")

    client = Client(language="en-US")

    username = input("Enter X Username or Email: ").strip()
    if not username:
        print("❌ Username cannot be empty.")
        return

    password = getpass.getpass("Enter X Password: ").strip()
    if not password:
        print("❌ Password cannot be empty.")
        return

    email_or_phone = input("Enter Backup Email/Phone (optional, press Enter to skip): ").strip() or None

    print("\n⏳ Logging into X...")
    try:
        await client.login(
            auth_info_1=username,
            auth_info_2=email_or_phone,
            password=password,
        )
    except Exception as exc:
        print(f"❌ Login failed: {exc}")
        print("Please check your credentials or 2FA settings and try again.")
        return

    cookies_path = Path(__file__).resolve().parent / "cookies.json"
    client.save_cookies(str(cookies_path))
    print(f"✅ Session cookies successfully saved to: {cookies_path}\n")

    # Read and encode to Base64 for GitHub Secrets
    with open(cookies_path, "rb") as f:
        encoded_b64 = base64.b64encode(f.read()).decode("utf-8")

    print("=" * 60)
    print("👉 COPY THIS VALUE INTO GITHUB SECRETS (Name: TWITTER_COOKIES_B64):")
    print("=" * 60)
    print(encoded_b64)
    print("=" * 60)
    print("\nNext Steps:")
    print("1. Go to your GitHub repo -> Settings -> Secrets and variables -> Actions")
    print("2. Add/Update secret 'TWITTER_COOKIES_B64' with the text above.")
    print("3. Done! The bot will use these cookies for 100% free posting without API fees.")


if __name__ == "__main__":
    asyncio.run(main())
