import sys
import asyncio
from telethon import TelegramClient
import config
from config import logger
from deal_listener import start_deal_listener

async def main():
    if not config.API_ID or not config.API_HASH:
        logger.error("API_ID or API_HASH missing in .env configuration!")
        print("\n❌ Error: API_ID and API_HASH are required in .env")
        sys.exit(1)
        
    logger.info(f"Starting Multi-Channel Telegram Deal Auto-Poster (Session: {config.SESSION_NAME})")
    
    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        logger.error("Session is not authorized. Please run python auto_login.py to complete authentication.")
        print("\n❌ Error: Userbot session is not authenticated.")
        print("Please run 'python auto_login.py' to complete 1-time authentication.\n")
        sys.exit(1)
        
    me = await client.get_me()
    logger.info(f"Authenticated as Telegram User: {me.first_name} (@{me.username or 'NoUsername'}) [ID: {me.id}]")
    
    # Register event listeners
    await start_deal_listener(client)
    
    print(f"\n🚀 Multi-Channel Deal Auto-Poster is running as @{me.username or me.first_name}!")
    print(f"Listening to incoming deal posts and replacing Amazon links with tags '{config.AFFILIATE_TAGS}'...\n")
    
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
