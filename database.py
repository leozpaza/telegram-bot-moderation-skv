# -*- coding: utf-8 -*-
"""
Модуль для работы с базой данных модерации Telegram-бота СКВ СПб
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from config import bot_config

@dataclass
class User:
    """Модель пользователя"""
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    warnings_count: int = 0
    is_banned: bool = False
    ban_until: Optional[datetime] = None
    # Система доверия
    joined_chat_at: Optional[datetime] = None
    messages_count: int = 0
    trust_level: str = "new"  # new, trusted, suspicious
    link_violations_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

@dataclass
class Violation:
    """Модель нарушения"""
    id: Optional[int] = None
    user_id: int = None
    message_id: int = None
    violation_type: str = None
    violation_text: str = None
    action_taken: str = None
    ai_confidence: Optional[float] = None
    created_at: datetime = None

@dataclass
class Appeal:
    """Модель обжалования"""
    id: Optional[int] = None
    user_id: int = None
    appeal_text: str = None
    status: str = "pending"  # pending, approved, rejected
    admin_id: Optional[int] = None
    admin_response: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None

class ModerationDatabase:
    """Класс для работы с базой данных модерации"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or bot_config.DATABASE_FILE
        self.logger = logging.getLogger(__name__)
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Таблица пользователей
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    warnings_count INTEGER DEFAULT 0,
                    is_banned BOOLEAN DEFAULT 0,
                    ban_until DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    joined_chat_at DATETIME,
                    messages_count INTEGER DEFAULT 0,
                    trust_level TEXT DEFAULT 'new',
                    link_violations_count INTEGER DEFAULT 0,
                    last_message_at DATETIME
                )
                """)
                
                # Таблица нарушений
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_id INTEGER,
                    violation_type TEXT NOT NULL,
                    violation_text TEXT,
                    action_taken TEXT NOT NULL,
                    ai_confidence REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                """)
                
                # Таблица настроек
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)

                # Таблица обжалований
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS appeals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    appeal_text TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    admin_id INTEGER,
                    admin_response TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                """)
                
                # Индексы для оптимизации
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_ban_until ON users(ban_until)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_violations_user_id ON violations(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_violations_created_at ON violations(created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_appeals_user_id ON appeals(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status)")
                
                conn.commit()
                self.logger.info("База данных инициализирована успешно")

            # Вызываем миграцию после создания таблиц
            self.migrate_database()
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM users WHERE user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                if row:
                    return User(
                        user_id=row['user_id'],
                        username=row['username'],
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        warnings_count=row['warnings_count'],
                        is_banned=bool(row['is_banned']),
                        ban_until=datetime.fromisoformat(row['ban_until']) if row['ban_until'] else None,
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None,
                        # Новые поля системы доверия
                        joined_chat_at=datetime.fromisoformat(row['joined_chat_at']) if row['joined_chat_at'] else None,
                        messages_count=row['messages_count'] or 0,
                        trust_level=row['trust_level'] or 'new',
                        link_violations_count=row['link_violations_count'] or 0,
                        last_message_at=datetime.fromisoformat(row['last_message_at']) if row['last_message_at'] else None
                    )
                return None
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения пользователя {user_id}: {e}")
            return None
    
    def create_or_update_user(self, user_id: int, username: str = None, 
                             first_name: str = None, last_name: str = None) -> User:
        """Создать или обновить пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существует ли пользователь
                existing_user = self.get_user(user_id)
                
                if existing_user:
                    # Обновляем информацию о пользователе
                    cursor.execute("""
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """, (username, first_name, last_name, user_id))
                    
                    existing_user.username = username
                    existing_user.first_name = first_name
                    existing_user.last_name = last_name
                    existing_user.updated_at = datetime.now()
                    
                    conn.commit()
                    return existing_user
                else:
                    # Создаем нового пользователя
                    cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    """, (user_id, username, first_name, last_name))
                    
                    conn.commit()
                    return User(
                        user_id=user_id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        warnings_count=0,
                        is_banned=False,
                        created_at=datetime.now()
                    )
                    
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка создания/обновления пользователя {user_id}: {e}")
            raise

    def migrate_database(self):
        """Миграция базы данных для добавления новых полей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, существуют ли новые колонки
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                # Добавляем отсутствующие колонки
                new_columns = [
                    ("joined_chat_at", "DATETIME"),
                    ("messages_count", "INTEGER DEFAULT 0"),
                    ("trust_level", "TEXT DEFAULT 'new'"),
                    ("link_violations_count", "INTEGER DEFAULT 0"),
                    ("last_message_at", "DATETIME")
                ]
                
                for column_name, column_type in new_columns:
                    if column_name not in columns:
                        try:
                            cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                            self.logger.info(f"Добавлена колонка {column_name}")
                        except sqlite3.Error as e:
                            self.logger.error(f"Ошибка добавления колонки {column_name}: {e}")
                
                conn.commit()
                self.logger.info("Миграция базы данных выполнена успешно")
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка миграции базы данных: {e}")
    
    def add_warning(self, user_id: int) -> int:
        """Добавить предупреждение пользователю"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE users 
                SET warnings_count = warnings_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """, (user_id,))
                
                # Получаем новое количество предупреждений
                cursor.execute("SELECT warnings_count FROM users WHERE user_id = ?", (user_id,))
                warnings_count = cursor.fetchone()[0]
                
                conn.commit()
                self.logger.info(f"Пользователю {user_id} добавлено предупреждение. Всего: {warnings_count}")
                return warnings_count
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка добавления предупреждения пользователю {user_id}: {e}")
            raise
    
    def ban_user(self, user_id: int, duration_minutes: int = None) -> None:
        """Заблокировать пользователя"""
        try:
            ban_until = None
            if duration_minutes:
                ban_until = datetime.now() + timedelta(minutes=duration_minutes)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE users 
                SET is_banned = 1, ban_until = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """, (ban_until.isoformat() if ban_until else None, user_id))
                
                conn.commit()
                self.logger.info(f"Пользователь {user_id} заблокирован до {ban_until}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка блокировки пользователя {user_id}: {e}")
            raise
    
    def unban_user(self, user_id: int) -> None:
        """Разблокировать пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE users 
                SET is_banned = 0, ban_until = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """, (user_id,))
                
                conn.commit()
                self.logger.info(f"Пользователь {user_id} разблокирован")
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка разблокировки пользователя {user_id}: {e}")
            raise
    
    def is_user_banned(self, user_id: int) -> bool:
        """Проверить, заблокирован ли пользователь"""
        user = self.get_user(user_id)
        if not user or not user.is_banned:
            return False
        
        # Проверяем, не истек ли срок бана
        if user.ban_until and user.ban_until <= datetime.now():
            self.unban_user(user_id)
            return False
        
        return True
    
    def add_violation(self, user_id: int, message_id: int, violation_type: str,
                     violation_text: str, action_taken: str, ai_confidence: float = None) -> None:
        """Добавить запись о нарушении"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                INSERT INTO violations (user_id, message_id, violation_type, violation_text, 
                                     action_taken, ai_confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, message_id, violation_type, violation_text, action_taken, ai_confidence))
                
                conn.commit()
                self.logger.info(f"Добавлено нарушение для пользователя {user_id}: {violation_type}")
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка добавления нарушения: {e}")
            raise
    
    def get_user_violations(self, user_id: int, limit: int = 10) -> List[Violation]:
        """Получить список нарушений пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM violations 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
                """, (user_id, limit))
                
                violations = []
                for row in cursor.fetchall():
                    violations.append(Violation(
                        id=row['id'],
                        user_id=row['user_id'],
                        message_id=row['message_id'],
                        violation_type=row['violation_type'],
                        violation_text=row['violation_text'],
                        action_taken=row['action_taken'],
                        ai_confidence=row['ai_confidence'],
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                    ))
                
                return violations
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения нарушений пользователя {user_id}: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """Получить статистику модерации"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Общее количество пользователей
                cursor.execute("SELECT COUNT(*) FROM users")
                total_users = cursor.fetchone()[0]
                
                # Количество заблокированных пользователей
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
                banned_users = cursor.fetchone()[0]
                
                # Общее количество нарушений
                cursor.execute("SELECT COUNT(*) FROM violations")
                total_violations = cursor.fetchone()[0]
                
                # Нарушения за последние 24 часа
                yesterday = datetime.now() - timedelta(days=1)
                cursor.execute("""
                SELECT COUNT(*) FROM violations 
                WHERE created_at > ?
                """, (yesterday.isoformat(),))
                violations_24h = cursor.fetchone()[0]
                
                # Топ типов нарушений
                cursor.execute("""
                SELECT violation_type, COUNT(*) as count 
                FROM violations 
                GROUP BY violation_type 
                ORDER BY count DESC 
                LIMIT 5
                """)
                top_violations = cursor.fetchall()
                
                return {
                    'total_users': total_users,
                    'banned_users': banned_users,
                    'total_violations': total_violations,
                    'violations_24h': violations_24h,
                    'top_violations': top_violations
                }
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    def cleanup_expired_bans(self) -> int:
        """Очистить истекшие баны"""
        # УБРАТЬ проверку bot_config.AUTO_CLEANUP_EXPIRED_BANS
        # Автоочистка всегда работает
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                cursor.execute("""
                UPDATE users 
                SET is_banned = 0, ban_until = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE is_banned = 1 AND ban_until IS NOT NULL AND ban_until <= ?
                """, (now,))
                
                cleaned_count = cursor.rowcount
                conn.commit()
                
                if cleaned_count > 0:
                    self.logger.info(f"Очищено {cleaned_count} истекших временных банов")
                
                return cleaned_count
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка очистки истекших банов: {e}")
            return 0

    def update_user_activity(self, user_id: int, increment_messages: bool = True) -> None:
        """Обновляет активность пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                update_query = "UPDATE users SET last_message_at = CURRENT_TIMESTAMP"
                if increment_messages:
                    update_query += ", messages_count = messages_count + 1"
                update_query += " WHERE user_id = ?"
                
                cursor.execute(update_query, (user_id,))
                conn.commit()
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка обновления активности пользователя {user_id}: {e}")

    def set_user_joined_chat(self, user_id: int) -> None:
        """Устанавливает время присоединения к чату"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE users 
                SET joined_chat_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND joined_chat_at IS NULL
                """, (user_id,))
                
                conn.commit()
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка установки времени присоединения {user_id}: {e}")

    def calculate_trust_level(self, user_id: int) -> str:
        """Вычисляет уровень доверия пользователя"""
        user = self.get_user(user_id)
        if not user or not user.joined_chat_at:
            return "new"
        
        from datetime import datetime, timedelta
        from config import bot_config
        
        days_in_chat = (datetime.now() - user.joined_chat_at).days
        
        if (days_in_chat >= bot_config.TRUST_DAYS_THRESHOLD and 
            user.messages_count >= bot_config.TRUST_MESSAGES_THRESHOLD):
            return "trusted"
        elif user.link_violations_count > 0:
            return "suspicious" 
        else:
            return "new"

    def update_trust_level(self, user_id: int) -> str:
        """Обновляет уровень доверия пользователя"""
        try:
            new_trust_level = self.calculate_trust_level(user_id)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE users 
                SET trust_level = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """, (new_trust_level, user_id))
                
                conn.commit()
                
            return new_trust_level
            
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка обновления уровня доверия {user_id}: {e}")
            return "new"

    def add_link_violation(self, user_id: int) -> int:
        """Добавляет нарушение по ссылкам"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE users 
                SET link_violations_count = link_violations_count + 1, trust_level = 'suspicious', updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """, (user_id,))
                
                cursor.execute("SELECT link_violations_count FROM users WHERE user_id = ?", (user_id,))
                violations_count = cursor.fetchone()[0]
                
                conn.commit()
                return violations_count
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка добавления нарушения по ссылкам {user_id}: {e}")
            return 0

    def get_trust_statistics(self) -> Dict:
        """Получить статистику системы доверия"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Статистика по уровням доверия
                cursor.execute("""
                SELECT trust_level, COUNT(*) 
                FROM users 
                GROUP BY trust_level
                """)
                trust_levels = dict(cursor.fetchall())
                
                # Средние сообщения у доверенных пользователей
                cursor.execute("""
                SELECT AVG(messages_count) 
                FROM users 
                WHERE trust_level = 'trusted'
                """)
                avg_trusted_messages = cursor.fetchone()[0] or 0
                
                return {
                    'trust_levels': trust_levels,
                    'avg_trusted_messages': round(avg_trusted_messages, 1)
                }
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения статистики доверия: {e}")
            return {}

    def recalculate_all_trust_levels(self) -> int:
        """Пересчитывает уровни доверия для всех пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Получаем всех пользователей
                cursor.execute("SELECT user_id FROM users")
                user_ids = [row[0] for row in cursor.fetchall()]
                
                updated_count = 0
                for user_id in user_ids:
                    try:
                        new_level = self.update_trust_level(user_id)
                        updated_count += 1
                        self.logger.debug(f"Обновлен уровень доверия для {user_id}: {new_level}")
                    except Exception as e:
                        self.logger.error(f"Ошибка пересчета для пользователя {user_id}: {e}")
                
                self.logger.info(f"Пересчитано уровней доверия: {updated_count}")
                return updated_count
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка пересчета всех уровней доверия: {e}")
            return 0

    def get_users_by_trust_level(self, trust_level: str, limit: int = 50) -> List[User]:
        """Получить пользователей по уровню доверия"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM users 
                WHERE trust_level = ? 
                ORDER BY updated_at DESC 
                LIMIT ?
                """, (trust_level, limit))
                
                users = []
                for row in cursor.fetchall():
                    users.append(User(
                        user_id=row['user_id'],
                        username=row['username'],
                        first_name=row['first_name'],
                        last_name=row['last_name'],
                        warnings_count=row['warnings_count'],
                        is_banned=bool(row['is_banned']),
                        ban_until=datetime.fromisoformat(row['ban_until']) if row['ban_until'] else None,
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                    ))
                
                return users
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения пользователей по уровню доверия {trust_level}: {e}")
            return []
        
    def add_appeal(self, user_id: int, appeal_text: str) -> int:
        """Добавить обжалование"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Проверяем, нет ли уже активного обжалования
                cursor.execute("""
                SELECT id FROM appeals 
                WHERE user_id = ? AND status = 'pending'
                """, (user_id,))
                
                if cursor.fetchone():
                    return -1  # Уже есть активное обжалование
                
                cursor.execute("""
                INSERT INTO appeals (user_id, appeal_text)
                VALUES (?, ?)
                """, (user_id, appeal_text))
                
                appeal_id = cursor.lastrowid
                conn.commit()
                
                self.logger.info(f"Добавлено обжалование {appeal_id} от пользователя {user_id}")
                return appeal_id
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка добавления обжалования: {e}")
            return 0

    def get_pending_appeals(self) -> List[Appeal]:
        """Получить список ожидающих обжалований"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM appeals 
                WHERE status = 'pending'
                ORDER BY created_at ASC
                """)
                
                appeals = []
                for row in cursor.fetchall():
                    appeals.append(Appeal(
                        id=row['id'],
                        user_id=row['user_id'],
                        appeal_text=row['appeal_text'],
                        status=row['status'],
                        admin_id=row['admin_id'],
                        admin_response=row['admin_response'],
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                    ))
                
                return appeals
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения обжалований: {e}")
            return []

    def update_appeal_status(self, appeal_id: int, status: str, admin_id: int, admin_response: str = None) -> bool:
        """Обновить статус обжалования"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE appeals 
                SET status = ?, admin_id = ?, admin_response = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (status, admin_id, admin_response, appeal_id))
                
                success = cursor.rowcount > 0
                conn.commit()
                
                if success:
                    self.logger.info(f"Обжалование {appeal_id} обновлено: {status}")
                
                return success
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка обновления обжалования: {e}")
            return False

    def get_appeal_by_id(self, appeal_id: int) -> Optional[Appeal]:
        """Получить обжалование по ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,))
                row = cursor.fetchone()
                
                if row:
                    return Appeal(
                        id=row['id'],
                        user_id=row['user_id'],
                        appeal_text=row['appeal_text'],
                        status=row['status'],
                        admin_id=row['admin_id'],
                        admin_response=row['admin_response'],
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                    )
                
                return None
                
        except sqlite3.Error as e:
            self.logger.error(f"Ошибка получения обжалования {appeal_id}: {e}")
            return None

# Глобальная инстанция базы данных
db = ModerationDatabase()