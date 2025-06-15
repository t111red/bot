#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import sqlite3
import functools
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
# from flask_wtf.csrf import CSRFProtect
import pandas as pd
import subprocess
import logging
import psutil
from werkzeug.utils import secure_filename

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Учетные данные администратора (из переменных среды или по умолчанию)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "password")

app = Flask(__name__)

# Настройки безопасности
app.config["WTF_CSRF_ENABLED"] = False  # Отключаем CSRF защиту
app.config["WTF_CSRF_SECRET_KEY"] = os.environ.get("CSRF_SECRET_KEY", "csrf_secret_key_for_forms")
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey123456789")  # Для сессий и flash сообщений
# Настройки сессии
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)  # 30 дней
app.config["SESSION_FILE_DIR"] = "./flask_session"
app.config["SESSION_USE_SIGNER"] = True

# Создаём директорию для сессий, если её нет
os.makedirs('flask_session', exist_ok=True)

# Инициализация Flask Session
Session(app)

# Отключаем CSRF Protection, так как она мешает входу
# csrf = CSRFProtect(app)

# Настраиваем директории для статических файлов
@app.before_request
def make_folders():
    os.makedirs('static/exports', exist_ok=True)
    os.makedirs('static/files', exist_ok=True)

# Конфигурация базы данных
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Маршрут для сервирования веб-приложения Telegram
@app.route("/webapp")
def webapp():
    return send_from_directory('static/webapp', 'index.html')

@app.route("/webapp/basic")
def webapp_basic():
    return send_from_directory('static/webapp', 'basic.html')

@app.route("/mini_app")
def mini_app():
    """Маршрут для интеграции с Telegram mini app"""
    return send_from_directory('static/webapp', 'basic.html')

@app.route("/mini_app/<path:path>")
def mini_app_static(path):
    """Маршрут для статических файлов в mini app"""
    return send_from_directory('static/webapp', path)

@app.route("/mini_app/process_order", methods=['POST', 'OPTIONS'])
@app.route("/api/process-order", methods=['POST', 'OPTIONS'])  # Добавляем второй маршрут для совместимости
def process_order():
    """Обработка заказов из Mini App (в стиле CRM Bitrix24)"""
    import json
    import sqlite3
    import uuid
    import time
    from datetime import datetime
    import traceback
    
    # Обработка OPTIONS запросов для CORS
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Telegram-Data,X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        app.logger.info(f"[MiniApp] Получен запрос на обработку заказа от {request.remote_addr}")
        app.logger.info(f"[MiniApp] Заголовки запроса: {dict(request.headers)}")
        app.logger.info(f"[MiniApp] Метод запроса: {request.method}")
        
        # Получаем данные заказа из JSON
        if not request.is_json:
            app.logger.error(f"[MiniApp] Неверный формат запроса, Content-Type: {request.content_type}")
            # Добавляем подробное логирование
            app.logger.error(f"[MiniApp] Запрос: {request.data}")
            return jsonify({"error": "Ожидается JSON формат данных", "success": False}), 400
            
        order_data = request.json
        if not order_data:
            app.logger.error("[MiniApp] Отсутствуют данные заказа в запросе")
            return jsonify({"error": "Отсутствуют данные заказа", "success": False}), 400
            
        app.logger.info(f"[MiniApp] Данные заказа: {json.dumps(order_data, ensure_ascii=False)}")
            
        # Проверка обязательных полей
        required_fields = ['name', 'phone', 'items']
        missing_fields = []
        for field in required_fields:
            if field not in order_data or not order_data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            app.logger.error(f"[MiniApp] Отсутствуют обязательные поля: {', '.join(missing_fields)}")
            return jsonify({
                "error": f"Отсутствуют обязательные поля: {', '.join(missing_fields)}", 
                "success": False,
                "missingFields": missing_fields
            }), 400
                
        # Генерируем уникальный ID заказа
        order_id = int(time.time() * 1000) % 10000000  # Более короткий и удобный ID заказа
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Преобразуем данные о товарах в строку JSON для хранения
        # Проверяем формат данных товаров и адаптируем их при необходимости
        items = order_data.get('items', [])
        if not items:
            app.logger.warning("[MiniApp] Пустой список товаров в заказе")
            items = []
            
        # Нормализуем структуру items для хранения
        if isinstance(items, list):
            # Для структуры MiniApp - список объектов с size и quantity
            normalized_items = []
            for item in items:
                if isinstance(item, dict):
                    normalized_item = {}
                    
                    # Получаем размер товара (обязательное поле)
                    size = item.get('size')
                    if size:
                        normalized_item['size'] = size
                    
                    # Получаем имя товара, или используем размер как имя
                    name = item.get('name')
                    if name:
                        normalized_item['name'] = name
                    elif size:
                        normalized_item['name'] = size
                    else:
                        normalized_item['name'] = 'Неизвестный товар'
                    
                    # Получаем количество товара
                    quantity = item.get('quantity', 1)
                    normalized_item['quantity'] = quantity
                    
                    # Получаем или вычисляем цену
                    price = item.get('price')
                    if price:
                        normalized_item['price'] = price
                    else:
                        # Устанавливаем цену в зависимости от размера
                        if size == 'Маленькая':
                            normalized_item['price'] = 500
                        elif size == 'Средняя':
                            normalized_item['price'] = 900
                        elif size == 'Крупная':
                            normalized_item['price'] = 1500
                        else:
                            normalized_item['price'] = 800
                    
                    normalized_items.append(normalized_item)
            
            # Заменяем исходный список нормализованным
            items = normalized_items
                            
        app.logger.info(f"[MiniApp] Нормализованный список товаров: {json.dumps(items, ensure_ascii=False)}")
        items_json = json.dumps(items, ensure_ascii=False)
        
        # Подключаемся к базе данных - исправлено для работы из любой директории
        current_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(current_dir, 'bot.db')
        app.logger.info(f"[MiniApp] Подключение к базе данных: {db_path}")
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            app.logger.info(f"[MiniApp] Успешное подключение к базе данных")
        except Exception as e:
            app.logger.error(f"[MiniApp] Ошибка подключения к базе данных: {str(e)}")
            raise
        
        # Проверяем, есть ли связанный Telegram пользователь
        tg_user_id = order_data.get('tgUserId')
        app.logger.info(f"Получен заказ от пользователя Telegram ID: {tg_user_id}")
        
        # УСИЛЕННАЯ ЗАЩИТА ОТ ДУБЛИРОВАНИЯ ЗАКАЗОВ
        # Проверка на использование идентификатора сессии для предотвращения дублирования
        session_id = order_data.get('sessionId')
        
        # Используем как session_id, так и дополнительные критерии для определения дублей
        if session_id:
            # Проверяем, не был ли уже создан заказ с таким sessionId
            cursor.execute("SELECT id FROM orders WHERE session_id = ?", (session_id,))
            existing_order = cursor.fetchone()
            if existing_order:
                app.logger.warning(f"Попытка создать дублирующий заказ с session_id: {session_id}. Отклоняем запрос.")
                return jsonify({
                    "success": True,
                    "orderId": existing_order['id'],
                    "message": "Заказ уже был создан ранее.",
                    "isDuplicate": True
                })
        
        # Дополнительная проверка для дублирования, если session_id отсутствует или пользователь пытается обойти защиту
        if tg_user_id:
            # Проверяем, нет ли недавнего заказа от этого пользователя (за последние 3 минуты)
            cursor.execute("""
                SELECT id FROM orders 
                WHERE user_id = ? AND timestamp > datetime('now', '-3 minutes')
                ORDER BY timestamp DESC LIMIT 1
            """, (tg_user_id,))
            recent_order = cursor.fetchone()
            
            if recent_order:
                app.logger.warning(f"Обнаружена попытка двойной отправки заказа от пользователя {tg_user_id}.")
                return jsonify({
                    "success": True,
                    "orderId": recent_order['id'],
                    "message": "Вы уже сделали заказ несколько секунд назад.",
                    "isDuplicate": True
                })
        
        # Проверяем наличие промокода и его действительность
        promo_code = order_data.get('promoCode', '')
        if promo_code and promo_code.upper() == 'РЫБА2025' and tg_user_id:
            cursor.execute("""
                SELECT COUNT(*) FROM orders 
                WHERE user_id = ? AND promo_used = ?
            """, (tg_user_id, 'РЫБА2025'))
            promo_used_count = cursor.fetchone()[0]
            
            if promo_used_count > 0:
                app.logger.warning(f"Промокод РЫБА2025 уже был использован пользователем {tg_user_id}.")
                order_data['promoCode'] = ''
                # Опционально: можно отправить сообщение пользователю, что промокод не применен
                # т.к. он уже был использован ранее
        
        # Проверяем, существует ли пользователь в базе
        user_exists = False
        is_repeat_customer = False
        if tg_user_id:
            cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_user_id,))
            user = cursor.fetchone()
            user_exists = user is not None
            
            # Проверяем, есть ли у пользователя предыдущие заказы
            if user_exists:
                cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (tg_user_id,))
                orders_count = cursor.fetchone()[0]
                is_repeat_customer = orders_count > 0
                app.logger.info(f"Текущее количество заказов пользователя: {orders_count}")
            
        # Если пользователя нет, создаем его
        if tg_user_id and not user_exists:
            cursor.execute(
                "INSERT INTO users (telegram_id, name, phone, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (tg_user_id, order_data['name'], order_data['phone'], current_timestamp, current_timestamp)
            )
            app.logger.info(f"Создан новый пользователь с Telegram ID: {tg_user_id}")
            
        # Если пользователь уже существует, обновляем его данные
        elif tg_user_id and user_exists:
            cursor.execute(
                "UPDATE users SET name = ?, phone = ?, updated_at = ? WHERE telegram_id = ?",
                (order_data['name'], order_data['phone'], current_timestamp, tg_user_id)
            )
            app.logger.info(f"Обновлена информация о пользователе с Telegram ID: {tg_user_id}")
        
        # Создаем новый заказ в базе данных
        cursor.execute("""
            INSERT INTO orders (
                user_id, full_name, phone, items, promo_used, 
                callback_time, status, timestamp, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tg_user_id or 0,  # Если tg_user_id не указан, используем 0
            order_data['name'],
            order_data['phone'],
            items_json,
            order_data.get('promoCode') or '',
            order_data.get('callbackTime') or '12',  # Время для звонка (по умолчанию 12:00)
            'Новый',  # Начальный статус заказа (важно использовать одинаковые статусы)
            current_timestamp,
            session_id or str(int(time.time() * 1000))  # Используем session_id или генерируем новый
        ))
        
        # Получаем ID только что созданного заказа
        cursor.execute("SELECT last_insert_rowid()")
        db_order_id = cursor.fetchone()[0]
        
        # Отслеживаем статус заказа
        cursor.execute("""
            INSERT INTO order_statuses (order_id, status, timestamp, notified)
            VALUES (?, ?, ?, 0)
        """, (db_order_id, 'Новый', current_timestamp))
        
        # Подготавливаем уведомление для администраторов о новом заказе
        admin_ids = []
        try:
            # Проверяем, существует ли столбец is_admin в таблице users
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            has_admin_column = any(column[1] == 'is_admin' for column in columns)
            
            if has_admin_column:
                cursor.execute("SELECT telegram_id FROM users WHERE is_admin = 1")
                admin_ids = [row[0] for row in cursor.fetchall()]
            
            # Если нет администраторов в базе данных, проверяем настройки
            if not admin_ids:
                # Проверяем существование таблицы app_settings
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'")
                if cursor.fetchone():
                    cursor.execute("SELECT value FROM app_settings WHERE key = 'admin_telegram_ids'")
                    admin_ids_setting = cursor.fetchone()
                    if admin_ids_setting and admin_ids_setting[0]:
                        # Парсим список ID администраторов из настроек
                        admin_ids = [int(admin_id.strip()) for admin_id in admin_ids_setting[0].split(',') if admin_id.strip()]
        except Exception as e:
            app.logger.error(f"Ошибка при получении ID администраторов: {str(e)}")
            # Используем заглушку для тестирования
            admin_ids = []
        
        # Если есть администраторы, создаем уведомления для них
        if admin_ids:
            items_list = []
            try:
                # items уже обработаны и нормализованы выше
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            # Получаем название товара
                            product_name = item.get('name', item.get('size', 'Неизвестный товар'))
                            
                            # Получаем количество товара
                            quantity = item.get('quantity', 1)
                            
                            # Добавляем информацию о товаре в список
                            items_list.append(f"{product_name} - {quantity} шт.")
                elif isinstance(items, dict):
                    for key, value in items.items():
                        if isinstance(value, dict):
                            # Если это словарь с деталями товара
                            product_name = value.get('name', key)
                            quantity = value.get('quantity', 1)
                            items_list.append(f"{product_name} - {quantity} шт.")
                        else:
                            # Если это просто пары ключ-значение
                            items_list.append(f"{key}: {value}")
            except Exception as e:
                app.logger.error(f"[MiniApp] Ошибка при обработке товаров для уведомления: {str(e)}")
                items_list = ["Ошибка обработки товаров"]
            
            # Форматируем список товаров для сообщения
            items_text = ", ".join(items_list) if items_list else "Нет товаров"
            app.logger.info(f"[MiniApp] Список товаров для уведомления: {items_text}")
            
            # Создаем текст сообщения для администраторов
            admin_notification = f"""
🆕 <b>Новый заказ #{db_order_id}</b>

👤 <b>Клиент:</b> {order_data['name']}
📞 <b>Телефон:</b> {order_data['phone']}
📋 <b>Заказ:</b> {items_text}
🕐 <b>Время:</b> {current_timestamp}
"""
            
            # Пытаемся напрямую отправить уведомления администраторам через HTTP-запрос к боту
            try:
                # Сначала добавляем запись в базу данных для отложенной отправки через бот
                for admin_id in admin_ids:
                    try:
                        cursor.execute(
                            "INSERT INTO failed_notifications (user_id, order_id, message, status, created_at, attempts) VALUES (?, ?, ?, ?, ?, 0)",
                            (admin_id, db_order_id, admin_notification, 'Новый', current_timestamp)
                        )
                    except:
                        # Возможно, в таблице нет некоторых столбцов
                        try:
                            cursor.execute(
                                "INSERT INTO failed_notifications (user_id, message, created_at, attempts) VALUES (?, ?, ?, 0)",
                                (admin_id, admin_notification, current_timestamp)
                            )
                        except Exception as e:
                            app.logger.error(f"Не удалось создать уведомление для администратора {admin_id}: {e}")
            except Exception as e:
                app.logger.error(f"Ошибка при отправке уведомлений администраторам: {e}")
        
        # Если есть Telegram пользователь, обязательно создаем или обновляем его лид
        # Эта функция не должна дублироваться в боте, ее вызов должен быть только здесь
        if tg_user_id:
            # Сначала проверим, есть ли уже лид, связанный с этим заказом
            cursor.execute("""
                SELECT id FROM leads 
                WHERE order_id = ?
            """, (db_order_id,))
            lead_for_order = cursor.fetchone()
            
            if not lead_for_order:
                # Проверяем, есть ли незавершенный лид для этого пользователя
                cursor.execute("""
                    SELECT id FROM leads 
                    WHERE user_id = ? AND is_completed = 0 AND expired = 0
                """, (tg_user_id,))
                existing_lead = cursor.fetchone()
                
                # Подготовка данных лида с правильной обработкой товаров
                try:
                    lead_data = {
                        'full_name': order_data['name'],
                        'phone': order_data['phone'],
                        'items': items,  # Используем уже нормализованные данные товаров
                        'promo_code': order_data.get('promoCode', ''),
                        'callback_time': order_data.get('callbackTime', '12')
                    }
                    lead_data_json = json.dumps(lead_data, ensure_ascii=False)
                    app.logger.info(f"[MiniApp] Подготовлены данные лида для заказа {db_order_id}")
                except Exception as e:
                    app.logger.error(f"[MiniApp] Ошибка при подготовке данных лида: {str(e)}")
                    # В случае ошибки, создаем упрощенный объект данных
                    lead_data = {
                        'full_name': order_data['name'],
                        'phone': order_data['phone'],
                        'items': [],
                        'promo_code': '',
                        'callback_time': '12'
                    }
                    lead_data_json = json.dumps(lead_data, ensure_ascii=False)
                
                if existing_lead:
                    # Обновляем существующий незавершенный лид
                    cursor.execute("""
                        UPDATE leads 
                        SET data = ?, stage = ?, timestamp = ?, is_completed = 1, order_id = ?
                        WHERE id = ?
                    """, (lead_data_json, 'completed', current_timestamp, db_order_id, existing_lead['id']))
                    app.logger.info(f"Обновлен существующий лид ID: {existing_lead['id']} для заказа ID: {db_order_id}")
                else:
                    # Создаем новый завершенный лид если не нашли ни одного подходящего
                    cursor.execute("""
                        INSERT INTO leads 
                        (user_id, data, stage, timestamp, is_repeat, is_completed, expired, order_id)
                        VALUES (?, ?, ?, ?, ?, 1, 0, ?)
                    """, (tg_user_id, lead_data_json, 'completed', current_timestamp, 1 if is_repeat_customer else 0, db_order_id))
                    app.logger.info(f"Создан новый завершенный лид для заказа ID: {db_order_id}")
            else:
                app.logger.info(f"Лид для заказа ID: {db_order_id} уже существует, пропускаем создание дубликата")
        
        # Применяем изменения и закрываем соединение
        conn.commit()
        conn.close()
        
        # Возвращаем успешный ответ с ID заказа
        response_message = "Заказ успешно создан"
        if is_repeat_customer:
            response_message += " (постоянный клиент)"
        
        return jsonify({
            "success": True,
            "orderId": db_order_id,
            "message": response_message
        })
        
    except Exception as e:
        app.logger.error(f"[MiniApp] Ошибка при обработке заказа: {e}")
        app.logger.error(traceback.format_exc())
        # Более подробное логирование для отладки
        app.logger.error(f"[MiniApp] Данные заказа, вызвавшие ошибку: {json.dumps(order_data, ensure_ascii=False) if 'order_data' in locals() else 'Данные недоступны'}")
        
        # Закрываем соединение, если оно было открыто
        if 'conn' in locals():
            conn.close()
            
        # Возвращаем более информативную ошибку клиенту
        error_message = str(e) if app.debug else "Произошла ошибка при обработке заказа"
        return jsonify({
            "error": error_message,
            "success": False,
            "orderId": None
        }), 500

@app.route("/webapp/<path:path>")
def webapp_static(path):
    return send_from_directory('static/webapp', path)
    
@app.route('/static/files/<path:path>')
def static_files(path):
    """Маршрут для доступа к файлам в static/files"""
    return send_from_directory('static/files', path)

# Константы
BOT_WORKFLOW = "bot_telegram"

# Функция для подключения к базе данных SQLite
def get_db_connection():
    conn = sqlite3.connect('bot.db', detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn

# Функция для проверки статуса процессов
def check_process_status():
    bot_running = False
    sync_running = False
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(proc.info['cmdline']) if proc.info['cmdline'] else ""
            if "python" in cmd and "botf.py" in cmd:
                bot_running = True
            elif "python" in cmd and "sync_service.py" in cmd:
                sync_running = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return {
        "bot": bot_running,
        "sync": sync_running
    }

# Заглушка вместо декоратора проверки авторизации
# Поскольку вход осуществляется через бота, не требуется дополнительная авторизация
def login_required(view_func):
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # Сразу возвращаем функцию без проверок
        return view_func(*args, **kwargs)
    return wrapped_view

# Маршруты приложения
@app.route("/")
def root():
    # Автоматически перенаправляем на админ-панель
    return redirect('/admin')
    # Старый код ниже больше не используется
    """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Золотая рыбка | Telegram бот</title>
        <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
        <style>
            body {
                background-color: #161b22;
                color: #f0f6fc;
                font-family: 'Arial', sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .container {
                max-width: 600px;
                text-align: center;
                padding: 2rem;
                border-radius: 10px;
                background-color: #0d1117;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            }
            .logo {
                max-width: 150px;
                margin-bottom: 1.5rem;
            }
            h1 {
                color: #f0f6fc;
                margin-bottom: 1rem;
            }
            p {
                margin-bottom: 1.5rem;
                line-height: 1.6;
            }
            .btn {
                display: inline-block;
                padding: 0.8rem 1.5rem;
                border-radius: 30px;
                background-color: #238636;
                color: white;
                text-decoration: none;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            .btn:hover {
                background-color: #2ea043;
                transform: translateY(-2px);
            }
            .admin-link {
                margin-top: 2rem;
                display: block;
                color: #8b949e;
                text-decoration: none;
            }
            .admin-link:hover {
                color: #58a6ff;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <img src="/static/logo.png" alt="Золотая рыбка" class="logo">
            <h1>Telegram бот "Золотая рыбка"</h1>
            <p>Это сервер Telegram бота для заказа рыбы.</p>
            <a href="https://t.me/YourGoldfishBot" target="_blank" class="btn">Открыть бота</a>
            <a href="/admin" class="admin-link">Вход для администратора</a>
        </div>
    </body>
    </html>
    """

@app.route("/admin")
def admin_dashboard():
    process_status = check_process_status()
    
    conn = get_db_connection()
    
    # Получение основной статистики
    orders_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    leads_count = conn.execute("SELECT COUNT(*) FROM leads WHERE is_completed = 0 AND expired = 0").fetchone()[0]
    users_count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM orders").fetchone()[0]
    
    # Получение последних заказов
    latest_orders = conn.execute("""
        SELECT id, user_id, full_name, total, status, timestamp 
        FROM orders 
        ORDER BY timestamp DESC 
        LIMIT 10
    """).fetchall()
    
    # Получение последних лидов
    latest_leads = conn.execute("""
        SELECT id, user_id, data, stage, timestamp 
        FROM leads 
        WHERE is_completed = 0 AND expired = 0
        ORDER BY timestamp DESC 
        LIMIT 10
    """).fetchall()
    
    # Обработка данных лидов для отображения
    processed_leads = []
    for lead in latest_leads:
        try:
            data = json.loads(lead['data']) if lead['data'] else {}
            name = data.get('full_name', 'Неизвестно')
            stage = lead['stage'].split(":")[-1] if ":" in lead['stage'] else lead['stage']
            
            processed_leads.append({
                'id': lead['id'],
                'user_id': lead['user_id'],
                'name': name,
                'stage': stage,
                'timestamp': lead['timestamp']
            })
        except json.JSONDecodeError:
            processed_leads.append({
                'id': lead['id'],
                'user_id': lead['user_id'],
                'name': 'Ошибка данных',
                'stage': lead['stage'],
                'timestamp': lead['timestamp']
            })
    
    conn.close()
    
    # Добавляем временную метку для принудительного обновления кэша CSS
    cache_buster = int(time.time())
    
    return render_template('index.html', 
                          process_status=process_status,
                          orders_count=orders_count,
                          leads_count=leads_count,
                          users_count=users_count,
                          latest_orders=latest_orders,
                          leads=processed_leads,
                          cache_buster=cache_buster)

@app.route("/orders")
def orders():
    """Отображение списка заказов с интеграцией CRM функциональности"""
    import json
    import traceback
    import pytz
    from datetime import datetime
    
    conn = get_db_connection()
    
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', '')
        per_page = 20
        offset = (page - 1) * per_page
        
        # Используем прямой запрос без JOIN, чтобы избежать ошибок
        query = """
            SELECT id, user_id, full_name, phone, items, total, promo_used, status, callback_time, timestamp
            FROM orders
        """
        count_query = "SELECT COUNT(*) FROM orders"
        params = []
        
        # Добавление фильтра по статусу, если указан
        if status_filter:
            query += " WHERE status = ?"
            count_query += " WHERE status = ?"
            params.append(status_filter)
        
        # Добавление сортировки и пагинации
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        # Выполнение запросов
        orders = conn.execute(query, params).fetchall()
        total_count = conn.execute(count_query, params[:-2] if params else []).fetchone()[0]
        
        # Получение уникальных статусов для фильтра
        statuses = conn.execute("SELECT DISTINCT status FROM orders").fetchall()

        # Настройка часового пояса UTC+8
        utc_tz = pytz.timezone('UTC')
        asia_tz = pytz.timezone('Asia/Shanghai')  # UTC+8 (Китай, Гонконг, Сингапур)
        
        # Обработка данных заказов
        processed_orders = []
        for order in orders:
            try:
                # Форматирование даты и времени в UTC+8
                date_str = order['timestamp']
                try:
                    # Парсим строку даты и применяем часовой пояс
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    date_obj_utc = utc_tz.localize(date_obj)
                    date_obj_asia = date_obj_utc.astimezone(asia_tz)
                    formatted_date = date_obj_asia.strftime('%Y-%m-%d %H:%M:%S (UTC+8)')
                except:
                    # Если не удается перевести время, оставляем оригинальную строку
                    formatted_date = f"{date_str} (UTC)"
                
                # Форматирование суммы заказа
                total_str = "Не указана"
                if order['total']:
                    try:
                        # Если уже строка с символом валюты - оставляем как есть
                        if isinstance(order['total'], str) and "₽" in order['total']:
                            total_str = order['total']
                        else:
                            # Преобразуем в число, затем форматируем
                            total_value = float(order['total'])
                            total_str = f"{total_value:.2f} ₽"
                    except:
                        # Если преобразование не удалось - просто выводим как строку
                        total_str = f"{order['total']} ₽"
                
                # Обработка списка товаров
                items_text = "Нет товаров"
                products_list = []
                
                if order['items']:
                    try:
                        items_data = json.loads(order['items'])
                        # Обработка различных форматов данных
                        if isinstance(items_data, list):
                            if len(items_data) > 0 and isinstance(items_data[0], dict):
                                # Формат списка словарей
                                items_str_list = []
                                for item in items_data:
                                    if isinstance(item, dict):
                                        if 'name' in item:
                                            item_text = f"{item['name']} ({item.get('quantity', 1)} шт.)"
                                            items_str_list.append(item_text)
                                            products_list.append(item_text)
                                        elif 'size' in item:
                                            item_text = f"{item['size']} ({item.get('quantity', 1)} шт.)"
                                            items_str_list.append(item_text)
                                            products_list.append(item_text)
                                        else:
                                            # Любой другой формат словаря
                                            item_text = str(item)
                                            items_str_list.append(item_text)
                                            products_list.append(item_text)
                                    elif isinstance(item, str):
                                        items_str_list.append(item)
                                        products_list.append(item)
                                        
                                items_text = ", ".join(items_str_list)
                            else:
                                # Формат списка строк
                                items_text = ", ".join(items_data)
                                products_list = list(items_data)
                        elif isinstance(items_data, dict):
                            # Словарь
                            items_str_list = []
                            for key, value in items_data.items():
                                if isinstance(value, dict) and 'name' in value:
                                    item_text = f"{value['name']} ({value.get('quantity', 1)} шт.)"
                                    items_str_list.append(item_text)
                                    products_list.append(item_text)
                                else:
                                    item_text = f"{key}: {value}"
                                    items_str_list.append(item_text)
                                    products_list.append(item_text)
                            items_text = ", ".join(items_str_list)
                    except:
                        # Если не удалось обработать JSON, просто выводим как строку
                        items_text = str(order['items'])
                        products_list = [items_text]
                
                username = None
                # Получаем информацию о пользователе, если есть
                if order['user_id']:
                    try:
                        user_info = conn.execute(
                            "SELECT username FROM users WHERE telegram_id = ?", 
                            (order['user_id'],)
                        ).fetchone()
                        
                        if user_info and 'username' in user_info and user_info['username']:
                            username = user_info['username']
                    except Exception as e:
                        app.logger.error(f"Ошибка при получении username пользователя: {e}")
                
                processed_orders.append({
                    'id': order['id'],
                    'user_id': order['user_id'],
                    'full_name': order['full_name'],
                    'phone': order['phone'],
                    'items': items_text,
                    'products_list': products_list,
                    'total': total_str,
                    'promo_used': order['promo_used'] or "Нет",
                    'status': order['status'] or "Новый",
                    'callback_time': order['callback_time'] or "12",
                    'timestamp': formatted_date,
                    'username': username
                })
            except json.JSONDecodeError:
                app.logger.error(f"Ошибка декодирования JSON в заказе {order['id']}")
                processed_orders.append({
                    'id': order['id'],
                    'user_id': order['user_id'],
                    'full_name': order['full_name'],
                    'phone': order['phone'],
                    'items': 'Ошибка данных',
                    'total': order['total'] or "Не указана",
                    'promo_used': order['promo_used'] or "Нет",
                    'status': order['status'] or "Новый",
                    'callback_time': order['callback_time'] or "12",
                    'timestamp': order['timestamp']
                })
            except Exception as e:
                app.logger.error(f"Ошибка обработки заказа {order['id']}: {e}")
                app.logger.error(traceback.format_exc())
                processed_orders.append({
                    'id': order['id'],
                    'user_id': order['user_id'],
                    'full_name': order['full_name'],
                    'phone': order['phone'],
                    'items': 'Ошибка обработки',
                    'total': order['total'] or "Не указана",
                    'promo_used': order['promo_used'] or "Нет",
                    'status': order['status'] or "Новый",
                    'callback_time': order['callback_time'] or "12",
                    'timestamp': order['timestamp']
                })
        
        total_pages = (total_count + per_page - 1) // per_page
        
        return render_template('orders.html', 
                            orders=processed_orders,
                            current_page=page,
                            total_pages=total_pages,
                            statuses=statuses,
                            current_status=status_filter)
    
    except Exception as e:
        app.logger.error(f"Ошибка при отображении списка заказов: {e}")
        app.logger.error(traceback.format_exc())
        flash(f"Произошла ошибка при загрузке списка заказов: {e}", "danger")
        return render_template('orders.html', orders=[], current_page=1, total_pages=1, statuses=[], current_status='')
    
    finally:
        conn.close()

@app.route("/leads")
def leads():
    """Отображение активных лидов с информацией о пользователях"""
    import json
    import traceback
    import pytz
    from datetime import datetime
    
    conn = get_db_connection()
    
    page = request.args.get('page', 1, type=int)
    lead_type = request.args.get('type', 'active')  # active, expired, all
    per_page = 20
    offset = (page - 1) * per_page
    
    # РАДИКАЛЬНЫЕ ИЗМЕНЕНИЯ: Перенастройка всей логики обработки лидов
    
    # Определяем условие фильтрации на основе типа лидов
    if lead_type == 'expired':
        # Только истекшие лиды
        where_condition = "expired = 1 AND is_completed = 0"
    elif lead_type == 'all':
        # Все лиды (и активные, и истекшие)
        where_condition = "is_completed = 0"
    else:
        # По умолчанию только активные (не истекшие) лиды
        where_condition = "is_completed = 0 AND (expired = 0 OR expired IS NULL)"
    
    # НОВЫЙ ПОДХОД: Получение лидов с простым подсчетом заказов напрямую
    try:
        # 1. Сначала получаем все идентификаторы пользователей из текущей выборки
        user_ids_query = f"""
            SELECT DISTINCT user_id 
            FROM leads 
            WHERE {where_condition}
            ORDER BY id DESC
        """
        user_ids_result = conn.execute(user_ids_query).fetchall()
        user_ids = [row['user_id'] for row in user_ids_result]
        
        # 2. Получаем количество заказов для каждого пользователя один раз
        orders_counts = {}
        if user_ids:
            # Вместо запроса для каждого пользователя, делаем один запрос
            placeholders = ','.join(['?'] * len(user_ids))
            orders_query = f"""
                SELECT user_id, COUNT(*) as count 
                FROM orders 
                WHERE user_id IN ({placeholders})
                GROUP BY user_id
            """
            orders_result = conn.execute(orders_query, user_ids).fetchall()
            for row in orders_result:
                orders_counts[row['user_id']] = row['count']
        
        # 3. Получаем основную информацию о лидах
        query = f"""
            SELECT id, user_id, data, stage, timestamp, is_repeat, is_completed, expired, order_id
            FROM leads
            WHERE {where_condition}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        leads_result = conn.execute(query, [per_page, offset]).fetchall()
        
        # 4. Получаем общее количество лидов для пагинации
        count_query = f"SELECT COUNT(*) FROM leads WHERE {where_condition}"
        total_count = conn.execute(count_query).fetchone()[0]
        
        # 5. Получаем имена пользователей Telegram для всех лидов
        usernames = {}
        if user_ids:
            placeholders = ','.join(['?'] * len(user_ids))
            username_query = f"""
                SELECT telegram_id, username 
                FROM users 
                WHERE telegram_id IN ({placeholders})
            """
            username_result = conn.execute(username_query, user_ids).fetchall()
            for row in username_result:
                usernames[row['telegram_id']] = row['username']
    
    except Exception as e:
        app.logger.error(f"Критическая ошибка при получении данных лидов: {e}")
        app.logger.error(traceback.format_exc())
        leads_result = []
        total_count = 0
        orders_counts = {}
        usernames = {}
    
    # Настройка часового пояса UTC+8
    utc_tz = pytz.timezone('UTC')
    asia_tz = pytz.timezone('Asia/Shanghai')  # UTC+8
    
    # Обработка данных лидов
    processed_leads = []
    for lead in leads_result:
        try:
            # Форматирование даты в UTC+8
            date_str = lead['timestamp']
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                date_obj_utc = utc_tz.localize(date_obj)
                date_obj_asia = date_obj_utc.astimezone(asia_tz)
                formatted_date = date_obj_asia.strftime('%Y-%m-%d %H:%M:%S (UTC+8)')
            except:
                formatted_date = f"{date_str} (UTC)"
            
            # Обработка данных лида с безопасной обработкой JSON
            try:
                data = json.loads(lead['data']) if lead['data'] else {}
            except json.JSONDecodeError:
                app.logger.error(f"Ошибка декодирования JSON для лида {lead['id']}")
                data = {}
            
            name = data.get('full_name', 'Неизвестно')
            phone = data.get('phone', 'Не указан')
            
            # ПЕРЕРАБОТКА ЛОГИКИ ОТОБРАЖЕНИЯ ТОВАРОВ
            items_str = "Нет товаров"
            items = data.get('items', [])
            
            if items:
                if isinstance(items, list):
                    # Список строк или объектов
                    if items and isinstance(items[0], dict):
                        # Список словарей
                        item_texts = []
                        for item in items:
                            item_name = item.get('name') or item.get('size') or "Товар"
                            item_qty = item.get('quantity', 1)
                            item_texts.append(f"{item_name} ({item_qty} шт.)")
                        items_str = ", ".join(item_texts)
                    else:
                        # Список строк
                        items_str = ", ".join(str(item) for item in items)
                        
                elif isinstance(items, dict):
                    # Словарь товаров
                    item_texts = []
                    for k, v in items.items():
                        if isinstance(v, dict):
                            item_name = v.get('name') or k
                            item_qty = v.get('quantity', 1)
                            item_texts.append(f"{item_name} ({item_qty} шт.)")
                        else:
                            item_texts.append(f"{k}: {v}")
                    items_str = ", ".join(item_texts)
                    
                else:
                    # Простая строка или число
                    items_str = str(items)
            
            # Получение количества заказов из предварительно рассчитанного словаря
            user_id = lead['user_id']
            orders_count = orders_counts.get(user_id, 0)
            
            # Получение username из предварительно загруженного словаря
            username = usernames.get(user_id)
            
            # Преобразование этапа в удобочитаемый формат
            stage = lead['stage'] if lead['stage'] else "Неизвестно"
            
            processed_leads.append({
                'id': lead['id'],
                'user_id': user_id,
                'name': name,
                'phone': phone,
                'items': items_str,
                'stage': stage,
                'timestamp': formatted_date,
                'is_repeat': lead['is_repeat'] == 1,
                'orders_count': orders_count,
                'username': username,
                'order_id': lead['order_id'],
                'expired': lead['expired']
            })
            
        except Exception as e:
            app.logger.error(f"Ошибка обработки лида {lead['id']}: {e}")
            app.logger.error(traceback.format_exc())
            # Добавляем запись с пометкой об ошибке
            processed_leads.append({
                'id': lead['id'] if 'id' in lead else 'Ошибка',
                'user_id': lead['user_id'] if 'user_id' in lead else 'Ошибка',
                'name': 'Ошибка данных',
                'phone': 'Ошибка данных',
                'items': 'Ошибка данных',
                'timestamp': lead['timestamp'] if 'timestamp' in lead else 'Ошибка времени',
                'is_repeat': False,
                'orders_count': 0,
                'username': None,
                'order_id': None,
                'expired': lead['expired'] if 'expired' in lead else 0
            })
    
    total_pages = (total_count + per_page - 1) // per_page
    
    conn.close()
    
    return render_template('leads.html', 
                          leads=processed_leads,
                          page=page,
                          total_pages=total_pages,
                          stage_filter='',  # Убираем фильтр по этапу
                          lead_type=lead_type,
                          stages=[])

@app.route("/settings", methods=["GET", "POST"])
def settings():
    conn = get_db_connection()
    
    # Создаем таблицу настроек, если она еще не существует
    conn.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    if request.method == "POST":
        # Получаем данные формы
        working_hours_start = request.form.get('working_hours_start', '09:00')
        working_hours_end = request.form.get('working_hours_end', '18:00')
        admin_telegram_ids = request.form.get('admin_telegram_ids', '')
        notifications_enabled = request.form.get('notifications_enabled', '') == 'on'
        
        # Сохраняем настройки в базу данных
        try:
            # Обновляем или создаем записи
            conn.execute('''
                INSERT INTO app_settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                value = excluded.value, updated_at = CURRENT_TIMESTAMP
            ''', ('working_hours_start', working_hours_start))
            
            conn.execute('''
                INSERT INTO app_settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                value = excluded.value, updated_at = CURRENT_TIMESTAMP
            ''', ('working_hours_end', working_hours_end))
            
            conn.execute('''
                INSERT INTO app_settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                value = excluded.value, updated_at = CURRENT_TIMESTAMP
            ''', ('admin_telegram_ids', admin_telegram_ids))
            
            conn.execute('''
                INSERT INTO app_settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET 
                value = excluded.value, updated_at = CURRENT_TIMESTAMP
            ''', ('notifications_enabled', "1" if notifications_enabled else "0"))
            
            conn.commit()
            flash("Настройки успешно обновлены", "success")
        except Exception as e:
            logging.error(f"Ошибка при сохранении настроек: {e}")
            flash(f"Ошибка при сохранении настроек: {e}", "danger")
            
        conn.close()
        return redirect(url_for('settings'))
    
    process_status = check_process_status()
    
    # Получаем текущие настройки из базы данных
    current_settings = {
        'working_hours_start': '',
        'working_hours_end': '',
        'admin_telegram_ids': '',
        'notifications_enabled': False
    }
    
    try:
        # Получаем настройки по одной
        cursor = conn.execute("SELECT key, value FROM app_settings")
        for row in cursor:
            if row['key'] == 'working_hours_start':
                current_settings['working_hours_start'] = row['value']
            elif row['key'] == 'working_hours_end':
                current_settings['working_hours_end'] = row['value']
            elif row['key'] == 'admin_telegram_ids':
                current_settings['admin_telegram_ids'] = row['value']
            elif row['key'] == 'notifications_enabled':
                current_settings['notifications_enabled'] = row['value'] == "1"
    except Exception as e:
        logging.error(f"Ошибка при загрузке настроек: {e}")
    
    conn.close()
    
    return render_template('settings.html', settings=current_settings, process_status=process_status)

@app.route("/export_excel")
def export_excel():
    
    conn = get_db_connection()
    
    # Получение данных заказов
    orders = conn.execute("""
        SELECT id, user_id, full_name, phone, items, total, promo_used, status, timestamp
        FROM orders 
        ORDER BY timestamp DESC
    """).fetchall()
    
    conn.close()
    
    # Обработка данных заказов
    processed_orders = []
    for order in orders:
        try:
            items_text = "Нет товаров"
            if order['items']:
                items_data = json.loads(order['items'])
                # Обработка различных форматов данных
                if isinstance(items_data, list):
                    if len(items_data) > 0 and isinstance(items_data[0], dict):
                        # Формат списка словарей
                        items_str_list = []
                        for item in items_data:
                            if 'name' in item:
                                items_str_list.append(f"{item['name']} ({item.get('quantity', 1)} шт.)")
                            elif 'size' in item:
                                items_str_list.append(f"{item['size']} ({item.get('quantity', 1)} шт.)")
                            else:
                                # Любой другой формат словаря
                                items_str_list.append(str(item))
                        items_text = ", ".join(items_str_list)
                    else:
                        # Формат списка строк
                        items_text = ", ".join(items_data)
                elif isinstance(items_data, dict):
                    # Словарь
                    items_str_list = []
                    for key, value in items_data.items():
                        if isinstance(value, dict) and 'name' in value:
                            items_str_list.append(f"{value['name']} ({value.get('quantity', 1)} шт.)")
                        else:
                            items_str_list.append(f"{key}: {value}")
                    items_text = ", ".join(items_str_list)
            
            processed_orders.append({
                'Номер заказа': order['id'],
                'ID пользователя': order['user_id'],
                'ФИО': order['full_name'],
                'Телефон': order['phone'],
                'Товары': items_text,
                'Сумма': order['total'] or "Не указана",
                'Промокод': order['promo_used'] or "Нет",
                'Статус': order['status'] or "Новый",
                'Дата': order['timestamp']
            })
        except json.JSONDecodeError:
            app.logger.error(f"Ошибка декодирования JSON в заказе {order['id']}")
            processed_orders.append({
                'Номер заказа': order['id'],
                'ID пользователя': order['user_id'],
                'ФИО': order['full_name'],
                'Телефон': order['phone'],
                'Товары': 'Ошибка данных',
                'Сумма': order['total'] or "Не указана",
                'Промокод': order['promo_used'] or "Нет",
                'Статус': order['status'] or "Новый",
                'Дата': order['timestamp']
            })
        except Exception as e:
            app.logger.error(f"Ошибка обработки заказа {order['id']}: {e}")
            processed_orders.append({
                'Номер заказа': order['id'],
                'ID пользователя': order['user_id'],
                'ФИО': order['full_name'],
                'Телефон': order['phone'],
                'Товары': 'Ошибка обработки',
                'Сумма': order['total'] or "Не указана",
                'Промокод': order['promo_used'] or "Нет",
                'Статус': order['status'] or "Новый",
                'Дата': order['timestamp']
            })
    
    # Создание DataFrame и экспорт в Excel
    df = pd.DataFrame(processed_orders)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"orders_export_{timestamp}.xlsx"
    filepath = os.path.join("static", "exports", filename)
    
    # Создаем директорию, если она не существует
    os.makedirs(os.path.join("static", "exports"), exist_ok=True)
    
    # Экспорт в Excel
    df.to_excel(filepath, index=False)
    
    return redirect(url_for('static', filename=f'exports/{filename}'))

# Функция для входа в систему

@app.route("/login", methods=["GET", "POST"])
def login():
    # Автоматически перенаправляем на админку, вход был отключен
    return redirect('/admin')

@app.route("/logout")
def logout():
    # Создаем response для удаления куки
    response = make_response(redirect('/login'))
    response.delete_cookie('admin_auth')
    
    flash("Вы вышли из системы", "info")
    return response

@app.route("/api/restart_bot", methods=["POST"])
def restart_bot():
    
    try:
        # Используем Replit workflow для перезапуска бота
        subprocess.run(["bash", "-c", "kill -TERM $(ps aux | grep '[p]ython.*botf.py' | awk '{print $2}') 2>/dev/null || true"])
        
        flash("Бот перезапущен", "success")
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Ошибка при перезапуске бота: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/restart_sync", methods=["POST"])
def restart_sync():
    
    try:
        # Используем Replit workflow для перезапуска сервиса синхронизации
        subprocess.run(["bash", "-c", "kill -TERM $(ps aux | grep '[p]ython.*sync_service.py' | awk '{print $2}') 2>/dev/null || true"])
        
        flash("Сервис синхронизации перезапущен", "success")
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Ошибка при перезапуске сервиса синхронизации: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route("/user/<int:user_id>")
def user_detail(user_id):
    
    conn = get_db_connection()
    
    # Получение информации о пользователе
    orders = conn.execute("""
        SELECT id, full_name, phone, items, total, promo_used, status, timestamp
        FROM orders 
        WHERE user_id = ?
        ORDER BY timestamp DESC
    """, (user_id,)).fetchall()
    
    # Получение username из таблицы users
    try:
        user_data = conn.execute("""
            SELECT username, name as first_name, created_at as created_at, updated_at as last_activity
            FROM users
            WHERE telegram_id = ?
        """, (user_id,)).fetchone()
        logging.info(f"Получены данные пользователя: {user_data}")
    except Exception as e:
        user_data = None
        logging.error(f"Ошибка при получении данных пользователя: {e}")
    
    # Получение активных лидов пользователя
    leads = conn.execute("""
        SELECT id, data, stage, timestamp, is_repeat, is_completed, expired
        FROM leads
        WHERE user_id = ? AND is_completed = 0 AND expired = 0
        ORDER BY timestamp DESC
    """, (user_id,)).fetchall()
    
    conn.close()
    
    # Обработка данных заказов
    processed_orders = []
    for order in orders:
        try:
            items_text = "Нет товаров"
            if order['items']:
                items_data = json.loads(order['items'])
                # Обработка различных форматов данных
                if isinstance(items_data, list):
                    if len(items_data) > 0 and isinstance(items_data[0], dict):
                        # Формат списка словарей
                        items_str_list = []
                        for item in items_data:
                            if 'name' in item:
                                items_str_list.append(f"{item['name']} ({item.get('quantity', 1)} шт.)")
                            elif 'size' in item:
                                items_str_list.append(f"{item['size']} ({item.get('quantity', 1)} шт.)")
                            else:
                                # Любой другой формат словаря
                                items_str_list.append(str(item))
                        items_text = ", ".join(items_str_list)
                    else:
                        # Формат списка строк
                        items_text = ", ".join(items_data)
                elif isinstance(items_data, dict):
                    # Словарь
                    items_str_list = []
                    for key, value in items_data.items():
                        if isinstance(value, dict) and 'name' in value:
                            items_str_list.append(f"{value['name']} ({value.get('quantity', 1)} шт.)")
                        else:
                            items_str_list.append(f"{key}: {value}")
                    items_text = ", ".join(items_str_list)
            
            processed_orders.append({
                'id': order['id'],
                'full_name': order['full_name'],
                'phone': order['phone'],
                'items': items_text,
                'products_list': items_data if isinstance(items_data, list) else [],
                'total': f"{order['total']} ₽" if order['total'] else "Не указана",
                'promo_used': order['promo_used'] or "Нет",
                'status': order['status'] or "Новый",
                'timestamp': order['timestamp']
            })
        except json.JSONDecodeError:
            app.logger.error(f"Ошибка декодирования JSON в заказе {order['id']}")
            processed_orders.append({
                'id': order['id'],
                'full_name': order['full_name'],
                'phone': order['phone'],
                'items': 'Ошибка данных',
                'total': order['total'] or "Не указана",
                'promo_used': order['promo_used'] or "Нет",
                'status': order['status'] or "Новый",
                'timestamp': order['timestamp']
            })
        except Exception as e:
            app.logger.error(f"Ошибка обработки заказа {order['id']}: {e}")
            processed_orders.append({
                'id': order['id'],
                'full_name': order['full_name'],
                'phone': order['phone'],
                'items': 'Ошибка обработки',
                'total': order['total'] or "Не указана",
                'promo_used': order['promo_used'] or "Нет",
                'status': order['status'] or "Новый",
                'timestamp': order['timestamp']
            })
    
    # Обработка данных лидов
    processed_leads = []
    for lead in leads:
        try:
            data = json.loads(lead['data']) if lead['data'] else {}
            name = data.get('full_name', 'Неизвестно')
            phone = data.get('phone', 'Не указан')
            items = data.get('items', [])
            if isinstance(items, list):
                items_str = ", ".join(items)
            else:
                items_str = str(items)
            
            stage = lead['stage'].split(":")[-1] if ":" in lead['stage'] else lead['stage']
            
            processed_leads.append({
                'id': lead['id'],
                'name': name,
                'phone': phone,
                'items': items_str,
                'stage': stage,
                'timestamp': lead['timestamp'],
                'is_repeat': lead['is_repeat']
            })
        except json.JSONDecodeError:
            processed_leads.append({
                'id': lead['id'],
                'name': 'Ошибка данных',
                'phone': 'Ошибка данных',
                'items': 'Ошибка данных',
                'stage': lead['stage'],
                'timestamp': lead['timestamp'],
                'is_repeat': lead['is_repeat']
            })
    
    # Извлекаем username из данных пользователя
    username = None
    if user_data and 'username' in user_data and user_data['username']:
        username = user_data['username']
    
    created_at = None
    last_activity = None
    if user_data:
        created_at = user_data.get('created_at')
        last_activity = user_data.get('last_activity')
    
    user_info = None
    if processed_orders:
        user_info = {
            'telegram_id': user_id,
            'name': processed_orders[0]['full_name'],
            'phone': processed_orders[0]['phone'],
            'orders_count': len(processed_orders),
            'username': username,
            'created_at': created_at,
            'last_activity': last_activity
        }
    elif processed_leads:
        user_info = {
            'telegram_id': user_id,
            'name': processed_leads[0]['name'],
            'phone': processed_leads[0]['phone'],
            'orders_count': 0,
            'username': username,
            'created_at': created_at,
            'last_activity': last_activity
        }
    else:
        user_info = {
            'telegram_id': user_id,
            'name': 'Неизвестно',
            'phone': 'Неизвестно',
            'orders_count': 0,
            'username': username,
            'created_at': created_at,
            'last_activity': last_activity
        }
    
    return render_template('user_detail.html', 
                          user=user_info,
                          orders=processed_orders,
                          leads=processed_leads)

@app.route("/order/<int:order_id>")
def order_detail(order_id):
    """Детальная информация о заказе с интегрированной CRM функциональностью"""
    import json
    import traceback
    
    conn = get_db_connection()
    
    try:
        # Получение информации о заказе
        order = conn.execute("""
            SELECT id, user_id, full_name, phone, items, total, promo_used, status, callback_time, timestamp, 
                   username, notion_page_id
            FROM orders 
            WHERE id = ?
        """, (order_id,)).fetchone()
        
        if not order:
            flash("Заказ не найден", "danger")
            return redirect(url_for('orders'))
        
        # Получение истории статусов заказа
        status_history = conn.execute("""
            SELECT status, timestamp, notified
            FROM order_statuses
            WHERE order_id = ?
            ORDER BY timestamp DESC
        """, (order_id,)).fetchall()
        
        # Получение связанного лида, если есть
        associated_lead = conn.execute("""
            SELECT id, data, stage, timestamp, is_repeat, is_completed, expired
            FROM leads
            WHERE order_id = ?
        """, (order_id,)).fetchone()
        
        # Получение информации о клиенте
        user_data = None
        if order['user_id']:
            user_query = """
                SELECT created_at, updated_at, 
                       (SELECT COUNT(*) FROM orders WHERE user_id = ?) as orders_count
                FROM users
                WHERE telegram_id = ?
            """
            user_data = conn.execute(user_query, (order['user_id'], order['user_id'])).fetchone()
        
        # Обработка данных заказа
        items_list = []
        try:
            if order['items']:
                items_data = json.loads(order['items'])
                # Если items - список строк
                if isinstance(items_data, list):
                    if len(items_data) > 0 and isinstance(items_data[0], dict):
                        # Обработка списка словарей
                        for item in items_data:
                            if 'name' in item:
                                items_list.append(f"{item['name']} - {item.get('quantity', 1)} шт.")
                            elif 'size' in item:
                                items_list.append(f"{item['size']} - {item.get('quantity', 1)} шт.")
                            else:
                                items_list.append(str(item))
                    else:
                        # Список строк
                        items_list = items_data
                # Если items - словарь
                elif isinstance(items_data, dict):
                    for key, value in items_data.items():
                        if isinstance(value, dict) and 'name' in value:
                            items_list.append(f"{value['name']} - {value.get('quantity', 1)} шт.")
                        else:
                            items_list.append(f"{key}: {value}")
        except json.JSONDecodeError:
            app.logger.error(f"Ошибка декодирования JSON в заказе {order_id}")
            app.logger.error(traceback.format_exc())
            items_list = ['Ошибка данных']
        except Exception as e:
            app.logger.error(f"Ошибка обработки товаров заказа {order_id}: {e}")
            app.logger.error(traceback.format_exc())
            items_list = ['Ошибка обработки данных']
        
        # Обработка данных лида
        lead_info = None
        if associated_lead:
            try:
                lead_data = json.loads(associated_lead['data']) if associated_lead['data'] else {}
                lead_stage = associated_lead['stage']
                
                # Преобразование стадии лида в понятный формат
                if ":" in lead_stage:
                    lead_stage = lead_stage.split(":")[-1]
                
                lead_info = {
                    'id': associated_lead['id'],
                    'stage': lead_stage,
                    'timestamp': associated_lead['timestamp'],
                    'is_repeat': associated_lead['is_repeat'] == 1,
                    'is_completed': associated_lead['is_completed'] == 1,
                    'expired': associated_lead['expired'] == 1,
                    'data': lead_data
                }
            except json.JSONDecodeError:
                app.logger.error(f"Ошибка декодирования JSON в лиде для заказа {order_id}")
                lead_info = {
                    'id': associated_lead['id'],
                    'stage': associated_lead['stage'],
                    'timestamp': associated_lead['timestamp'],
                    'is_repeat': associated_lead['is_repeat'] == 1,
                    'is_completed': associated_lead['is_completed'] == 1,
                    'expired': associated_lead['expired'] == 1,
                    'data': 'Ошибка данных'
                }
        
        # Определяем, повторный ли клиент
        is_repeat_customer = False
        customer_since = None
        if user_data:
            is_repeat_customer = user_data['orders_count'] > 1 if 'orders_count' in user_data else False
            customer_since = user_data['created_at'] if 'created_at' in user_data else None
        
        # Подготовка данных для отображения
        # Используем другое название для списка товаров, чтобы избежать конфликта с методом items() у dict
        processed_order = {
            'id': order['id'],
            'user_id': order['user_id'],
            'full_name': order['full_name'],
            'phone': order['phone'],
            'products_list': items_list,  # Изменено название ключа с 'items' на 'products_list'
            'total': order['total'] or 'Не указана',
            'promo_used': order['promo_used'] or "Нет",
            'status': order['status'],
            'callback_time': order['callback_time'],
            'timestamp': order['timestamp'],
            'is_repeat_customer': is_repeat_customer,
            'customer_since': customer_since,
            'notion_status': 'Синхронизирован' if order['notion_page_id'] else 'Не синхронизирован', 
            'username': order['username'] if 'username' in order else None
        }
        
        # Возможные статусы заказа (упрощенный набор)
        available_statuses = ['Новый', 'В работе', 'Завершён']
        
        return render_template('order_detail.html', 
                               order=processed_order,
                               status_history=status_history,
                               available_statuses=available_statuses,
                               lead=lead_info)
    
    except Exception as e:
        app.logger.error(f"Ошибка при отображении заказа {order_id}: {e}")
        app.logger.error(traceback.format_exc())
        flash(f"Произошла ошибка при загрузке заказа: {e}", "danger")
        return redirect(url_for('orders'))
    
    finally:
        conn.close()

@app.route("/api/change_order_status", methods=["POST"])
def change_order_status():
    """Изменение статуса заказа"""
    try:
        # Для обработки как JSON, так и form-data
        if request.is_json:
            data = request.json
            order_id = data.get('order_id')
            new_status = data.get('status')
        else:
            order_id = request.form.get('order_id')
            new_status = request.form.get('new_status')
        
        if not order_id or not new_status:
            return jsonify({"success": False, "message": "Не указан ID заказа или новый статус"})
        
        conn = get_db_connection()
        
        # Проверяем существование заказа и текущий статус
        order = conn.execute("SELECT user_id, status FROM orders WHERE id = ?", (order_id,)).fetchone()
        
        if not order:
            conn.close()
            return jsonify({"success": False, "message": "Заказ не найден"})
        
        # Если текущий статус такой же как новый - не делаем ничего
        if order['status'] == new_status:
            conn.close()
            flash(f"Статус заказа уже установлен как \"{new_status}\"", "info")
            return redirect(url_for('orders'))
        
        # Обновляем статус в локальной БД
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        
        # Проверяем, есть ли уже такой статус в истории статусов
        existing_status = conn.execute(
            "SELECT id FROM order_statuses WHERE order_id = ? AND status = ?", 
            (order_id, new_status)
        ).fetchone()
        
        # Добавляем запись в историю статусов только если такого статуса еще не было
        if not existing_status:
            conn.execute(
                "INSERT INTO order_statuses (order_id, status, timestamp, notified) VALUES (?, ?, ?, 0)",
                (order_id, new_status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            
            # Записываем информацию для отправки уведомления только для новых статусов
            # Для уведомлений используется таблица failed_notifications с последующей 
            # обработкой сервисом синхронизации и ботом
            user_id = order['user_id']
            
            # Отправляем уведомления только для определенных статусов
            if new_status.lower() == "в работе":
                notification_message = "Ваш заказ взят в работу! Скоро с вами свяжется менеджер."
                
                # Проверяем наличие необходимых столбцов в таблице failed_notifications
                has_order_id = False
                has_status = False
                
                try:
                    cursor = conn.execute("SELECT order_id FROM failed_notifications LIMIT 1")
                    has_order_id = True
                except:
                    pass
                    
                try:
                    cursor = conn.execute("SELECT status FROM failed_notifications LIMIT 1")
                    has_status = True
                except:
                    pass
                
                # Создаем SQL запрос в зависимости от доступных столбцов
                if has_order_id and has_status:
                    conn.execute(
                        "INSERT INTO failed_notifications (user_id, order_id, message, status, created_at, attempts) VALUES (?, ?, ?, ?, ?, 0)",
                        (user_id, order_id, notification_message, new_status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    )
                else:
                    # Если нет нужных столбцов, используем только те, которые точно есть
                    conn.execute(
                        "INSERT INTO failed_notifications (user_id, message, created_at, attempts) VALUES (?, ?, ?, 0)",
                        (user_id, notification_message, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    )
        
        conn.commit()
        conn.close()
        
        flash(f"Статус заказа №{order_id} успешно изменен на \"{new_status}\"", "success")
        return redirect(url_for('orders'))
    
    except Exception as e:
        logging.error(f"Ошибка при изменении статуса заказа: {str(e)}")
        flash(f"Произошла ошибка при изменении статуса заказа.", "danger")
        return redirect(url_for('orders'))

@app.route("/api/delete_order", methods=["POST"])
def delete_order():
    """Удаление заказа из системы"""
    try:
        # Для обработки как JSON, так и form-data
        if request.is_json:
            data = request.json
            order_id = data.get('order_id')
        else:
            order_id = request.form.get('order_id')
        
        if not order_id:
            return jsonify({"success": False, "message": "Не указан ID заказа"})
        
        conn = get_db_connection()
        
        # Проверяем существование заказа
        order = conn.execute("SELECT id FROM orders WHERE id = ?", (order_id,)).fetchone()
        
        if not order:
            return jsonify({"success": False, "message": "Заказ не найден"})
        
        # Удаляем историю статусов
        conn.execute("DELETE FROM order_statuses WHERE order_id = ?", (order_id,))
        
        # Удаляем заказ
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        
        conn.commit()
        conn.close()
        
        flash(f"Заказ №{order_id} успешно удален", "success")
        return jsonify({"success": True})
    
    except Exception as e:
        logging.error(f"Ошибка при удалении заказа: {str(e)}")
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    # Создаем директорию для экспорта
    os.makedirs(os.path.join("static", "exports"), exist_ok=True)
    
    app.run(host="0.0.0.0", port=5000, debug=True)
@app.route("/tools")
def tools():
    """Страница с инструментами для работы с ботом"""
    return render_template('tools.html')

@app.route("/api/bot_backup")
def bot_backup():
    """API для скачивания резервной копии базы данных бота"""
    import shutil
    from flask import send_file
    import tempfile
    import os
    
    try:
        # Создаем временную копию базы данных
        temp_dir = tempfile.gettempdir()
        backup_path = os.path.join(temp_dir, "bot_backup.db")
        
        # Копируем файл базы данных
        shutil.copy2("bot.db", backup_path)
        
        # Отправляем файл на скачивание
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=f"bot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            mimetype="application/octet-stream"
        )
    except Exception as e:
        flash(f"Ошибка при создании резервной копии: {str(e)}", "danger")
        return redirect(url_for('tools'))

@app.route("/api/bot_archive")
def bot_archive():
    """API для скачивания архива всех файлов бота"""
    import shutil
    from flask import send_file
    import tempfile
    import os
    import zipfile
    
    try:
        # Создаем временную директорию для архива
        temp_dir = tempfile.gettempdir()
        archive_path = os.path.join(temp_dir, "bot_archive.zip")
        
        # Создаем архив
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Добавляем основные файлы
            for file in ['botf.py', 'run.py', 'main.py', 'bot.db']:
                if os.path.exists(file):
                    zipf.write(file)
            
            # Добавляем шаблоны
            for root, dirs, files in os.walk('templates'):
                for file in files:
                    zipf.write(os.path.join(root, file))
            
            # Добавляем статические файлы
            for root, dirs, files in os.walk('static'):
                for file in files:
                    zipf.write(os.path.join(root, file))
            
            # Добавляем документацию в README.md файл
            with open(os.path.join(temp_dir, "README.md"), 'w') as readme:
                readme.write("# Бот 'Золотая рыбка'\n\n")
                readme.write("## Описание проекта\n")
                readme.write("Telegram-бот для заказа рыбы с веб-панелью администратора.\n\n")
                readme.write("## Структура проекта\n")
                readme.write("- botf.py - Основной файл бота\n")
                readme.write("- run.py - Скрипт для запуска бота\n")
                readme.write("- main.py - Flask-приложение для админ-панели\n")
                readme.write("- bot.db - База данных SQLite\n\n")
                readme.write("## Настройка\n")
                readme.write("1. Установите зависимости: aiogram, flask, flask-login, requests\n") 
                readme.write("2. Настройте переменные окружения для токенов Telegram\n")
                readme.write("3. Запустите бота с помощью run.py\n\n")
                readme.write("## Промокоды\n")
                readme.write("- РЫБА2025 - Общий промокод для всех пользователей\n")
                readme.write("- ЗОЛОТО - Специальный промокод для клиентов с 3+ заказами\n\n")
                readme.write("## Контакты\n")
                readme.write("По всем вопросам обращайтесь в поддержку бота.\n")
            
            zipf.write(os.path.join(temp_dir, "README.md"), "README.md")
        
        # Отправляем архив на скачивание
        return send_file(
            archive_path,
            as_attachment=True,
            download_name=f"bot_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mimetype="application/zip"
        )
    except Exception as e:
        flash(f"Ошибка при создании архива: {str(e)}", "danger")
        return redirect(url_for('tools'))

@app.route("/api/send_broadcast", methods=["POST"])
def send_broadcast():
    """API для отправки рассылок через бота"""
    import sqlite3
    import os
    import json
    import requests
    
    try:
        # Получаем данные формы
        text = request.form.get("broadcast_text")
        send_all = request.form.get("send_all") == "on"
        user_group = request.form.get("user_group")
        
        # Проверяем, что текст сообщения указан
        if not text:
            return jsonify({"success": False, "error": "Не указан текст сообщения"})
        
        # Обрабатываем изображение, если оно есть
        image_file = request.files.get("broadcast_image")
        image_path = None
        
        if image_file and image_file.filename:
            # Проверяем, что это изображение
            if not image_file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                return jsonify({"success": False, "error": "Файл должен быть изображением (PNG, JPG, JPEG, GIF)"})
            
            # Создаем временную директорию для хранения изображения
            import tempfile
            temp_dir = tempfile.gettempdir()
            image_path = os.path.join(temp_dir, f"broadcast_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            image_file.save(image_path)
        
        # Получаем токен бота из переменных окружения
        telegram_token = os.environ.get("TELEGRAM_TOKEN", "7902503164:AAFUVT64sz45cC22Idgwbr3fN3oAdKhP70k")
        
        # Определяем целевую аудиторию для рассылки
        conn = get_db_connection()
        
        if send_all:
            # Получаем всех пользователей
            users = conn.execute("SELECT DISTINCT user_id FROM orders").fetchall()
            leads = conn.execute("SELECT DISTINCT user_id FROM leads").fetchall()
            
            # Объединяем списки пользователей
            all_users = set()
            for user in users:
                all_users.add(user['user_id'])
            for lead in leads:
                all_users.add(lead['user_id'])
            
            target_users = list(all_users)
        else:
            # Фильтруем пользователей по выбранной группе
            if user_group == "active":
                # Активные пользователи (последняя активность за последние 30 дней)
                target_users = conn.execute("""
                    SELECT DISTINCT user_id FROM orders 
                    WHERE timestamp > datetime('now', '-30 days')
                """).fetchall()
            elif user_group == "new":
                # Новые пользователи (за последний месяц)
                target_users = conn.execute("""
                    SELECT DISTINCT user_id FROM (
                        SELECT user_id, MIN(timestamp) as first_activity 
                        FROM orders 
                        GROUP BY user_id
                    ) WHERE first_activity > datetime('now', '-30 days')
                """).fetchall()
            elif user_group == "customers":
                # Клиенты, оформившие заказы
                target_users = conn.execute("""
                    SELECT DISTINCT user_id FROM orders 
                    WHERE status IN ('Принят', 'Готовится', 'Доставляется', 'Выполнен')
                """).fetchall()
            elif user_group == "leads":
                # Незавершенные лиды
                target_users = conn.execute("""
                    SELECT DISTINCT user_id FROM leads 
                    WHERE is_completed = 0 AND status != 'expired'
                """).fetchall()
            else:
                return jsonify({"success": False, "error": "Неизвестная группа пользователей"})
            
            # Преобразуем результат запроса в список
            target_users = [user['user_id'] for user in target_users]
        
        conn.close()
        
        # Отправляем сообщения
        sent_count = 0
        error_count = 0
        error_list = []
        
        for user_id in target_users:
            try:
                if image_path:
                    # Отправляем изображение с подписью
                    with open(image_path, 'rb') as img:
                        url = f"https://api.telegram.org/bot{telegram_token}/sendPhoto"
                        files = {'photo': img}
                        data = {'chat_id': user_id, 'caption': text}
                        response = requests.post(url, files=files, data=data)
                else:
                    # Отправляем текстовое сообщение
                    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                    data = {'chat_id': user_id, 'text': text, 'parse_mode': 'HTML'}
                    response = requests.post(url, json=data)
                
                if response.status_code == 200:
                    sent_count += 1
                else:
                    error_data = response.json()
                    error_count += 1
                    error_list.append({
                        'user_id': user_id,
                        'error': f"Ошибка {response.status_code}: {error_data.get('description', 'Неизвестная ошибка')}"
                    })
            except Exception as e:
                error_count += 1
                error_list.append({
                    'user_id': user_id,
                    'error': str(e)
                })
        
        # Удаляем временный файл изображения, если он был создан
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        
        return jsonify({
            "success": True, 
            "sent": sent_count, 
            "errors": error_count,
            "error_list": error_list
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
