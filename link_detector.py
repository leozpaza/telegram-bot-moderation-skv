# -*- coding: utf-8 -*-
"""
Модуль детекции ссылок для системы доверия
"""

import re
from urllib.parse import urlparse
from typing import List, Tuple

# Регулярные выражения для поиска ссылок
URL_PATTERNS = [
    r'https?://[^\s]+',  # http/https ссылки
    r'www\.[^\s]+',      # www ссылки
    r't\.me/[^\s]+',     # Telegram ссылки
    r'@[a-zA-Z0-9_]+',   # Telegram username
]

# Доверенные домены по умолчанию
DEFAULT_TRUSTED_DOMAINS = ["t.me", "youtube.com", "youtu.be"]

def detect_links(text: str) -> Tuple[bool, List[str]]:
    """
    Обнаруживает ссылки в тексте
    
    Returns:
        tuple: (найдены ли ссылки, список найденных ссылок)
    """
    if not text:
        return False, []
        
    found_links = []
    
    for pattern in URL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found_links.extend(matches)
    
    return len(found_links) > 0, found_links

def get_trusted_domains():
    """Получает список доверенных доменов из конфигурации"""
    try:
        # Поздний импорт, чтобы избежать циклических зависимостей
        from config import bot_config
        return bot_config.TRUSTED_DOMAINS if bot_config.TRUSTED_DOMAINS else DEFAULT_TRUSTED_DOMAINS
    except (ImportError, AttributeError):
        return DEFAULT_TRUSTED_DOMAINS

def is_trusted_link(link: str) -> bool:
    """
    Проверяет, является ли ссылка доверенной
    """
    if not link:
        return False
        
    trusted_domains = get_trusted_domains()
    
    if not trusted_domains:
        return False
    
    try:
        # Обрабатываем ссылки без протокола
        if not link.startswith(('http://', 'https://')):
            link = 'http://' + link
        
        parsed = urlparse(link)
        domain = parsed.netloc.lower()
        
        # Удаляем www. для сравнения
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return any(trusted_domain.lower() in domain for trusted_domain in trusted_domains)
        
    except Exception:
        return False

def has_suspicious_links(text: str) -> Tuple[bool, List[str]]:
    """
    Проверяет на подозрительные (недоверенные) ссылки
    """
    if not text:
        return False, []
        
    has_links, found_links = detect_links(text)
    
    if not has_links:
        return False, []
    
    suspicious_links = []
    for link in found_links:
        if not is_trusted_link(link):
            suspicious_links.append(link)
    
    return len(suspicious_links) > 0, suspicious_links