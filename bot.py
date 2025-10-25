import json
import logging
import os
from datetime import datetime, date, time, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')  # Из переменных окружения
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
MASTER_NAME = "Ден"

# Проверка токена
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN not set! Please set environment variable.")
    exit(1)

if not ADMIN_ID:
    logging.error("❌ ADMIN_ID not set! Please set environment variable.")
    exit(1)

WORK_START = (10, 0)   # 10:00
WORK_END = (22, 0)     # 22:00
INTERVAL_MIN = 45      # шаг 45 минут
DAYS_AHEAD = 7         # даты на 7 дней

DATA_FILE = "bookings.json"

# Услуги
SERVICES = [
    {"id": 1, "name": "Мужская стрижка", "price": "80,000 сум"},
    {"id": 2, "name": "Борода", "price": "50,000 сум"},
    {"id": 3, "name": "Стрижка + укладка", "price": "100,000 сум"},
    {"id": 4, "name": "Окрашивание волос", "price": "150,000 сум"},
]

# ---------------- LOG ----------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------- Storage helpers ----------------
def load_bookings():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                return []
    except Exception as e:
        logger.error("Error loading bookings: %s", e)
        return []

def save_bookings(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Error saving bookings: %s", e)

def booking_id():
    return int(datetime.now().timestamp() * 1000)

# ---------------- Helpers: dates & times ----------------
def generate_dates(n=DAYS_AHEAD):
    today = date.today()
    return [today + timedelta(days=i) for i in range(1, n+1)]

def generate_times():
    times = []
    cur = datetime.combine(date.today(), time(hour=WORK_START[0], minute=WORK_START[1]))
    end_dt = datetime.combine(date.today(), time(hour=WORK_END[0], minute=WORK_END[1]))
    while cur <= end_dt:
        times.append(cur.time().strftime("%H:%M"))
        cur += timedelta(minutes=INTERVAL_MIN)
    return times

def slot_is_free(bookings, date_iso, time_str):
    for b in bookings:
        if b.get("date") == date_iso and b.get("time") == time_str and b.get("status") == "confirmed":
            return False
    return True

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    
    kb = [
        [InlineKeyboardButton("📅 Записаться", callback_data="book")],
    ]
    
    if update.message:
        await update.message.reply_text(
            f"Привет! Я бот для записи к мастеру {MASTER_NAME}. ✨\n\n"
            f"Нажмите кнопку ниже чтобы записаться:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await update.callback_query.edit_message_text(
            f"Привет! Я бот для записи к мастеру {MASTER_NAME}. ✨\n\n"
            f"Нажмите кнопку ниже чтобы записаться:",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def handle_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["selected_services"] = []
    
    await query.edit_message_text(
        "📝 *Начата новая запись*\n\n"
        "Выберите услуги (нажмите для отметки):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💇 Мужская стрижка — 80,000 сум", callback_data="svc_1")],
            [InlineKeyboardButton("🧔 Борода — 50,000 сум", callback_data="svc_2")],
            [InlineKeyboardButton("✂️ Стрижка + укладка — 100,000 сум", callback_data="svc_3")],
            [InlineKeyboardButton("🎨 Окрашивание волос — 150,000 сум", callback_data="svc_4")],
            [InlineKeyboardButton("✅ Готово", callback_data="svc_done")],
            [InlineKeyboardButton("🔙 Отмена", callback_data="back_start")],
        ]),
        parse_mode='Markdown'
    )

async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "svc_done":
        if not context.user_data.get("selected_services"):
            await query.answer("Выберите хотя бы одну услугу", show_alert=True)
            return
        
        dates = generate_dates()
        kb = []
        for d in dates:
            day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            day_name = day_names[d.weekday()]
            kb.append([InlineKeyboardButton(f"📅 {d.strftime('%d.%m.%Y')} ({day_name})", callback_data=f"date_{d.isoformat()}")])
        kb.append([InlineKeyboardButton("🔙 Назад", callback_data="back_services")])
        
        await query.edit_message_text(
            "Выберите дату:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        sid = int(data.split("_")[1])
        sel = context.user_data.get("selected_services", [])
        if sid in sel:
            sel.remove(sid)
        else:
            sel.append(sid)
        context.user_data["selected_services"] = sel
        
        # Обновляем кнопки с отметками
        kb = []
        for s in SERVICES:
            prefix = "✅ " if s["id"] in sel else ""
            kb.append([InlineKeyboardButton(f"{prefix}{s['name']} — {s['price']}", callback_data=f"svc_{s['id']}")])
        kb.append([InlineKeyboardButton("✅ Готово", callback_data="svc_done")])
        kb.append([InlineKeyboardButton("🔙 Отмена", callback_data="back_start")])
        
        await query.edit_message_text(
            "Выберите услуги (нажмите для отметки):",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_services":
        sel = context.user_data.get("selected_services", [])
        kb = []
        for s in SERVICES:
            prefix = "✅ " if s["id"] in sel else ""
            kb.append([InlineKeyboardButton(f"{prefix}{s['name']} — {s['price']}", callback_data=f"svc_{s['id']}")])
        kb.append([InlineKeyboardButton("✅ Готово", callback_data="svc_done")])
        kb.append([InlineKeyboardButton("🔙 Отмена", callback_data="back_start")])
        
        await query.edit_message_text(
            "Выберите услуги (нажмите для отметки):",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        iso_date = data.replace("date_", "")
        context.user_data["date"] = iso_date
        
        sel_date = context.user_data.get("date")
        bookings = load_bookings()
        all_times = generate_times()
        
        buttons = []
        for t in all_times:
            if slot_is_free(bookings, sel_date, t):
                buttons.append(InlineKeyboardButton(t, callback_data=f"time_{t}"))
            else:
                buttons.append(InlineKeyboardButton(f"❌ {t}", callback_data="busy"))
        
        rows = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
        rows.append([InlineKeyboardButton("🔙 Назад", callback_data="back_dates")])
        
        date_display = datetime.fromisoformat(sel_date).strftime('%d.%m.%Y')
        await query.edit_message_text(
            f"🕐 Выберите время на {date_display}:",
            reply_markup=InlineKeyboardMarkup(rows)
        )

async def handle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_dates":
        dates = generate_dates()
        kb = []
        for d in dates:
            day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            day_name = day_names[d.weekday()]
            kb.append([InlineKeyboardButton(f"📅 {d.strftime('%d.%m.%Y')} ({day_name})", callback_data=f"date_{d.isoformat()}")])
        kb.append([InlineKeyboardButton("🔙 Назад", callback_data="back_services")])
        
        await query.edit_message_text(
            "Выберите дату:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    elif data == "busy":
        await query.answer("Этот слот занят", show_alert=True)
    else:
        time_str = data.replace("time_", "")
        
        bookings = load_bookings()
        if not slot_is_free(bookings, context.user_data["date"], time_str):
            await query.answer("Слот уже заняли", show_alert=True)
            return
        
        context.user_data["time"] = time_str
        await query.edit_message_text("👤 Введите ваше имя:")

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Введите имя (минимум 2 символа):")
        return
    
    context.user_data["name"] = name
    
    contact_keyboard = [[KeyboardButton("📱 Отправить номер", request_contact=True)]]
    await update.message.reply_text(
        "📞 Введите номер телефона:",
        reply_markup=ReplyKeyboardMarkup(contact_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

async def phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    
    digits = ''.join(filter(str.isdigit, phone))
    if len(digits) < 9:
        await update.message.reply_text("Неверный номер. Попробуйте еще раз:")
        return
    
    context.user_data["phone"] = phone
    
    services = [s["name"] for s in SERVICES if s["id"] in context.user_data.get("selected_services", [])]
    dt = context.user_data["date"]
    tm = context.user_data["time"]
    
    summary = (
        f"# Zapis.uz\n"
        f"## *Подтвердите запись:*\n\n"
        f"- Имя: {context.user_data['name']}\n"
        f"  Телефон: {phone}\n"
        f"- Услуги: {', '.join(services)}\n"
        f"  Дата: {datetime.fromisoformat(dt).strftime('%d.%m.%Y')}\n"
        f"  Время: {tm}\n"
        f"  Мастер: {MASTER_NAME}\n\n"
        f"---\n"
    )
    
    kb = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_book")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_flow")]
    ]
    
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(kb))

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_flow":
        await query.edit_message_text("Запись отменена. /start чтобы начать заново.")
        context.user_data.clear()
        return
    
    if data == "confirm_book":
        bookings = load_bookings()
        dt = context.user_data["date"]
        tm = context.user_data["time"]
        
        if not slot_is_free(bookings, dt, tm):
            await query.answer("Слот уже заняли", show_alert=True)
            return
        
        b_id = booking_id()
        services = [s["name"] for s in SERVICES if s["id"] in context.user_data.get("selected_services", [])]
        
        booking = {
            "id": b_id,
            "user_id": str(query.from_user.id),
            "name": context.user_data["name"],
            "phone": context.user_data["phone"],
            "services": services,
            "date": dt,
            "time": tm,
            "status": "confirmed",
            "created": datetime.now().isoformat()
        }
        
        bookings.append(booking)
        save_bookings(bookings)
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🆕 Новая запись #{b_id}\n"
                    f"👤 {booking['name']}\n"
                    f"📞 {booking['phone']}\n"
                    f"💈 {', '.join(services)}\n"
                    f"📅 {dt} {tm}\n\n"
                    f"❌ Удалить запись: /delete_{b_id}"
                )
            )
        except Exception as e:
            logger.error("Admin notify error: %s", e)
        
        # ФИНАЛЬНОЕ СООБЩЕНИЕ
        date_display = datetime.fromisoformat(dt).strftime('%d.%m.%Y')
        
        final_text = (
            f"### Вы записаны к {MASTER_NAME}!\n\n"
            f"- Услуги: {', '.join(services)}\n"
            f"  Дата: {date_display}\n"
            f"  Время: {tm}\n"
            f"  Имя: {context.user_data['name']}\n"
            f"  Телефон: {context.user_data['phone']}\n\n"
            f"---\n\n"
            f"### Ждем вас!\n\n"
            f"Если передумаете, можете отменить запись:\n"
            f"01:00\n\n"
            f"---\n"
        )
        
        kb = [
            [InlineKeyboardButton("❌ Отменить эту запись", callback_data=f"cancel_{b_id}")],
        ]
        
        await query.message.reply_text(
            final_text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode='Markdown'
        )
        
        context.user_data.clear()

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("cancel_"):
        try:
            bid = int(query.data.replace("cancel_", ""))
        except ValueError:
            await query.answer("❌ Ошибка отмены", show_alert=True)
            return
        
        logger.info(f"Клиент отменяет запись #{bid}")
        
        bookings = load_bookings()
        
        for i, b in enumerate(bookings):
            if b.get("id") == bid and b.get("status") == "confirmed":
                if str(b.get("user_id")) != str(query.from_user.id):
                    await query.answer("❌ Это не ваша запись", show_alert=True)
                    return
                
                # ОТМЕНЯЕМ ЗАПИСЬ
                bookings[i]["status"] = "cancelled"
                bookings[i]["cancelled_at"] = datetime.now().isoformat()
                bookings[i]["cancelled_by"] = "client"
                save_bookings(bookings)
                
                # Уведомление админу
                try:
                    await context.bot.send_message(
                        ADMIN_ID, 
                        f"❌ КЛИЕНТ ОТМЕНИЛ ЗАПИСЬ #{bid}\n"
                        f"👤 {b.get('name')} ({b.get('phone')})\n"
                        f"📅 {b.get('date')} {b.get('time')}\n"
                        f"💈 {', '.join(b.get('services', []))}"
                    )
                except Exception as e:
                    logger.error("Admin notify error: %s", e)
                
                # Сообщение об отмене
                date_display = datetime.fromisoformat(b.get('date')).strftime('%d.%m.%Y')
                
                await query.edit_message_text(
                    f"✅ *Запись отменена!*\n\n"
                    f"📅 {date_display} {b.get('time')}\n"
                    f"💈 {', '.join(b.get('services', []))}\n\n"
                    f"Для новой записи нажмите /start",
                    parse_mode='Markdown'
                )
                return
        
        await query.answer("❌ Запись не найдена", show_alert=True)

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_start":
        await start(update, context)

# КОМАНДА ДЛЯ АДМИНА
async def admin_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    bookings = load_bookings()
    active_bookings = [b for b in bookings if b.get('status') == 'confirmed']
    
    if not active_bookings:
        await update.message.reply_text("📭 Активных записей нет")
        return
    
    text = "📊 *Активные записи:*\n\n"
    kb = []
    
    for b in active_bookings:
        date_display = datetime.fromisoformat(b['date']).strftime('%d.%m.%Y')
        text += f"🔹 {date_display} {b['time']}\n"
        text += f"   👤 {b.get('name')} ({b.get('phone')})\n"
        text += f"   💈 {', '.join(b.get('services', []))}\n"
        text += f"   ID: #{b.get('id')}\n\n"
        
        kb.append([InlineKeyboardButton(
            f"🗑️ Удалить {date_display} {b['time']}", 
            callback_data=f"admin_cancel_{b['id']}"
        )])
    
    await update.message.reply_text(
        text, 
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode='Markdown'
    )

# ОБРАБОТЧИК ОТМЕНЫ АДМИНОМ
async def handle_admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("admin_cancel_"):
        try:
            bid = int(query.data.replace("admin_cancel_", ""))
        except ValueError:
            await query.answer("❌ Ошибка отмены", show_alert=True)
            return
        
        if query.from_user.id != ADMIN_ID:
            await query.answer("❌ Только админ может отменять записи", show_alert=True)
            return
        
        logger.info(f"Админ отменяет запись #{bid}")
        
        bookings = load_bookings()
        booking_found = False
        
        for i, b in enumerate(bookings):
            if b.get("id") == bid and b.get("status") == "confirmed":
                booking_found = True
                
                # ОТМЕНЯЕМ ЗАПИСЬ
                bookings[i]["status"] = "cancelled"
                bookings[i]["cancelled_at"] = datetime.now().isoformat()
                bookings[i]["cancelled_by"] = "admin"
                save_bookings(bookings)
                
                # Уведомление клиенту
                try:
                    user_id = int(b.get('user_id'))
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"❌ *Ваша запись отменена администратором*\n\n"
                            f"📅 {datetime.fromisoformat(b['date']).strftime('%d.%m.%Y')} {b['time']}\n"
                            f"💈 {', '.join(b.get('services', []))}\n\n"
                            f"Для новой записи нажмите /start"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error notifying user: {e}")
                
                # Обновляем сообщение админа
                await query.edit_message_text(
                    f"✅ *Запись #{bid} отменена*\n\n"
                    f"👤 {b.get('name')} ({b.get('phone')})\n"
                    f"📅 {b.get('date')} {b.get('time')}\n"
                    f"💈 {', '.join(b.get('services', []))}",
                    parse_mode='Markdown'
                )
                break
        
        if not booking_found:
            await query.answer("❌ Запись не найдена или уже отменена", show_alert=True)

# ОБРАБОТЧИК КОМАНДЫ УДАЛЕНИЯ ДЛЯ АДМИНА
async def handle_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещен")
        return
    
    command = update.message.text
    if command.startswith('/delete_'):
        try:
            bid = int(command.replace('/delete_', ''))
        except ValueError:
            await update.message.reply_text("❌ Неверный ID записи")
            return
        
        bookings = load_bookings()
        booking_found = False
        
        for i, b in enumerate(bookings):
            if b.get("id") == bid and b.get("status") == "confirmed":
                booking_found = True
                
                # ОТМЕНЯЕМ ЗАПИСЬ
                bookings[i]["status"] = "cancelled"
                bookings[i]["cancelled_at"] = datetime.now().isoformat()
                bookings[i]["cancelled_by"] = "admin"
                save_bookings(bookings)
                
                # Уведомление клиенту
                try:
                    user_id = int(b.get('user_id'))
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"❌ *Ваша запись отменена администратором*\n\n"
                            f"📅 {datetime.fromisoformat(b['date']).strftime('%d.%m.%Y')} {b['time']}\n"
                            f"💈 {', '.join(b.get('services', []))}\n\n"
                            f"Для новой записи нажмите /start"
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error notifying user: {e}")
                
                await update.message.reply_text(
                    f"✅ *Запись #{bid} отменена*\n\n"
                    f"👤 {b.get('name')} ({b.get('phone')})\n"
                    f"📅 {b.get('date')} {b.get('time')}\n"
                    f"💈 {', '.join(b.get('services', []))}",
                    parse_mode='Markdown'
                )
                break
        
        if not booking_found:
            await update.message.reply_text("❌ Запись не найдена или уже отменена")

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}")

# ---------------- MAIN ----------------
def main():
    try:
        app = Application.builder().token(BOT_TOKEN).build()
        logger.info("✅ Бот создан успешно!")
    except Exception as e:
        logger.error(f"❌ Ошибка создания бота: {e}")
        return

    # ОБРАБОТЧИКИ
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bookings", admin_bookings))
    app.add_handler(MessageHandler(filters.Regex(r'^/delete_\d+'), handle_delete_command))
    
    # Обработчики callback
    app.add_handler(CallbackQueryHandler(handle_book, pattern="^book$"))
    app.add_handler(CallbackQueryHandler(handle_service, pattern="^svc_"))
    app.add_handler(CallbackQueryHandler(handle_date, pattern="^date_"))
    app.add_handler(CallbackQueryHandler(handle_time, pattern="^time_"))
    app.add_handler(CallbackQueryHandler(handle_back, pattern="^back_"))
    app.add_handler(CallbackQueryHandler(handle_confirm, pattern="^(confirm_book|cancel_flow)$"))
    app.add_handler(CallbackQueryHandler(handle_cancel, pattern="^cancel_"))
    app.add_handler(CallbackQueryHandler(handle_admin_cancel, pattern="^admin_cancel_"))
    
    # Обработчики сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler))
    app.add_handler(MessageHandler(filters.CONTACT, phone_handler))
    
    # Обработчик ошибок
    app.add_error_handler(error_handler)

    logger.info("✅ Бот запускается...")
    
    # Бесконечный перезапуск при ошибках
    while True:
        try:
            app.run_polling(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"❌ Бот упал: {e}")
            logger.info("🔄 Перезапуск через 10 секунд...")
            import time
            time.sleep(10)

if __name__ == "__main__":
    main()