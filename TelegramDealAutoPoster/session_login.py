import sys
import asyncio
from telethon import TelegramClient
import config

async def main():
    if not config.API_ID or not config.API_HASH:
        print("\n❌ Error: API_ID and API_HASH are required!")
        print("Get your credentials at https://my.telegram.org/apps and add them to .env\n")
        sys.exit(1)
        
    print(f"Connecting to Telegram with API_ID: {config.API_ID}...")
    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
    await client.start(phone=config.PHONE_NUMBER)
    
    me = await client.get_me()
    print(f"\n✅ Session authenticated successfully as: {me.first_name} (@{me.username or 'NoUsername'}) [ID: {me.id}]")
    print(f"Session saved as: '{config.SESSION_NAME}.session'\n")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
