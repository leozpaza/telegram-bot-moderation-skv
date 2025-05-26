#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный файл запуска Telegram-бота модерации СКВ СПб

Использование:
    python main.py              - Запуск с GUI
    python main.py --console    - Запуск только бота в консоли
    python main.py --help       - Показать справку
"""

import sys
import argparse
import asyncio
import logging
import signal
import os
from pathlib import Path

# Добавляем текущую директорию в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent))

from config import bot_config
from bot import bot
# Условный импорт GUI только если не на сервере
GUI_AVAILABLE = True
try:
    if os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('DYNO') or os.getenv('HEROKU_APP_NAME'):
        # В облачной среде GUI не нужен
        GUI_AVAILABLE = False
        ModerationGUI = None
    else:
        from gui import ModerationGUI
except ImportError:
    GUI_AVAILABLE = False
    ModerationGUI = None
    print("⚠️ GUI недоступен - работаем только в консольном режиме")

# Проверка на Railway деплой
def is_railway_deploy():
    return os.getenv('RAILWAY_ENVIRONMENT') is not None

def setup_railway_config():
    """Настройка для Railway"""
    if is_railway_deploy():
        # Railway автоматически предоставляет PORT
        port = os.getenv('PORT', '8000')
        # Можно добавить дополнительные настройки для облака
        print(f"🚂 Запуск на Railway, порт: {port}")
        return True
    return False

def setup_signal_handlers():
    """Настройка обработчиков сигналов для корректного завершения"""
    def signal_handler(signum, frame):
        print(f"\nПолучен сигнал {signum}. Завершение работы...")
        if bot.is_running:
            loop = asyncio.get_event_loop()
            loop.create_task(bot.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def run_console_mode():
    """Запуск бота только в консольном режиме"""
    try:
        print("🤖 Telegram Bot Модерация СКВ СПб")
        print("=" * 50)
        
        # Проверяем наличие обязательных настроек
        if not bot_config.BOT_TOKEN:
            print("❌ Ошибка: Не указан BOT_TOKEN!")
            print("Установите переменную окружения BOT_TOKEN или настройте конфигурацию.")
            return False
        
        # Настройка логирования
        bot.setup_logging()
        
        print("📋 Загруженная конфигурация:")
        print(f"   • Chat ID: {bot_config.CHAT_ID or 'Не указан'}")
        print(f"   • Admin Chat ID: {bot_config.ADMIN_CHAT_ID or 'Не указан'}")
        print(f"   • OpenAI анализ: {'Включен' if bot_config.USE_OPENAI_ANALYSIS else 'Выключен'}")
        print(f"   • Автоудаление: {'Включено' if bot_config.AUTO_DELETE_BANNED_WORDS else 'Выключено'}")
        print(f"   • Автобан: {'Включен' if bot_config.AUTO_BAN_ON_BANNED_WORDS else 'Выключен'}")
        print()
        
        print("🚀 Инициализация бота...")
        await bot.initialize()
        
        print("▶️ Запуск бота...")
        await bot.start()
        
        print("✅ Бот запущен и готов к работе!")
        print("Нажмите Ctrl+C для остановки")
        print("=" * 50)
        
        # Ждем до получения сигнала остановки
        try:
            while bot.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Получен сигнал остановки...")
        
        print("🔄 Остановка бота...")
        await bot.stop()
        print("✅ Бот успешно остановлен")
        
        return True
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка в консольном режиме: {e}")
        return False

def run_gui_mode():
    """Запуск с графическим интерфейсом"""
    if not GUI_AVAILABLE or ModerationGUI is None:
        print("❌ GUI недоступен в этой среде")
        print("🔄 Переключение на консольный режим...")
        return run_console_mode()
    
    try:
        print("🖥️ Запуск графического интерфейса...")
        
        # Создаем и запускаем GUI
        app = ModerationGUI()
        app.run()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка запуска GUI: {e}")
        print("🔄 Переключение на консольный режим...")
        return run_console_mode()

def check_dependencies():
    """Проверка наличия необходимых зависимостей"""
    missing_packages = []
    
    try:
        import telegram
    except ImportError:
        missing_packages.append("python-telegram-bot")
    
    try:
        import aiohttp
    except ImportError:
        missing_packages.append("aiohttp")
    
    try:
        import tkinter
    except ImportError:
        missing_packages.append("tkinter (обычно входит в стандартную поставку Python)")
    
    if missing_packages:
        print("❌ Отсутствуют необходимые пакеты:")
        for package in missing_packages:
            print(f"   • {package}")
        print("\nУстановите их командой:")
        print("pip install python-telegram-bot aiohttp")
        return False
    
    return True

def create_env_file_template():
    """Создание шаблона .env файла"""
    env_template = """# Конфигурация Telegram-бота модерации СКВ СПб
# Скопируйте этот файл в .env и заполните настройки

# Telegram настройки
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
CHAT_ID=YOUR_CHAT_ID_HERE
ADMIN_CHAT_ID=YOUR_ADMIN_CHAT_ID_HERE

# OpenAI настройки
OPENAI_API_KEY=YOUR_OPENAI_API_KEY_HERE
OPENAI_MODEL=gpt-3.5-turbo

# Настройки модерации
AUTO_DELETE_BANNED_WORDS=true
AUTO_BAN_ON_BANNED_WORDS=true
BAN_DURATION_MINUTES=60
WARNING_THRESHOLD=3

# Настройки анализа OpenAI
USE_OPENAI_ANALYSIS=true
OPENAI_ANALYSIS_THRESHOLD=0.7

# Логирование
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_TO_CONSOLE=true
"""
    
    env_file = Path(".env.example")
    if not env_file.exists():
        try:
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(env_template)
            print(f"✅ Создан шаблон конфигурации: {env_file}")
        except Exception as e:
            print(f"⚠️ Не удалось создать шаблон .env: {e}")

def load_env_file():
    """Загрузка переменных окружения из .env файла"""
    env_file = Path(".env")
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            print(f"✅ Загружена конфигурация из {env_file}")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки .env файла: {e}")

def print_logo():
    """Вывод логотипа приложения"""
    logo = """
╔══════════════════════════════════════════════════════════════╗
║              Telegram Bot Модерация СКВ СПб                  ║
║                                                              ║
║    🏢 ООО "Строительная Корпорация "Возрождение СПб"         ║
║    🤖 Автоматическая модерация чата управляющей компании     ║
║    📱 Фильтрация, AI-анализ, статистика                     ║
║                                                              ║
║    Версия: 1.0                                               ║
║    Разработано: 2025, Май                                         ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(logo)

def main():
    """Главная функция приложения"""
    # Настройка аргументов командной строки
    parser = argparse.ArgumentParser(
        description="Telegram-бот модерации для СКВ СПб",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                 Запуск с графическим интерфейсом
  python main.py --console       Запуск только бота в консоли
  python main.py --check-deps    Проверка зависимостей
  python main.py --create-env    Создание шаблона конфигурации
  
Переменные окружения:
  BOT_TOKEN                      Токен Telegram бота (обязательно)
  CHAT_ID                        ID чата для модерации
  ADMIN_CHAT_ID                  ID админского чата
  OPENAI_API_KEY                 Ключ OpenAI API
  
Более подробную настройку можно выполнить через GUI или .env файл.
"""
    )
    
    parser.add_argument(
        '--console', 
        action='store_true',
        help='Запуск только бота без GUI'
    )
    
    parser.add_argument(
        '--check-deps',
        action='store_true', 
        help='Проверить наличие зависимостей'
    )
    
    parser.add_argument(
        '--create-env',
        action='store_true',
        help='Создать шаблон .env файла'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Telegram Bot Модерация СКВ СПб v1.0'
    )
    
    args = parser.parse_args()
    
    # Показываем логотип
    print_logo()
    
    # Проверка зависимостей
    if args.check_deps:
        print("🔍 Проверка зависимостей...")
        if check_dependencies():
            print("✅ Все зависимости установлены")
        sys.exit(0)
    
    # Создание шаблона .env
    if args.create_env:
        create_env_file_template()
        sys.exit(0)
    
    # Проверяем зависимости перед запуском
    if not check_dependencies():
        sys.exit(1)
    
    # Загружаем переменные окружения
    load_env_file()
    create_env_file_template()  # Создаем шаблон если его нет
    
    # Настройка обработчиков сигналов
    setup_signal_handlers()
    
    is_cloud = setup_railway_config()
    
    try:
        if args.console or is_cloud:
            # Консольный режим (обязательно в облаке)
            print("🖥️ Режим: Консольный")
            success = asyncio.run(run_console_mode())
        else:
            # GUI режим (только локально)
            if GUI_AVAILABLE:
                print("🖼️ Режим: Графический интерфейс")
                success = run_gui_mode()
            else:
                print("⚠️ GUI недоступен, запуск в консольном режиме")
                success = asyncio.run(run_console_mode())
        
        if success:
            print("\n✅ Программа завершена успешно")
            sys.exit(0)
        else:
            print("\n❌ Программа завершена с ошибками")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Прерывание пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка в main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()