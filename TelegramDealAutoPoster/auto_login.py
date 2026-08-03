import sys
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import config

async def main():
    if not config.API_ID or not config.API_HASH or not config.PHONE_NUMBER:
        print("\n❌ Error: API_ID, API_HASH, and PHONE_NUMBER are required in .env!")
        sys.exit(1)
        
    print(f"Connecting with API_ID: {config.API_ID} for Phone: {config.PHONE_NUMBER}...")
    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print(f"Sending login code request to {config.PHONE_NUMBER}...")
        sent_code = await client.send_code_request(config.PHONE_NUMBER)
        print("LOGIN_CODE_SENT")
        print("Check your Telegram app / Telegram Web chat for the 5-digit verification code.")
        
        # Read code from stdin
        code = input("Enter the 5-digit code: ").strip()
        try:
            await client.sign_in(config.PHONE_NUMBER, code, phone_code_hash=sent_code.phone_code_hash)
        except SessionPasswordNeededError:
            pwd = input("Enter your 2FA password: ").strip()
            await client.sign_in(password=pwd)
            
    me = await client.get_me()
    print(f"\n✅ Session authenticated as: {me.first_name} (@{me.username or 'NoUsername'}) [ID: {me.id}]")
    print(f"Session saved to '{config.SESSION_NAME}.session'\n")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
