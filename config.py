# -*- coding: utf-8 -*-
"""
Конфигурационные настройки для Telegram-бота модерации СКВ СПб
"""

import os
from typing import Dict, List
from dataclasses import dataclass, field

@dataclass
class BotConfig:
    """Конфигурация бота"""
    # Telegram настройки
    BOT_TOKEN: str = ""
    CHAT_ID: str = ""
    ADMIN_CHAT_ID: str = ""
    
    # OpenAI настройки
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    
    # Настройки модерации
    AUTO_DELETE_BANNED_WORDS: bool = True
    AUTO_BAN_ON_BANNED_WORDS: bool = True
    BAN_DURATION_MINUTES: int = 60  # Продолжительность бана в минутах
    WARNING_THRESHOLD: int = 3  # Количество предупреждений до бана

    # Настройки системы доверия
    TRUST_SYSTEM_ENABLED: bool = True
    TRUST_DAYS_THRESHOLD: int = 3  # Дней до получения доверия
    TRUST_MESSAGES_THRESHOLD: int = 10  # Сообщений до получения доверия
    LINK_DETECTION_ENABLED: bool = True
    AUTO_DELETE_LINKS_FROM_NEW: bool = True
    BAN_ON_REPEATED_LINK_VIOLATION: bool = True
    TRUSTED_DOMAINS: List[str] = field(default_factory=list)  # Доверенные домены (t.me, youtube.com и т.д.)
    
    # Настройки анализа OpenAI
    USE_OPENAI_ANALYSIS: bool = True
    OPENAI_ANALYSIS_THRESHOLD: float = 0.85  # Порог для определения нарушения (0-1)
    
    # Файлы базы данных
    DATABASE_FILE: str = "moderation.db"
    LOG_FILE: str = "moderation.log"
    
    # Настройки логирования
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = True
    LOG_TO_CONSOLE: bool = True

# Правила управляющей компании для анализа OpenAI
COMPANY_RULES = """
Правила общения в чате управляющей компании СКВ СПб:

ЗАПРЕЩЕНО:
1. Использовать нелитературную лексику и обсценную лексику
2. Оскорблять, угрожать другим участникам чата, администраторам, сотрудникам УК
3. Публиковать записи, не относящиеся к работе управляющей компании
4. Проявлять неуважительное отношение (сексизм, шовинизм, расизм, религиозная и политическая нетерпимость)
5. Разглашать личную информацию участников без согласия
6. Флудить, флеймить, троллить, писать одно и то же несколько раз
7. Дублировать заблокированные аккаунты
8. Писать заглавными буквами или злоупотреблять восклицательными знаками
9. Размещать рекламу сторонних сайтов, товаров и услуг
10. Обсуждать деятельность других компаний, не связанных с УК
11. Заниматься пропагандой наркотиков, публиковать неприличный контент
12. Нарушать законодательство РФ

ВАЖНО: Заявки через социальные сети НЕ ПРИНИМАЮТСЯ. Для заявок использовать:
- Телефон: +7 (812) 325-35-35
- Мобильное приложение «ЛСР»
- Обращение к управляющему МКД

Рабочие часы для ответов в соцсетях: будние дни с 8:30 до 17:00.
"""

# Промпт для анализа OpenAI
OPENAI_ANALYSIS_PROMPT = """
Ты - модератор чата управляющей компании. Проанализируй следующее сообщение на соответствие правилам:

{rules}

Сообщение для анализа: "{message}"

ВАЖНО: К ТЕМАТИКЕ УК ОТНОСЯТСЯ:
- Вопросы о ремонте, покраске, уборке придомовой территории
- Проблемы с лифтами, подъездами, дворами, заборами, парковками
- Коммунальные услуги, отопление, водоснабжение
- Управление домом, собрания собственников
- Заявки на ремонт и обслуживание

НЕ СЧИТАЙ НАРУШЕНИЕМ:
- Вежливые вопросы о работе УК
- Просьбы о ремонте или обслуживании
- Сообщения о проблемах в доме/дворе
- Благодарности за работу

НАРУШЕНИЯМИ СЧИТАЙ ТОЛЬКО:
- Явные оскорбления и мат
- Откровенную рекламу товаров/услуг
- Политику, религию, не связанную с УК
- Спам (много одинаковых сообщений)

Ответь в формате JSON:
{{
    "violation": true/false,
    "violation_type": "тип нарушения или null",
    "confidence": 0.0-1.0,
    "reason": "подробное объяснение решения",
    "action": "рекомендуемое действие: delete/warn/ban/none"
}}
"""

# Типы нарушений
VIOLATION_TYPES = {
    "bad_language": "Нелитературная лексика",
    "insults": "Оскорбления и угрозы", 
    "offtopic": "Сообщения не по теме",
    "disrespect": "Неуважительное отношение",
    "personal_info": "Разглашение личной информации",
    "spam": "Спам и флуд",
    "caps": "Злоупотребление капсом",
    "advertising": "Реклама",
    "inappropriate": "Неприличный контент",
    "illegal": "Нарушение законодательства",
    "suspicious_links": "Подозрительные ссылки"
}

# Действия модерации
MODERATION_ACTIONS = {
    "none": "Без действий",
    "warn": "Предупреждение",
    "delete": "Удаление сообщения", 
    "mute": "Временное ограничение",
    "ban": "Блокировка"
}

# Тексты сообщений бота
BOT_MESSAGES = {
    "banned_word_warning": "⚠️ Ваше сообщение содержит недопустимую лексику и было удалено.",
    "ai_violation_warning": "⚠️ Ваше сообщение нарушает правила чата и было удалено.",
    "user_banned": "🚫 Пользователь заблокирован за нарушение правил чата.",
    "user_muted": "🔇 Пользователь временно ограничен в правах за нарушение правил.",
    "user_warned": "⚠️ Пользователю выдано предупреждение за нарушение правил.",

    # 📋 Полный текст правил вставляем через f-строку
    "rules_reminder": f"""📋 Напоминаем правила нашего чата:

{COMPANY_RULES}

Соблюдение правил поможет сделать общение комфортным для всех участников.
""",

    "link_violation_warning": (
        "⚠️ Ваше сообщение со ссылками было удалено. "
        "Новые участники не могут отправлять ссылки первые дни."
    ),
    "link_violation_ban": "🚫 Вы заблокированы за повторную отправку ссылок.",
    "trust_level_updated": "🔒 Ваш уровень доверия обновлен"
}

def load_config_from_env() -> BotConfig:
    """Загружает конфигурацию из переменных окружения"""
    config = BotConfig()
    
    config.BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    config.CHAT_ID = os.getenv("CHAT_ID", "")
    config.ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
    config.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Настройки системы доверия
    config.TRUST_SYSTEM_ENABLED = os.getenv("TRUST_SYSTEM_ENABLED", "true").lower() == "true"
    config.TRUST_DAYS_THRESHOLD = int(os.getenv("TRUST_DAYS_THRESHOLD", "3"))
    config.TRUST_MESSAGES_THRESHOLD = int(os.getenv("TRUST_MESSAGES_THRESHOLD", "10"))
    config.LINK_DETECTION_ENABLED = os.getenv("LINK_DETECTION_ENABLED", "true").lower() == "true"
    config.AUTO_DELETE_LINKS_FROM_NEW = os.getenv("AUTO_DELETE_LINKS_FROM_NEW", "true").lower() == "true"
    config.BAN_ON_REPEATED_LINK_VIOLATION = os.getenv("BAN_ON_REPEATED_LINK_VIOLATION", "true").lower() == "true"

    # Доверенные домены
    trusted_domains_str = os.getenv("TRUSTED_DOMAINS", "t.me,youtube.com,youtu.be")
    if trusted_domains_str.strip():
        config.TRUSTED_DOMAINS = [domain.strip() for domain in trusted_domains_str.split(",") if domain.strip()]
    else:
        config.TRUSTED_DOMAINS = ["t.me", "youtube.com", "youtu.be"]
    
    # Булевы значения
    config.AUTO_DELETE_BANNED_WORDS = os.getenv("AUTO_DELETE_BANNED_WORDS", "true").lower() == "true"
    config.AUTO_BAN_ON_BANNED_WORDS = os.getenv("AUTO_BAN_ON_BANNED_WORDS", "true").lower() == "true"
    config.USE_OPENAI_ANALYSIS = os.getenv("USE_OPENAI_ANALYSIS", "true").lower() == "true"
    
    # Числовые значения
    try:
        config.BAN_DURATION_MINUTES = int(os.getenv("BAN_DURATION_MINUTES", "60"))
        config.WARNING_THRESHOLD = int(os.getenv("WARNING_THRESHOLD", "3"))
        config.OPENAI_ANALYSIS_THRESHOLD = float(os.getenv("OPENAI_ANALYSIS_THRESHOLD", "0.7"))
    except ValueError:
        pass  # Используем значения по умолчанию
    
    return config

def save_config_to_env(config: BotConfig) -> None:
    """Сохраняет конфигурацию в переменные окружения"""
    os.environ["BOT_TOKEN"] = config.BOT_TOKEN
    os.environ["CHAT_ID"] = config.CHAT_ID
    os.environ["ADMIN_CHAT_ID"] = config.ADMIN_CHAT_ID
    os.environ["OPENAI_API_KEY"] = config.OPENAI_API_KEY
    os.environ["AUTO_DELETE_BANNED_WORDS"] = str(config.AUTO_DELETE_BANNED_WORDS).lower()
    os.environ["AUTO_BAN_ON_BANNED_WORDS"] = str(config.AUTO_BAN_ON_BANNED_WORDS).lower()
    os.environ["USE_OPENAI_ANALYSIS"] = str(config.USE_OPENAI_ANALYSIS).lower()
    os.environ["BAN_DURATION_MINUTES"] = str(config.BAN_DURATION_MINUTES)
    os.environ["WARNING_THRESHOLD"] = str(config.WARNING_THRESHOLD)
    os.environ["OPENAI_ANALYSIS_THRESHOLD"] = str(config.OPENAI_ANALYSIS_THRESHOLD)
    os.environ["TRUST_SYSTEM_ENABLED"] = str(config.TRUST_SYSTEM_ENABLED).lower()
    os.environ["TRUST_DAYS_THRESHOLD"] = str(config.TRUST_DAYS_THRESHOLD)
    os.environ["TRUST_MESSAGES_THRESHOLD"] = str(config.TRUST_MESSAGES_THRESHOLD)
    os.environ["LINK_DETECTION_ENABLED"] = str(config.LINK_DETECTION_ENABLED).lower()
    os.environ["AUTO_DELETE_LINKS_FROM_NEW"] = str(config.AUTO_DELETE_LINKS_FROM_NEW).lower()
    os.environ["BAN_ON_REPEATED_LINK_VIOLATION"] = str(config.BAN_ON_REPEATED_LINK_VIOLATION).lower()
    if config.TRUSTED_DOMAINS:
        os.environ["TRUSTED_DOMAINS"] = ",".join(config.TRUSTED_DOMAINS)
    else:
        os.environ["TRUSTED_DOMAINS"] = "t.me,youtube.com,youtu.be"

def load_env_file():
    """Загрузка переменных окружения из .env файла"""
    env_file = ".env"
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            print(f"Загружена конфигурация из {env_file}")
        except Exception as e:
            print(f"Ошибка загрузки .env файла: {e}")

# Загружаем .env при импорте модуля
load_env_file()

def save_to_env_file(config_obj):
    """Сохранение конфигурации в .env файл"""
    env_content = f"""# Конфигурация Telegram-бота модерации СКВ СПб
# Telegram настройки
BOT_TOKEN={config_obj.BOT_TOKEN}
CHAT_ID={config_obj.CHAT_ID}
ADMIN_CHAT_ID={config_obj.ADMIN_CHAT_ID}

# OpenAI настройки
OPENAI_API_KEY={config_obj.OPENAI_API_KEY}
OPENAI_MODEL={config_obj.OPENAI_MODEL}

# Настройки модерации
AUTO_DELETE_BANNED_WORDS={str(config_obj.AUTO_DELETE_BANNED_WORDS).lower()}
AUTO_BAN_ON_BANNED_WORDS={str(config_obj.AUTO_BAN_ON_BANNED_WORDS).lower()}
BAN_DURATION_MINUTES={config_obj.BAN_DURATION_MINUTES}
WARNING_THRESHOLD={config_obj.WARNING_THRESHOLD}

# Настройки анализа OpenAI
USE_OPENAI_ANALYSIS={str(config_obj.USE_OPENAI_ANALYSIS).lower()}
OPENAI_ANALYSIS_THRESHOLD={config_obj.OPENAI_ANALYSIS_THRESHOLD}

# Настройки системы доверия
TRUST_SYSTEM_ENABLED={str(config_obj.TRUST_SYSTEM_ENABLED).lower()}
TRUST_DAYS_THRESHOLD={config_obj.TRUST_DAYS_THRESHOLD}
TRUST_MESSAGES_THRESHOLD={config_obj.TRUST_MESSAGES_THRESHOLD}
LINK_DETECTION_ENABLED={str(config_obj.LINK_DETECTION_ENABLED).lower()}
AUTO_DELETE_LINKS_FROM_NEW={str(config_obj.AUTO_DELETE_LINKS_FROM_NEW).lower()}
BAN_ON_REPEATED_LINK_VIOLATION={str(config_obj.BAN_ON_REPEATED_LINK_VIOLATION).lower()}
TRUSTED_DOMAINS={",".join(config_obj.TRUSTED_DOMAINS or [])}

# Логирование
LOG_LEVEL={config_obj.LOG_LEVEL}
LOG_TO_FILE={str(config_obj.LOG_TO_FILE).lower()}
LOG_TO_CONSOLE={str(config_obj.LOG_TO_CONSOLE).lower()}
"""
    
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        print("Настройки сохранены в .env файл")
    except Exception as e:
        print(f"Ошибка сохранения в .env файл: {e}")

# Глобальная конфигурация
bot_config = load_config_from_env()