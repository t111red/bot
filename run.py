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
cloudflared_web_process = None
cloudflared_miniapp_process = None
running = True

# Файлы для отслеживания состояния процессов
BOT_PID_FILE = "bot.pid"
SYNC_PID_FILE = "sync.pid"
WEB_PID_FILE = "web.pid"
MINIAPP_PID_FILE = "miniapp.pid"

# URL-адреса для доступа
web_url = None
miniapp_url = None

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

def kill_process_on_port(port):
    """Завершает процессы, использующие указанный порт."""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                connections = proc.info['connections']
                if connections:
                    for conn in connections:
                        if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                            logging.info(f"Завершаем процесс {proc.info['pid']} ({proc.info['name']}), использующий порт {port}")
                            proc.terminate()
                            try:
                                proc.wait(timeout=3)
                            except psutil.TimeoutExpired:
                                proc.kill()
                            break
            except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
                continue
    except Exception as e:
        logging.error(f"Ошибка при освобождении порта {port}: {e}")

def start_cloudflared_tunnel(port, service_name):
    """Запускает cloudflared туннель для указанного порта."""
    try:
        # Проверяем, установлен ли cloudflared
        result = subprocess.run(['cloudflared', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logging.warning("cloudflared не установлен. Пропускаем создание туннелей.")
            return None, None
            
        logging.info(f"🌐 Запускаем cloudflared туннель для {service_name} на порту {port}...")
        
        # Запускаем cloudflared туннель
        process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', f'http://localhost:{port}'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Ждем получения URL
        url = None
        start_time = time.time()
        while time.time() - start_time < 30:  # Ждем максимум 30 секунд
            line = process.stdout.readline()
            if line:
                logging.info(f"[CLOUDFLARED-{service_name.upper()}] {line.strip()}")
                if 'https://' in line and '.trycloudflare.com' in line:
                    # Извлекаем URL из строки
                    import re
                    url_match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                    if url_match:
                        url = url_match.group(0)
                        logging.info(f"✅ {service_name} доступен по адресу: {url}")
                        break
            
            if process.poll() is not None:
                logging.error(f"cloudflared для {service_name} завершился с кодом {process.returncode}")
                break
                
            time.sleep(0.5)
        
        if not url:
            logging.warning(f"Не удалось получить URL для {service_name}")
            if process.poll() is None:
                process.terminate()
            return None, None
            
        # Запускаем поток для чтения оставшегося вывода
        start_output_reader(process.stdout, f"CLOUDFLARED-{service_name.upper()}")
        
        return process, url
        
    except FileNotFoundError:
        logging.warning("cloudflared не найден в PATH. Пропускаем создание туннелей.")
        return None, None
    except Exception as e:
        logging.error(f"Ошибка при запуске cloudflared для {service_name}: {e}")
        return None, None

def start_bot():
    """Запускает бота и направляет логи сразу в консоль."""
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
        [sys.executable, botf_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    # Сохраняем PID бота в файл
    save_pid(bot_process.pid, BOT_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(bot_process.stdout, "БОТ")

def start_web_app():
    """Запускает веб-приложение администратора через Flask."""
    global web_process, cloudflared_web_process, web_url
    
    # Проверяем, не запущено ли уже веб-приложение
    if is_process_running(WEB_PID_FILE):
        logging.info("⚠️ Веб-приложение уже запущено, пропускаем запуск")
        return
    
    # Освобождаем порт 5000 если он занят
    if is_port_in_use(5000):
        logging.warning("⚠️ Порт 5000 уже используется, освобождаем...")
        kill_process_on_port(5000)
        time.sleep(2)
    
    logging.info("🌐 Запускаем веб-приложение администратора на порту 5000...")
    
    # Получаем текущий путь скрипта
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Запускаем веб-приложение через Flask
    web_process = subprocess.Popen(
        [sys.executable, "-c", 
         "import sys; sys.path.insert(0, '.'); from main import app; app.run(host='0.0.0.0', port=5000, debug=False)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    # Сохраняем PID веб-приложения в файл
    save_pid(web_process.pid, WEB_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(web_process.stdout, "ВЕБ")
    
    # Ждем запуска веб-приложения
    time.sleep(3)
    
    # Запускаем cloudflared туннель для веб-приложения
    cloudflared_web_process, web_url = start_cloudflared_tunnel(5000, "веб-приложение")

def start_sync_service():
    """Запускает сервис внутренней синхронизации."""
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
        [sys.executable, "-c", "from sync_service import InternalSyncService; InternalSyncService().run()"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=current_dir
    )
    
    # Сохраняем PID сервиса синхронизации в файл
    save_pid(sync_process.pid, SYNC_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(sync_process.stdout, "СИНХРОНИЗАЦИЯ")

def start_miniapp():
    """Запускает мини-приложение для заказа рыбы."""
    global miniapp_process, cloudflared_miniapp_process, miniapp_url
    
    # Получаем текущий путь скрипта
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Проверяем, не запущено ли уже мини-приложение
    if is_process_running(MINIAPP_PID_FILE):
        logging.info("⚠️ Мини-приложение уже запущено, пропускаем запуск")
        return
    
    # Освобождаем порт 8080 если он занят
    if is_port_in_use(8080):
        logging.warning("⚠️ Порт 8080 уже используется, освобождаем...")
        kill_process_on_port(8080)
        time.sleep(2)
    
    logging.info("🚀 Запускаем Telegram Mini App на порту 8080...")
    
    # Готовим код для мини-приложения
    miniapp_code = f"""
import os
import sys
from flask import Flask, render_template, send_from_directory, request, jsonify

current_dir = r'{current_dir}'
app = Flask(__name__, 
           static_folder=os.path.join(current_dir, "static", "webapp"), 
           template_folder=os.path.join(current_dir, "static", "webapp"))

@app.route('/')
def index():
    return render_template('basic.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(current_dir, "static", "webapp"), path)

@app.route('/webapp/<path:path>')
def serve_webapp(path):
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
        
        # Генерируем ID заказа
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
    
    # Сохраняем PID мини-приложения в файл
    save_pid(miniapp_process.pid, MINIAPP_PID_FILE)
    
    # Запускаем поток для чтения вывода
    start_output_reader(miniapp_process.stdout, "MINIAPP")
    
    # Ждем запуска мини-приложения
    time.sleep(3)
    
    # Запускаем cloudflared туннель для мини-приложения
    cloudflared_miniapp_process, miniapp_url = start_cloudflared_tunnel(8080, "мини-приложение")

def start_output_reader(pipe, prefix):
    """Запускает обработчик вывода процесса в отдельном потоке."""
    def reader_thread():
        try:
            for line in iter(pipe.readline, ''):
                if line:
                    # Убираем лишние переносы строк
                    line = line.rstrip()
                    if line:
                        logging.info(f"[{prefix}] {line}")
        except Exception as e:
            logging.error(f"Ошибка в потоке чтения для {prefix}: {e}")
    
    thread = threading.Thread(target=reader_thread, daemon=True)
    thread.start()
    return thread

def stop_processes():
    """Останавливает все запущенные процессы."""
    global bot_process, sync_process, web_process, miniapp_process
    global cloudflared_web_process, cloudflared_miniapp_process
    
    logging.info("Останавливаем все процессы...")
    
    # Останавливаем cloudflared туннели
    for process, name in [(cloudflared_web_process, "веб-туннель"), 
                         (cloudflared_miniapp_process, "miniapp-туннель")]:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
                logging.info(f"✅ {name} остановлен")
            except:
                try:
                    process.kill()
                except:
                    pass
    
    # Останавливаем основные процессы
    processes = [
        (bot_process, BOT_PID_FILE, "бот"),
        (sync_process, SYNC_PID_FILE, "сервис синхронизации"),
        (web_process, WEB_PID_FILE, "веб-приложение"),
        (miniapp_process, MINIAPP_PID_FILE, "мини-приложение")
    ]
    
    for process, pid_file, name in processes:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
                logging.info(f"✅ {name} остановлен")
            except:
                try:
                    process.kill()
                except:
                    pass
            remove_pid_file(pid_file)
    
    logging.info("Все процессы остановлены")

def check_duplicate_processes():
    """Проверяет наличие дублирующихся процессов и завершает их."""
    
    # Проверка процессов бота по имени 'python' и аргументу 'botf.py'
    bot_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] in ['python', 'python3', 'python.exe']:
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
        
    # Проверка на дублирующиеся процессы бота
    check_duplicate_processes()

def cleanup_orphaned_processes():
    """Очистка процессов-сирот, которые могли остаться от предыдущих запусков."""
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

def print_access_info():
    """Выводит информацию о доступе к сервисам."""
    logging.info("=" * 80)
    logging.info("🐟 СИСТЕМА 'ЗОЛОТАЯ РЫБКА' ЗАПУЩЕНА")
    logging.info("=" * 80)
    
    logging.info("📍 ЛОКАЛЬНЫЕ АДРЕСА:")
    logging.info(f"   • Веб-панель администратора: http://localhost:5000")
    logging.info(f"   • Telegram Mini App: http://localhost:8080")
    
    if web_url or miniapp_url:
        logging.info("🌐 ПУБЛИЧНЫЕ АДРЕСА (через cloudflared):")
        if web_url:
            logging.info(f"   • Веб-панель администратора: {web_url}")
        if miniapp_url:
            logging.info(f"   • Telegram Mini App: {miniapp_url}")
    else:
        logging.info("⚠️  cloudflared не установлен или недоступен")
        logging.info("   Для публичного доступа установите cloudflared:")
        logging.info("   https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
    
    logging.info("=" * 80)
    logging.info("ℹ️  Для остановки системы нажмите Ctrl+C")
    logging.info("=" * 80)

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
    start_miniapp()
    
    # Ждем запуска всех сервисов
    time.sleep(5)
    
    # Выводим информацию о доступе
    print_access_info()
    
    try:
        # Основной цикл
        while running:
            check_processes()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nПолучен сигнал прерывания, завершение работы...")
    finally:
        # Останавливаем все процессы
        stop_processes()

if __name__ == "__main__":
    print(f"🐟 Запуск системы 'Золотая рыбка' v2.0 (Flask + cloudflared)")
    print(f"🖥️  Операционная система: {platform.system()} {platform.release()}")
    main()