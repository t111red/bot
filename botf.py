# -*- coding: utf-8 -*-  
import asyncio
import os
import sys
import logging
import sqlite3
import json
import zipfile
from datetime import datetime, timedelta
def adapt_datetime(dt):
    return dt.isoformat()
def convert_datetime(s):
    return datetime.fromisoformat(s.decode())
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("datetime", convert_datetime)
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
import pytz
from aiogram.exceptions import TelegramForbiddenError
import pandas as pd
from aiogram.types import InputFile
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
# ==================== НАСТРОЙКИ ====================
TOKEN = "7902503164:AAFUVT64sz45cC22Idgwbr3fN3oAdKhP70k"
ADMIN_IDS = [977248218, 7620299755]
BOOK_LINK = ""  # Ссылка на книгу удалена
TIMEZONE = pytz.timezone('Asia/Irkutsk')
WORK_HOURS = (8, 18)  # Рабочее время с 8:00 до 18:00
DB_BACKUP_TIME = 20  # Время отправки файла bot.db администратору (в часах)
REGULAR_ORDERS_COUNT = 3
PROMO_CODE = "РЫБА2025"
GOLD_PROMO = "ЗОЛОТО"
DISCOUNT = 0.9
GOLD_DISCOUNT = 0.9
# Время истечения лидов в минутах
LEAD_EXPIRATION_MINUTES = 15
# Цены для расчёта итоговой суммы
PRICES = {
    "маленькая": 450,
    "средняя": 600,
    "крупная": 750
}
# Отслеживание использования промокодов (user_id, промокод)
used_promo_users = {}
# Словарь для хранения выданного (но ещё не использованного) промокода GOLD_PROMO
awarded_gold = {}
LEAD_EXPIRATION_MINUTES = 1440  # Время в минутах (24 часа), через которое лид истекает
# Ссылка на канал с отзывами
REVIEWS_CHANNEL_URL = "https://t.me/+i-z81AuC_gxiMzVi"  # Замените на реальную ссылку
# Константы администратора
ADMIN_API_KEY = os.environ.get("ADMIN_KEY", "admin_access_secret")  # Ключ для доступа к админке

# Словарь соответствия статусов Notion и текстовых сообщений для пользователя
STATUS_MESSAGES = {
    "Новый": "Ваш заказ успешно создан!",
    "В работе": "Ваш заказ взят в работу! Скоро с вами свяжется менеджер.",
    "Доставлен": "Ваш заказ доставлен! Надеемся, вам понравился наш сервис.",
    "Отменён": "К сожалению, ваш заказ был отменён.",
    "Ожидает оплаты": "Ваш заказ ожидает оплаты."
}

# ==================== ТЕКСТОВЫЕ КОНСТАНТЫ ====================
WELCOME_TEXT = "Привет! Я помогу легко оформить заказ\n\nМы предлагаем только свежую рыбу по отличным условиям."
WELCOME_IMAGE_ID = "AgACAgIAAxkBAAIH52e9xLEj0FmF7zWSsGB_Nc1U1k1pAAKE9TEb0hHwSdjSJov3eGfrAQADAgADeAADNgQ"  # Замените эту строку на реальный ID изображения
MAKE_ORDER_BUTTON = "🐟Оформить заказ"
ASK_NAME_TEXT = "Как к вам обращаться?"
SIZE_PROMPT_TEXT = "Выберите размер рыбы:"
CART_HEADER_TEXT = "🛒 Ваша корзина:"
PROMO_PROMPT_TEXT = "🎟 Введите промокод или воспользуйтесь кнопкой ниже:"
NO_PROMO_BUTTON_TEXT = "Нет"
# Шаблон запроса номера: если заказ повторный, перед двоеточием добавляется "(вдруг изменился)"
PHONE_PROMPT_TEXT = "📞 {0}, введите ваш номер телефона{1}:"
CALLBACK_PROMPT_TEXT = "⏰ Рабочий день уже закончился. Пожалуйста, укажите удобное время для связи на завтра(8-17):"
ORDER_SUCCESS_TEXT = "✅ Заказ оформлен! Скоро с вами свяжутся."
ADMIN_ORDER_TEMPLATE = ("📦 Новый заказ!\n"
                        "Заказ # {0}\n"
                        "👤 {1}\n"
                        "📞 {2}\n"
                        "🛒 Состав заказа:\n{3}\n"
                        "💰 {4}\n"
                        "🎟 Промокод: {5}\n"
                        "Статус: {6}")
ORDER_CONFIRMATION_PROMPT = "✅ Пожалуйста, оставьте обратную связь о сервисе:"
ADMIN_PANEL_TEXT = "⚙️ Панель управления:"
NO_HISTORY_TEXT = "📜 История заказов пуста."
DELETE_ORDER_SUCCESS_TEXT = "✅ Заказ удалён."
DELETE_ORDER_FAILURE_TEXT = "❌ Заказ не найден."
FEEDBACK_PROMPT_TEXT = "✍️ Напишите ваш отзыв(можно с фото):"
FEEDBACK_THANKS_TEXT = "📨 Спасибо за обратную связь!"
ADMIN_FEEDBACK_TEMPLATE = "📝 Отзыв от {0}:\n\n{1}"
NEW_ORDER_PROMPT = "Хотите оформить новый заказ?"
# Константы для жалоб и предложений
COMPLAINT_PROMPT_TEXT = "✍️ Напишите ваше обращение(можно с фото):"
COMPLAINT_THANKS_TEXT = "📨 Ваше обращение отправлено!"
ADMIN_COMPLAINT_TEMPLATE = "📝 Жалоба/Предложение от {0}:\n\n{1}"
STAGE_NAMES = {
    "OrderState:waiting_name": "Этап ввода ФИО",
    "OrderState:waiting_size": "Этап выбора размера рыбы",
    "OrderState:waiting_promo": "Этап ввода промокода",
    "OrderState:waiting_phone": "Этап ввода номера телефона",
    "OrderState:waiting_callback_time": "Этап указания времени звонка",
}
ORDER_RECOVERY_PROMPT = "У вас был незавершенный заказ. Хотите продолжить оформление?"
ORDER_RECOVERY_BTN = "✅ Продолжить оформление"
ORDER_START_NEW_BTN = "🔄 Начать новый заказ"
# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('bot.db', detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    
    # Таблица orders
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        full_name TEXT,
        items TEXT,
        total REAL,
        promo_used TEXT,
        phone TEXT,
        status TEXT DEFAULT 'неподтверждён',
        confirmed INTEGER DEFAULT 0,
        callback_time INTEGER,
        timestamp DATETIME,
        notion_page_id TEXT)''')
    
    # Таблица leads
    cursor.execute('''CREATE TABLE IF NOT EXISTS leads(
        id INTEGER PRIMARY KEY,  
        user_id INTEGER UNIQUE,  
        data TEXT,  
        stage TEXT,  
        timestamp DATETIME,  
        is_repeat INTEGER DEFAULT 0,
        is_completed INTEGER DEFAULT 0,        
        expired INTEGER DEFAULT 0,
        order_id INTEGER,
        notion_page_id TEXT,
        synced_to_notion INTEGER DEFAULT 0)''')  # Поля для работы с Notion
    
    # Таблица order_statuses для отслеживания статусов заказов
    cursor.execute('''CREATE TABLE IF NOT EXISTS order_statuses(
        id INTEGER PRIMARY KEY,
        order_id INTEGER,
        status TEXT,
        timestamp DATETIME,
        notified INTEGER DEFAULT 0,
        FOREIGN KEY(order_id) REFERENCES orders(id))''')
        
    cursor.execute("PRAGMA table_info(orders)")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    if 'notion_page_id' not in column_names:
        cursor.execute('ALTER TABLE orders ADD COLUMN notion_page_id TEXT')
        
    conn.commit()
    conn.close()

def update_db():
    conn = sqlite3.connect('bot.db', detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    
    # Проверяем, существует ли столбец expired в таблице leads
    cursor.execute("PRAGMA table_info(leads)")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    
    # Добавляем столбец expired, если его нет
    if 'expired' not in column_names:
        cursor.execute('''ALTER TABLE leads ADD COLUMN expired INTEGER DEFAULT 0''')
    
    # Добавляем столбец version, если его нет
    if 'version' not in column_names:
        cursor.execute('''ALTER TABLE leads ADD COLUMN version INTEGER DEFAULT 1''')
    
    # Добавляем столбец history, если его нет
    if 'history' not in column_names:
        cursor.execute('''ALTER TABLE leads ADD COLUMN history TEXT''')
        
    # Добавляем столбец notion_page_id, если его нет
    if 'notion_page_id' not in column_names:
        cursor.execute('''ALTER TABLE leads ADD COLUMN notion_page_id TEXT''')
        
    # Добавляем столбец synced_to_notion, если его нет
    if 'synced_to_notion' not in column_names:
        cursor.execute('''ALTER TABLE leads ADD COLUMN synced_to_notion INTEGER DEFAULT 0''')
    
    # Проверяем, существует ли таблица order_statuses
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_statuses'")
    if not cursor.fetchone():
        cursor.execute('''CREATE TABLE order_statuses(
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            status TEXT,
            timestamp DATETIME,
            notified INTEGER DEFAULT 0,
            FOREIGN KEY(order_id) REFERENCES orders(id))''')
    
    # Проверяем, существует ли таблица failed_notifications
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='failed_notifications'")
    if not cursor.fetchone():
        cursor.execute('''CREATE TABLE failed_notifications(
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            message TEXT,
            created_at DATETIME,
            last_attempt DATETIME,
            attempts INTEGER DEFAULT 1)''')
    
    conn.commit()
    conn.close()

init_db()
update_db()

# ==================== СЛУЖЕБНЫЕ ФУНКЦИИ ====================
def get_current_time():
    return datetime.now(TIMEZONE)

def db_execute(query, params=()):
    conn = None
    cursor = None
    try:
        conn = sqlite3.connect('bot.db', detect_types=sqlite3.PARSE_DECLTYPES)
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        # Если это INSERT запрос, сохраняем lastrowid
        lastrowid = None
        if query.strip().upper().startswith("INSERT"):
            lastrowid = cursor.lastrowid
            
        conn.commit()
        
        # Если это запрос SELECT, получаем результаты перед закрытием соединения
        if query.strip().upper().startswith("SELECT"):
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            # Создаем новый курсор из результатов запроса
            class ResultCursor:
                def __init__(self, results, lastrowid=None):
                    self.results = results
                    self.position = 0
                    self.lastrowid = lastrowid
                
                def fetchone(self):
                    if self.position < len(self.results):
                        result = self.results[self.position]
                        self.position += 1
                        return result
                    return None
                
                def fetchall(self):
                    remaining = self.results[self.position:]
                    self.position = len(self.results)
                    return remaining
            
            return ResultCursor(results)
        
        # Для не-SELECT запросов, имитируем курсор с необходимыми атрибутами
        class NonSelectCursor:
            def __init__(self, lastrowid=None):
                self.lastrowid = lastrowid
                
            def fetchone(self):
                return None
                
            def fetchall(self):
                return []
        
        # Закрываем курсор и соединение
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
        # Для INSERT запросов, возвращаем курсор с lastrowid
        if query.strip().upper().startswith("INSERT"):
            return NonSelectCursor(lastrowid)
            
        # Для остальных запросов, возвращаем пустой курсор
        return NonSelectCursor()
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        raise

def is_working_time():
    current_hour = get_current_time().hour
    return WORK_HOURS[0] <= current_hour < WORK_HOURS[1]

def is_regular_client(user_id):
    cursor = db_execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND confirmed = 1", (user_id,))
    result = cursor.fetchone()
    count = result[0] if result else 0
    return count >= REGULAR_ORDERS_COUNT
    
def get_name_and_initial(full_name):
    parts = full_name.split()
    if len(parts) >= 2:
        name = parts[0]
        initial = parts[1][0] + "."
        return f"{name} {initial}"
    return full_name  # Если фамилия не указана, возвращаем полное имя

def get_user_info(user_id):
    """Получает информацию о пользователе из базы данных."""
    try:
        # Сначала ищем в заказах
        cursor = db_execute(
            "SELECT full_name, phone, COUNT(*) as orders_count FROM orders WHERE user_id = ? GROUP BY full_name, phone ORDER BY COUNT(*) DESC LIMIT 1", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result:
            return {
                "full_name": result[0], 
                "phone": result[1],
                "orders_count": result[2],
                "is_regular": result[2] >= REGULAR_ORDERS_COUNT
            }
            
        # Если заказов нет, проверяем в лидах
        cursor = db_execute(
            "SELECT data FROM leads WHERE user_id = ? AND expired = 0 ORDER BY timestamp DESC LIMIT 1", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result and result[0]:
            try:
                data = json.loads(result[0])
                if data.get("full_name") and data.get("phone"):
                    return {
                        "full_name": data.get("full_name"),
                        "phone": data.get("phone"),
                        "orders_count": 0,
                        "is_regular": False
                    }
            except json.JSONDecodeError:
                pass
                
        return None
    except Exception as e:
        logging.error(f"Error getting user info: {e}")
        return None

def get_lead_data(user_id):
    """Получает данные незавершенного лида для пользователя."""
    try:
        cursor = db_execute(
            "SELECT id, data, stage, is_completed, expired FROM leads WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", 
            (user_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            return None
            
        lead_id, data_json, stage, is_completed, expired = result
        
        # Если лид уже завершен или истек (expired=1), возвращаем None
        if is_completed or (expired is not None and expired == 1):
            return None
            
        try:
            data = json.loads(data_json) if data_json else {}
            return {
                "id": lead_id,
                "data": data,
                "stage": stage
            }
        except json.JSONDecodeError:
            logging.error(f"Failed to decode lead data JSON for user {user_id}")
            return None
    except Exception as e:
        logging.error(f"Error retrieving lead data for user {user_id}: {e}")
        return None

def expire_old_leads():
    """Помечает устаревшие лиды как истекшие. Сохраняет последний лид для каждого пользователя активным."""
    expiration_time = datetime.now() - timedelta(minutes=LEAD_EXPIRATION_MINUTES)
    
    try:
        # Находим самые последние лиды для каждого пользователя, чтобы не помечать их как expired
        result = db_execute(
            """UPDATE leads SET expired = 1 
               WHERE timestamp < ? AND is_completed = 0 AND (expired = 0 OR expired IS NULL)
               AND id NOT IN (
                   SELECT MAX(id) FROM leads 
                   WHERE is_completed = 0 AND (expired = 0 OR expired IS NULL)
                   GROUP BY user_id
               )""",
            (expiration_time,)
        )
        
        # Получаем количество помеченных лидов
        affected_rows = result.rowcount if hasattr(result, 'rowcount') else 0
        if affected_rows > 0:
            logging.info(f"Пометил {affected_rows} устаревших лидов старше {expiration_time}")
        else:
            logging.info(f"Expired old leads older than {expiration_time}")
    except Exception as e:
        logging.error(f"Failed to expire old leads: {e}")
        import traceback
        logging.error(f"Exception traceback: {traceback.format_exc()}")

def update_lead(user_id, data, stage, is_completed=False, order_id=None):
    """Обновляет или создает запись лида."""
    try:
        # Преобразуем данные в JSON
        data_json = json.dumps(data) if data else None
        
        # Проверяем существующий активный лид
        cursor = db_execute(
            "SELECT id FROM leads WHERE user_id = ? AND is_completed = 0 AND (expired = 0 OR expired IS NULL)", 
            (user_id,)
        )
        existing_lead = cursor.fetchone()
        
        current_time = datetime.now()
        
        if existing_lead:
            # Обновляем существующий лид
            lead_id = existing_lead[0]
            db_execute(
                "UPDATE leads SET data = ?, stage = ?, timestamp = ?, is_completed = ?, expired = 0, order_id = ? WHERE id = ?",
                (data_json, stage, current_time, 1 if is_completed else 0, order_id, lead_id)
            )
            logging.info(f"Updated lead {lead_id} for user {user_id}, stage: {stage}")
            return lead_id
        else:
            # Проверяем наличие истекшего лида для того же пользователя
            cursor = db_execute(
                "SELECT id FROM leads WHERE user_id = ? AND (expired = 1 OR is_completed = 1) ORDER BY timestamp DESC LIMIT 1", 
                (user_id,)
            )
            expired_lead = cursor.fetchone()
            
            if expired_lead:
                # Обновляем истекший лид вместо создания нового
                lead_id = expired_lead[0]
                db_execute(
                    "UPDATE leads SET data = ?, stage = ?, timestamp = ?, is_completed = 0, expired = 0, order_id = ? WHERE id = ?",
                    (data_json, stage, current_time, order_id, lead_id)
                )
                logging.info(f"Reactivated expired lead {lead_id} for user {user_id}, stage: {stage}")
                return lead_id
            else:
                # Создаем новый лид
                is_repeat = 1 if get_user_info(user_id) else 0
                
                # Используем строго именованные колонки для избежания ошибок
                cursor = db_execute(
                    """INSERT INTO leads 
                       (user_id, data, stage, timestamp, is_repeat, is_completed, expired, order_id) 
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                    (user_id, data_json, stage, current_time, is_repeat, 1 if is_completed else 0, order_id)
                )
                
                lead_id = cursor.lastrowid
                logging.info(f"Created new lead {lead_id} for user {user_id}, stage: {stage}, is_repeat: {is_repeat}")
                return lead_id
    except Exception as e:
        logging.error(f"Failed to update lead for user {user_id}: {e}")
        # Детальное логирование ошибки для отладки
        import traceback
        logging.error(f"Exception traceback: {traceback.format_exc()}")
        return None

def track_order_status(order_id, status):
    """Отслеживает изменение статуса заказа."""
    try:
        db_execute(
            "INSERT INTO order_statuses (order_id, status, timestamp, notified) VALUES (?, ?, ?, 0)",
            (order_id, status, datetime.now())
        )
        logging.info(f"Tracked new status '{status}' for order {order_id}")
    except Exception as e:
        logging.error(f"Failed to track status for order {order_id}: {e}")

def save_failed_notification(user_id, message_text):
    """Сохраняет неудачное уведомление для повторной попытки."""
    try:
        db_execute(
            "INSERT INTO failed_notifications (user_id, message, created_at, last_attempt, attempts) VALUES (?, ?, ?, ?, 1)",
            (user_id, message_text, datetime.now(), datetime.now())
        )
        logging.info(f"Saved failed notification for user {user_id} for retry later")
        return True
    except Exception as e:
        logging.error(f"Failed to save failed notification: {e}")
        return False

async def retry_failed_notifications(bot):
    """Повторяет отправку неудачных уведомлений."""
    try:
        # Получаем неудачные уведомления, которые не пытались отправить слишком много раз
        cursor = db_execute(
            "SELECT id, user_id, message FROM failed_notifications WHERE attempts < 5"
        )
        notifications = cursor.fetchall()
        
        if not notifications:
            return 0
            
        success_count = 0
        for notification_id, user_id, message in notifications:
            try:
                # Повторяем отправку сообщения с поддержкой HTML-форматирования
                await bot.send_message(user_id, message, parse_mode="HTML")
                
                # Удаляем успешно отправленное уведомление
                db_execute("DELETE FROM failed_notifications WHERE id = ?", (notification_id,))
                success_count += 1
                logging.info(f"Successfully resent notification #{notification_id} to user {user_id}")
            except Exception as e:
                # Увеличиваем счетчик попыток
                db_execute(
                    "UPDATE failed_notifications SET attempts = attempts + 1, last_attempt = ? WHERE id = ?",
                    (datetime.now(), notification_id)
                )
                logging.warning(f"Failed to resend notification #{notification_id} to user {user_id}: {e}")
        
        # Удаляем слишком старые уведомления (старше 7 дней)
        week_ago = datetime.now() - timedelta(days=7)
        db_execute("DELETE FROM failed_notifications WHERE created_at < ?", (week_ago,))
        
        return success_count
    except Exception as e:
        logging.error(f"Error in retry_failed_notifications: {e}")
        return 0

async def notify_status_change(bot, order_id, status):
    """Уведомляет пользователя и всех администраторов об изменении статуса заказа."""
    try:
        # Получаем информацию о заказе
        cursor = db_execute("""
            SELECT orders.user_id, orders.full_name, orders.phone, orders.items 
            FROM orders 
            WHERE orders.id = ?
        """, (order_id,))
        result = cursor.fetchone()
        
        if not result:
            logging.error(f"Order {order_id} not found for status notification")
            return False
            
        user_id, full_name, phone, items_json = result
        
        # Определяем, нужно ли отправлять уведомление пользователю и какой текст
        if status.lower() == "в работе":
            # Для статуса "В работе" отправляем только сообщение, что заказ взят в работу
            send_to_user = True
            user_message = "Ваш заказ взят в работу! Скоро с вами свяжется менеджер."
        elif status.lower() in ["завершен", "завершён", "выполнен", "новый"]:
            # Для этих статусов уведомления пользователю не отправляем
            send_to_user = False
            user_message = ""
        else:
            # Для всех остальных статусов используем стандартное сообщение
            send_to_user = True
            user_message = f"Статус вашего заказа #{order_id} изменен на: {status}"
        
        # Формируем детальное сообщение для администраторов
        items = json.loads(items_json) if items_json else []
        admin_message = (
            f"🔄 <b>Изменение статуса заказа #{order_id}</b>\n\n"
            f"👤 <b>Клиент:</b> {full_name}\n"
            f"📞 <b>Телефон:</b> {phone}\n"
            f"📋 <b>Заказ:</b> {', '.join(items) if isinstance(items, list) else str(items)}\n"
            f"📊 <b>Новый статус:</b> {status}"
        )
        
        # Отправляем уведомление пользователю, если это требуется
        user_notified = False
        if send_to_user and user_message:
            try:
                await bot.send_message(user_id, user_message, parse_mode="HTML")
                logging.info(f"Уведомление о статусе заказа {order_id} отправлено пользователю {user_id}")
                user_notified = True
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
                # Сохраняем для повторной отправки
                if not isinstance(e, TelegramForbiddenError):  # Если не блокировка бота
                    save_failed_notification(user_id, user_message)
        
        # Отправляем уведомления всем администраторам
        admin_notified_count = 0
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_message, parse_mode="HTML")
                admin_notified_count += 1
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")
        
        # Помечаем статус как отправленный в любом случае
        db_execute(
            "UPDATE order_statuses SET notified = 1 WHERE order_id = ? AND status = ?",
            (order_id, status)
        )
        
        return user_notified or admin_notified_count > 0
    
    except Exception as e:
        logging.error(f"Ошибка в функции notify_status_change для заказа {order_id}: {e}")
        return False

# ==================== СОСТОЯНИЯ FSM ====================
class OrderState(StatesGroup):
    waiting_name = State()
    waiting_size = State()
    waiting_promo = State()
    waiting_phone = State()
    waiting_callback_time = State()

class DeleteOrderState(StatesGroup):
    waiting_order_id = State()

class FeedbackState(StatesGroup):
    waiting_text = State()

class ComplaintState(StatesGroup):
    waiting_text = State()
    
class BroadcastState(StatesGroup):
    waiting_message = State()

# ==================== КЛАВИАТУРЫ ====================
# Админ-панель больше не используется, согласно требованиям

def main_menu_keyboard():
    # Создаем URL для WebApp
    # Получаем актуальный домен Replit
    replit_domain = os.environ.get("REPLIT_DOMAINS", "").split(",")[0]
    if not replit_domain:
        # Резервный URL, если REPLIT_DOMAINS отсутствует
        replit_domain = "gold-fish-bot.replit.app"
        
    # Создаем URL для Telegram mini-app
    webapp_url = f"https://{replit_domain}/mini_app"
    
    # Добавляем только кнопку "Оформить заказ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Оформить заказ", web_app={"url": webapp_url})]
    ])

def size_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Маленькая")],
            [types.KeyboardButton(text="Средняя")],
            [types.KeyboardButton(text="Крупная")],
            [types.KeyboardButton(text="❌ Отмена"),
             types.KeyboardButton(text="✅ Подтвердить заказ")]
        ],
        resize_keyboard=True
    )

def promo_keyboard():
    button_text = NO_PROMO_BUTTON_TEXT if 'NO_PROMO_BUTTON_TEXT' in globals() else "Нет промокода"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, callback_data="no_promo")]
    ])

def phone_unchanged_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Не изменился", callback_data="phone_not_changed")]
    ])

def recovery_keyboard():
    continue_btn_text = ORDER_RECOVERY_BTN if 'ORDER_RECOVERY_BTN' in globals() else "Продолжить заказ"
    new_btn_text = ORDER_START_NEW_BTN if 'ORDER_START_NEW_BTN' in globals() else "Начать новый заказ"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=continue_btn_text, callback_data="continue_order")],
        [InlineKeyboardButton(text=new_btn_text, callback_data="new_order")]
    ])

# ==================== ОСНОВНОЙ КОД ====================
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command("admin"))
async def admin_panel_access(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к админ-панели.")
        return
    
    # Формируем URL с доменом Replit
    base_url = os.environ.get("REPLIT_DOMAINS", "")
    if base_url:
        base_url = f"https://{base_url}"
    else:
        base_url = "https://6111cce6-da00-4d3f-9152-89fd7833c233-00-115ombxz6wayd.pike.replit.dev"
    
    # Создаем ссылку с автоматическим входом для администратора
    admin_url = f"{base_url}/login?auto_login=true&admin_key={os.environ.get('ADMIN_KEY', 'admin_access_secret')}"
    
    # Создаем инлайн-клавиатуру с кнопкой-ссылкой на админ-панель
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 Войти в админ-панель", url=admin_url)]
    ])
    
    await message.answer(
        "Панель администратора доступна по кнопке ниже.\n"
        "В ней вы можете:\n"
        "• Просматривать и управлять заказами\n"
        "• Работать с лидами (незавершенными заказами)\n"
        "• Экспортировать данные в Excel\n"
        "• Настраивать интеграцию с Notion",
        reply_markup=keyboard
    )

@dp.message(Command("start"))
async def main_page(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверка незавершенного заказа
    incomplete_lead = get_lead_data(user_id)
    
    # Отправка приветственного сообщения
    cursor = db_execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    order_count = cursor.fetchone()[0]
    
    await message.answer_photo(
        WELCOME_IMAGE_ID, 
        caption=WELCOME_TEXT,
        reply_markup=main_menu_keyboard()
    )
    
    # Больше не отправляем книгу пользователям
    
    # Больше не предлагаем продолжить незавершенный заказ - заказы только через приложение

@dp.callback_query(lambda c: c.data == "continue_order")
async def process_continue_order(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    
    # Получаем данные незавершенного заказа
    incomplete_lead = get_lead_data(user_id)
    
    if not incomplete_lead:
        await callback_query.answer("Заказ устарел или был завершен")
        await callback_query.message.edit_text(
            "Незавершенный заказ не найден. Начните новый заказ.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Восстанавливаем данные и состояние
    lead_stage = incomplete_lead["stage"]
    lead_data = incomplete_lead["data"]
    
    # Загружаем данные в состояние
    await state.update_data(lead_data)
    
    # Определяем, на каком этапе продолжить
    if lead_stage == "OrderState:waiting_name":
        await state.set_state(OrderState.waiting_name)
        await callback_query.message.answer(ASK_NAME_TEXT)
    elif lead_stage == "OrderState:waiting_size":
        await state.set_state(OrderState.waiting_size)
        await callback_query.message.answer(SIZE_PROMPT_TEXT, reply_markup=size_keyboard())
    elif lead_stage == "OrderState:waiting_promo":
        await state.set_state(OrderState.waiting_promo)
        await callback_query.message.answer(PROMO_PROMPT_TEXT, reply_markup=promo_keyboard())
    elif lead_stage == "OrderState:waiting_phone":
        await state.set_state(OrderState.waiting_phone)
        # Получаем имя из данных лида
        full_name = lead_data.get("full_name", "")
        is_repeat = get_user_info(user_id) is not None
        phone_prompt_suffix = " (вдруг изменился)" if is_repeat else ""
        await callback_query.message.answer(
            PHONE_PROMPT_TEXT.format(full_name, phone_prompt_suffix),
            reply_markup=phone_unchanged_keyboard() if is_repeat else None
        )
    elif lead_stage == "OrderState:waiting_callback_time":
        await state.set_state(OrderState.waiting_callback_time)
        await callback_query.message.answer(CALLBACK_PROMPT_TEXT)
    else:
        # Если состояние неизвестно, начинаем заново
        await state.clear()
        await callback_query.message.answer(
            "Невозможно восстановить заказ. Пожалуйста, начните новый.",
            reply_markup=main_menu_keyboard()
        )
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "new_order")
async def process_new_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Очищаем предыдущее состояние и помечаем лид как истекший
    user_id = callback_query.from_user.id
    db_execute(
        "UPDATE leads SET expired = 1 WHERE user_id = ? AND is_completed = 0 AND expired = 0", 
        (user_id,)
    )
    
    await state.clear()
    await callback_query.answer()
    await process_make_order(callback_query, state)

@dp.callback_query(lambda c: c.data == "make_order")
async def process_make_order(callback_query: types.CallbackQuery, state: FSMContext):
    # Инициализируем корзину
    await state.update_data(cart=[])
    
    # Проверяем предыдущие заказы
    user_id = callback_query.from_user.id
    user_info = get_user_info(user_id)
    
    await state.set_state(OrderState.waiting_name)
    
    # Если это повторный заказ, предлагаем использовать старое имя
    if user_info and user_info.get("full_name"):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Использовать {user_info['full_name']}", callback_data="use_previous_name")]
        ])
        await callback_query.message.answer(ASK_NAME_TEXT, reply_markup=keyboard)
    else:
        await callback_query.message.answer(ASK_NAME_TEXT)
    
    # Записываем лид
    update_lead(user_id, {}, "OrderState:waiting_name")
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "use_previous_name")
async def use_previous_name(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    user_info = get_user_info(user_id)
    
    if user_info and user_info.get("full_name"):
        # Используем предыдущее имя
        await state.update_data(full_name=user_info["full_name"])
        
        # Переходим к следующему шагу
        await state.set_state(OrderState.waiting_size)
        
        # Обновляем лид
        state_data = await state.get_data()
        update_lead(user_id, state_data, "OrderState:waiting_size")
        
        await callback_query.message.answer(SIZE_PROMPT_TEXT, reply_markup=size_keyboard())
    else:
        await callback_query.message.answer(ASK_NAME_TEXT)
    
    await callback_query.answer()

@dp.message(OrderState.waiting_name)
async def process_name(message: types.Message, state: FSMContext):
    # Сохраняем имя
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    
    # Обновляем лид
    user_id = message.from_user.id
    state_data = await state.get_data()
    update_lead(user_id, state_data, "OrderState:waiting_size")
    
    # Переходим к выбору размера
    await state.set_state(OrderState.waiting_size)
    await message.answer(SIZE_PROMPT_TEXT, reply_markup=size_keyboard())

@dp.message(OrderState.waiting_size)
async def process_size(message: types.Message, state: FSMContext):
    text = message.text.lower()
    
    # Получаем текущее состояние корзины
    state_data = await state.get_data()
    cart = state_data.get("cart", [])
    
    if text == "❌ отмена":
        # Если отмена, очищаем состояние
        await state.clear()
        await message.answer("Заказ отменен.", reply_markup=ReplyKeyboardRemove())
        await main_page(message, state)
        return
    
    if text == "✅ подтвердить заказ":
        if not cart:
            await message.answer("Корзина пуста. Выберите хотя бы один размер рыбы.")
            return
        
        # Переходим к вводу промокода
        await state.set_state(OrderState.waiting_promo)
        
        # Обновляем лид
        user_id = message.from_user.id
        state_data = await state.get_data()
        update_lead(user_id, state_data, "OrderState:waiting_promo")
        
        await message.answer(
            f"{CART_HEADER_TEXT}\n" + "\n".join([f"- {item}" for item in cart]),
            reply_markup=ReplyKeyboardRemove()
        )
        await message.answer(PROMO_PROMPT_TEXT, reply_markup=promo_keyboard())
        return
    
    # Проверяем размер рыбы
    if text in ["маленькая", "средняя", "крупная"]:
        # Добавляем размер в корзину
        cart.append(text.capitalize())
        await state.update_data(cart=cart)
        
        # Обновляем лид
        user_id = message.from_user.id
        state_data = await state.get_data()
        update_lead(user_id, state_data, "OrderState:waiting_size")
        
        await message.answer(f"Добавлено: {text.capitalize()}\nВыберите еще размер или подтвердите заказ.")
    else:
        await message.answer("Пожалуйста, выберите один из предложенных вариантов размера рыбы.")

@dp.callback_query(lambda c: c.data == "no_promo")
async def no_promo(callback_query: types.CallbackQuery, state: FSMContext):
    await state.update_data(promo_code="")
    
    # Переходим к вводу телефона
    await process_promo_code(callback_query.message, state)
    await callback_query.answer()

@dp.message(OrderState.waiting_promo)
async def process_promo(message: types.Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    
    # Проверяем валидность промокода - теперь используем точное совпадение с "РЫБА2025" и "ЗОЛОТО"
    valid_promos = ["РЫБА2025", "ЗОЛОТО"]
    if promo_code and promo_code not in valid_promos:
        await message.answer("Промокод недействителен. Пожалуйста, введите корректный промокод или нажмите 'Нет промокода'.", 
                            reply_markup=promo_keyboard())
        return
    
    # Сохраняем промокод
    await state.update_data(promo_code=promo_code)
    
    # Если промокод применен, сообщаем о размере скидки
    if promo_code == "РЫБА2025":
        await message.answer("✅ Промокод 'РЫБА2025' успешно применен! Скидка 10%")
    elif promo_code == "ЗОЛОТО":
        await message.answer("✅ Промокод 'ЗОЛОТО' успешно применен! Скидка 20%") 
    
    # Обновляем лид
    user_id = message.from_user.id
    state_data = await state.get_data()
    update_lead(user_id, state_data, "OrderState:waiting_phone")
    
    # Переходим к вводу телефона
    await process_promo_code(message, state)

async def process_promo_code(message: types.Message, state: FSMContext):
    # Переходим к вводу телефона
    await state.set_state(OrderState.waiting_phone)
    
    # Получаем данные формы
    state_data = await state.get_data()
    full_name = state_data.get("full_name", "")
    
    # Проверяем, есть ли у пользователя предыдущие заказы
    user_id = message.chat.id if hasattr(message, 'chat') else message.from_user.id
    user_info = get_user_info(user_id)
    is_repeat = user_info is not None
    
    # Формируем сообщение и клавиатуру
    phone_prompt_suffix = " (вдруг изменился)" if is_repeat else ""
    
    await message.answer(
        PHONE_PROMPT_TEXT.format(full_name, phone_prompt_suffix),
        reply_markup=phone_unchanged_keyboard() if is_repeat else None
    )

@dp.callback_query(lambda c: c.data == "phone_not_changed")
async def phone_not_changed(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    user_info = get_user_info(user_id)
    
    if user_info and user_info.get("phone"):
        # Используем предыдущий номер телефона
        await state.update_data(phone=user_info["phone"])
        
        # Проверяем рабочее время
        if is_working_time():
            # Оформляем заказ
            await complete_order(callback_query.message, state)
        else:
            # Запрашиваем время для обратного звонка
            await state.set_state(OrderState.waiting_callback_time)
            
            # Обновляем лид
            state_data = await state.get_data()
            update_lead(user_id, state_data, "OrderState:waiting_callback_time")
            
            await callback_query.message.answer(CALLBACK_PROMPT_TEXT)
    else:
        await callback_query.message.answer("Не удалось найти ваш предыдущий номер телефона. Пожалуйста, введите его.")
    
    await callback_query.answer()

@dp.message(OrderState.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    
    # Проверяем формат телефона (простая проверка)
    if not phone.replace("+", "").replace(" ", "").isdigit():
        await message.answer("Пожалуйста, введите корректный номер телефона.")
        return
    
    # Сохраняем телефон
    await state.update_data(phone=phone)
    
    # Обновляем лид
    user_id = message.from_user.id
    state_data = await state.get_data()
    update_lead(user_id, state_data, "OrderState:waiting_callback_time" if not is_working_time() else "completed")
    
    # Проверяем рабочее время
    if is_working_time():
        # Оформляем заказ
        await complete_order(message, state)
    else:
        # Запрашиваем время для обратного звонка
        await state.set_state(OrderState.waiting_callback_time)
        await message.answer(CALLBACK_PROMPT_TEXT)

@dp.message(OrderState.waiting_callback_time)
async def process_callback_time(message: types.Message, state: FSMContext):
    time_text = message.text.strip()
    
    try:
        # Пытаемся преобразовать введенное время в числовой формат
        callback_time = int(time_text)
        
        # Проверяем, что время в допустимом диапазоне
        if callback_time < 8 or callback_time > 17:
            await message.answer("Пожалуйста, укажите время с 8 до 17 часов.")
            return
        
        # Сохраняем время для обратного звонка
        await state.update_data(callback_time=callback_time)
        
        # Завершаем оформление заказа
        await complete_order(message, state)
    except ValueError:
        await message.answer("Пожалуйста, введите только число (час для звонка).")

async def complete_order(message: types.Message, state: FSMContext):
    try:
        # Получаем данные из состояния
        state_data = await state.get_data()
        user_id = message.chat.id if hasattr(message, 'chat') else message.from_user.id
        full_name = state_data.get("full_name", "")
        cart = state_data.get("cart", [])
        phone = state_data.get("phone", "")
        promo_code = state_data.get("promo_code", "")
        callback_time = state_data.get("callback_time")
        
        # Подсчитываем итоговую сумму
        total_sum = sum(PRICES.get(item.lower(), 0) for item in cart)
        
        # Применяем оптовую скидку (если количество товаров >= 4)
        if len(cart) >= 4:
            wholesale_discount = 0.9  # 10% скидка
            total_sum *= wholesale_discount
            logging.info(f"Applied wholesale discount for user {user_id}: {len(cart)} items")
        
        # Применяем скидку, если есть промокод
        if promo_code == PROMO_CODE:
            total_sum *= DISCOUNT
            used_promo_users[user_id] = PROMO_CODE
            logging.info(f"Applied promo code {PROMO_CODE} for user {user_id}")
        elif promo_code == GOLD_PROMO:
            total_sum *= GOLD_DISCOUNT
            used_promo_users[user_id] = GOLD_PROMO
            logging.info(f"Applied promo code {GOLD_PROMO} for user {user_id}")
        
        # Создаем запись в БД
        cursor = db_execute(
            "INSERT INTO orders (user_id, full_name, items, total, promo_used, phone, callback_time, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, full_name, json.dumps(cart), total_sum, promo_code, phone, callback_time, datetime.now())
        )
        order_id = cursor.lastrowid
        
        # Обновляем лид как завершенный и привязываем к заказу
        update_lead(user_id, state_data, "completed", True, order_id)
        
        # Отслеживаем статус
        track_order_status(order_id, "Новый")
        
        # Notion интеграция удалена
        
        # Отправляем уведомление администраторам о новом заказе
        # Создаем короткое сообщение с описанием заказа
        cart_summary = ", ".join([f"{item}" for item in cart])
        admin_notification = (
            f"🆕 Новый заказ #{order_id}!\n"
            f"Заказ: {cart_summary}\n"
            f"Номер телефона: {phone}\n"
            f"Клиент: {full_name}"
        )
        
        # Отправляем уведомление всем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_notification)
                logging.info(f"Admin notification sent to {admin_id} for order #{order_id}")
            except Exception as e:
                logging.error(f"Failed to send admin notification to {admin_id}: {e}")
        
        # Отправляем сообщение пользователю
        await message.answer(ORDER_SUCCESS_TEXT)
        
        # Очищаем состояние
        await state.clear()
        
        # Предлагаем оставить отзыв
        # await message.answer(
        #     ORDER_CONFIRMATION_PROMPT,
        #     reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        #         [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data=f"feedback_{order_id}")]
        #     ])
        # )
        
        logging.info(f"Order {order_id} created successfully for user {user_id}")
        
        return order_id
    except Exception as e:
        logging.error(f"Error completing order: {e}")
        await message.answer("Произошла ошибка при оформлении заказа. Пожалуйста, попробуйте позже.")
        await state.clear()
        return None

# Функция sync_notion_data удалена из-за отказа от Notion интеграции

@dp.callback_query(lambda c: c.data == "history")
async def show_history(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        # Показываем историю заказов пользователя
        cursor = db_execute(
            "SELECT id, items, total, timestamp, status FROM orders WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
            (user_id,)
        )
        
        orders = cursor.fetchall()
        
        if not orders:
            await callback_query.message.answer(NO_HISTORY_TEXT)
            await callback_query.answer()
            return
            
        history_text = "📜 Ваша история заказов:\n\n"
        
        for order in orders:
            order_id, items_json, total, timestamp, status = order
            items = json.loads(items_json) if items_json else []
            order_date = timestamp.strftime("%d.%m.%Y %H:%M")
            
            history_text += f"Заказ #{order_id} от {order_date}\n"
            history_text += f"Статус: {status}\n"
            history_text += "Состав:\n"
            
            for item in items:
                history_text += f"- {item}\n"
                
            history_text += f"Сумма: {total} ₽\n\n"
            
        await callback_query.message.answer(history_text)
    else:
        # Для админа показываем последние 20 заказов
        cursor = db_execute(
            "SELECT orders.id, orders.user_id, orders.full_name, orders.items, orders.total, orders.timestamp, "
            "orders.status, orders.notion_page_id FROM orders ORDER BY timestamp DESC LIMIT 20"
        )
        
        orders = cursor.fetchall()
        
        if not orders:
            await callback_query.message.answer(NO_HISTORY_TEXT)
            await callback_query.answer()
            return
            
        # Создаем DataFrame для экспорта
        df = pd.DataFrame(
            orders, 
            columns=["ID", "User ID", "Name", "Items", "Total", "Date", "Status", "Notion ID"]
        )
        
        # Преобразуем JSON-строки элементов в списки
        df["Items"] = df["Items"].apply(lambda x: ", ".join(json.loads(x)) if x else "")
        
        # Форматируем даты
        df["Date"] = df["Date"].apply(lambda x: x.strftime("%d.%m.%Y %H:%M") if x else "")
        
        # Сохраняем во временный файл
        df.to_excel("orders_history.xlsx", index=False)
        
        # Отправляем файл
        with open("orders_history.xlsx", "rb") as file:
            await callback_query.message.answer_document(
                types.BufferedInputFile(
                    file.read(),
                    filename="orders_history.xlsx"
                ),
                caption="📊 История заказов"
            )
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == "delete_order")
async def delete_order_request(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await callback_query.answer("У вас нет доступа к этой функции")
        return
        
    await state.set_state(DeleteOrderState.waiting_order_id)
    await callback_query.message.answer("Введите ID заказа для удаления:")
    await callback_query.answer()

@dp.message(DeleteOrderState.waiting_order_id)
async def delete_order(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой функции")
        await state.clear()
        return
        
    try:
        order_id = int(message.text.strip())
        
        # Проверяем существование заказа
        cursor = db_execute("SELECT id FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        
        if not order:
            await message.answer(DELETE_ORDER_FAILURE_TEXT)
        else:
            # Удаляем запись из базы
            db_execute("DELETE FROM orders WHERE id = ?", (order_id,))
            db_execute("DELETE FROM order_statuses WHERE order_id = ?", (order_id,))
            
            await message.answer(DELETE_ORDER_SUCCESS_TEXT)
            
        # Очищаем состояние
        await state.clear()
        
        # Возвращаем к главной странице
        await message.answer("Операция выполнена успешно!")
        await main_page(message, FSMContext(MemoryStorage(), message.chat.id, dp))
    except ValueError:
        await message.answer("Пожалуйста, введите числовой ID заказа.")

@dp.callback_query(lambda c: c.data == "broadcast")
async def broadcast_request(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await callback_query.answer("У вас нет доступа к этой функции")
        return
        
    await state.set_state(BroadcastState.waiting_message)
    await callback_query.message.answer("Введите сообщение для рассылки всем пользователям:")
    await callback_query.answer()

@dp.message(BroadcastState.waiting_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой функции")
        await state.clear()
        return
        
    broadcast_text = message.text
    
    # Получаем уникальных пользователей из базы данных
    cursor = db_execute("SELECT DISTINCT user_id FROM orders")
    users = cursor.fetchall()
    
    total_count = len(users)
    success_count = 0
    error_count = 0
    
    await message.answer(f"Начинаю рассылку {total_count} пользователям...")
    
    for user in users:
        recipient_id = user[0]
        try:
            await bot.send_message(recipient_id, broadcast_text)
            success_count += 1
        except Exception as e:
            logging.error(f"Failed to send broadcast to user {recipient_id}: {e}")
            error_count += 1
    
    await message.answer(f"✅ Рассылка завершена!\n📊 Статистика:\n✓ Успешно: {success_count}\n✗ Ошибок: {error_count}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "complaints")
async def complaint_request(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(ComplaintState.waiting_text)
    await callback_query.message.answer(COMPLAINT_PROMPT_TEXT)
    await callback_query.answer()

@dp.message(ComplaintState.waiting_text)
async def process_complaint(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    complaint_text = message.text
    
    # Отправляем жалобу администраторам
    admin_message = ADMIN_COMPLAINT_TEMPLATE.format(full_name, complaint_text)
    
    for admin_id in ADMIN_IDS:
        try:
            # Если есть фото, пересылаем его
            if message.photo:
                await bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=admin_message
                )
            else:
                await bot.send_message(admin_id, admin_message)
        except Exception as e:
            logging.error(f"Failed to send complaint to admin {admin_id}: {e}")
    
    # Благодарим пользователя
    await message.answer(COMPLAINT_THANKS_TEXT)
    
    # Очищаем состояние
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("feedback_"))
async def feedback_request(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = int(callback_query.data.split("_")[1])
    await state.update_data(order_id=order_id)
    await state.set_state(FeedbackState.waiting_text)
    await callback_query.message.answer(FEEDBACK_PROMPT_TEXT)
    await callback_query.answer()

@dp.message(FeedbackState.waiting_text)
async def process_feedback(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    order_id = state_data.get("order_id")
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    feedback_text = message.text
    
    # Благодарим пользователя
    await message.answer(FEEDBACK_THANKS_TEXT)
    
    # Формируем сообщение для администраторов
    admin_message = ADMIN_FEEDBACK_TEMPLATE.format(full_name, feedback_text)
    if order_id:
        admin_message += f"\n\nОтзыв на заказ #{order_id}"
    
    # Отправляем отзыв администраторам
    for admin_id in ADMIN_IDS:
        try:
            # Если есть фото, пересылаем его
            if message.photo:
                await bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=admin_message
                )
            else:
                await bot.send_message(admin_id, admin_message)
        except Exception as e:
            logging.error(f"Failed to send feedback to admin {admin_id}: {e}")
    
    # Очищаем состояние
    await state.clear()
    
    # Предлагаем оформить новый заказ
    await message.answer(
        NEW_ORDER_PROMPT,
        reply_markup=main_menu_keyboard()
    )

@dp.message(Command("backup"))
async def send_backup(message: types.Message):
    """Отправляет резервную копию базы данных администратору."""
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав на выполнение этой команды.")
        return
    
    try:
        # Отправляем базу данных
        with open('bot.db', 'rb') as file:
            await bot.send_document(
                user_id, 
                types.BufferedInputFile(
                    file.read(),
                    filename="bot_backup.db"
                ),
                caption="📦 Резервная копия базы данных"
            )
        await message.answer("✅ Резервная копия базы данных отправлена.")
    except Exception as e:
        logging.error(f"Failed to send DB backup: {e}")
        await message.answer(f"❌ Ошибка при отправке резервной копии: {e}")

@dp.message(Command("archive"))
async def archive_files(message: types.Message):
    """Создает архив всех файлов бота и отправляет администратору."""
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав на выполнение этой команды.")
        return
    
    # Отправляем сообщение о начале архивации
    progress_message = await message.answer("⏳ Создаю архив файлов бота...")
    
    try:
        import shutil
        import os
        from datetime import datetime
        
        # Получаем текущий путь скрипта
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Создаем временную директорию для архивации
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        archive_dir = os.path.join(current_dir, "export_files")
        archive_name = f"bot_files_{timestamp}"
        archive_path = os.path.join(archive_dir, f"{archive_name}.zip")
        readme_path = os.path.join(archive_dir, "README.md")
        
        # Создаем директорию, если она не существует
        os.makedirs(archive_dir, exist_ok=True)
        
        # Создаем README.md файл с описанием проекта
        with open(readme_path, 'w', encoding='utf-8') as readme:
            readme.write("""# Telegram бот "Золотая рыбка" 🐟

## Общее описание

Это Telegram-бот для автоматизации приема заказов рыбы с полной интеграцией с Notion CRM. Бот работает на Python с использованием библиотеки aiogram и предлагает пользователям заказывать рыбу разных размеров через Telegram Mini App (WebApp).

## Структура проекта

### Основные файлы

- **botf.py** - Основной файл бота с логикой обработки команд, коллбэков и WebApp данных
- **run.py** - Скрипт для запуска бота, управления процессами и автоматического перезапуска
- **sync_service.py** - Сервис для синхронизации данных между ботом и Notion CRM
- **notion_integration.py** - Интеграция с Notion API для управления заказами и лидами
- **main.py** - Flask веб-сервер для административного интерфейса и WebApp
- **static/** - Статические файлы (CSS, JavaScript, изображения)
  - **webapp/** - Файлы для Telegram Mini App (WebApp)
- **templates/** - HTML шаблоны для административного интерфейса
- **bot.db** - SQLite база данных для хранения заказов, лидов и других данных

### База данных

В проекте используется SQLite с тремя основными таблицами:
- **orders** - Данные о заказах
- **leads** - Данные о незавершенных заказах (лидах)
- **order_statuses** - Отслеживание статусов заказов

## Необходимые библиотеки Python

Для корректной работы проекта необходимы следующие библиотеки:

```
aiogram==3.0.0 или выше
flask==2.0.0 или выше
flask-login==0.6.0 или выше
flask-session==0.5.0 или выше
flask-sqlalchemy==3.0.0 или выше
flask-wtf==1.1.0 или выше
gunicorn==23.0.0 или выше
pandas==2.0.0 или выше
psutil==5.9.0 или выше
psycopg2-binary==2.9.0 или выше 
pytz==2022.0 или выше
requests==2.28.0 или выше
# watchdog удалён для совместимости с Windows
werkzeug==2.3.0 или выше
email-validator==2.0.0 или выше
```

Установка библиотек:
```bash
pip install -r requirements.txt
```

Содержимое файла requirements.txt:
```
aiogram>=3.0.0
flask>=2.0.0
flask-login>=0.6.0
flask-session>=0.5.0
flask-sqlalchemy>=3.0.0
flask-wtf>=1.1.0
gunicorn>=23.0.0
pandas>=2.0.0
psutil>=5.9.0
psycopg2-binary>=2.9.0
pytz>=2022.0
requests>=2.28.0
# watchdog удалён для совместимости с Windows
werkzeug>=2.3.0
email-validator>=2.0.0
```

## Основные функции бота

1. **Оформление заказов через WebApp**
   - Выбор размеров рыбы (маленькая, средняя, крупная)
   - Указание количества каждого размера
   - Применение промокодов (РЫБА2025: 10%, ЗОЛОТО: 20%)
   - Автоматическая оптовая скидка (10% при заказе 4+ рыб)

2. **Управление лидами**
   - Сохранение незавершенных заказов на 15 минут
   - Возможность восстановления оформления заказа

3. **Интеграция с Notion**
   - Автоматическая синхронизация заказов и лидов
   - Отслеживание изменений статусов заказов в реальном времени
   - Экспорт данных из Notion в Excel

4. **Административные функции**
   - Команда /backup - создание резервной копии базы данных
   - Команда /archive - архивация всех файлов проекта
   - Команда /file - экспорт заказов в Excel
   - Команда /post - рассылка сообщений всем пользователям

5. **Система уведомлений**
   - Автоматические уведомления пользователей об изменении статуса заказа
   - Уведомления администраторов о новых заказах

## Технические аспекты

### Промокоды и скидки
- РЫБА2025 - скидка 10% для всех пользователей
- ЗОЛОТО - скидка 20% для постоянных клиентов (от 3 заказов)
- Оптовая скидка 10% при заказе 4+ рыб (применяется автоматически)

### Настройка времени
- Рабочее время: с 8:00 до 18:00 по Иркутскому времени (UTC+8)
- Вне рабочего времени бот запрашивает удобное время для звонка

### Особенности WebApp
- Одностраничное приложение на чистом JavaScript
- Корзина с возможностью изменения количества товаров
- Автоматический расчет скидок

## Инструкции по внесению изменений

### Изменение промокодов
Промокоды и скидки настраиваются в начале файла botf.py:
```python
PROMO_CODE = "РЫБА2025"    # Стандартный промокод (10% скидка)
GOLD_PROMO = "ЗОЛОТО"      # Золотой промокод (20% скидка)
DISCOUNT = 0.9             # Коэффициент скидки для стандартного промокода (90% от цены)
GOLD_DISCOUNT = 0.8        # Коэффициент скидки для золотого промокода (80% от цены)
```

### Изменение цен
Цены на рыбу разного размера настраиваются в словаре PRICES:
```python
PRICES = {
    "маленькая": 450,
    "средняя": 600,
    "крупная": 750
}
```

### Добавление администраторов
ID администраторов указываются в списке ADMIN_IDS в начале файла botf.py.

## Требования и зависимости

- Python 3.10+
- aiogram - для работы Telegram бота
- Flask - для административного интерфейса
- Pandas - для работы с данными и экспорта в Excel
- SQLite - для хранения данных
- Тег html для Telegram WebApp

Созданно: ${timestamp}
""")
        
        # Список файлов для архивации (Python файлы, Telegram WebApp, шаблоны и т.д.)
        files_to_archive = [
            "botf.py", 
            "main.py", 
            "run.py", 
            "sync_service.py",
            "bot.db",
            "INSTALLATION.md"
        ]
        
        # Добавляем директории
        directories_to_archive = [
            "static",
            "templates"
        ]
        
        # Создаем файл requirements.txt для простой установки зависимостей
        requirements_path = f"{archive_dir}/requirements.txt"
        if not os.path.exists(requirements_path):
            with open(requirements_path, 'w', encoding='utf-8') as req_file:
                req_file.write("""aiogram>=3.0.0
flask>=2.0.0
flask-login>=0.6.0
flask-session>=0.5.0
flask-sqlalchemy>=3.0.0
flask-wtf>=1.1.0
gunicorn>=23.0.0
pandas>=2.0.0
psutil>=5.9.0
psycopg2-binary>=2.9.0
pytz>=2022.0
requests>=2.28.0
# watchdog удалён для совместимости с Windows
werkzeug>=2.3.0
email-validator>=2.0.0
openpyxl>=3.1.0
""")
                
        # Создаем архив
        with zipfile.ZipFile(archive_path, 'w') as zipf:
            # Архивируем файлы
            for file in files_to_archive:
                if os.path.exists(file):
                    zipf.write(file)
                    logging.info(f"Added {file} to archive")
                else:
                    logging.warning(f"File {file} not found, skipping")
            
            # Архивируем директории
            for directory in directories_to_archive:
                if os.path.exists(directory):
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            file_path = os.path.join(root, file)
                            zipf.write(file_path)
                            logging.info(f"Added {file_path} to archive")
                else:
                    logging.warning(f"Directory {directory} not found, skipping")
            
            # Добавляем README.md в архив
            zipf.write(readme_path, "README.md")
            logging.info("Added README.md to archive")
            
            # Добавляем requirements.txt в архив
            zipf.write(requirements_path, "requirements.txt")
            logging.info("Added requirements.txt to archive")
        
        # Отправляем архив
        with open(archive_path, 'rb') as file:
            await bot.send_document(
                user_id, 
                types.BufferedInputFile(
                    file.read(),
                    filename=f"{archive_name}.zip"
                ),
                caption="📦 Архив файлов бота с полной документацией для нейросетей (README.md и requirements.txt со списком библиотек для установки)"
            )
        
        # Отправляем отдельно README.md для удобства
        with open(readme_path, 'rb') as file:
            await bot.send_document(
                user_id, 
                types.BufferedInputFile(
                    file.read(),
                    filename="README.md"
                ),
                caption="📝 Документация по функционалу бота для нейросети"
            )
            
        # Отправляем отдельно INSTALLATION.md для удобства
        if os.path.exists("INSTALLATION.md"):
            with open("INSTALLATION.md", 'rb') as file:
                await bot.send_document(
                    user_id, 
                    types.BufferedInputFile(
                        file.read(),
                        filename="INSTALLATION.md"
                    ),
                    caption="🔧 Инструкция по установке и настройке бота"
                )
        
        await progress_message.edit_text("✅ Архив файлов бота и документация успешно отправлены.")
        
    except Exception as e:
        logging.error(f"Failed to create archive: {e}", exc_info=True)
        await progress_message.edit_text(f"❌ Ошибка при создании архива: {e}")

@dp.message(Command("file"))
async def export_orders_to_excel(message: types.Message):
    """Экспортирует заказы из базы данных в файл Excel."""
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав на выполнение этой команды.")
        return
    
    # Отправляем сообщение о начале экспорта
    progress_message = await message.answer("⏳ Начинаю экспорт данных из базы данных...")
    
    try:
        # Получаем данные из базы данных
        cursor = db_execute(
            "SELECT id, user_id, full_name, phone, items, total, timestamp, status FROM orders ORDER BY timestamp DESC"
        )
        orders = cursor.fetchall()
        
        if not orders:
            await progress_message.edit_text("❌ В базе данных нет заказов.")
            return
        
        # Создаем DataFrame
        import pandas as pd
        df = pd.DataFrame(
            orders, 
            columns=["ID", "User ID", "Name", "Phone", "Items", "Total", "Date", "Status"]
        )
        
        # Преобразуем JSON-строки элементов в списки
        df["Items"] = df["Items"].apply(lambda x: ", ".join(json.loads(x)) if x else "")
        
        # Форматируем даты
        df["Date"] = df["Date"].apply(lambda x: x.strftime("%d.%m.%Y %H:%M") if x else "")
        
        # Создаем имя файла с текущей датой
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = f"orders_{timestamp}.xlsx"
        
        # Сохраняем DataFrame в Excel файл
        df.to_excel(file_name, index=False)
        
        # Отправляем файл пользователю
        with open(file_name, 'rb') as file:
            await message.answer_document(
                types.BufferedInputFile(
                    file.read(), 
                    filename=file_name
                ),
                caption=f"📊 Экспорт заказов по состоянию на {timestamp}"
            )
        
        # Удаляем временный файл
        import os
        os.remove(file_name)
        
        await progress_message.delete()
        
    except Exception as e:
        logging.error(f"Error exporting orders to Excel: {e}")
        await progress_message.edit_text(f"❌ Произошла ошибка при экспорте данных: {str(e)}")

@dp.message(Command("post"))
async def start_broadcast(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id in ADMIN_IDS:
        # Переходим в состояние ожидания текста рассылки
        await state.set_state(BroadcastState.waiting_message)
        await message.answer("✏️ Введите текст для рассылки всем пользователям:")
    else:
        # Для обычных пользователей показываем обычное меню
        await message.answer("⛔ У вас нет доступа к этой команде.")

# Обработчик для непредвиденных исключений
@dp.error()
async def error_handler(update, exception):
    logging.error(f"Unhandled exception: {exception}")
    
    # Пытаемся получить информацию о пользователе
    user_id = None
    if hasattr(update, 'from_user'):
        user_id = update.from_user.id
    elif hasattr(update, 'message') and hasattr(update.message, 'from_user'):
        user_id = update.message.from_user.id
    
    # Если удалось определить пользователя, отправляем ему сообщение об ошибке
    if user_id:
        try:
            await bot.send_message(
                user_id,
                "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже или обратитесь в поддержку."
            )
        except Exception as e:
            logging.error(f"Failed to send error message: {e}")
    
    # Уведомляем администраторов об ошибке
    error_message = f"❌ Ошибка в боте:\n{exception}\n\nUpdate: {update}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, error_message)
        except Exception as e:
            logging.error(f"Failed to notify admin {admin_id} about error: {e}")

# Инициализируем задачи по расписанию
async def scheduled_tasks():
    while True:
        try:
            # Помечаем незавершенные лиды как истекшие
            expire_old_leads()
            
            # Notion интеграция удалена
            
            # Проверяем неудачные уведомления и пытаемся отправить их снова
            try:
                resent_count = await retry_failed_notifications(bot)
                if resent_count > 0:
                    logging.info(f"Successfully resent {resent_count} notifications")
            except Exception as e:
                logging.error(f"Failed to retry notifications: {e}")
            
            # Проверяем неотправленные уведомления об изменении статуса
            try:
                cursor = db_execute(
                    "SELECT order_statuses.id, order_statuses.order_id, order_statuses.status, orders.user_id "
                    "FROM order_statuses JOIN orders ON order_statuses.order_id = orders.id "
                    "WHERE order_statuses.notified = 0"
                )
                notifications = cursor.fetchall()
                
                for notification_id, order_id, status, user_id in notifications:
                    # Отправляем уведомление
                    message = STATUS_MESSAGES.get(status, f"Статус вашего заказа изменен на: {status}")
                    
                    try:
                        await bot.send_message(user_id, message)
                        logging.info(f"Sent notification for order {order_id}: '{message}'")
                        
                        # Отмечаем уведомление как отправленное
                        db_execute(
                            "UPDATE order_statuses SET notified = 1 WHERE id = ?",
                            (notification_id,)
                        )
                    except TelegramForbiddenError:
                        logging.warning(f"User {user_id} blocked the bot, marking notification as sent")
                        db_execute(
                            "UPDATE order_statuses SET notified = 1 WHERE id = ?",
                            (notification_id,)
                        )
                    except Exception as e:
                        logging.error(f"Failed to send notification to {user_id}: {e}")
            except Exception as e:
                logging.error(f"Failed to process notifications: {e}")
        
        except Exception as e:
            logging.error(f"Error in scheduled_tasks: {e}")
        
        # Выполняем проверки каждые 10 секунд
        await asyncio.sleep(10)

# Обработчик для получения данных из WebApp
@dp.message(lambda message: hasattr(message, 'web_app_data') and message.web_app_data.data)
async def handle_webapp_data(message: types.Message, state: FSMContext):
    """Обработчик данных из веб-приложения Telegram Mini App."""
    try:
        # Получаем данные от веб-приложения и преобразуем их из JSON
        data = json.loads(message.web_app_data.data)
        
        logging.info(f"Получены данные из WebApp: {data}")
        
        # ПОЛНОСТЬЮ НОВАЯ РЕАЛИЗАЦИЯ
        # Теперь просто отправляем подтверждение пользователю, без создания дублирующих записей
        # Все создание заказов происходит только в Flask приложении
        
        # Активируем лид для пользователя (если имеется истекший)
        user_id = message.from_user.id
        # Проверяем наличие истекшего лида для данного пользователя
        cursor = db_execute(
            "SELECT id FROM leads WHERE user_id = ? AND expired = 1 ORDER BY timestamp DESC LIMIT 1", 
            (user_id,)
        )
        expired_lead = cursor.fetchone()
        
        if expired_lead:
            # Реактивируем лид
            lead_id = expired_lead[0]
            db_execute(
                "UPDATE leads SET timestamp = ?, expired = 0 WHERE id = ?",
                (datetime.now(), lead_id)
            )
            logging.info(f"Реактивирован истекший лид {lead_id} для пользователя {user_id} через WebApp")
        
        # Проверяем тип данных - ожидаем только уведомление об успешном заказе с телеграм приложения
        if 'action' in data and data.get('action') == 'order_completed':
            # Это уведомление о завершении заказа в mini_app
            order_id = data.get('orderId')
            
            if not order_id:
                await message.answer("❌ Ошибка: не указан ID заказа. Пожалуйста, свяжитесь с нами для уточнения деталей заказа.")
                return
            
            # Используем redis-подобный глобальный кеш для отслеживания уже обработанных уведомлений
            # (простая реализация без Redis для этого проекта)
            global _processed_notifications
            if not hasattr(sys.modules[__name__], '_processed_notifications'):
                _processed_notifications = {}
            
            # Создаем уникальный ключ для этого уведомления
            notification_key = f"{message.from_user.id}_{order_id}"
            
            # Если это уведомление уже было обработано, просто молча выходим
            if notification_key in _processed_notifications:
                logging.info(f"Пропущено повторное уведомление о заказе #{order_id} для пользователя {message.from_user.id}")
                return
            
            # Отправляем только подтверждение пользователю, что заказ был получен
            await message.answer(
                f"✅ Спасибо! Ваш заказ #{order_id} успешно оформлен!\n\n"
                "📱 Мы скоро свяжемся с вами для уточнения деталей."
            )
            
            # Отмечаем это уведомление как обработанное
            _processed_notifications[notification_key] = True
            
            # Через минуту можно очистить старые записи, чтобы не занимать память
            asyncio.create_task(_cleanup_old_notifications())
            
            logging.info(f"Отправлено подтверждение о заказе #{order_id} для пользователя {message.from_user.id}")
        else:
            # Для обратной совместимости
            logging.warning("Получены данные в нераспознанном формате")
            await message.answer(
                "❓ Произошла ошибка при обработке данных. Пожалуйста, попробуйте еще раз или свяжитесь с нами."
            )
    except json.JSONDecodeError:
        logging.error("Ошибка при декодировании JSON из WebApp")
        await message.answer("Ошибка при обработке данных. Пожалуйста, попробуйте снова.")
    except Exception as e:
        logging.error(f"Ошибка при обработке данных из WebApp: {e}")
        await message.answer("Произошла ошибка при обработке заказа. Пожалуйста, попробуйте позже или свяжитесь с нами напрямую.")
            
# Вспомогательная функция для очистки старых уведомлений
async def _cleanup_old_notifications():
    """Удаляет старые записи об обработанных уведомлениях через 60 секунд"""
    await asyncio.sleep(60)
    global _processed_notifications
    if hasattr(sys.modules[__name__], '_processed_notifications'):
        _processed_notifications.clear()

# Запуск бота
async def main():
    # Запускаем задачи по расписанию в отдельной таске
    asyncio.create_task(scheduled_tasks())
    
    logging.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен!")
