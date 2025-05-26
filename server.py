#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Серверная версия бота без GUI для облачного деплоя
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from config import bot_config
from bot import bot

async def main():
    """Главная функция сервера"""
    print("🚂 Railway Server - Telegram Bot Модерация СКВ СПб")
    print("=" * 50)
    
    # Проверяем конфигурацию
    if not bot_config.BOT_TOKEN:
        print("❌ BOT_TOKEN не установлен!")
        return False
    
    print(f"🔧 Конфигурация:")
    print(f"   BOT_TOKEN: {'✅ Установлен' if bot_config.BOT_TOKEN else '❌ НЕ УСТАНОВЛЕН'}")
    print(f"   CHAT_ID: {bot_config.CHAT_ID or '❌ НЕ УСТАНОВЛЕН'}")
    print(f"   OpenAI: {'✅ Включен' if bot_config.USE_OPENAI_ANALYSIS else '❌ Выключен'}")
    print()
    
    try:
        # Настройка логирования
        bot.setup_logging()
        
        print("🚀 Инициализация бота...")
        await bot.initialize()
        
        print("▶️ Запуск бота...")
        await bot.start()
        
        print("✅ Бот запущен успешно!")
        print("🔄 Бот работает... (Ctrl+C для остановки)")
        
        # Ждем до получения сигнала остановки
        try:
            while bot.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Получен сигнал остановки...")
        
        print("🔄 Остановка бота...")
        await bot.stop()
        print("✅ Бот остановлен")
        
        return True
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.error(f"Критическая ошибка: {e}")
        return False

if __name__ == "__main__":
    # Запуск без GUI
    success = asyncio.run(main())
    sys.exit(0 if success else 1)