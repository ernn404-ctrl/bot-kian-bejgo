"""
🚀 Nexus Extractor - PRO TELEGRAM BOT (RAILWAY EDITION)
"""
import os
import json
import asyncio
import logging
import secrets
from io import BytesIO
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import redis.asyncio as aioredis 

# ================= Configuration =================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")

# دریافت لیست ادمین‌ها (پشتیبانی از چند ادمین با کاما)
admin_ids_env = os.environ.get("ADMIN_IDS", "123456789")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_env.split(",") if x.strip().isdigit()]

# آدرس دامنه Railway شما (بدون اسلش آخر)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://your-app.up.railway.app").rstrip('/')
PORT = int(os.environ.get("PORT", "8080")) 
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

APP_SECRET_HEADER = "JetApp-Secure-Client"

# اتصال به دیتابیس
db = aioredis.from_url(REDIS_URL, decode_responses=True)

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# ================= Helper Functions =================
async def send_links_file(bot, chat_id, export_type="batch"):
    """
    export_type: 
      "batch" -> فقط خروجی سری جدید (آخرین پردازش)
      "all" -> خروجی کل دیتابیس از ابتدا تاکنون
    """
    if export_type == "batch":
        # دریافت فقط شماره‌های سری جدید
        batch_phones = await db.lrange("jet:current_batch", 0, -1)
        if not batch_phones:
            await bot.send_message(chat_id=chat_id, text="❌ هیچ اکانت جدیدی در این سری برای خروجی وجود ندارد.")
            return
        
        records = []
        for p in batch_phones:
            val = await db.hget("jet:bulk_accounts", p)
            if val:
                records.append(json.loads(val))
                
        # پاکسازی لیست موقت سری فعلی پس از استخراج
        await db.delete("jet:current_batch")
        caption_type = "سری جدید"
        
    else:
        # دریافت کل اکانت‌ها
        raw_records = await db.hgetall("jet:bulk_accounts")
        if not raw_records:
            await bot.send_message(chat_id=chat_id, text="❌ هیچ لینکی در سیستم موجود نیست.")
            return
        records = [json.loads(val) for val in raw_records.values()]
        caption_type = "کل دیتابیس"

    # مرتب‌سازی بر اساس ردیف (ID) برای جلوگیری از به هم ریختگی
    records.sort(key=lambda x: x.get('id', 0))

    detailed_text = f"🔗 **بخش اول: لیست جامع ({caption_type})**\n" + "="*40 + "\n"
    compact_text = f"\n\n📱 **بخش دوم: فرمت فشرده ({caption_type})**\n" + "="*40 + "\n"
    raw_links_text = f"\n\n🌐 **بخش سوم: فقط لینک‌ها ({caption_type})**\n" + "="*40 + "\n"

    for data in records:
        link = f"{WEBHOOK_URL}/auth/{data['token']}"
        name = data.get('name', 'کاربر')
        phone = data.get('phone', 'نامشخص')
        row_id = data.get('id', '?') # ردیف پیوسته دیتابیس

        # 1. فرمت جامع شماره‌گذاری شده
        detailed_text += f"ردیف {row_id} | 📱 {phone} | 👤 {name}\n   🔗 {link}\n"
        # 2. فرمت فشرده
        compact_text += f"{row_id}. {phone}  ➡️  {link}\n"
        # 3. لینک خام
        raw_links_text += f"{link}\n"

    full_content = detailed_text + compact_text + raw_links_text
        
    file_bytes = BytesIO(full_content.encode('utf-8'))
    file_bytes.name = f"Nexus_Links_{caption_type}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    
    caption_text = (
        f"✅ **خروجی لینک‌ها ({caption_type}) با موفقیت آماده شد!**\n\n"
        f"📊 **تعداد اکانت‌های این فایل:** {len(records)}\n\n"
        f"داخل فایل پیوست ۳ مدل خروجی قرار دارد:\n"
        f"1️⃣ لیست با نام، شماره و ردیف کل\n"
        f"2️⃣ فرمت (ردیف. شماره ➡️ لینک)\n"
        f"3️⃣ فقط لینک‌های خام زیر هم"
    )
    
    await bot.send_document(chat_id=chat_id, document=file_bytes, caption=caption_text)

# ================= Telegram Handlers =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await admin_panel(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    
    keyboard = [
        [InlineKeyboardButton("▶️ شروع پردازش همزمان", callback_data="adm_start_bulk")],
        [InlineKeyboardButton("🔗 دریافت لینک‌های سری جدید", callback_data="adm_export_batch")],
        [InlineKeyboardButton("📥 دریافت تمام لینک‌ها (کل دیتابیس)", callback_data="adm_export_all_links")],
        [InlineKeyboardButton("📦 خروجی دیتابیس JSON", callback_data="adm_export_all")],
        [InlineKeyboardButton("⚠️ پاکسازی کل دیتابیس", callback_data="adm_clear_db_warn")]
    ]
    text = "⚙️ **پنل اتوماسیون مرکزی:**\n\nتولید لینک‌ها به صورت ایزوله در این سرور انجام می‌شود."
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS: return
    await query.answer()

    if query.data == "adm_start_bulk":
        await db.rpush("bot:admin_commands", "START_BULK")
        await query.message.reply_text("🚀 عملیات پردازش آغاز شد. گزارشات به زودی در همین چت ارسال می‌شوند...", parse_mode="Markdown")

    elif query.data == "adm_export_batch":
        msg = await query.message.reply_text("⏳ در حال ساخت فایل لینک‌های سری جدید...")
        await send_links_file(context.bot, query.message.chat.id, export_type="batch")
        await msg.delete()

    elif query.data == "adm_export_all_links":
        msg = await query.message.reply_text("⏳ در حال ساخت فایل تمامی لینک‌ها...")
        await send_links_file(context.bot, query.message.chat.id, export_type="all")
        await msg.delete()

    elif query.data == "adm_export_all":
        msg = await query.message.reply_text("⏳ در حال خروجی JSON...")
        keys = await db.keys("jet_session:*")
        all_accounts = {}
        for k in keys:
            data = await db.get(k)
            if data: all_accounts[k] = json.loads(data)
        
        file_bytes = BytesIO(json.dumps(all_accounts, ensure_ascii=False, indent=2).encode('utf-8'))
        file_bytes.name = f"Nexus_Database_{datetime.now().strftime('%Y%m%d')}.json"
        await context.bot.send_document(chat_id=query.message.chat.id, document=file_bytes)
        await msg.delete()

    elif query.data == "adm_clear_db_warn":
        warn_keyboard = [
            [InlineKeyboardButton("✅ بله، دیتابیس فلش شود", callback_data="adm_clear_db_confirm")],
            [InlineKeyboardButton("❌ انصراف", callback_data="adm_cancel_action")]
        ]
        await query.message.reply_text(
            "⚠️ **هشدار امنیتی!**\nآیا از پاکسازی کل دیتابیس اطمینان دارید؟\nاین عملیات تمام لینک‌ها، نشست‌ها، شمارنده‌ها و حافظه خطوط استخراج شده را به صورت کامل پاک می‌کند.", 
            reply_markup=InlineKeyboardMarkup(warn_keyboard), 
            parse_mode="Markdown"
        )

    elif query.data == "adm_clear_db_confirm":
        # پاکسازی تمامی رکوردهای مرتبط
        await db.delete("jet:processed_phones", "jet:bulk_accounts", "jet:current_batch", "jet:account_counter")
        keys = await db.keys("jet_session:*")
        if keys:
            await db.delete(*keys)
        await query.message.edit_text("🧹 دیتابیس و شمارنده‌ها با موفقیت به صورت کامل فلش شدند.")

    elif query.data == "adm_cancel_action":
        await query.message.edit_text("✅ عملیات لغو شد.")

# ================= Background Workers =================
async def alert_listener(app: Application):
    while True:
        try:
            alert = await db.lpop("bot:admin_alerts")
            if alert:
                for admin_id in ADMIN_IDS:
                    try:
                        await app.bot.send_message(chat_id=admin_id, text=alert, parse_mode="Markdown")
                        # وقتی عملیات دیجی‌کالا تمام می‌شود، فقط خروجی همان سری جدید (batch) ارسال می‌شود
                        if "گزارش نهایی" in alert:
                            await app.bot.send_message(chat_id=admin_id, text="⏳ در حال آماده‌سازی خودکار فایل لینک‌های این سری...")
                            await send_links_file(app.bot, admin_id, export_type="batch")
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(2)

async def file_listener(app: Application):
    while True:
        try:
            file_data_str = await db.lpop("bot:admin_files")
            if file_data_str:
                file_data = json.loads(file_data_str)
                file_bytes = BytesIO(file_data["content"].encode('utf-8'))
                file_bytes.name = file_data["filename"]
                
                for admin_id in ADMIN_IDS:
                    try:
                        file_bytes.seek(0)
                        await app.bot.send_document(
                            chat_id=admin_id, 
                            document=file_bytes, 
                            caption="📄 **فایل گزارش کامل عملیات (دیباگ)**",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(2)

async def token_generator_worker():
    while True:
        try:
            raw_data = await db.lpop("bot:new_accounts")
            if raw_data:
                acc = json.loads(raw_data)
                phone, name, final_json = acc["phone"], acc["name"], acc["data"]
                
                session_token = secrets.token_urlsafe(14)
                
                # تولید ردیف (شماره سریال) یکتا و پیوسته برای این اکانت
                global_id = await db.incr("jet:account_counter")
                
                await db.setex(f"jet_session:{session_token}", 30 * 24 * 3600, json.dumps(final_json, ensure_ascii=False))
                
                # ذخیره اطلاعات همراه با ردیف اختصاصی
                record = {"phone": phone, "token": session_token, "name": name, "id": global_id}
                await db.hset("jet:bulk_accounts", phone, json.dumps(record, ensure_ascii=False))
                
                # اضافه کردن به لیست موقت "سری جدید" برای خروجی‌گیری هوشمند
                await db.rpush("jet:current_batch", phone)
                
        except Exception:
            pass
        await asyncio.sleep(1)

# ================= Secure Gateway Web Route =================
async def web_telegram_webhook(request: web.Request):
    app = request.app["bot_app"]
    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
    except Exception:
        pass
    return web.Response(text="OK")

async def web_secure_gateway(request: web.Request):
    token_key = request.match_info.get("token")
    session_data_str = await db.get(f"jet_session:{token_key}")

    if not session_data_str:
        return web.Response(text="پیوند منقضی یا نامعتبر است.", status=404, content_type="text/plain;charset=utf-8")

    user_agent = request.headers.get("User-Agent", "")
    app_header = request.headers.get("X-Client-App", "")

    if app_header == APP_SECRET_HEADER or "JetAppClient" in user_agent:
        return web.json_response({"status": "success", "session": json.loads(session_data_str)})

    html_blocked = '<html dir="rtl" lang="fa"><meta charset="UTF-8"><body style="font-family:Tahoma;text-align:center;margin-top:50px;"><h3>دسترسی مسدود است</h3><p>لینک فقط در اپلیکیشن باز می‌شود.</p></body></html>'
    return web.Response(text=html_blocked, content_type="text/html")

async def main():
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("admin", admin_panel))
    bot_app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_"))
    
    web_app = web.Application()
    web_app["bot_app"] = bot_app
    # مسیر وب‌هوک تلگرام
    web_app.router.add_post(f"/webhook/{TOKEN}", web_telegram_webhook)
    # مسیر تحویل امن اطلاعات
    web_app.router.add_get("/auth/{token}", web_secure_gateway)
    
    await bot_app.initialize()
    await bot_app.start()
    
    # تنظیم وب‌هوک به صورت خودکار
    webhook_endpoint = f"{WEBHOOK_URL}/webhook/{TOKEN}"
    await bot_app.bot.set_webhook(url=webhook_endpoint)
    
    # اجرای تسک‌های پس‌زمینه
    asyncio.create_task(alert_listener(bot_app))
    asyncio.create_task(file_listener(bot_app))
    asyncio.create_task(token_generator_worker())
    
    # راه‌اندازی سرور Aiohttp برای Railway
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logging.info(f"Bot Webhook set to: {webhook_endpoint}")
    logging.info(f"Web server started on port {PORT}")
    
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot_app.stop()
        await bot_app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
