import html
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import config
from config import logger
from amazon_converter import convert_all_amazon_links

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user_name = html.escape(update.effective_user.first_name) if update.effective_user else "Friend"
    welcome_text = (
        f"👋 <b>Hello, {user_name}!</b>\n\n"
        f"I am the <b>TechSelect Deals Bot</b> 🇮🇳\n\n"
        f"🔗 Send or forward any Amazon product link or deal post here (or add me to a group),\n"
        f"and I will automatically convert it into clean Amazon Affiliate links.\n\n"
        f"🌐 Reviews & buying guides: <a href=\"{config.WEBSITE_URL}\">TechSelect.blog</a>\n\n"
        f"Type /help for more information."
    )
    await update.message.reply_html(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "💡 <b>How to use this Bot:</b>\n\n"
        "1. Simply paste any Amazon URL into this chat.\n"
        "2. Supported URL formats:\n"
        "   • <code>https://www.amazon.com/dp/B08N5WRWNW</code>\n"
        "   • <code>https://amzn.to/example</code> (shortened links)\n"
        "   • <code>https://www.amazon.in/gp/product/B08N5WRWNW</code>\n\n"
        "3. <b>Multiple Links</b>: You can paste messages containing multiple Amazon links, and I will convert all of them!\n"
        "4. <b>Group Usage</b>: Add this bot to any Telegram group and grant message access. "
        "It will automatically reply with affiliate links whenever an Amazon URL is shared!\n\n"
        f"🌐 More deals & reviews: <a href=\"{config.WEBSITE_URL}\">TechSelect.blog</a>"
    )
    await update.message.reply_html(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming messages to check for Amazon links."""
    message = update.effective_message
    if not message:
        return

    text = message.text or message.caption
    if not text:
        return

    chat = update.effective_chat
    if chat and chat.type == "channel":
        logger.info(f"Channel post seen in chat_id={chat.id} — set CHANNEL_ID={chat.id} in .env to enable channel posting")

    tag = config.get_affiliate_tag()
    affiliate_links = await convert_all_amazon_links(text, tag, config.AMAZON_DOMAIN)
    
    if not affiliate_links:
        return  # No Amazon links found, stay silent
        
    logger.info(f"Converted {len(affiliate_links)} Amazon link(s) for user {update.effective_user.id if update.effective_user else 'unknown'}")
    
    # Build buttons and message content
    keyboard = []
    response_lines = ["🛍️ <b>Amazon Affiliate Link(s) Generated:</b>\n"]
    
    for idx, (orig_url, aff_url) in enumerate(affiliate_links, 1):
        response_lines.append(f"{idx}. <a href=\"{aff_url}\">{aff_url}</a>")
        btn_label = f"🛒 Product #{idx}" if len(affiliate_links) > 1 else "🛒 Buy / View Product on Amazon"
        keyboard.append([InlineKeyboardButton(btn_label, url=aff_url)])

    keyboard.append([InlineKeyboardButton("🌐 More deals on TechSelect.blog", url=config.WEBSITE_URL)])
        
    response_lines.append(f"\n🏷️ <i>Affiliate Tag applied: <code>{html.escape(tag)}</code></i>")

    reply_markup = InlineKeyboardMarkup(keyboard)
    response_text = "\n".join(response_lines)

    # Stay silent in the source channel; reply everywhere else
    is_source = chat and config.SOURCE_CHANNEL_ID and str(chat.id) == str(config.source_chat_id())
    if not is_source:
        await message.reply_html(
            text=response_text,
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )

    # Post to your channel/group, unless the message already came from it
    if config.CHANNEL_ID and chat and str(chat.id) != str(config.channel_chat_id()):
        try:
            if message.photo:
                # Repost with the original photo and caption, swapping in affiliate links
                caption_text = message.caption or ""
                for orig_url, aff_url in affiliate_links:
                    caption_text = caption_text.replace(orig_url, aff_url)
                channel_caption = html.escape(caption_text) if caption_text else "🛍️ <b>Amazon Affiliate Deal</b>"
                if len(channel_caption) > 1000:
                    channel_caption = channel_caption[:1000] + "…"
                await context.bot.send_photo(
                    chat_id=config.channel_chat_id(),
                    photo=message.photo[-1].file_id,
                    caption=channel_caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                await context.bot.send_message(
                    chat_id=config.channel_chat_id(),
                    text=response_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=False,
                )
        except Exception as e:
            logger.error(f"Failed to post to channel {config.CHANNEL_ID}: {e}")

    # Push to Website and X (Twitter)
    try:
        import re
        asins = []
        for _, aff_url in affiliate_links:
            m = re.search(r"/dp/([A-Z0-9]{10})", aff_url)
            if m:
                asins.append(m.group(1))

        if asins:
            # 1. Website Push
            if getattr(config, "WEBSITE_WEBHOOK_URL", None):
                try:
                    import httpx, time as _time
                    async with httpx.AsyncClient(timeout=5.0) as http:
                        await http.post(
                            config.WEBSITE_WEBHOOK_URL,
                            json={
                                "asins": asins,
                                "text": text,
                                "source_title": "Telegram Bot",
                                "has_media": bool(message.photo),
                                "posted_at": _time.time(),
                            },
                            headers={"x-webhook-secret": getattr(config, "WEBSITE_WEBHOOK_SECRET", "")},
                        )
                except Exception as e:
                    logger.error(f"Website push failed: {e}")

            # 2. X (Twitter) Push
            try:
                from TelegramDealAutoPoster.x_poster import push_deal_to_x
                await push_deal_to_x(text=text, asins=asins)
            except Exception as e:
                logger.error(f"X push failed: {e}")
    except Exception as exc:
        logger.error(f"Integrations error: {exc}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify dev chat if configured."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if config.DEV_CHAT_ID:
        try:
            err_msg = html.escape(str(context.error))
            await context.bot.send_message(
                chat_id=config.DEV_CHAT_ID,
                text=f"⚠️ <b>AffiliateBot Error Alert</b>\n<code>{err_msg}</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send alert to DEV_CHAT_ID: {e}")

def main() -> None:
    """Start the Telegram bot."""
    if not config.TOKEN:
        logger.error("Error: TELEGRAM_TOKEN environment variable is not set!")
        print("\n❌ Error: TELEGRAM_TOKEN environment variable is not set.")
        print("Please copy .env.example to .env and add your Telegram bot token from @BotFather.\n")
        sys.exit(1)
        
    logger.info(f"Starting Affiliate Telegram Bot (Domain: {config.AMAZON_DOMAIN}, Tags: {', '.join(config.AFFILIATE_TAGS)})")
    
    app = Application.builder().token(config.TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    print(f"🚀 Affiliate Telegram Bot is running! Using tags: {', '.join(config.AFFILIATE_TAGS)}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
