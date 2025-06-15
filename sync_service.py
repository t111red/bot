import time
import sqlite3
import logging
import datetime
import signal
import sys
import os

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='[SYNC] %(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class InternalSyncService:
    def __init__(self):
        """Инициализирует сервис внутренней синхронизации."""
        self.conn = None
        self.is_running = True
        self.check_interval = 5  # Проверка каждые 5 секунд для более быстрой реакции
        logging.info("🔄 Сервис внутренней синхронизации инициализирован")
        
        # Регистрируем обработчики сигналов для корректного завершения
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, sig, frame):
        """Обрабатывает сигналы завершения."""
        logging.info("🛑 Получен сигнал завершения")
        self.is_running = False
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        sys.exit(0)
    
    def db_connect(self):
        """Подключается к базе данных бота."""
        try:
            if self.conn:
                try:
                    # Проверяем подключение
                    self.conn.execute("SELECT 1")
                    return self.conn
                except:
                    # Если подключение не работает, закрываем его
                    try:
                        self.conn.close()
                    except:
                        pass
                    self.conn = None
            
            # Получаем текущий путь скрипта
            current_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(current_dir, "bot.db")
            
            self.conn = sqlite3.connect(db_path)
            self.conn.row_factory = sqlite3.Row
            
            # Обеспечиваем обратную совместимость с различными типами datetime
            sqlite3.register_adapter(datetime.datetime, lambda dt: dt.isoformat())
            sqlite3.register_converter("datetime", lambda s: datetime.datetime.fromisoformat(s.decode()))
            
            # Проверяем наличие необходимых колонок и создаем их при необходимости
            self._ensure_columns_exist()
            
            return self.conn
        except Exception as e:
            logging.error(f"❌ Ошибка подключения к базе данных: {e}")
            return None
            
    def _ensure_columns_exist(self):
        """Проверяет наличие необходимых колонок в таблицах и создает их при необходимости."""
        try:
            # Гарантируем подключение к базе данных
            if self.conn is None:
                self.db_connect()
                
            if self.conn is None:
                logging.error("Не удалось подключиться к базе данных для проверки колонок")
                return
                
            # Проверяем наличие колонки created_at в таблице leads
            try:
                self.conn.execute("SELECT created_at FROM leads LIMIT 1")
            except sqlite3.OperationalError as e:
                if "no such column" in str(e).lower():
                    logging.warning("Колонка created_at не найдена в таблице leads. Добавляем...")
                    self.conn.execute("ALTER TABLE leads ADD COLUMN created_at TEXT")
                    self.conn.execute("UPDATE leads SET created_at = timestamp")
                    self.conn.commit()
                    logging.info("✅ Колонка created_at успешно добавлена в таблицу leads")
            
            # Проверяем наличие колонки last_ping в таблице leads
            try:
                self.conn.execute("SELECT last_ping FROM leads LIMIT 1")
            except sqlite3.OperationalError as e:
                if "no such column" in str(e).lower():
                    logging.warning("Колонка last_ping не найдена в таблице leads. Добавляем...")
                    self.conn.execute("ALTER TABLE leads ADD COLUMN last_ping TEXT")
                    # Заполняем новую колонку текущим временем
                    now = datetime.datetime.now().isoformat()
                    self.conn.execute("UPDATE leads SET last_ping = ?", (now,))
                    self.conn.commit()
                    logging.info("✅ Колонка last_ping успешно добавлена в таблицу leads")
                    
        except Exception as e:
            logging.error(f"❌ Ошибка при проверке/создании колонок: {e}")
    
    def check_unnotified_statuses(self):
        """Проверяет неотправленные уведомления об изменении статуса."""
        try:
            conn = self.db_connect()
            if not conn:
                return
            
            # Получаем все неотправленные уведомления
            cursor = conn.execute(
                """
                SELECT * FROM failed_notifications
                WHERE attempts < 10
                ORDER BY id
                """
            )
            notifications = cursor.fetchall()
            
            if notifications:
                logging.info(f"✉️ Найдено {len(notifications)} неотправленных уведомлений")
            
            for notif in notifications:
                # Обновляем количество попыток отправки
                now = datetime.datetime.now()
                conn.execute(
                    """
                    UPDATE failed_notifications
                    SET attempts = attempts + 1, last_attempt = ?
                    WHERE id = ?
                    """,
                    (now, notif['id'])
                )
                conn.commit()
            
            # Удаляем уведомления, которые не удалось отправить более 10 раз
            conn.execute(
                """
                DELETE FROM failed_notifications
                WHERE attempts >= 10
                """
            )
            conn.commit()
            
        except Exception as e:
            logging.error(f"❌ Ошибка при проверке неотправленных уведомлений: {e}")
    
    def process_expired_leads(self):
        """Обрабатывает устаревшие лиды. Сохраняет последний лид для каждого пользователя активным."""
        try:
            conn = self.db_connect()
            if not conn:
                return
            
            now = datetime.datetime.now()
            expiry_time = now - datetime.timedelta(minutes=15)  # Лиды старше 15 минут
            
            # Помечаем лиды как устаревшие, сохраняя самый свежий лид для каждого пользователя
            updated_rows = conn.execute(
                """
                UPDATE leads
                SET expired = 1
                WHERE timestamp < ? AND is_completed = 0 AND (expired = 0 OR expired IS NULL)
                AND id NOT IN (
                    SELECT MAX(id) FROM leads 
                    WHERE is_completed = 0 AND (expired = 0 OR expired IS NULL)
                    GROUP BY user_id
                )
                """,
                (expiry_time,)
            ).rowcount
            
            conn.commit()
            
            if updated_rows > 0:
                logging.info(f"✅ Помечено {updated_rows} устаревших лидов (старше 15 минут)")
            
        except Exception as e:
            import traceback
            logging.error(f"❌ Ошибка при обработке устаревших лидов: {e}")
            logging.error(f"❌ Трассировка: {traceback.format_exc()}")
    
    def cleanup_old_data(self):
        """Очищает устаревшие данные из базы."""
        try:
            conn = self.db_connect()
            if not conn:
                return
            
            # Проверка наличия таблицы failed_notifications
            try:
                # Проверяем существование таблицы
                conn.execute("SELECT 1 FROM failed_notifications LIMIT 1")
                
                # Удаляем очень старые уведомления (старше 30 дней)
                thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
                deleted_rows = conn.execute(
                    """
                    DELETE FROM failed_notifications
                    WHERE timestamp < ?
                    """,
                    (thirty_days_ago,)
                ).rowcount
                
                conn.commit()
                
                if deleted_rows > 0:
                    logging.info(f"🧹 Удалено {deleted_rows} устаревших уведомлений")
                
            except sqlite3.OperationalError as e:
                if "no such table" in str(e).lower():
                    logging.info("Таблица failed_notifications не существует, пропускаем очистку")
                else:
                    raise
            
        except Exception as e:
            logging.error(f"❌ Ошибка при очистке старых данных: {e}")
    
    def run(self):
        """Запускает сервис синхронизации в бесконечном цикле."""
        logging.info("▶️ Сервис синхронизации запущен")
        last_cleanup = datetime.datetime.now()
        last_check_expired = datetime.datetime.now()
        
        while self.is_running:
            try:
                now = datetime.datetime.now()
                
                # Проверяем неотправленные уведомления каждый цикл
                self.check_unnotified_statuses()
                
                # Обрабатываем устаревшие лиды каждые 10 секунд
                if (now - last_check_expired).total_seconds() >= 10:
                    self.process_expired_leads()
                    last_check_expired = now
                    logging.info("🔄 Выполнена обработка истекших лидов (старше 15 минут)")
                
                # Очистка устаревших данных - выполняем реже (раз в час)
                if (now - last_cleanup).total_seconds() >= 3600:  # 1 час
                    self.cleanup_old_data()
                    last_cleanup = now
                
                # Приостанавливаем выполнение на заданный интервал
                time.sleep(self.check_interval)
                
            except Exception as e:
                logging.error(f"❌ Неожиданная ошибка в сервисе синхронизации: {e}")
                time.sleep(30)  # Ждем 30 секунд при неожиданной ошибке

if __name__ == "__main__":
    service = InternalSyncService()
    service.run()