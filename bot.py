# -*- coding: utf-8 -*-
"""
Основной модуль Telegram-бота модерации для СКВ СПб
"""

import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List

from telegram import Update, Message, User as TgUser, ChatMember
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackContext, 
    ChatMemberHandler,
    filters
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError

from config import bot_config, BOT_MESSAGES, VIOLATION_TYPES, MODERATION_ACTIONS
from database import db, User
from openai_analyzer import analyzer, AnalysisResult
from banned_words import check_banned_words

# Условный импорт детектора ссылок
try:
    from link_detector import detect_links, has_suspicious_links, is_trusted_link
    LINK_DETECTOR_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Модуль link_detector не найден: {e}")
    LINK_DETECTOR_AVAILABLE = False
    
    # Заглушки если модуль не найден
    def detect_links(text: str):
        return False, []
    
    def has_suspicious_links(text: str):
        return False, []
    
    def is_trusted_link(link: str):
        return True
    
    logging.warning("Модуль link_detector не найден, система доверия отключена")

class ModerationBot:
    """Основной класс Telegram-бота модерации"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.application = None
        self.is_running = False
        
        # Статистика работы
        self.stats = {
            'messages_processed': 0,
            'violations_detected': 0,
            'users_banned': 0,
            'users_warned': 0,
            'bot_started': None
        }
    
    def setup_logging(self):
        """Настройка логирования"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Настройка корневого логгера
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, bot_config.LOG_LEVEL.upper()))
        
        # Очищаем существующие обработчики
        root_logger.handlers.clear()
        
        # Логирование в консоль
        if bot_config.LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(console_handler)
        
        # Логирование в файл
        if bot_config.LOG_TO_FILE:
            file_handler = logging.FileHandler(bot_config.LOG_FILE, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(file_handler)
    
    async def initialize(self):
        """Инициализация бота"""
        if not bot_config.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не установлен в конфигурации")
        
        # Настройка приложения
        self.application = Application.builder().token(bot_config.BOT_TOKEN).build()
        
        # Регистрация обработчиков команд
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("rules", self.cmd_rules))
        self.application.add_handler(CommandHandler("stats", self.cmd_stats))
        self.application.add_handler(CommandHandler("ban", self.cmd_ban))
        self.application.add_handler(CommandHandler("unban", self.cmd_unban))
        self.application.add_handler(CommandHandler("mute", self.cmd_mute))
        self.application.add_handler(CommandHandler("warn", self.cmd_warn))
        self.application.add_handler(CommandHandler("user_info", self.cmd_user_info))
        self.application.add_handler(CommandHandler("cleanup", self.cmd_cleanup))

        # Команды системы доверия
        self.application.add_handler(CommandHandler("trust_info", self.cmd_trust_info))
        self.application.add_handler(CommandHandler("trust_stats", self.cmd_trust_stats))
        self.application.add_handler(CommandHandler("set_trust", self.cmd_set_trust))

        self.application.add_handler(CommandHandler("confirm_accept", self.cmd_confirm_accept))

        # Команды для обжалований
        self.application.add_handler(CommandHandler("appeal", self.cmd_appeal))
        self.application.add_handler(CommandHandler("list_appeals", self.cmd_list_appeals))
        self.application.add_handler(CommandHandler("accept_appeal", self.cmd_accept_appeal))
        self.application.add_handler(CommandHandler("reject_appeal", self.cmd_reject_appeal))
        
        # Обработчик сообщений
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        
        # Обработчик изменений участников чата
        self.application.add_handler(ChatMemberHandler(self.handle_chat_member_update))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
        
        self.logger.info("Бот инициализирован успешно")
    
    async def start(self):
        """Запуск бота"""
        try:
            # Проверяем, инициализировано ли приложение
            if not self.application:
                raise ValueError("Приложение не инициализировано. Вызовите initialize() сначала.")
            
            # Инициализируем приложение если оно еще не инициализировано
            if not self.application.running:
                await self.application.initialize()
            
            await self.application.start()
            await self.application.updater.start_polling()
            
            self.is_running = True
            self.stats['bot_started'] = datetime.now()
            
            self.logger.info("Бот запущен и ожидает сообщений")
            
            # Запускаем фоновые задачи
            asyncio.create_task(self.background_tasks())
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска бота: {e}")
            raise
    
    async def stop(self):
        """Остановка бота"""
        if self.application and self.is_running:
            try:
                self.is_running = False
                
                if self.application.updater and self.application.updater.running:
                    await self.application.updater.stop()
                
                if self.application.running:
                    await self.application.stop()
                    await self.application.shutdown()
                
                self.logger.info("Бот остановлен")
                
            except Exception as e:
                self.logger.error(f"Ошибка остановки бота: {e}")
        else:
            self.logger.info("Бот уже остановлен или не был запущен")
    
    async def background_tasks(self):
        """Фоновые задачи бота"""
        while self.is_running:
            try:
                # Очистка истекших банов каждые 5 минут
                cleaned_bans = db.cleanup_expired_bans()
                if cleaned_bans > 0:
                    self.logger.info(f"Очищено {cleaned_bans} истекших банов")
                
                # Ожидание перед следующей проверкой
                await asyncio.sleep(300)  # 5 минут
                
            except Exception as e:
                self.logger.error(f"Ошибка в фоновых задачах: {e}")
                await asyncio.sleep(60)  # Пауза при ошибке
    
    async def handle_message(self, update: Update, context: CallbackContext):
        """Обработчик входящих сообщений"""
        message = update.message
        user = message.from_user
        
        if not message or not user:
            return
        
        self.stats['messages_processed'] += 1
        
        # Создаем/обновляем пользователя в БД
        db_user = db.create_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Обновляем активность пользователя
        db.update_user_activity(user.id, increment_messages=True)

        # Обновляем уровень доверия
        trust_level = db.update_trust_level(user.id)
        
        # Проверяем, не заблокирован ли пользователь
        if db.is_user_banned(user.id):
            await self.delete_message_safe(message)
            return

        # Система доверия - проверка ссылок
        if await self.handle_trust_system(message, db_user):
            return  # Сообщение обработано системой доверия

        # Проверяем на запрещенные слова
        has_banned_words, found_words = check_banned_words(message.text)
        
        if has_banned_words:
            await self.handle_banned_words_violation(message, found_words, db_user)
            return
        
        # Если запрещенные слова не найдены, анализируем через AI
        if bot_config.USE_OPENAI_ANALYSIS:
            await self.handle_ai_analysis(message, db_user)
    
    async def handle_banned_words_violation(self, message: Message, found_words: List[str], user: User):
        """Обработка нарушения с запрещенными словами"""
        user_id = message.from_user.id
        
        self.logger.info(f"Найдены запрещенные слова у пользователя {user_id}: {found_words}")
        
        # Удаляем сообщение
        if bot_config.AUTO_DELETE_BANNED_WORDS:
            await self.delete_message_safe(message)
        
        # Добавляем нарушение в БД
        db.add_violation(
            user_id=user_id,
            message_id=message.message_id,
            violation_type="bad_language",
            violation_text=message.text[:500],  # Ограничиваем длину
            action_taken="delete"
        )
        
        # Определяем действие
        if bot_config.AUTO_BAN_ON_BANNED_WORDS:
            # Банируем пользователя
            db.ban_user(user_id, bot_config.BAN_DURATION_MINUTES)
            await self.notify_user_action(message, "banned", "Использование запрещенной лексики")
            self.stats['users_banned'] += 1
        else:
            # Выдаем предупреждение
            warnings_count = db.add_warning(user_id)
            await self.notify_user_action(message, "warned", f"Предупреждение {warnings_count}")
            
            # Проверяем, не превышен ли лимит предупреждений
            if warnings_count >= bot_config.WARNING_THRESHOLD:
                db.ban_user(user_id, bot_config.BAN_DURATION_MINUTES)
                await self.notify_user_action(message, "banned", "Превышен лимит предупреждений")
                self.stats['users_banned'] += 1
            else:
                self.stats['users_warned'] += 1
        
        self.stats['violations_detected'] += 1
    
    async def handle_ai_analysis(self, message: Message, user: User):
        """Обработка анализа сообщения через AI"""
        try:
            # Получаем анализ от AI
            user_info = f"Предупреждения: {user.warnings_count}, Заблокирован: {user.is_banned}"
            analysis = await analyzer.analyze_message(message.text, user_info)
            
            if not analysis:
                self.logger.warning("Не удалось получить анализ от AI")
                return
            
            # Проверяем, значительно ли нарушение
            if not analyzer.is_violation_significant(analysis):
                return  # Нарушение не критично
            
            self.logger.info(f"AI обнаружил нарушение: {analysis.violation_type} (уверенность: {analysis.confidence})")
            
            # Определяем рекомендуемое действие
            recommended_action = analyzer.get_recommended_action(analysis, user.warnings_count)
            
            # Добавляем нарушение в БД
            db.add_violation(
                user_id=message.from_user.id,
                message_id=message.message_id,
                violation_type=analysis.violation_type or "ai_detected",
                violation_text=message.text[:500],
                action_taken=recommended_action,
                ai_confidence=analysis.confidence
            )

            # Сначала удаляем нарушающее сообщение
            await self.delete_message_safe(message)

            # Затем выполняем действие модерации
            await self.execute_moderation_action(message, recommended_action, analysis.reason)

            # Отправляем предупреждение в ЛС пользователю
            if recommended_action in ["delete", "warn", "mute", "ban"]:
                warning_text = f"⚠️ Ваше сообщение нарушает правила чата и было удалено.\n\nПричина: {analysis.reason}"
                await self.send_private_warning(message.from_user, warning_text)

            self.stats['violations_detected'] += 1
            
        except Exception as e:
            self.logger.error(f"Ошибка AI анализа: {e}")

    async def handle_trust_system(self, message: Message, user: User) -> bool:
        """
        Обработка системы доверия
        
        Returns:
            bool: True если сообщение было обработано системой доверия
        """
        if not LINK_DETECTOR_AVAILABLE:
            return False
            
        if not bot_config.TRUST_SYSTEM_ENABLED or not bot_config.LINK_DETECTION_ENABLED:
            return False
        
        # Проверяем на подозрительные ссылки
        has_links, suspicious_links = has_suspicious_links(message.text)
        
        if not has_links:
            return False
        
        # Получаем текущий уровень доверия
        trust_level = db.calculate_trust_level(message.from_user.id)
        
        # Если пользователь доверенный, пропускаем проверку
        if trust_level == "trusted":
            self.logger.info(f"Доверенный пользователь {message.from_user.id} отправил ссылки: {suspicious_links}")
            return False
        
        # Новый или подозрительный пользователь отправил ссылки
        self.logger.info(f"Пользователь {message.from_user.id} (уровень: {trust_level}) отправил подозрительные ссылки: {suspicious_links}")
        
        # Увеличиваем счетчик нарушений по ссылкам
        violations_count = db.add_link_violation(message.from_user.id)
        
        # Удаляем сообщение если включено автоудаление
        if bot_config.AUTO_DELETE_LINKS_FROM_NEW:
            await self.delete_message_safe(message)
        
        # Добавляем нарушение в БД
        db.add_violation(
            user_id=message.from_user.id,
            message_id=message.message_id,
            violation_type="suspicious_links",
            violation_text=message.text[:500],
            action_taken="delete_warn" if violations_count == 1 else "ban"
        )
        
        if violations_count == 1:
            # Первое нарушение - предупреждение
            warning_text = (
                f"⚠️ Ваше сообщение со ссылками было удалено.\n"
                f"🔒 Новые участники не могут отправлять ссылки первые {bot_config.TRUST_DAYS_THRESHOLD} дня(ей) "
                f"или до отправки {bot_config.TRUST_MESSAGES_THRESHOLD} сообщений.\n"
                f"⚡ При повторной попытке вы будете заблокированы."
            )
            await self.notify_user_action(message, "link_warning", warning_text)
            await self.send_private_warning(message.from_user, warning_text)
            
        elif violations_count >= 2 and bot_config.BAN_ON_REPEATED_LINK_VIOLATION:
            # Повторное нарушение - бан
            db.ban_user(message.from_user.id, bot_config.BAN_DURATION_MINUTES)
            ban_text = (
                f"🚫 Вы заблокированы за повторную отправку ссылок.\n"
                f"⏰ Блокировка на {bot_config.BAN_DURATION_MINUTES} минут."
            )
            await self.notify_user_action(message, "banned", ban_text)
            await self.send_private_warning(message.from_user, ban_text)
            self.stats['users_banned'] += 1
        
        self.stats['violations_detected'] += 1
        return True
    
    async def send_private_warning(self, user, warning_text: str):
        """Отправка предупреждения в личные сообщения"""
        try:
            await self.application.bot.send_message(
                chat_id=user.id,
                text=warning_text,
                parse_mode=ParseMode.MARKDOWN
            )
            self.logger.info(f"Отправлено предупреждение в ЛС пользователю {user.id}")
        except TelegramError as e:
            self.logger.warning(f"Не удалось отправить ЛС пользователю {user.id}: {e}")

    async def execute_moderation_action(self, message: Message, action: str, reason: str):
        """Выполнение действия модерации"""
        user_id = message.from_user.id
        
        if action == "delete":
            # Сообщение уже удалено в handle_ai_analysis
            await self.notify_user_action(message, "message_deleted", reason)
            
        elif action == "warn":
            warnings_count = db.add_warning(user_id)
            await self.notify_user_action(message, "warned", f"Предупреждение {warnings_count}: {reason}")
            self.stats['users_warned'] += 1
            
            # Проверяем лимит предупреждений
            if warnings_count >= bot_config.WARNING_THRESHOLD:
                db.ban_user(user_id, bot_config.BAN_DURATION_MINUTES)
                await self.notify_user_action(message, "banned", "Превышен лимит предупреждений")
                self.stats['users_banned'] += 1
                
        elif action == "mute":
            # Сообщение уже удалено
            db.ban_user(user_id, bot_config.BAN_DURATION_MINUTES)
            await self.notify_user_action(message, "muted", reason)
            self.stats['users_banned'] += 1
            
        elif action == "ban":
            # Сообщение уже удалено
            db.ban_user(user_id, None)  # Постоянный бан
            await self.notify_user_action(message, "banned", reason)
            self.stats['users_banned'] += 1
    
    async def delete_message_safe(self, message: Message) -> bool:
        """Безопасное удаление сообщения"""
        try:
            await message.delete()
            return True
        except TelegramError as e:
            self.logger.warning(f"Не удалось удалить сообщение {message.message_id}: {e}")
            return False
    
    async def notify_user_action(self, message: Message, action: str, reason: str):
        """Уведомление о действии модерации"""
        user = message.from_user
        chat_id = message.chat.id
        
        # Сообщения для различных действий
        notifications = {
            "warned": f"⚠️ @{user.username or user.first_name}, вам выдано предупреждение: {reason}",
            "banned": f"🚫 Пользователь @{user.username or user.first_name} заблокирован: {reason}",
            "muted": f"🔇 Пользователь @{user.username or user.first_name} ограничен: {reason}",
            "message_deleted": f"🗑️ Сообщение от @{user.username or user.first_name} удалено: {reason}"
        }
        
        notification_text = notifications.get(action, f"Выполнено действие {action}: {reason}")
        
        try:
            # Отправляем уведомление в чат (с автоудалением через 30 секунд)
            bot_message = await self.application.bot.send_message(
                chat_id=chat_id,
                text=notification_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Удаляем уведомление через 30 секунд
            asyncio.create_task(self.delete_message_after_delay(bot_message, 60))
            
            # Уведомляем админов в приватном чате
            if bot_config.ADMIN_CHAT_ID:
                admin_text = f"🔧 Модерация в чате:\n{notification_text}\nСообщение: \"{message.text[:100]}...\""
                await self.application.bot.send_message(
                    chat_id=bot_config.ADMIN_CHAT_ID,
                    text=admin_text
                )
                
        except TelegramError as e:
            self.logger.error(f"Ошибка отправки уведомления: {e}")
    
    async def delete_message_after_delay(self, message: Message, delay: int):
        """Удаление сообщения с задержкой"""
        await asyncio.sleep(delay)
        await self.delete_message_safe(message)

    async def cmd_trust_info(self, update: Update, context: CallbackContext):
        """Команда /trust_info"""
        if len(context.args) < 1:
            # Показываем информацию о себе
            user_id = update.effective_user.id
        else:
            if not await self.is_admin(update.effective_user.id):
                await update.message.reply_text("❌ Команда доступна только администраторам")
                return
            try:
                user_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ Некорректный ID пользователя")
                return

        user = db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return

        # Вычисляем текущий уровень доверия
        trust_level = db.calculate_trust_level(user_id)
        
        trust_level_names = {
            'new': 'Новый',
            'trusted': 'Доверенный',
            'suspicious': 'Подозрительный'
        }
        
        trust_info = f"""
    🔒 *Информация о доверии пользователя {user_id}:*

    📊 *Статистика:*
    - Уровень доверия: {trust_level_names.get(trust_level, trust_level)}
    - Сообщений отправлено: {user.messages_count}
    - Нарушений по ссылкам: {user.link_violations_count}
    - В чате с: {user.joined_chat_at.strftime('%d.%m.%Y') if user.joined_chat_at else 'Неизвестно'}
    - Последняя активность: {user.last_message_at.strftime('%d.%m.%Y %H:%M') if user.last_message_at else 'Неизвестно'}

    ℹ️ *Требования для доверия:*
    - Дней в чате: {bot_config.TRUST_DAYS_THRESHOLD}
    - Сообщений: {bot_config.TRUST_MESSAGES_THRESHOLD}
    """

        await update.message.reply_text(trust_info, parse_mode=ParseMode.MARKDOWN)

    async def cmd_trust_stats(self, update: Update, context: CallbackContext):
        """Команда /trust_stats"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return

        stats = db.get_trust_statistics()
        
        trust_level_names = {
            'new': 'Новые',
            'trusted': 'Доверенные',
            'suspicious': 'Подозрительные'
        }
        
        stats_text = f"""
    📊 *Статистика системы доверия:*

    👥 *Пользователи по уровням:*
    """
        
        for level, count in stats.get('trust_levels', {}).items():
            level_name = trust_level_names.get(level, level)
            stats_text += f"• {level_name}: {count}\n"
        
        stats_text += f"\n📈 *Среднее сообщений у доверенных:* {stats.get('avg_trusted_messages', 0)}"
        
        # Добавляем общую статистику нарушений
        general_stats = db.get_statistics()
        violations = general_stats.get('top_violations', [])
        link_violations = next((count for violation_type, count in violations if violation_type == 'suspicious_links'), 0)
        
        stats_text += f"\n🔗 *Всего нарушений по ссылкам:* {link_violations}"
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

    async def cmd_set_trust(self, update: Update, context: CallbackContext):
        """Команда /set_trust"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Использование: /set_trust <user_id> <new|trusted|suspicious>")
            return

        try:
            user_id = int(context.args[0])
            new_level = context.args[1].lower()
            
            if new_level not in ['new', 'trusted', 'suspicious']:
                await update.message.reply_text("❌ Доступные уровни: new, trusted, suspicious")
                return
            
            # Обновляем уровень доверия
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                UPDATE users 
                SET trust_level = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """, (new_level, user_id))
                conn.commit()
            
            trust_level_names = {
                'new': 'Новый',
                'trusted': 'Доверенный', 
                'suspicious': 'Подозрительный'
            }
            
            await update.message.reply_text(f"✅ Уровень доверия пользователя {user_id} установлен: {trust_level_names[new_level]}")
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def handle_chat_member_update(self, update: Update, context: CallbackContext):
        """Обработчик изменений участников чата"""
        chat_member_update = update.chat_member
        
        if not chat_member_update:
            return
        
        # Обновляем информацию о пользователе
        user = chat_member_update.new_chat_member.user
        db_user = db.create_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Если пользователь присоединился к чату, отмечаем время
        if (chat_member_update.old_chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED] and
            chat_member_update.new_chat_member.status == ChatMemberStatus.MEMBER):
            db.set_user_joined_chat(user.id)
            self.logger.info(f"Пользователь {user.id} присоединился к чату")
    
    # Команды бота
    async def cmd_start(self, update: Update, context: CallbackContext):
        """Команда /start"""
        await update.message.reply_text(
            "🏢 Добро пожаловать в чат управляющей компании СКВ СПб!\n\n"
            "Я - бот-модератор, который помогает поддерживать порядок в чате.\n"
            "Используйте /rules для ознакомления с правилами общения.\n"
            "Используйте /help для просмотра доступных команд."
        )
    
    async def cmd_help(self, update: Update, context: CallbackContext):
        """Команда /help"""
        is_admin = await self.is_admin(update.effective_user.id)
        
        if is_admin:
            help_text = """
    📋 Команды администратора:

    👮 Модерация:
    /stats - Статистика модерации  
    /ban <user_id> [время] - Заблокировать пользователя
    /unban <user_id> - Разблокировать пользователя
    /mute <user_id> [время] - Ограничить пользователя
    /warn <user_id> - Предупреждение пользователю
    /user_info <user_id> - Информация о пользователе
    /cleanup - Очистка истекших банов

    🔒 Система доверия:
    /trust_info [user_id] - Информация о доверии
    /trust_stats - Статистика доверия  
    /set_trust <user_id> <level> - Установить уровень доверия

    📮 Обжалования:
    /list_appeals - Список активных обжалований
    /accept_appeal <appeal_id> - Принять обжалование
    /reject_appeal <appeal_id> - Отклонить обжалование
    """
        else:
            help_text = """
    📋 Доступные команды:

    /start - Приветствие и информация о боте
    /help - Показать это сообщение
    /rules - Правила чата
    /appeal <текст> - Подать обжалование блокировки
    """
        
        await update.message.reply_text(help_text)
    
    async def cmd_rules(self, update: Update, context: CallbackContext):
        """Команда /rules"""
        await update.message.reply_text(BOT_MESSAGES["rules_reminder"])
    
    async def cmd_stats(self, update: Update, context: CallbackContext):
        """Команда /stats"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        stats = db.get_statistics()
        bot_uptime = datetime.now() - self.stats['bot_started'] if self.stats['bot_started'] else timedelta(0)
        
        stats_text = f"""
📊 *Статистика модерации:*

🤖 *Работа бота:*
• Время работы: {str(bot_uptime).split('.')[0]}
• Обработано сообщений: {self.stats['messages_processed']}
• Обнаружено нарушений: {self.stats['violations_detected']}

👥 *Пользователи:*
• Всего пользователей: {stats.get('total_users', 0)}
• Заблокированных: {stats.get('banned_users', 0)}
• Предупреждений выдано: {self.stats['users_warned']}
• Блокировок выполнено: {self.stats['users_banned']}

📈 *Нарушения:*
• За сегодня: {stats.get('violations_24h', 0)}
• Всего: {stats.get('total_violations', 0)}
"""
        
        if stats.get('top_violations'):
            stats_text += "\n🔥 *Топ нарушений:*\n"
            for violation_type, count in stats['top_violations']:
                violation_name = VIOLATION_TYPES.get(violation_type, violation_type)
                stats_text += f"• {violation_name}: {count}\n"
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_ban(self, update: Update, context: CallbackContext):
        """Команда /ban"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /ban <user_id> [минуты]")
            return
        
        try:
            user_id = int(context.args[0])
            duration = int(context.args[1]) if len(context.args) > 1 else None
            
            db.ban_user(user_id, duration)
            
            duration_text = f"на {duration} минут" if duration else "навсегда"
            await update.message.reply_text(f"✅ Пользователь {user_id} заблокирован {duration_text}")
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя или время")
    
    async def cmd_unban(self, update: Update, context: CallbackContext):
        """Команда /unban"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /unban <user_id>")
            return
        
        try:
            user_id = int(context.args[0])
            db.unban_user(user_id)
            await update.message.reply_text(f"✅ Пользователь {user_id} разблокирован")
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя")
    
    async def cmd_mute(self, update: Update, context: CallbackContext):
        """Команда /mute"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /mute <user_id> [минуты]")
            return
        
        try:
            user_id = int(context.args[0])
            duration = int(context.args[1]) if len(context.args) > 1 else bot_config.BAN_DURATION_MINUTES
            
            db.ban_user(user_id, duration)
            await update.message.reply_text(f"✅ Пользователь {user_id} ограничен на {duration} минут")
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя или время")
    
    async def cmd_warn(self, update: Update, context: CallbackContext):
        """Команда /warn"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /warn <user_id>")
            return
        
        try:
            user_id = int(context.args[0])
            warnings_count = db.add_warning(user_id)
            await update.message.reply_text(f"✅ Пользователю {user_id} выдано предупреждение. Всего: {warnings_count}")
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя")
    
    async def cmd_user_info(self, update: Update, context: CallbackContext):
        """Команда /user_info"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /user_info <user_id>")
            return
        
        try:
            user_id = int(context.args[0])
            user = db.get_user(user_id)
            
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            violations = db.get_user_violations(user_id, 5)
            
            info_text = f"""
👤 *Информация о пользователе {user_id}:*

📝 *Данные:*
• Имя: {user.first_name or 'Не указано'}
• Фамилия: {user.last_name or 'Не указана'}
• Username: @{user.username or 'Не указан'}
• Предупреждения: {user.warnings_count}
• Заблокирован: {'Да' if user.is_banned else 'Нет'}
• Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Неизвестна'}
"""
            
            if user.ban_until:
                info_text += f"• Бан до: {user.ban_until.strftime('%d.%m.%Y %H:%M')}\n"
            
            if violations:
                info_text += f"\n🚫 *Последние нарушения:*\n"
                for violation in violations:
                    violation_name = VIOLATION_TYPES.get(violation.violation_type, violation.violation_type)
                    date_str = violation.created_at.strftime('%d.%m %H:%M') if violation.created_at else 'Неизвестно'
                    info_text += f"• {date_str}: {violation_name}\n"
            
            await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)
            
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID пользователя")
    
    async def cmd_cleanup(self, update: Update, context: CallbackContext):
        """Команда /cleanup"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        cleaned_count = db.cleanup_expired_bans()
        await update.message.reply_text(f"✅ Очищено {cleaned_count} истекших банов")
    
    async def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        try:
            if not bot_config.CHAT_ID:
                return True  # Если чат не настроен, разрешаем всем
            
            chat_member = await self.application.bot.get_chat_member(bot_config.CHAT_ID, user_id)
            return chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
            
        except TelegramError:
            return False
        
    async def cmd_appeal(self, update: Update, context: CallbackContext):
        """Команда /appeal для подачи обжалования"""
        user_id = update.effective_user.id
        
        # Проверяем, заблокирован ли пользователь
        if not db.is_user_banned(user_id):
            await update.message.reply_text("❌ Вы не заблокированы, обжалование не требуется")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text(
                "Для подачи обжалования укажите причину:\n"
                "/appeal <ваше объяснение>\n\n"
                "Например: /appeal Я не нарушал правила, сообщение было неправильно понято"
            )
            return
        
        appeal_text = " ".join(context.args)
        
        if len(appeal_text) < 10:
            await update.message.reply_text("❌ Текст обжалования слишком короткий (минимум 10 символов)")
            return
        
        if len(appeal_text) > 1000:
            await update.message.reply_text("❌ Текст обжалования слишком длинный (максимум 1000 символов)")
            return
        
        appeal_id = db.add_appeal(user_id, appeal_text)
        
        if appeal_id == -1:
            await update.message.reply_text("❌ У вас уже есть активное обжалование. Дождитесь рассмотрения.")
            return
        elif appeal_id == 0:
            await update.message.reply_text("❌ Ошибка при подаче обжалования. Попробуйте позже.")
            return
        
        await update.message.reply_text(
            f"✅ Ваше обжалование #{appeal_id} принято к рассмотрению.\n"
            "Администраторы рассмотрят его в ближайшее время."
        )
        
        # Уведомляем админов
        if bot_config.ADMIN_CHAT_ID:
            user = update.effective_user
            admin_notification = (
                f"📮 Новое обжалование #{appeal_id}\n"
                f"👤 От: {user.first_name} (@{user.username or 'без username'})\n"
                f"🆔 User ID: {user_id}\n"
                f"📝 Текст: {appeal_text}\n\n"
                f"Команды:\n/accept_appeal {appeal_id}\n/reject_appeal {appeal_id}"
            )
            try:
                await self.application.bot.send_message(
                    chat_id=bot_config.ADMIN_CHAT_ID,
                    text=admin_notification
                )
            except Exception as e:
                self.logger.error(f"Ошибка отправки уведомления админам: {e}")

    async def cmd_list_appeals(self, update: Update, context: CallbackContext):
        """Команда /list_appeals для просмотра обжалований"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        appeals = db.get_pending_appeals()
        
        if not appeals:
            await update.message.reply_text("📭 Нет ожидающих обжалований")
            return
        
        appeals_text = "📮 Активные обжалования:\n\n"
        
        for appeal in appeals[:10]:  # Показываем максимум 10
            user = db.get_user(appeal.user_id)
            user_name = f"{user.first_name or 'Неизвестно'}" if user else "Неизвестно"
            
            appeals_text += (
                f"#{appeal.id} - {user_name} (ID: {appeal.user_id})\n"
                f"📅 {appeal.created_at.strftime('%d.%m %H:%M') if appeal.created_at else 'Неизвестно'}\n"
                f"💬 {appeal.appeal_text[:100]}{'...' if len(appeal.appeal_text) > 100 else ''}\n\n"
            )
        
        appeals_text += f"\n📊 Всего: {len(appeals)}"
        
        await update.message.reply_text(appeals_text)

    async def cmd_accept_appeal(self, update: Update, context: CallbackContext):
        """Команда /accept_appeal для принятия обжалования"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /accept_appeal <appeal_id>")
            return
        
        try:
            appeal_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID обжалования")
            return
        
        appeal = db.get_appeal_by_id(appeal_id)
        if not appeal:
            await update.message.reply_text("❌ Обжалование не найдено")
            return
        
        if appeal.status != "pending":
            await update.message.reply_text("❌ Обжалование уже рассмотрено")
            return
        
        # Запрашиваем подтверждение
        user = db.get_user(appeal.user_id)
        user_info = f"{user.first_name or 'Неизвестно'} (ID: {appeal.user_id})" if user else f"ID: {appeal.user_id}"
        
        confirmation_text = (
            f"⚠️ ПОДТВЕРЖДЕНИЕ ДЕЙСТВИЯ\n\n"
            f"Вы действительно хотите принять обжалование #{appeal_id}?\n"
            f"👤 Пользователь: {user_info}\n"
            f"📝 Обжалование: {appeal.appeal_text[:200]}{'...' if len(appeal.appeal_text) > 200 else ''}\n\n"
            f"Это приведет к разблокировке пользователя!\n\n"
            f"Для подтверждения отправьте: /confirm_accept {appeal_id}"
        )
        
        await update.message.reply_text(confirmation_text)

    async def cmd_reject_appeal(self, update: Update, context: CallbackContext):
        """Команда /reject_appeal для отклонения обжалования"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("Использование: /reject_appeal <appeal_id> [причина]")
            return
        
        try:
            appeal_id = int(context.args[0])
            reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Не указана"
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID обжалования")
            return
        
        appeal = db.get_appeal_by_id(appeal_id)
        if not appeal:
            await update.message.reply_text("❌ Обжалование не найдено")
            return
        
        if appeal.status != "pending":
            await update.message.reply_text("❌ Обжалование уже рассмотрено")
            return
        
        admin_id = update.effective_user.id
        success = db.update_appeal_status(appeal_id, "rejected", admin_id, reason)
        
        if success:
            await update.message.reply_text(f"✅ Обжалование #{appeal_id} отклонено")
            
            # Уведомляем пользователя
            try:
                await self.application.bot.send_message(
                    chat_id=appeal.user_id,
                    text=f"❌ Ваше обжалование #{appeal_id} отклонено.\nПричина: {reason}"
                )
            except Exception as e:
                self.logger.error(f"Ошибка уведомления пользователя: {e}")
        else:
            await update.message.reply_text("❌ Ошибка при отклонении обжалования")

    async def cmd_confirm_accept(self, update: Update, context: CallbackContext):
        """Команда /confirm_accept для подтверждения принятия обжалования"""
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Команда доступна только администраторам")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text("❌ Некорректное использование команды")
            return
        
        try:
            appeal_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID обжалования")
            return
        
        appeal = db.get_appeal_by_id(appeal_id)
        if not appeal or appeal.status != "pending":
            await update.message.reply_text("❌ Обжалование не найдено или уже рассмотрено")
            return
        
        admin_id = update.effective_user.id
        
        # Принимаем обжалование
        success = db.update_appeal_status(appeal_id, "approved", admin_id, "Обжалование принято")
        
        if success:
            # Разблокируем пользователя
            db.unban_user(appeal.user_id)
            
            await update.message.reply_text(f"✅ Обжалование #{appeal_id} принято, пользователь разблокирован")
            
            # Уведомляем пользователя
            try:
                await self.application.bot.send_message(
                    chat_id=appeal.user_id,
                    text=f"🎉 Ваше обжалование #{appeal_id} принято! Вы разблокированы."
                )
            except Exception as e:
                self.logger.error(f"Ошибка уведомления пользователя: {e}")
        else:
            await update.message.reply_text("❌ Ошибка при принятии обжалования")
        
    async def error_handler(self, update: Update, context: CallbackContext):
        """Обработчик ошибок"""
        self.logger.error(f"Ошибка при обработке обновления: {context.error}")
        
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ Произошла ошибка при обработке сообщения"
                )
            except TelegramError:
                pass  # Игнорируем ошибки отправки

# Глобальный экземпляр бота
bot = ModerationBot()