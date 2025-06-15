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
import platform
import json
import traceback

# Обеспечиваем работу из любой директории
script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
os.chdir(script_dir)

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
cloudflared_web_process = None
cloudflared_miniapp_process = None
running = True

# Файлы для отслеживания состояния процессов
BOT_PID_FILE = "bot.pid"
SYNC_PID_FILE = "sync.pid"
WEB_PID_FILE = "web.pid"
MINIAPP_PID_FILE = "miniapp.pid"

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
            
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
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

def kill_process_on_port(port):
    """Завершает процессы, использующие указанный порт."""
    try:
        if platform.system() == "Windows":
            # Windows
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', pid], check=True)
                            logging.info(f"Завершен процесс {pid} на порту {port}")
                        except subprocess.CalledProcessError:
                            pass
        else:
            # Unix-like systems
            try:
                result = subprocess.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True)
                if result.stdout:
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        if pid:
                            try:
                                subprocess.run(['kill', '-9', pid], check=True)
                                logging.info(f"Завершен процесс {pid} на порту {port}")
                            except subprocess.CalledProcessError:
                                pass
            except FileNotFoundError:
                # lsof не найден, пробуем альтернативный метод
                pass
    except Exception as e:
        logging.warning(f"Ошибка при завершении процессов на порту {port}: {e}")

def start_cloudflared_tunnel(port, service_name):
    """Запускает cloudflared туннель для указанного порта."""
    try:
        # Проверяем, установлен ли cloudflared
        result = subprocess.run(['cloudflared', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            logging.warning("cloudflared не установлен. Пропускаем создание туннелей.")
            return None
            
        logging.info(f"🌐 Запускаем cloudflared туннель для {service_name} на порту {port}...")
        
        process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', f'http://localhost:{port}'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Запускаем поток для чтения вывода и извлечения URL
        def read_cloudflared_output():
            for line in iter(process.stdout.readline, ''):
                if line:
                    line = line.strip()
                    if 'trycloudflare.com' in line or 'https://' in line:
                        # Извлекаем URL из строки
                        parts = line.split()
                        for part in parts:
                            if 'https://' in part and 'trycloudflare.com' in part:
                                logging.info(f"🔗 {service_name} доступен по адресу: {part}")
                                break
                    if line:
                        logging.info(f"[CLOUDFLARED-{service_name.upper()}] {line}")
        
        thread = threading.Thread(target=read_cloudflared_output, daemon=True)
        thread.start()
        
        return process
        
    except FileNotFoundError:
        logging.warning("cloudflared не найден в PATH. Установите cloudflared для автоматического создания туннелей.")
        return None
    except Exception as e:
        logging.error(f"Ошибка при запуске cloudflared для {service_name}: {e}")
        return None

def start_bot():
    """Запускает бота."""
    global bot_process
    
    if is_process_running(BOT_PID_FILE):
        logging.info("⚠️ Бот уже запущен, пропускаем запуск")
        return
    
    logging.info("🚀 Запускаем бота...")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    botf_path = os.path.join(current_dir, "botf.py")
    
    bot_process = subprocess.Popen(
        [sys.executable, botf_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    save_pid(bot_process.pid, BOT_PID_FILE)
    start_output_reader(bot_process.stdout, "БОТ")

def start_web_app():
    """Запускает веб-приложение администратора на Flask."""
    global web_process, cloudflared_web_process
    
    if is_process_running(WEB_PID_FILE):
        logging.info("⚠️ Веб-приложение уже запущено, пропускаем запуск")
        return
    
    if is_port_in_use(5000):
        logging.warning("⚠️ Порт 5000 уже используется, освобождаем...")
        kill_process_on_port(5000)
        time.sleep(2)
    
    logging.info("🌐 Запускаем веб-приложение администратора на Flask...")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Запускаем Flask приложение напрямую
    web_process = subprocess.Popen(
        [sys.executable, "-c", 
         f"import sys; sys.path.insert(0, '{current_dir}'); "
         "from main import app; app.run(host='0.0.0.0', port=5000, debug=False)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    save_pid(web_process.pid, WEB_PID_FILE)
    start_output_reader(web_process.stdout, "ВЕБ")
    
    # Ждем немного, чтобы веб-сервер запустился
    time.sleep(3)
    
    # Запускаем cloudflared туннель для веб-приложения
    cloudflared_web_process = start_cloudflared_tunnel(5000, "Админ-панель")

def start_miniapp():
    """Запускает мини-приложение для заказа рыбы."""
    global miniapp_process, cloudflared_miniapp_process
    
    if is_process_running(MINIAPP_PID_FILE):
        logging.info("⚠️ Мини-приложение уже запущено, пропускаем запуск")
        return
    
    if is_port_in_use(8080):
        logging.warning("⚠️ Порт 8080 уже используется, освобождаем...")
        kill_process_on_port(8080)
        time.sleep(2)
    
    logging.info("🚀 Запускаем Telegram Mini App на порту 8080...")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    miniapp_code = f"""
import os
import sys
from flask import Flask, render_template, send_from_directory, request, jsonify

current_dir = '{current_dir.replace(chr(92), chr(92)+chr(92))}'
app = Flask(__name__, 
           static_folder=os.path.join(current_dir, "static", "webapp"), 
           template_folder=os.path.join(current_dir, "static", "webapp"))

@app.route('/')
def index():
    return render_template('basic.html')

@app.route('/webapp/<path:path>')
def serve_webapp_static(path):
    return send_from_directory(os.path.join(current_dir, "static", "webapp"), path)

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(current_dir, "static", "webapp"), path)

@app.route('/api/process_order', methods=['POST', 'OPTIONS'])
def process_order():
    if request.method == 'OPTIONS':
        response = jsonify({{}})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Telegram-Data,X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
        
    try:
        order_data = request.get_json(silent=True) or {{}}
        print("Получен заказ через API:", str(order_data))
        
        import time
        order_id = int(time.time() * 1000) % 10000000
        
        return jsonify({{"success": True, "orderId": order_id, "message": "Заказ получен"}})
    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        print("Ошибка при обработке заказа:", error_text)
        return jsonify({{"success": False, "message": "Ошибка обработки заказа"}}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
"""
    
    miniapp_process = subprocess.Popen(
        [sys.executable, "-c", miniapp_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    save_pid(miniapp_process.pid, MINIAPP_PID_FILE)
    start_output_reader(miniapp_process.stdout, "MINIAPP")
    
    # Ждем немного, чтобы мини-приложение запустилось
    time.sleep(3)
    
    # Запускаем cloudflared туннель для мини-приложения
    cloudflared_miniapp_process = start_cloudflared_tunnel(8080, "Mini App")

def start_sync_service():
    """Запускает сервис внутренней синхронизации."""
    global sync_process
    
    if is_process_running(SYNC_PID_FILE):
        logging.info("⚠️ Сервис синхронизации уже запущен, пропускаем запуск")
        return
    
    logging.info("🔄 Запускаем сервис синхронизации...")
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    sync_process = subprocess.Popen(
        [sys.executable, "-c", "from sync_service import InternalSyncService; InternalSyncService().run()"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    save_pid(sync_process.pid, SYNC_PID_FILE)
    start_output_reader(sync_process.stdout, "СИНХРОНИЗАЦИЯ")

def start_output_reader(pipe, prefix):
    """Запускает обработчик вывода процесса в отдельном потоке."""
    def reader_thread():
        for line in iter(pipe.readline, ''):
            if line:
                line = line.rstrip()
                if line:
                    logging.info(f"[{prefix}] {line}")
    
    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()
    return thread

def stop_processes():
    """Останавливает все запущенные процессы."""
    global bot_process, sync_process, web_process, miniapp_process
    global cloudflared_web_process, cloudflared_miniapp_process
    
    logging.info("Останавливаем все процессы...")
    
    processes = [
        (bot_process, BOT_PID_FILE, "бота"),
        (sync_process, SYNC_PID_FILE, "синхронизации"),
        (web_process, WEB_PID_FILE, "веб-приложения"),
        (miniapp_process, MINIAPP_PID_FILE, "мини-приложения"),
        (cloudflared_web_process, None, "cloudflared веб"),
        (cloudflared_miniapp_process, None, "cloudflared miniapp")
    ]
    
    for process, pid_file, name in processes:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
                logging.info(f"Процесс {name} остановлен")
            except:
                try:
                    process.kill()
                    logging.info(f"Процесс {name} принудительно завершен")
                except:
                    pass
            if pid_file:
                remove_pid_file(pid_file)
    
    logging.info("Все процессы остановлены")

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
        remove_pid_file(MINIAPP_PID_FILE)
        start_miniapp()
    elif not miniapp_process and not is_process_running(MINIAPP_PID_FILE):
        start_miniapp()

def cleanup_orphaned_processes():
    """Очистка процессов-сирот."""
    logging.info("Проверка на наличие процессов-сирот от предыдущих запусков...")
    
    pid_files = [BOT_PID_FILE, SYNC_PID_FILE, WEB_PID_FILE, MINIAPP_PID_FILE]
    
    for pid_file in pid_files:
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        logging.info(f"Завершаем процесс с PID {pid} от предыдущего запуска")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
            except (ValueError, ProcessLookupError, psutil.NoSuchProcess):
                pass
            try:
                os.remove(pid_file)
            except FileNotFoundError:
                pass
    
    # Освобождаем порты
    for port in [5000, 8080]:
        if is_port_in_use(port):
            logging.info(f"Освобождаем порт {port}...")
            kill_process_on_port(port)

def main():
    """Основная функция запуска."""
    # Регистрация обработчика сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Очистка процессов от предыдущего запуска
    cleanup_orphaned_processes()
    
    logging.info("🐟 Запуск системы 'Золотая рыбка' v2.0 (Flask + cloudflared)")
    logging.info(f"🖥️ Операционная система: {platform.system()} {platform.release()}")
    
    # Запуск всех компонентов
    start_bot()
    start_sync_service()
    start_web_app()
    start_miniapp()
    
    logging.info("✅ Все сервисы запущены")
    logging.info("📋 Локальные адреса:")
    logging.info("   - Админ-панель: http://localhost:5000")
    logging.info("   - Mini App: http://localhost:8080")
    logging.info("🌐 Публичные URL будут показаны выше после запуска cloudflared")
    
    try:
        while running:
            check_processes()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nПолучен сигнал прерывания, завершение работы...")
    finally:
        stop_processes()

if __name__ == "__main__":
    main()