# -*- coding: utf-8 -*-
"""
Графический интерфейс управления Telegram-ботом модерации СКВ СПб
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import asyncio
import logging
from datetime import datetime
import json
import os
from typing import Dict, Any

from config import bot_config, save_config_to_env, VIOLATION_TYPES, MODERATION_ACTIONS
from database import db
from banned_words import BANNED_WORDS, add_banned_word, remove_banned_word
from bot import bot
from openai_analyzer import analyzer

class ModerationGUI:
    """Главный класс графического интерфейса"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Telegram Bot Модерация СКВ СПб")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)
        
        # Переменные для контроля бота
        self.bot_running = False
        self.bot_thread = None
        self.status_update_running = False
        
        # Настройка стилей
        self.setup_styles()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Загрузка настроек ПОСЛЕ создания виджетов
        self.load_settings()
        
        # Запуск обновления статуса
        self.start_status_updates()
        
        # Обработчик закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_styles(self):
        """Настройка стилей интерфейса"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Стили для кнопок
        style.configure('Success.TButton', foreground='white', background='#28a745')
        style.configure('Danger.TButton', foreground='white', background='#dc3545')
        style.configure('Warning.TButton', foreground='white', background='#ffc107')
        style.configure('Info.TButton', foreground='white', background='#17a2b8')
    
    def create_widgets(self):
        """Создание виджетов интерфейса"""
        # Главное меню
        self.create_menubar()
        
        # Панель инструментов
        self.create_toolbar()
        
        # Основная область с вкладками
        self.create_notebook()
        
        # Статусная строка
        self.create_statusbar()
    
    def create_menubar(self):
        """Создание меню"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Меню Файл
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Сохранить настройки", command=self.save_settings)
        file_menu.add_command(label="Загрузить настройки", command=self.load_settings_from_file)
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт логов", command=self.export_logs)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.on_closing)
        
        # Меню Бот
        bot_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Бот", menu=bot_menu)
        bot_menu.add_command(label="Запустить", command=self.start_bot)
        bot_menu.add_command(label="Остановить", command=self.stop_bot)
        bot_menu.add_separator()
        bot_menu.add_command(label="Тест подключения", command=self.test_connections)
        
        # Меню Помощь
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Помощь", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)
    
    def create_toolbar(self):
        """Создание панели инструментов"""
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Кнопки управления ботом
        self.start_btn = ttk.Button(toolbar, text="▶ Запустить бота", 
                                   command=self.start_bot, style='Success.TButton')
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(toolbar, text="⏹ Остановить бота", 
                                  command=self.stop_bot, style='Danger.TButton', state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Разделитель
        ttk.Separator(toolbar, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Статус бота
        self.status_label = ttk.Label(toolbar, text="Статус: Остановлен", foreground='red')
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Счетчики
        self.stats_label = ttk.Label(toolbar, text="Сообщений: 0 | Нарушений: 0")
        self.stats_label.pack(side=tk.RIGHT, padx=10)
    
    def create_notebook(self):
        """Создание блокнота с вкладками"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Вкладки
        self.create_settings_tab()
        self.create_monitoring_tab()
        self.create_users_tab()
        self.create_trust_tab()
        self.create_banned_words_tab()
        self.create_logs_tab()
    
    def create_settings_tab(self):
        """Вкладка настроек"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="⚙️ Настройки")

        # Создание областей с прокруткой
        canvas = tk.Canvas(settings_frame)
        scrollbar = ttk.Scrollbar(settings_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # ДОБАВЛЕНО: Сохраняем ID окна на канвасе для изменения его ширины
        self.settings_canvas_window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # ДОБАВЛЕНО: Функция для обновления ширины scrollable_frame при изменении размера canvas
        def _configure_scrollable_frame_width(event):
            canvas.itemconfig(self.settings_canvas_window_id, width=event.width)
        canvas.bind("<Configure>", _configure_scrollable_frame_width)

        # Telegram настройки
        telegram_group = ttk.LabelFrame(scrollable_frame, text="Настройки Telegram", padding=10)
        telegram_group.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(telegram_group, text="Bot Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.bot_token_var = tk.StringVar(value=bot_config.BOT_TOKEN)
        # ИЗМЕНЕНО: убран width, sticky=tk.EW для растягивания
        ttk.Entry(telegram_group, textvariable=self.bot_token_var, show="*").grid(row=0, column=1, sticky=tk.EW, padx=5)

        ttk.Label(telegram_group, text="ID чата:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.chat_id_var = tk.StringVar(value=bot_config.CHAT_ID)
        # ИЗМЕНЕНО: убран width, sticky=tk.EW для растягивания
        ttk.Entry(telegram_group, textvariable=self.chat_id_var).grid(row=1, column=1, sticky=tk.EW, padx=5)

        ttk.Label(telegram_group, text="ID админ чата:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.admin_chat_id_var = tk.StringVar(value=bot_config.ADMIN_CHAT_ID)
        # ИЗМЕНЕНО: убран width, sticky=tk.EW для растягивания
        ttk.Entry(telegram_group, textvariable=self.admin_chat_id_var).grid(row=2, column=1, sticky=tk.EW, padx=5)
        
        # ДОБАВЛЕНО: Настройка растяжения колонки для полей ввода
        telegram_group.columnconfigure(1, weight=1)

        # OpenAI настройки
        openai_group = ttk.LabelFrame(scrollable_frame, text="Настройки OpenAI", padding=10)
        openai_group.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(openai_group, text="API Key:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.openai_key_var = tk.StringVar(value=bot_config.OPENAI_API_KEY)
        # ИЗМЕНЕНО: убран width, sticky=tk.EW для растягивания
        ttk.Entry(openai_group, textvariable=self.openai_key_var, show="*").grid(row=0, column=1, sticky=tk.EW, padx=5)

        ttk.Label(openai_group, text="Модель:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.openai_model_var = tk.StringVar(value=bot_config.OPENAI_MODEL)
        # ИЗМЕНЕНО: Добавлена модель "gpt-4o"
        model_combo = ttk.Combobox(openai_group, textvariable=self.openai_model_var,
                                  values=["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o"]) # ИЗМЕНЕНО
        model_combo.grid(row=1, column=1, sticky=tk.EW, padx=5) # ИЗМЕНЕНО: sticky=tk.EW

        self.use_openai_var = tk.BooleanVar(value=bot_config.USE_OPENAI_ANALYSIS)
        ttk.Checkbutton(openai_group, text="Использовать анализ OpenAI",
                       variable=self.use_openai_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=5)

        ttk.Label(openai_group, text="Порог уверенности:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.openai_threshold_var = tk.DoubleVar(value=bot_config.OPENAI_ANALYSIS_THRESHOLD)
        # Для Scale виджета, sticky=tk.EW также поможет ему занять доступное место, если это нужно
        ttk.Scale(openai_group, from_=0.0, to=1.0, variable=self.openai_threshold_var,
                 orient=tk.HORIZONTAL, length=200).grid(row=3, column=1, sticky=tk.EW, padx=5) # ИЗМЕНЕНО: sticky=tk.EW

        # ДОБАВЛЕНО: Настройка растяжения колонки для полей ввода и комбобокса
        openai_group.columnconfigure(1, weight=1)

        # Настройки модерации
        moderation_group = ttk.LabelFrame(scrollable_frame, text="Настройки модерации", padding=10)
        moderation_group.pack(fill=tk.X, padx=5, pady=5)

        self.auto_delete_var = tk.BooleanVar(value=bot_config.AUTO_DELETE_BANNED_WORDS)
        ttk.Checkbutton(moderation_group, text="Автоудаление запрещенных слов",
                       variable=self.auto_delete_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)

        self.auto_ban_var = tk.BooleanVar(value=bot_config.AUTO_BAN_ON_BANNED_WORDS)
        ttk.Checkbutton(moderation_group, text="Автобан за запрещенные слова",
                       variable=self.auto_ban_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)

        ttk.Label(moderation_group, text="Длительность бана (минуты):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.ban_duration_var = tk.IntVar(value=bot_config.BAN_DURATION_MINUTES)
        # Spinbox обычно имеет фиксированную ширину, но если нужно растягивать, можно использовать sticky=tk.EW
        ttk.Spinbox(moderation_group, from_=1, to=10080, textvariable=self.ban_duration_var,
                   width=10).grid(row=2, column=1, sticky=tk.W, padx=5) # Оставляем sticky=tk.W для Spinbox если не нужен сильный stretch

        ttk.Label(moderation_group, text="Лимит предупреждений:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.warning_threshold_var = tk.IntVar(value=bot_config.WARNING_THRESHOLD)
        ttk.Spinbox(moderation_group, from_=1, to=10, textvariable=self.warning_threshold_var,
                   width=10).grid(row=3, column=1, sticky=tk.W, padx=5) # Оставляем sticky=tk.W для Spinbox

        # ДОБАВЛЕНО: Настройка растяжения колонки для Spinbox, если необходимо (пока вес 0, т.е. не растягивается сильно)
        moderation_group.columnconfigure(1, weight=0) # Можно поставить weight=1 если нужно растягивать Spinbox

        # Кнопки
        buttons_frame = ttk.Frame(scrollable_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=10)

        ttk.Button(buttons_frame, text="Сохранить настройки",
                  command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Сбросить",
                  command=self.reset_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Тест подключений",
                  command=self.test_connections, style='Info.TButton').pack(side=tk.RIGHT, padx=5)

        # Упаковка прокрутки
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_monitoring_tab(self):
        """Вкладка мониторинга"""
        monitoring_frame = ttk.Frame(self.notebook)
        self.notebook.add(monitoring_frame, text="📊 Мониторинг")
        
        # Статистика в реальном времени
        stats_group = ttk.LabelFrame(monitoring_frame, text="Статистика в реальном времени", padding=10)
        stats_group.pack(fill=tk.X, padx=5, pady=5)
        
        stats_frame = ttk.Frame(stats_group)
        stats_frame.pack(fill=tk.X)
        
        # Левая колонка статистики
        left_stats = ttk.Frame(stats_frame)
        left_stats.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.messages_count_label = ttk.Label(left_stats, text="Обработано сообщений: 0", font=('Arial', 12, 'bold'))
        self.messages_count_label.pack(anchor=tk.W, pady=2)
        
        self.violations_count_label = ttk.Label(left_stats, text="Нарушений обнаружено: 0", font=('Arial', 12, 'bold'))
        self.violations_count_label.pack(anchor=tk.W, pady=2)
        
        self.users_banned_label = ttk.Label(left_stats, text="Пользователей заблокировано: 0", font=('Arial', 12, 'bold'))
        self.users_banned_label.pack(anchor=tk.W, pady=2)
        
        # Правая колонка статистики
        right_stats = ttk.Frame(stats_frame)
        right_stats.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        self.users_warned_label = ttk.Label(right_stats, text="Предупреждений выдано: 0", font=('Arial', 12, 'bold'))
        self.users_warned_label.pack(anchor=tk.W, pady=2)
        
        self.uptime_label = ttk.Label(right_stats, text="Время работы: 00:00:00", font=('Arial', 12, 'bold'))
        self.uptime_label.pack(anchor=tk.W, pady=2)
        
        # База данных статистика
        db_stats_group = ttk.LabelFrame(monitoring_frame, text="Статистика базы данных", padding=10)
        db_stats_group.pack(fill=tk.X, padx=5, pady=5)
        
        self.db_stats_text = scrolledtext.ScrolledText(db_stats_group, height=10, wrap=tk.WORD)
        self.db_stats_text.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки обновления
        update_frame = ttk.Frame(monitoring_frame)
        update_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(update_frame, text="Обновить статистику", 
                  command=self.update_db_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(update_frame, text="Очистить истекшие баны", 
                  command=self.cleanup_bans).pack(side=tk.LEFT, padx=5)
    
    def create_users_tab(self):
        """Вкладка управления пользователями"""
        users_frame = ttk.Frame(self.notebook)
        self.notebook.add(users_frame, text="👥 Пользователи")
        
        # Поиск пользователя
        search_frame = ttk.LabelFrame(users_frame, text="Поиск пользователя", padding=10)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(search_frame, text="User ID:").pack(side=tk.LEFT, padx=5)
        self.user_search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.user_search_var, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="Найти", command=self.search_user).pack(side=tk.LEFT, padx=5)
        
        # Информация о пользователе
        user_info_frame = ttk.LabelFrame(users_frame, text="Информация о пользователе", padding=10)
        user_info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.user_info_text = scrolledtext.ScrolledText(user_info_frame, height=8, wrap=tk.WORD)
        self.user_info_text.pack(fill=tk.BOTH, expand=True)
        
        # Действия с пользователем
        actions_frame = ttk.LabelFrame(users_frame, text="Действия", padding=10)
        actions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Первая строка действий
        actions_row1 = ttk.Frame(actions_frame)
        actions_row1.pack(fill=tk.X, pady=2)
        
        ttk.Button(actions_row1, text="Предупреждение", command=self.warn_user, 
                  style='Warning.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_row1, text="Заблокировать", command=self.ban_user, 
                  style='Danger.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(actions_row1, text="Разблокировать", command=self.unban_user, 
                  style='Success.TButton').pack(side=tk.LEFT, padx=5)
        
        # Вторая строка - настройки времени
        actions_row2 = ttk.Frame(actions_frame)
        actions_row2.pack(fill=tk.X, pady=2)
        
        ttk.Label(actions_row2, text="Время бана (минуты):").pack(side=tk.LEFT, padx=5)
        self.ban_time_var = tk.IntVar(value=60)
        ttk.Spinbox(actions_row2, from_=1, to=10080, textvariable=self.ban_time_var, 
                   width=10).pack(side=tk.LEFT, padx=5)
        
        # Обжалования пользователя
        appeals_frame = ttk.LabelFrame(users_frame, text="Обжалования пользователя", padding=10)
        appeals_frame.pack(fill=tk.X, padx=5, pady=5)

        self.appeals_info_text = scrolledtext.ScrolledText(appeals_frame, height=4, wrap=tk.WORD)
        self.appeals_info_text.pack(fill=tk.BOTH, expand=True)
        
        # История нарушений
        violations_frame = ttk.LabelFrame(users_frame, text="История нарушений", padding=10)
        violations_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Таблица нарушений
        columns = ('Дата', 'Тип', 'Действие', 'AI Уверенность')
        self.violations_tree = ttk.Treeview(violations_frame, columns=columns, show='headings', height=8)
        
        for col in columns:
            self.violations_tree.heading(col, text=col)
            self.violations_tree.column(col, width=150)
        
        violations_scrollbar = ttk.Scrollbar(violations_frame, orient=tk.VERTICAL, command=self.violations_tree.yview)
        self.violations_tree.configure(yscrollcommand=violations_scrollbar.set)
        
        self.violations_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        violations_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_banned_words_tab(self):
        """Вкладка управления запрещенными словами"""
        words_frame = ttk.Frame(self.notebook)
        self.notebook.add(words_frame, text="🚫 Запрещенные слова")
        
        # Добавление слов
        add_frame = ttk.LabelFrame(words_frame, text="Добавить слово", padding=10)
        add_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(add_frame, text="Новое слово:").pack(side=tk.LEFT, padx=5)
        self.new_word_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.new_word_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(add_frame, text="Добавить", command=self.add_banned_word).pack(side=tk.LEFT, padx=5)
        
        # Список слов
        list_frame = ttk.LabelFrame(words_frame, text="Список запрещенных слов", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Поиск в списке
        search_words_frame = ttk.Frame(list_frame)
        search_words_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(search_words_frame, text="Поиск:").pack(side=tk.LEFT, padx=5)
        self.search_words_var = tk.StringVar()
        self.search_words_var.trace('w', self.filter_banned_words)
        ttk.Entry(search_words_frame, textvariable=self.search_words_var, width=30).pack(side=tk.LEFT, padx=5)
        
        # Список с прокруткой
        words_list_frame = ttk.Frame(list_frame)
        words_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.words_listbox = tk.Listbox(words_list_frame, selectmode=tk.SINGLE)
        words_listbox_scroll = ttk.Scrollbar(words_list_frame, orient=tk.VERTICAL, command=self.words_listbox.yview)
        self.words_listbox.configure(yscrollcommand=words_listbox_scroll.set)
        
        self.words_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        words_listbox_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопки управления
        words_buttons_frame = ttk.Frame(list_frame)
        words_buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(words_buttons_frame, text="Удалить выбранное", 
                  command=self.remove_banned_word, style='Danger.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(words_buttons_frame, text="Экспорт списка", 
                  command=self.export_banned_words).pack(side=tk.LEFT, padx=5)
        ttk.Button(words_buttons_frame, text="Импорт списка", 
                  command=self.import_banned_words).pack(side=tk.LEFT, padx=5)
        
        # Загружаем список слов
        self.load_banned_words()
    
    def create_logs_tab(self):
        """Вкладка логов"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="📋 Логи")
        
        # Фильтры логов
        filters_frame = ttk.LabelFrame(logs_frame, text="Фильтры", padding=10)
        filters_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(filters_frame, text="Уровень:").pack(side=tk.LEFT, padx=5)
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_combo = ttk.Combobox(filters_frame, textvariable=self.log_level_var, 
                                      values=["DEBUG", "INFO", "WARNING", "ERROR"], width=10)
        log_level_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(filters_frame, text="Обновить", command=self.load_logs).pack(side=tk.LEFT, padx=10)
        ttk.Button(filters_frame, text="Очистить", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(filters_frame, text="Экспорт", command=self.export_logs).pack(side=tk.RIGHT, padx=5)
        
        # Область логов
        self.logs_text = scrolledtext.ScrolledText(logs_frame, wrap=tk.WORD, height=25)
        self.logs_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Автопрокрутка
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(logs_frame, text="Автопрокрутка", 
                       variable=self.auto_scroll_var).pack(anchor=tk.W, padx=5, pady=2)
        
        # Загружаем логи
        self.load_logs()

    def create_trust_tab(self):
        """Вкладка системы доверия"""
        trust_frame = ttk.Frame(self.notebook)
        self.notebook.add(trust_frame, text="🔒 Система доверия")

        # Создание областей с прокруткой
        trust_canvas = tk.Canvas(trust_frame)
        trust_scrollbar = ttk.Scrollbar(trust_frame, orient="vertical", command=trust_canvas.yview)
        trust_scrollable_frame = ttk.Frame(trust_canvas)

        trust_scrollable_frame.bind(
            "<Configure>",
            lambda e: trust_canvas.configure(scrollregion=trust_canvas.bbox("all"))
        )

        # ДОБАВЛЕНО: Сохраняем ID окна на канвасе для изменения его ширины
        self.trust_canvas_window_id = trust_canvas.create_window((0, 0), window=trust_scrollable_frame, anchor="nw")
        trust_canvas.configure(yscrollcommand=trust_scrollbar.set)

        # ДОБАВЛЕНО: Функция для обновления ширины trust_scrollable_frame при изменении размера trust_canvas
        def _configure_trust_scrollable_frame_width(event):
            trust_canvas.itemconfig(self.trust_canvas_window_id, width=event.width)
        trust_canvas.bind("<Configure>", _configure_trust_scrollable_frame_width)


        # Включение системы доверия
        enable_group = ttk.LabelFrame(trust_scrollable_frame, text="Основные настройки", padding=10)
        enable_group.pack(fill=tk.X, padx=5, pady=5)

        self.trust_enabled_var = tk.BooleanVar(value=bot_config.TRUST_SYSTEM_ENABLED)
        ttk.Checkbutton(enable_group, text="Включить систему доверия",
                    variable=self.trust_enabled_var).pack(anchor=tk.W, pady=2)

        self.link_detection_var = tk.BooleanVar(value=bot_config.LINK_DETECTION_ENABLED)
        ttk.Checkbutton(enable_group, text="Включить детекцию ссылок",
                    variable=self.link_detection_var).pack(anchor=tk.W, pady=2)

        # Пороги доверия
        thresholds_group = ttk.LabelFrame(trust_scrollable_frame, text="Пороги доверия", padding=10)
        thresholds_group.pack(fill=tk.X, padx=5, pady=5)
        # ИЗМЕНЕНО: weight=0, так как Spinbox имеет фиксированную ширину и мы его не растягиваем, а колонка с метками (0) может занимать остальное место
        thresholds_group.columnconfigure(0, weight=1) # Метки могут занимать больше места, если нужно
        thresholds_group.columnconfigure(1, weight=0) # Spinbox-ы не будут сильно растягиваться

        ttk.Label(thresholds_group, text="Дней в чате для доверия:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.trust_days_var = tk.IntVar(value=bot_config.TRUST_DAYS_THRESHOLD)
        ttk.Spinbox(thresholds_group, from_=1, to=30, textvariable=self.trust_days_var,
                width=10).grid(row=0, column=1, sticky=tk.W, padx=5) # sticky=tk.W для Spinbox

        ttk.Label(thresholds_group, text="Сообщений для доверия:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.trust_messages_var = tk.IntVar(value=bot_config.TRUST_MESSAGES_THRESHOLD)
        ttk.Spinbox(thresholds_group, from_=1, to=100, textvariable=self.trust_messages_var,
                width=10).grid(row=1, column=1, sticky=tk.W, padx=5) # sticky=tk.W для Spinbox

        # Действия при нарушениях
        actions_group = ttk.LabelFrame(trust_scrollable_frame, text="Действия при нарушениях", padding=10)
        actions_group.pack(fill=tk.X, padx=5, pady=5)

        self.auto_delete_links_var = tk.BooleanVar(value=bot_config.AUTO_DELETE_LINKS_FROM_NEW)
        ttk.Checkbutton(actions_group, text="Автоудаление ссылок от новых пользователей",
                    variable=self.auto_delete_links_var).pack(anchor=tk.W, pady=2)

        self.ban_repeated_links_var = tk.BooleanVar(value=bot_config.BAN_ON_REPEATED_LINK_VIOLATION)
        ttk.Checkbutton(actions_group, text="Бан за повторную отправку ссылок",
                    variable=self.ban_repeated_links_var).pack(anchor=tk.W, pady=2)

        # Доверенные домены
        domains_group = ttk.LabelFrame(trust_scrollable_frame, text="Доверенные домены", padding=10)
        domains_group.pack(fill=tk.X, padx=5, pady=5)
        # ДОБАВЛЕНО: Растягиваем колонку с полем ввода
        domains_group.columnconfigure(0, weight=1)


        ttk.Label(domains_group, text="Домены (через запятую):").grid(row=0, column=0, sticky=tk.W, pady=2) # ИЗМЕНЕНО: pack на grid
        self.trusted_domains_var = tk.StringVar(value=",".join(bot_config.TRUSTED_DOMAINS or []))
        domains_entry = ttk.Entry(domains_group, textvariable=self.trusted_domains_var)
        domains_entry.grid(row=1, column=0, sticky=tk.EW, pady=2, padx=5) # ИЗМЕНЕНО: pack на grid, sticky=tk.EW

        # Статистика доверия
        stats_group = ttk.LabelFrame(trust_scrollable_frame, text="Статистика системы доверия", padding=10)
        stats_group.pack(fill=tk.X, padx=5, pady=5)

        self.trust_stats_text = scrolledtext.ScrolledText(stats_group, height=8, wrap=tk.WORD)
        self.trust_stats_text.pack(fill=tk.BOTH, expand=True) # Это правильно для ScrolledText

        # Кнопки управления
        trust_buttons_frame = ttk.Frame(trust_scrollable_frame)
        trust_buttons_frame.pack(fill=tk.X, padx=5, pady=10)

        ttk.Button(trust_buttons_frame, text="Сохранить настройки доверия",
                command=self.save_trust_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(trust_buttons_frame, text="Обновить статистику",
                command=self.update_trust_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(trust_buttons_frame, text="Пересчитать уровни доверия",
                command=self.recalculate_trust_levels).pack(side=tk.LEFT, padx=5)

        # Упаковка прокрутки
        trust_canvas.pack(side="left", fill="both", expand=True)
        trust_scrollbar.pack(side="right", fill="y")

        # Загружаем статистику
        self.update_trust_stats()

    def save_trust_settings(self):
        """Сохранение настроек системы доверия"""
        try:
            # Обновляем конфигурацию
            bot_config.TRUST_SYSTEM_ENABLED = self.trust_enabled_var.get()
            bot_config.LINK_DETECTION_ENABLED = self.link_detection_var.get()
            bot_config.TRUST_DAYS_THRESHOLD = self.trust_days_var.get()
            bot_config.TRUST_MESSAGES_THRESHOLD = self.trust_messages_var.get()
            bot_config.AUTO_DELETE_LINKS_FROM_NEW = self.auto_delete_links_var.get()
            bot_config.BAN_ON_REPEATED_LINK_VIOLATION = self.ban_repeated_links_var.get()
            
            # Обрабатываем доверенные домены
            domains_text = self.trusted_domains_var.get().strip()
            if domains_text:
                bot_config.TRUSTED_DOMAINS = [domain.strip() for domain in domains_text.split(",") if domain.strip()]
            else:
                bot_config.TRUSTED_DOMAINS = []
            
            # Сохраняем в переменные окружения
            save_config_to_env(bot_config)
            
            self.status_text.set("Настройки системы доверия сохранены")
            messagebox.showinfo("Успех", "Настройки системы доверия сохранены!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")

    def update_trust_stats(self):
        """Обновление статистики системы доверия"""
        try:
            stats = db.get_trust_statistics()
            
            stats_text = f"""📊 Статистика системы доверия:

    👥 Пользователи по уровням доверия:"""
            
            trust_levels_names = {
                'new': 'Новые',
                'trusted': 'Доверенные', 
                'suspicious': 'Подозрительные'
            }
            
            for level, count in stats.get('trust_levels', {}).items():
                level_name = trust_levels_names.get(level, level)
                stats_text += f"\n   • {level_name}: {count}"
            
            stats_text += f"\n\n📈 Средние сообщения у доверенных: {stats.get('avg_trusted_messages', 0)}"
            
            # Общая статистика нарушений по ссылкам
            general_stats = db.get_statistics()
            violations = general_stats.get('top_violations', [])
            link_violations = next((count for violation_type, count in violations if violation_type == 'suspicious_links'), 0)
            
            stats_text += f"\n\n🔗 Нарушений по ссылкам: {link_violations}"
            
            self.trust_stats_text.delete(1.0, tk.END)
            self.trust_stats_text.insert(tk.END, stats_text)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить статистику: {e}")

    def recalculate_trust_levels(self):
        """Пересчет уровней доверия для всех пользователей"""
        try:
            if messagebox.askyesno("Подтверждение", "Пересчитать уровни доверия для всех пользователей?"):
                # Здесь должен быть метод для пересчета всех пользователей
                # Это может быть длительная операция, поэтому лучше в отдельном потоке
                
                def recalculate_thread():
                    try:
                        # Получаем всех пользователей и пересчитываем их уровни
                        # Этот метод нужно добавить в database.py
                        count = db.recalculate_all_trust_levels()
                        self.root.after(0, lambda: messagebox.showinfo("Результат", f"Пересчитано уровней доверия: {count}"))
                        self.root.after(0, self.update_trust_stats)
                    except Exception as e:
                        self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка пересчета: {e}"))
                
                threading.Thread(target=recalculate_thread, daemon=True).start()
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка пересчета: {e}")
    
    def create_statusbar(self):
        """Создание статусной строки"""
        self.statusbar = ttk.Frame(self.root)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_text = tk.StringVar(value="Готов к работе")
        ttk.Label(self.statusbar, textvariable=self.status_text).pack(side=tk.LEFT, padx=5)
        
        self.time_label = ttk.Label(self.statusbar, text="")
        self.time_label.pack(side=tk.RIGHT, padx=5)
        
        # Обновление времени
        self.update_time()
    
    def update_time(self):
        """Обновление времени в статусной строке"""
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.config(text=current_time)
        self.root.after(1000, self.update_time)
    
    def start_status_updates(self):
        """Запуск обновления статуса"""
        if not self.status_update_running:
            self.status_update_running = True
            self.update_status()
    
    def update_status(self):
        """Обновление статуса интерфейса"""
        if self.status_update_running:
            try:
                # Обновляем статистику бота
                if hasattr(bot, 'stats'):
                    self.messages_count_label.config(text=f"Обработано сообщений: {bot.stats['messages_processed']}")
                    self.violations_count_label.config(text=f"Нарушений обнаружено: {bot.stats['violations_detected']}")
                    self.users_banned_label.config(text=f"Пользователей заблокировано: {bot.stats['users_banned']}")
                    self.users_warned_label.config(text=f"Предупреждений выдано: {bot.stats['users_warned']}")
                    
                    if bot.stats['bot_started']:
                        uptime = datetime.now() - bot.stats['bot_started']
                        uptime_str = str(uptime).split('.')[0]
                        self.uptime_label.config(text=f"Время работы: {uptime_str}")
                
                # Обновляем статистику в тулбаре
                if hasattr(bot, 'stats'):
                    stats_text = f"Сообщений: {bot.stats['messages_processed']} | Нарушений: {bot.stats['violations_detected']}"
                    self.stats_label.config(text=stats_text)
                
            except Exception as e:
                print(f"Ошибка обновления статуса: {e}")
            
            # Планируем следующее обновление
            self.root.after(2000, self.update_status)
    
    def start_bot(self):
        """Запуск бота"""
        if self.bot_running:
            messagebox.showwarning("Предупреждение", "Бот уже запущен!")
            return
        
        # Сохраняем настройки перед запуском
        self.save_settings()
        
        # Проверяем обязательные настройки
        if not bot_config.BOT_TOKEN:
            messagebox.showerror("Ошибка", "Не указан Bot Token!")
            return
        
        try:
            self.status_text.set("Запуск бота...")
            
            # Запускаем бота в отдельном потоке
            def run_bot():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.run_bot_async())
                except Exception as error:
                    # Исправляем проблему с переменной e
                    self.root.after(0, lambda err=error: messagebox.showerror("Ошибка", f"Ошибка запуска бота: {err}"))
                    self.root.after(0, lambda: self.status_text.set("Ошибка запуска"))
                finally:
                    loop.close()
            
            self.bot_thread = threading.Thread(target=run_bot, daemon=True)
            self.bot_thread.start()
            
        except Exception as error:
            messagebox.showerror("Ошибка", f"Не удалось запустить бота: {error}")
            self.status_text.set("Ошибка запуска")
    
    async def run_bot_async(self):
        """Асинхронный запуск бота"""
        try:
            bot.setup_logging()
            await bot.initialize()
            await bot.start()
            
            # Обновляем UI в главном потоке
            self.root.after(0, self.on_bot_started)
            
        except Exception as error:
            # Исправляем проблему с lambda и переменной e
            self.root.after(0, lambda err=error: self.on_bot_error(err))
    
    def on_bot_started(self):
        """Обработчик успешного запуска бота"""
        self.bot_running = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="Статус: Запущен", foreground='green')
        self.status_text.set("Бот запущен и работает")
    
    def on_bot_error(self, error):
        """Обработчик ошибки запуска бота"""
        self.bot_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="Статус: Ошибка", foreground='red')
        self.status_text.set(f"Ошибка: {error}")
        messagebox.showerror("Ошибка", f"Ошибка запуска бота: {error}")
    
    def stop_bot(self):
        """Остановка бота"""
        if not self.bot_running:
            messagebox.showwarning("Предупреждение", "Бот не запущен!")
            return
        
        try:
            self.status_text.set("Остановка бота...")
            
            # Останавливаем бота
            def stop_bot_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(bot.stop())
                except Exception as error:
                    print(f"Ошибка остановки бота: {error}")
                finally:
                    loop.close()
                    self.root.after(0, self.on_bot_stopped)
            
            threading.Thread(target=stop_bot_async, daemon=True).start()
            
        except Exception as error:
            messagebox.showerror("Ошибка", f"Не удалось остановить бота: {error}")
    
    def on_bot_stopped(self):
        """Обработчик остановки бота"""
        self.bot_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="Статус: Остановлен", foreground='red')
        self.status_text.set("Бот остановлен")
    
    def save_settings(self):
        """Сохранение настроек"""
        try:
            # Обновляем конфигурацию
            bot_config.BOT_TOKEN = self.bot_token_var.get().strip()
            bot_config.CHAT_ID = self.chat_id_var.get().strip()
            bot_config.ADMIN_CHAT_ID = self.admin_chat_id_var.get().strip()
            bot_config.OPENAI_API_KEY = self.openai_key_var.get().strip()
            bot_config.OPENAI_MODEL = self.openai_model_var.get()
            bot_config.USE_OPENAI_ANALYSIS = self.use_openai_var.get()
            bot_config.OPENAI_ANALYSIS_THRESHOLD = self.openai_threshold_var.get()
            bot_config.AUTO_DELETE_BANNED_WORDS = self.auto_delete_var.get()
            bot_config.AUTO_BAN_ON_BANNED_WORDS = self.auto_ban_var.get()
            bot_config.BAN_DURATION_MINUTES = self.ban_duration_var.get()
            bot_config.WARNING_THRESHOLD = self.warning_threshold_var.get()
            
            # Настройки системы доверия (если вкладка создана)
            if hasattr(self, 'trust_enabled_var'):
                bot_config.TRUST_SYSTEM_ENABLED = self.trust_enabled_var.get()
                bot_config.LINK_DETECTION_ENABLED = self.link_detection_var.get()
                bot_config.TRUST_DAYS_THRESHOLD = self.trust_days_var.get()
                bot_config.TRUST_MESSAGES_THRESHOLD = self.trust_messages_var.get()
                bot_config.AUTO_DELETE_LINKS_FROM_NEW = self.auto_delete_links_var.get()
                bot_config.BAN_ON_REPEATED_LINK_VIOLATION = self.ban_repeated_links_var.get()
                
                domains_text = self.trusted_domains_var.get().strip()
                if domains_text:
                    bot_config.TRUSTED_DOMAINS = [domain.strip() for domain in domains_text.split(",") if domain.strip()]
                else:
                    bot_config.TRUSTED_DOMAINS = []
            
            # Сохраняем в переменные окружения И в .env файл
            save_config_to_env(bot_config)
            
            # Импортируем и используем новую функцию
            from config import save_to_env_file
            save_to_env_file(bot_config)
            
            self.status_text.set("Настройки сохранены")
            messagebox.showinfo("Успех", "Настройки успешно сохранены!")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки: {e}")
    
    def load_settings(self):
        """Загрузка настроек из конфигурации"""
        try:
            # Перезагружаем конфигурацию из переменных окружения
            from config import load_config_from_env
            updated_config = load_config_from_env()
            
            # Обновляем глобальную конфигурацию
            import config
            config.bot_config = updated_config
            
            # Основные настройки
            if hasattr(self, 'bot_token_var'):
                self.bot_token_var.set(updated_config.BOT_TOKEN or "")
                self.chat_id_var.set(updated_config.CHAT_ID or "")
                self.admin_chat_id_var.set(updated_config.ADMIN_CHAT_ID or "")
                self.openai_key_var.set(updated_config.OPENAI_API_KEY or "")
                self.openai_model_var.set(updated_config.OPENAI_MODEL or "gpt-3.5-turbo")
                self.use_openai_var.set(updated_config.USE_OPENAI_ANALYSIS)
                self.openai_threshold_var.set(updated_config.OPENAI_ANALYSIS_THRESHOLD)
                self.auto_delete_var.set(updated_config.AUTO_DELETE_BANNED_WORDS)
                self.auto_ban_var.set(updated_config.AUTO_BAN_ON_BANNED_WORDS)
                self.ban_duration_var.set(updated_config.BAN_DURATION_MINUTES)
                self.warning_threshold_var.set(updated_config.WARNING_THRESHOLD)
            
            # Настройки системы доверия (если вкладка создана)
            if hasattr(self, 'trust_enabled_var'):
                self.trust_enabled_var.set(updated_config.TRUST_SYSTEM_ENABLED)
                self.link_detection_var.set(updated_config.LINK_DETECTION_ENABLED)
                self.trust_days_var.set(updated_config.TRUST_DAYS_THRESHOLD)
                self.trust_messages_var.set(updated_config.TRUST_MESSAGES_THRESHOLD)
                self.auto_delete_links_var.set(updated_config.AUTO_DELETE_LINKS_FROM_NEW)
                self.ban_repeated_links_var.set(updated_config.BAN_ON_REPEATED_LINK_VIOLATION)
                self.trusted_domains_var.set(",".join(updated_config.TRUSTED_DOMAINS or []))
            
            self.logger.info("Настройки загружены успешно") if hasattr(self, 'logger') else print("Настройки загружены")
            
        except Exception as e:
            error_msg = f"Ошибка загрузки настроек: {e}"
            if hasattr(self, 'logger'):
                self.logger.error(error_msg)
            else:
                print(error_msg)
    
    def reset_settings(self):
        """Сброс настроек"""
        if messagebox.askyesno("Подтверждение", "Сбросить все настройки к значениям по умолчанию?"):
            # Очищаем переменные
            self.bot_token_var.set("")
            self.chat_id_var.set("")
            self.admin_chat_id_var.set("")
            self.openai_key_var.set("")
            self.openai_model_var.set("gpt-3.5-turbo")
            self.use_openai_var.set(True)
            self.openai_threshold_var.set(0.7)
            self.auto_delete_var.set(True)
            self.auto_ban_var.set(True)
            self.ban_duration_var.set(60)
            self.warning_threshold_var.set(3)
    
    def test_connections(self):
        """Тестирование подключений"""
        self.status_text.set("Тестирование подключений...")
        
        def test_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Тест OpenAI
                openai_result = loop.run_until_complete(analyzer.test_connection())
                
                # Результат
                result_text = f"OpenAI API: {'✅ Успешно' if openai_result else '❌ Ошибка'}"
                
                self.root.after(0, lambda: messagebox.showinfo("Результат тестирования", result_text))
                self.root.after(0, lambda: self.status_text.set("Тестирование завершено"))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Ошибка тестирования: {e}"))
            finally:
                loop.close()
        
        threading.Thread(target=test_async, daemon=True).start()
    
    def update_db_stats(self):
        """Обновление статистики базы данных"""
        try:
            stats = db.get_statistics()
            
            stats_text = f"""📊 Статистика базы данных:

👥 Пользователи:
   • Всего пользователей: {stats.get('total_users', 0)}
   • Заблокированных: {stats.get('banned_users', 0)}

📈 Нарушения:
   • Всего нарушений: {stats.get('total_violations', 0)}
   • За последние 24 часа: {stats.get('violations_24h', 0)}

🔥 Топ нарушений:"""
            
            for violation_type, count in stats.get('top_violations', []):
                violation_name = VIOLATION_TYPES.get(violation_type, violation_type)
                stats_text += f"\n   • {violation_name}: {count}"
            
            self.db_stats_text.delete(1.0, tk.END)
            self.db_stats_text.insert(tk.END, stats_text)
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить статистику: {e}")
    
    def cleanup_bans(self):
        """Очистка истекших банов"""
        try:
            cleaned_count = db.cleanup_expired_bans()
            messagebox.showinfo("Результат", f"Очищено {cleaned_count} истекших банов")
            self.update_db_stats()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось очистить баны: {e}")
    
    def search_user(self):
        """Поиск пользователя"""
        try:
            user_id = int(self.user_search_var.get())
            user = db.get_user(user_id)
            
            if not user:
                self.user_info_text.delete(1.0, tk.END)
                self.user_info_text.insert(tk.END, "Пользователь не найден")
                return
            
            # Отображаем информацию о пользователе

            trust_level_names = {
                'new': 'Новый',
                'trusted': 'Доверенный',
                'suspicious': 'Подозрительный'
            }

            trust_level_name = trust_level_names.get(user.trust_level, user.trust_level)

            info_text = f"""👤 Информация о пользователе {user_id}:

📝 Данные:
   • Имя: {user.first_name or 'Не указано'}
   • Фамилия: {user.last_name or 'Не указана'}
   • Username: @{user.username or 'Не указан'}
   • Предупреждения: {user.warnings_count}
   • Заблокирован: {'Да' if user.is_banned else 'Нет'}
   • Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Неизвестна'}

🔒 Система доверия:
   • Уровень доверия: {trust_level_name}
   • Сообщений отправлено: {user.messages_count}
   • Нарушений по ссылкам: {user.link_violations_count}
   • В чате с: {user.joined_chat_at.strftime('%d.%m.%Y') if user.joined_chat_at else 'Неизвестно'}
   • Последняя активность: {user.last_message_at.strftime('%d.%m.%Y %H:%M') if user.last_message_at else 'Неизвестно'}"""
            
            if user.ban_until:
                info_text += f"\n   • Бан до: {user.ban_until.strftime('%d.%m.%Y %H:%M')}"
            
            self.user_info_text.delete(1.0, tk.END)
            self.user_info_text.insert(tk.END, info_text)
            
            # Загружаем нарушения
            self.load_user_violations(user_id)
            
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный ID пользователя")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка поиска пользователя: {e}")
    
    def load_user_violations(self, user_id: int):
        """Загрузка нарушений пользователя"""
        try:
            # Очищаем таблицу
            for item in self.violations_tree.get_children():
                self.violations_tree.delete(item)
            
            violations = db.get_user_violations(user_id, 20)
            
            for violation in violations:
                date_str = violation.created_at.strftime('%d.%m %H:%M') if violation.created_at else 'Неизвестно'
                violation_name = VIOLATION_TYPES.get(violation.violation_type, violation.violation_type)
                action_name = MODERATION_ACTIONS.get(violation.action_taken, violation.action_taken)
                confidence_str = f"{violation.ai_confidence:.2f}" if violation.ai_confidence else "N/A"
                
                self.violations_tree.insert('', 'end', values=(date_str, violation_name, action_name, confidence_str))
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка загрузки нарушений: {e}")
    
    def warn_user(self):
        """Выдача предупреждения пользователю"""
        try:
            user_id = int(self.user_search_var.get())
            warnings_count = db.add_warning(user_id)
            messagebox.showinfo("Успех", f"Пользователю {user_id} выдано предупреждение. Всего: {warnings_count}")
            self.search_user()  # Обновляем информацию
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный ID пользователя")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка выдачи предупреждения: {e}")
    
    def ban_user(self):
        """Блокировка пользователя"""
        try:
            user_id = int(self.user_search_var.get())
            duration = self.ban_time_var.get()
            
            db.ban_user(user_id, duration)
            messagebox.showinfo("Успех", f"Пользователь {user_id} заблокирован на {duration} минут")
            self.search_user()  # Обновляем информацию
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный ID пользователя")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка блокировки: {e}")
    
    def unban_user(self):
        """Разблокировка пользователя"""
        try:
            user_id = int(self.user_search_var.get())
            db.unban_user(user_id)
            messagebox.showinfo("Успех", f"Пользователь {user_id} разблокирован")
            self.search_user()  # Обновляем информацию
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректный ID пользователя")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка разблокировки: {e}")

    def load_user_appeals(self, user_id: int):
        """Загрузка обжалований пользователя"""
        try:
            # Здесь можно добавить метод в database.py для получения обжалований пользователя
            appeals = db.get_user_appeals(user_id, 5)  # Нужно добавить этот метод в database.py
            
            self.appeals_info_text.delete(1.0, tk.END)
            
            if not appeals:
                self.appeals_info_text.insert(tk.END, "Обжалований нет")
                return
            
            for appeal in appeals:
                status_text = {"pending": "Ожидает", "approved": "Принято", "rejected": "Отклонено"}
                status = status_text.get(appeal.status, appeal.status)
                date_str = appeal.created_at.strftime('%d.%m %H:%M') if appeal.created_at else 'Неизвестно'
                
                self.appeals_info_text.insert(tk.END, f"#{appeal.id} - {status} ({date_str})\n")
                self.appeals_info_text.insert(tk.END, f"{appeal.appeal_text[:100]}...\n\n")
        
        except Exception as e:
            self.appeals_info_text.delete(1.0, tk.END)
            self.appeals_info_text.insert(tk.END, f"Ошибка загрузки: {e}")
    
    def load_banned_words(self):
        """Загрузка списка запрещенных слов"""
        self.words_listbox.delete(0, tk.END)
        for word in sorted(BANNED_WORDS):
            self.words_listbox.insert(tk.END, word)
    
    def filter_banned_words(self, *args):
        """Фильтрация списка запрещенных слов"""
        search_term = self.search_words_var.get().lower()
        self.words_listbox.delete(0, tk.END)
        
        for word in sorted(BANNED_WORDS):
            if search_term in word.lower():
                self.words_listbox.insert(tk.END, word)
    
    def add_banned_word(self):
        """Добавление запрещенного слова"""
        word = self.new_word_var.get().strip()
        if not word:
            messagebox.showwarning("Предупреждение", "Введите слово для добавления")
            return
        
        if add_banned_word(word):
            self.load_banned_words()
            self.new_word_var.set("")
            messagebox.showinfo("Успех", f"Слово '{word}' добавлено в список")
        else:
            messagebox.showwarning("Предупреждение", f"Слово '{word}' уже есть в списке")
    
    def remove_banned_word(self):
        """Удаление запрещенного слова"""
        selection = self.words_listbox.curselection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите слово для удаления")
            return
        
        word = self.words_listbox.get(selection[0])
        if messagebox.askyesno("Подтверждение", f"Удалить слово '{word}' из списка?"):
            if remove_banned_word(word):
                self.load_banned_words()
                messagebox.showinfo("Успех", f"Слово '{word}' удалено из списка")
            else:
                messagebox.showerror("Ошибка", f"Не удалось удалить слово '{word}'")
    
    def export_banned_words(self):
        """Экспорт списка запрещенных слов"""
        try:
            filename = filedialog.asksaveasfilename(
                title="Сохранить список запрещенных слов",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    for word in sorted(BANNED_WORDS):
                        f.write(word + '\n')
                
                messagebox.showinfo("Успех", f"Список сохранен в файл {filename}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка экспорта: {e}")
    
    def import_banned_words(self):
        """Импорт списка запрещенных слов"""
        try:
            filename = filedialog.askopenfilename(
                title="Загрузить список запрещенных слов",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            
            if filename:
                with open(filename, 'r', encoding='utf-8') as f:
                    words = [line.strip() for line in f if line.strip()]
                
                added_count = 0
                for word in words:
                    if add_banned_word(word):
                        added_count += 1
                
                self.load_banned_words()
                messagebox.showinfo("Успех", f"Добавлено {added_count} новых слов из файла {filename}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка импорта: {e}")
    
    def load_logs(self):
        """Загрузка логов"""
        try:
            if os.path.exists(bot_config.LOG_FILE):
                with open(bot_config.LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = f.read()
                
                self.logs_text.delete(1.0, tk.END)
                self.logs_text.insert(tk.END, logs)
                
                if self.auto_scroll_var.get():
                    self.logs_text.see(tk.END)
            else:
                self.logs_text.delete(1.0, tk.END)
                self.logs_text.insert(tk.END, "Файл логов не найден")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка загрузки логов: {e}")
    
    def clear_logs(self):
        """Очистка логов"""
        if messagebox.askyesno("Подтверждение", "Очистить все логи?"):
            try:
                with open(bot_config.LOG_FILE, 'w', encoding='utf-8') as f:
                    f.write("")
                self.logs_text.delete(1.0, tk.END)
                messagebox.showinfo("Успех", "Логи очищены")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка очистки логов: {e}")
    
    def export_logs(self):
        """Экспорт логов"""
        try:
            filename = filedialog.asksaveasfilename(
                title="Сохранить логи",
                defaultextension=".log",
                filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
            )
            
            if filename:
                with open(bot_config.LOG_FILE, 'r', encoding='utf-8') as src:
                    with open(filename, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
                
                messagebox.showinfo("Успех", f"Логи сохранены в файл {filename}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка экспорта логов: {e}")
    
    def load_settings_from_file(self):
        """Загрузка настроек из файла"""
        try:
            filename = filedialog.askopenfilename(
                title="Загрузить настройки",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            
            if filename:
                with open(filename, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # Применяем настройки
                for key, value in settings.items():
                    if hasattr(self, f"{key}_var"):
                        getattr(self, f"{key}_var").set(value)
                
                messagebox.showinfo("Успех", f"Настройки загружены из файла {filename}")
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка загрузки настроек: {e}")
    
    def show_about(self):
        """Показ информации о программе"""
        about_text = """
Telegram Bot Модерация СКВ СПб
Версия 1.0

Бот для автоматической модерации чата управляющей компании.

Возможности:
• Фильтрация запрещенных слов
• AI-анализ сообщений через OpenAI
• Автоматические предупреждения и баны
• Статистика и мониторинг
• Управление пользователями

Разработано для ООО «СКВ СПб»
2024
"""
        messagebox.showinfo("О программе", about_text)
    
    def on_closing(self):
        """Обработчик закрытия окна"""
        try:
            # Автоматически сохраняем настройки при закрытии
            self.save_settings()
        except:
            pass  # Игнорируем ошибки сохранения при закрытии
        
        if self.bot_running:
            if messagebox.askyesno("Подтверждение", "Бот все еще работает. Остановить его и выйти?"):
                self.stop_bot()
                # Даем время на остановку
                self.root.after(2000, self.root.destroy)
            return
        
        self.status_update_running = False
        self.root.destroy()
    
    def run(self):
        """Запуск GUI"""
        self.root.mainloop()

if __name__ == "__main__":
    app = ModerationGUI()
    app.run()