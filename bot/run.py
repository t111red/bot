#!/usr/bin/env python3
import os
import time
import subprocess
import threading
import signal
import logging
import sys
import psutil
import socket
import importlib
import traceback

# Обеспечиваем работу из любой директории
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
os.chdir(script_dir)  # Устанавливаем рабочую директорию в директорию скрипта

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Глобальные переменные
bot_process = None
sync_process = None
web_process = None
miniapp_process = None
running = True

# Файлы для отслеживания состояния процессов
BOT_PID_FILE = "bot.pid"
SYNC_PID_FILE = "sync.pid"
WEB_PID_FILE = "web.pid"

def signal_handler(sig, frame):
    """Обработчик сигналов для корректного завершения процессов."""
    global running
    logging.info("Получен сигнал завершения, останавливаем процессы...")
    running = False
    stop_processes()
    sys.exit(0)

def is_port_in_use(port):
    """Проверяет, занят ли указанный порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def is_process_running(pid_file):
    """Проверяет, запущен ли процесс по PID из файла."""
    if not os.path.exists(pid_file):
        return False
        
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
            
        # Проверяем, существует ли процесс с таким PID
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            # Если процесс зомби, считаем его неработающим
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
            return True
        return False
    except (ValueError, ProcessLookupError, psutil.NoSuchProcess):
        return False

def save_pid(pid, pid_file):
    """Сохраняет PID процесса в файл."""
    with open(pid_file, 'w') as f:
        f.write(str(pid))

def remove_pid_file(pid_file):
    """Удаляет файл с PID."""
    if os.path.exists(pid_file):
        os.remove(pid_file)

def start_bot():
    """Запускает бота и направляет логи сразу в консоль."""
    import subprocess  # Локальный импорт для обеспечения доступности
    global bot_process
    
    # Проверяем, не запущен ли уже бот
    if is_process_running(BOT_PID_FILE):
        logging.info("⚠️ Бот уже запущен, пропускаем запуск")
        return
    
    logging.info("🚀 Запускаем бота...")
    
    # Получаем текущий путь скрипта
    current_dir = os.path.dirname(os.path.abspath(__file__))
    botf_path = os.path.join(current_dir, "botf.py")
    
    # Запускаем процесс бота
    bot_process = subprocess.Popen(
        ["python", botf_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir  # Устанавливаем рабочую директорию
    )
    
    # Сохраняем PID бота в файл
    save_pid(bot_process.pid, BOT_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(bot_process.stdout, "БОТ")

def start_web_app():
    """Запускает веб-приложение администратора."""
    global web_process
    
    # Проверяем, не запущено ли уже веб-приложение
    if is_process_running(WEB_PID_FILE):
        logging.info("⚠️ Веб-приложение уже запущено, пропускаем запуск")
        return
    
    # Проверяем, не занят ли порт 5000
    if is_port_in_use(5000):
        logging.warning("⚠️ Порт 5000 уже используется, попытка освободить...")
        # На Replit не используем connections, просто завершаем процессы на этом порту
        try:
            # Используем lsof или netstat для поиска процессов, если они доступны
            import subprocess
            try:
                # Пробуем lsof (Linux/Mac)
                output = subprocess.check_output(["lsof", "-i", ":5000", "-t"], text=True)
                pids = [int(pid.strip()) for pid in output.split('\n') if pid.strip()]
                
                for pid in pids:
                    logging.info(f"Завершаем процесс {pid}, использующий порт 5000")
                    try:
                        proc = psutil.Process(pid)
                        proc.terminate()
                        proc.wait(timeout=3)
                    except (ProcessLookupError, psutil.NoSuchProcess):
                        pass
            except (subprocess.SubprocessError, FileNotFoundError):
                logging.warning("Не удалось использовать lsof для поиска процессов")
                
                # Альтернативный подход - просто убиваем все gunicorn-процессы
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if 'gunicorn' in proc.info['name'].lower():
                            logging.info(f"Завершаем gunicorn процесс {proc.info['pid']}")
                            proc.terminate()
                            proc.wait(timeout=3)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
        except Exception as e:
            logging.error(f"Ошибка при попытке освободить порт 5000: {e}")
    
    logging.info("🌐 Запускаем веб-приложение администратора...")
    
    # Получаем текущий путь скрипта
    current_dir = os.path.dirname(os.path.abspath(__file__))
    main_path = os.path.join(current_dir, "main.py")
    
    # Запускаем веб-приложение через прямой путь к main.py
    import subprocess as sp
    import platform
    main_file = os.path.join(current_dir, "main.py")
    
    # На Windows используем прямой запуск Flask вместо gunicorn
    if platform.system() == 'Windows':
        logging.info("Определена ОС Windows, запускаем веб-приложение через Flask без gunicorn")
        web_process = sp.Popen(
            [sys.executable, "-c", 
             "import sys; sys.path.insert(0, '.'); from main import app; app.run(host='0.0.0.0', port=5000, debug=False)"],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            bufsize=1,
            cwd=current_dir
        )
    else:
        # На Unix-системах используем gunicorn
        web_process = sp.Popen(
            ["gunicorn", "--bind", "0.0.0.0:5000", "--reuse-port", "--reload", 
             "--pythonpath", current_dir, "main:app"],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            text=True,
            bufsize=1,
            cwd=current_dir  # Устанавливаем рабочую директорию
        )
    
    # Сохраняем PID веб-приложения в файл
    save_pid(web_process.pid, WEB_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(web_process.stdout, "ВЕБ")

def start_sync_service():
    """Запускает сервис внутренней синхронизации."""
    import subprocess  # Локальный импорт для обеспечения доступности
    global sync_process
    
    # Проверяем, не запущен ли уже сервис синхронизации
    if is_process_running(SYNC_PID_FILE):
        logging.info("⚠️ Сервис синхронизации уже запущен, пропускаем запуск")
        return
    
    logging.info("🔄 Запускаем сервис синхронизации...")
    
    # Получаем текущий путь скрипта
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Запускаем сервис синхронизации
    sync_process = subprocess.Popen(
        ["python", "-c", "from sync_service import InternalSyncService; InternalSyncService().run()"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir  # Устанавливаем рабочую директорию
    )
    
    # Сохраняем PID сервиса синхронизации в файл
    save_pid(sync_process.pid, SYNC_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(sync_process.stdout, "СИНХРОНИЗАЦИЯ")

def start_output_reader(pipe, prefix):
    """Запускает обработчик вывода процесса в отдельном потоке."""
    def reader_thread():
        for line in iter(pipe.readline, ''):
            if line:
                # Убираем лишние переносы строк
                line = line.rstrip()
                if line:
                    logging.info(f"[{prefix}] {line}")
    
    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()
    return thread

def stop_processes():
    """Останавливает все запущенные процессы."""
    global bot_process, sync_process, web_process, miniapp_process
    
    logging.info("Останавливаем все процессы...")
    
    # Останавливаем бота
    if bot_process and bot_process.poll() is None:
        try:
            bot_process.terminate()
            bot_process.wait(timeout=5)
        except:
            bot_process.kill()
        remove_pid_file(BOT_PID_FILE)
    
    # Останавливаем сервис синхронизации
    if sync_process and sync_process.poll() is None:
        try:
            sync_process.terminate()
            sync_process.wait(timeout=5)
        except:
            sync_process.kill()
        remove_pid_file(SYNC_PID_FILE)
    
    # Останавливаем веб-приложение
    if web_process and web_process.poll() is None:
        try:
            web_process.terminate()
            web_process.wait(timeout=5)
        except:
            web_process.kill()
        remove_pid_file(WEB_PID_FILE)
    
    # Останавливаем мини-приложение
    if miniapp_process and miniapp_process.poll() is None:
        try:
            miniapp_process.terminate()
            miniapp_process.wait(timeout=5)
        except:
            miniapp_process.kill()
        remove_pid_file("miniapp.pid")
    
    logging.info("Все процессы остановлены")

# Функция автоматического перезапуска бота при изменениях в файлах отключена
# Теперь перезапуск должен производиться вручную для повышения стабильности

def restart_bot():
    """Перезапускает бота."""
    global bot_process
    
    logging.info("🔄 Перезапускаем бота...")
    
    # Останавливаем текущий процесс бота
    if bot_process and bot_process.poll() is None:
        try:
            bot_process.terminate()
            bot_process.wait(timeout=5)
        except:
            bot_process.kill()
    
    # Удаляем файл с PID
    remove_pid_file(BOT_PID_FILE)
    
    # Запускаем бота снова
    start_bot()

def check_duplicate_processes():
    """Проверяет наличие дублирующихся процессов и завершает их."""
    
    # Проверка процессов бота по имени 'python' и аргументу 'botf.py'
    bot_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python' or proc.info['name'] == 'python3':
                cmdline = proc.info['cmdline']
                if cmdline and any('botf.py' in arg for arg in cmdline):
                    bot_processes.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if len(bot_processes) > 1:
        logging.warning(f"⚠️ Обнаружено {len(bot_processes)} запущенных процессов бота")
        # Сохраняем первый процесс, остальные завершаем
        for pid in bot_processes[1:]:
            try:
                proc = psutil.Process(pid)
                logging.info(f"🛑 Завершаем лишний процесс бота (PID: {pid})")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
            except (ProcessLookupError, psutil.NoSuchProcess):
                continue
    
    # Проверка процессов синхронизации
    sync_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python' or proc.info['name'] == 'python3':
                cmdline = proc.info['cmdline']
                if cmdline and any('InternalSyncService' in arg for arg in cmdline):
                    sync_processes.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if len(sync_processes) > 1:
        logging.warning(f"⚠️ Обнаружено {len(sync_processes)} запущенных процессов синхронизации")
        # Сохраняем первый процесс, остальные завершаем
        for pid in sync_processes[1:]:
            try:
                proc = psutil.Process(pid)
                logging.info(f"🛑 Завершаем лишний процесс синхронизации (PID: {pid})")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    proc.kill()
            except (ProcessLookupError, psutil.NoSuchProcess):
                continue

def check_processes():
    """Проверяет состояние запущенных процессов и перезапускает их при необходимости."""
    global bot_process, sync_process, web_process, miniapp_process
    
    # Проверяем состояние бота
    if bot_process and bot_process.poll() is not None:
        logging.warning("⚠️ Обнаружено завершение процесса бота, перезапускаем...")
        remove_pid_file(BOT_PID_FILE)
        start_bot()
    elif not bot_process and not is_process_running(BOT_PID_FILE):
        start_bot()
    
    # Проверяем состояние сервиса синхронизации
    if sync_process and sync_process.poll() is not None:
        logging.warning("⚠️ Обнаружено завершение процесса синхронизации, перезапускаем...")
        remove_pid_file(SYNC_PID_FILE)
        start_sync_service()
    elif not sync_process and not is_process_running(SYNC_PID_FILE):
        start_sync_service()
    
    # Проверяем состояние веб-приложения
    if web_process and web_process.poll() is not None:
        logging.warning("⚠️ Обнаружено завершение процесса веб-приложения, перезапускаем...")
        remove_pid_file(WEB_PID_FILE)
        start_web_app()
    elif not web_process and not is_process_running(WEB_PID_FILE):
        start_web_app()
        
    # Проверяем состояние мини-приложения
    if miniapp_process and miniapp_process.poll() is not None:
        logging.warning("⚠️ Обнаружено завершение процесса мини-приложения, перезапускаем...")
        remove_pid_file("miniapp.pid")
        start_miniapp()
    elif not miniapp_process and not is_process_running("miniapp.pid"):
        start_miniapp()
        
    # Проверка на дублирующиеся процессы бота
    check_duplicate_processes()

def cleanup_orphaned_processes():
    """Очистка процессов-сирот, которые могли остаться от предыдущих запусков."""
    import os  # Локально импортируем os для надежности
    import psutil  # Локально импортируем psutil
    logging.info("Проверка на наличие процессов-сирот от предыдущих запусков...")
    
    # Проверяем процессы бота
    if os.path.exists(BOT_PID_FILE):
        try:
            with open(BOT_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    logging.info(f"Завершаем процесс бота с PID {pid} от предыдущего запуска")
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
        except (ValueError, ProcessLookupError, psutil.NoSuchProcess):
            pass
        try:
            os.remove(BOT_PID_FILE)
        except FileNotFoundError:
            # Игнорируем, если файл уже был удален
            pass
    
    # Проверяем процессы синхронизации
    if os.path.exists(SYNC_PID_FILE):
        try:
            with open(SYNC_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    logging.info(f"Завершаем процесс синхронизации с PID {pid} от предыдущего запуска")
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
        except (ValueError, ProcessLookupError, psutil.NoSuchProcess):
            pass
        try:
            os.remove(SYNC_PID_FILE)
        except FileNotFoundError:
            # Игнорируем, если файл уже был удален
            pass
    
    # Проверяем процессы веб-приложения
    if os.path.exists(WEB_PID_FILE):
        try:
            with open(WEB_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    logging.info(f"Завершаем процесс веб-приложения с PID {pid} от предыдущего запуска")
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
        except (ValueError, ProcessLookupError, psutil.NoSuchProcess):
            pass
        try:
            os.remove(WEB_PID_FILE)
        except FileNotFoundError:
            # Игнорируем, если файл уже был удален
            pass
    
    # Освобождаем порт 5000, если он занят
    if is_port_in_use(5000):
        logging.info("Освобождаем порт 5000...")
        # Используем более простой подход, так как connections может быть недоступен на некоторых системах
        try:
            import subprocess
            output = subprocess.check_output(['lsof', '-i', ':5000', '-t'], stderr=subprocess.DEVNULL, text=True)
            if output:
                for pid in output.strip().split('\n'):
                    if pid:
                        pid = int(pid)
                        logging.info(f"Завершаем процесс {pid}, использующий порт 5000")
                        try:
                            proc = psutil.Process(pid)
                            proc.terminate()
                            proc.wait(timeout=3)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                            try:
                                import os
                                os.kill(pid, 9)  # SIGKILL
                            except:
                                pass
        except:
            # Альтернативный метод, просто ищем и завершаем gunicorn процессы
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and 'gunicorn' in proc.info['name']:
                        logging.info(f"Завершаем gunicorn процесс {proc.info['pid']}")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue

def start_miniapp():
    """Запускает мини-приложение для заказа рыбы."""
    import subprocess  # Локальный импорт для обеспечения доступности
    import os  # Локальный импорт для обеспечения доступности
    global miniapp_process
    
    # Получаем текущий путь скрипта
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Проверяем, не запущено ли уже мини-приложение
    miniapp_pid_file = os.path.join(current_dir, "miniapp.pid")
    if is_process_running(miniapp_pid_file):
        logging.info("⚠️ Мини-приложение уже запущено, пропускаем запуск")
        return
    
    # Проверяем, не занят ли порт 8080
    if is_port_in_use(8080):
        logging.warning("⚠️ Порт 8080 уже используется, попытка освободить...")
        # На Replit не используем connections, просто завершаем процессы на этом порту
        try:
            # Используем lsof или netstat для поиска процессов, если они доступны
            import subprocess
            try:
                # Пробуем lsof (Linux/Mac)
                output = subprocess.check_output(["lsof", "-i", ":8080", "-t"], text=True)
                pids = [int(pid.strip()) for pid in output.split('\n') if pid.strip()]
                
                for pid in pids:
                    logging.info(f"Завершаем процесс {pid}, использующий порт 8080")
                    try:
                        proc = psutil.Process(pid)
                        proc.terminate()
                        proc.wait(timeout=3)
                    except (ProcessLookupError, psutil.NoSuchProcess):
                        pass
            except (subprocess.SubprocessError, FileNotFoundError):
                logging.warning("Не удалось использовать lsof для поиска процессов")
                
                # Альтернативный подход - завершаем все flask-процессы
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if 'flask' in proc.info['name'].lower():
                            logging.info(f"Завершаем flask процесс {proc.info['pid']}")
                            proc.terminate()
                            proc.wait(timeout=3)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
        except Exception as e:
            logging.error(f"Ошибка при попытке освободить порт 8080: {e}")
    
    # Импортируем код запуска Mini App прямо здесь
    from flask import Flask, render_template, send_from_directory, request, jsonify
    
    # Создаем Flask приложение для Mini App
    miniapp = Flask(__name__, 
                  static_folder='static/webapp',
                  template_folder='static/webapp')
    
    @miniapp.route('/')
    def index():
        """Главная страница Mini App"""
        return render_template('index.html')
    
    @miniapp.route('/<path:path>')
    def serve_static(path):
        """Обслуживание статических файлов"""
        return send_from_directory('static/webapp', path)
    
    # Импортируем json для корректной работы с JSON-данными
    import json
    
    @miniapp.route('/api/process-order', methods=['POST', 'OPTIONS'])
    def process_order():
        """API для обработки заказов из Mini App"""
        # Обработка OPTIONS запросов для CORS
        if request.method == 'OPTIONS':
            response = jsonify({})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Telegram-Data,X-Requested-With')
            response.headers.add('Access-Control-Allow-Methods', 'POST')
            return response
            
        if not request.is_json:
            logging.error(f"[MiniApp] Неверный формат запроса, Content-Type: {request.content_type}")
            return jsonify({"error": "Ожидается JSON формат данных", "success": False}), 400
            
        # Получаем данные заказа из запроса
        order_data = request.get_json()
        if not order_data:
            logging.error("[MiniApp] Отсутствуют данные заказа в запросе")
            return jsonify({"error": "Отсутствуют данные заказа", "success": False}), 400
            
        logging.info(f"[MiniApp] Данные заказа: {json.dumps(order_data, ensure_ascii=False)}")
            
        # Проверка обязательных полей
        required_fields = ['name', 'phone', 'items']
        missing_fields = []
        for field in required_fields:
            if field not in order_data or not order_data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            logging.error(f"[MiniApp] Отсутствуют обязательные поля: {', '.join(missing_fields)}")
            return jsonify({
                "error": f"Отсутствуют обязательные поля: {', '.join(missing_fields)}", 
                "success": False,
                "missingFields": missing_fields
            }), 400
        
        # Обработка списка товаров - нормализация данных
        items = order_data.get('items', [])
        if isinstance(items, list):
            # Создаем нормализованный список товаров
            normalized_items = []
            for item in items:
                if isinstance(item, dict):
                    normalized_item = {}
                    # Получаем размер товара
                    size = item.get('size')
                    if size:
                        normalized_item['size'] = size
                    
                    # Получаем имя товара или используем размер
                    name = item.get('name')
                    if name:
                        normalized_item['name'] = name
                    elif size:
                        normalized_item['name'] = size
                    else:
                        normalized_item['name'] = 'Неизвестный товар'
                    
                    # Получаем количество
                    quantity = item.get('quantity', 1)
                    normalized_item['quantity'] = quantity
                    
                    # Получаем или вычисляем цену
                    price = item.get('price')
                    if price:
                        normalized_item['price'] = price
                    else:
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
            order_data['items'] = normalized_items
        
        # Генерируем уникальный ID заказа
        import time
        from datetime import datetime
        order_id = int(time.time() * 1000) % 10000000  # Более короткий ID заказа
        
        # Возвращаем успешный ответ с ID заказа
        return jsonify({
            'success': True,
            'orderId': order_id,
            'message': 'Заказ успешно создан!'
        })
    
    logging.info("🚀 Запускаем Telegram Mini App на порту 8080...")
    
    # Запускаем мини-приложение напрямую через python
    miniapp_path = os.path.join(current_dir, "miniapp.py")
    # Готовим строку с путем к директории в безопасном формате
    app_dir = current_dir.replace("\\", "\\\\")  # Экранируем обратные слеши для Windows
    miniapp_code = f"""
import os
import sys
from flask import Flask, render_template, send_from_directory, request, jsonify

current_dir = '{app_dir}'  # Используем фактический путь из основного скрипта
app = Flask(__name__, 
           static_folder=os.path.join(current_dir, "static", "webapp"), 
           template_folder=os.path.join(current_dir, "static", "webapp"))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(current_dir, "static", "webapp"), path)

@app.route('/api/order', methods=['POST'])
def process_order():
    \"\"\"Обработка API заказов.\"\"\"
    try:
        order_data = request.get_json(silent=True) or {{}}
        print("Получен заказ через API:", str(order_data))
        return jsonify({{"success": True, "message": "Заказ получен"}})
    except Exception:
        import traceback
        error_text = traceback.format_exc()
        print("Ошибка при обработке заказа:", error_text)
        return jsonify({{"success": False, "message": "Ошибка обработки заказа"}}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
else:
    # Для запуска через gunicorn или другой WSGI-сервер
    application = app

# Запускаем без режима отладки для совместимости с Windows
app.run(host='0.0.0.0', port=8080, debug=False)
"""
    
    miniapp_process = subprocess.Popen(
        ["python", "-c", miniapp_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    # Сохраняем PID мини-приложения в файл
    save_pid(miniapp_process.pid, miniapp_pid_file)
    
    # Запускаем поток для чтения вывода
    start_output_reader(miniapp_process.stdout, "MINIAPP")

def main():
    """Основная функция запуска."""
    # Регистрация обработчика сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Очистка процессов от предыдущего запуска
    cleanup_orphaned_processes()
    
    # Запуск всех компонентов
    start_bot()
    start_sync_service()
    start_web_app()
    start_miniapp()  # Добавляем запуск Telegram Mini App
    
    # Автоматический мониторинг изменений файлов отключен для повышения стабильности
    logging.info("Запуск в стабильном режиме без автоматического отслеживания изменений в файлах")
    
    try:
        # Основной цикл
        while running:
            check_processes()
            time.sleep(5)
    except KeyboardInterrupt:
        print("Получен сигнал прерывания, завершение работы...")
    finally:
        # Останавливаем все процессы
        stop_processes()

if __name__ == "__main__":
    print(f"🐟 Запуск системы 'Золотая рыбка' v1.0")
    main()