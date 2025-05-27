# -*- coding: utf-8 -*-
"""
Система защиты от спама для Telegram-бота модерации СКВ СПб
"""

import time
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
from difflib import SequenceMatcher

@dataclass
class SpamDetectionResult:
    """Результат проверки на спам"""
    is_spam: bool
    spam_type: str
    confidence: float
    reason: str
    action: str  # warn, mute, ban

@dataclass 
class UserMessageHistory:
    """История сообщений пользователя"""
    messages: deque = field(default_factory=lambda: deque(maxlen=20))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=20))
    spam_violations: int = 0
    last_violation_time: float = 0

class AntiSpamSystem:
    """Система защиты от спама"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.user_histories: Dict[int, UserMessageHistory] = defaultdict(UserMessageHistory)
        
        # Настройки антиспама
        self.FLOOD_MESSAGES_LIMIT = 5  # сообщений
        self.FLOOD_TIME_WINDOW = 60    # секунд
        self.DUPLICATE_TIME_WINDOW = 300  # секунд для проверки дублей
        self.SIMILARITY_THRESHOLD = 0.8   # порог схожести сообщений
        self.SHORT_MESSAGE_LIMIT = 3      # количество коротких сообщений
        self.SHORT_MESSAGE_LENGTH = 10    # длина "короткого" сообщения
        self.SHORT_MESSAGE_TIME_WINDOW = 120  # секунд
        
        # Типичные спам фразы
        self.SPAM_PATTERNS = [
            "ау", "аууу", "ответьте", "отвечайте", "эй", "где все", "алло",
            "???", "!!!", "где вода", "где", "когда", "почему", "ну и",
            "блин", "опять", "снова", "опааа"
        ]
    
    def check_message(self, user_id: int, message_text: str) -> Optional[SpamDetectionResult]:
        """
        Проверяет сообщение на спам
        
        Args:
            user_id: ID пользователя
            message_text: Текст сообщения
            
        Returns:
            SpamDetectionResult или None если спам не обнаружен
        """
        if not message_text or len(message_text.strip()) == 0:
            return None
            
        current_time = time.time()
        history = self.user_histories[user_id]
        
        # Проверяем на флуд (слишком много сообщений)
        flood_result = self._check_flood(history, current_time)
        if flood_result:
            self._add_violation(history, current_time)
            return flood_result
        
        # Проверяем на дублированные сообщения
        duplicate_result = self._check_duplicates(history, message_text, current_time)
        if duplicate_result:
            self._add_violation(history, current_time)
            return duplicate_result
        
        # Проверяем на похожие сообщения
        similar_result = self._check_similar_messages(history, message_text, current_time)
        if similar_result:
            self._add_violation(history, current_time)
            return similar_result
        
        # Проверяем на спам короткими сообщениями
        short_spam_result = self._check_short_message_spam(history, message_text, current_time)
        if short_spam_result:
            self._add_violation(history, current_time)
            return short_spam_result
        
        # Добавляем сообщение в историю
        history.messages.append(message_text.lower().strip())
        history.timestamps.append(current_time)
        
        return None
    
    def _check_flood(self, history: UserMessageHistory, current_time: float) -> Optional[SpamDetectionResult]:
        """Проверка на флуд"""
        # Считаем сообщения за последнюю минуту
        recent_messages = 0
        for timestamp in history.timestamps:
            if current_time - timestamp <= self.FLOOD_TIME_WINDOW:
                recent_messages += 1
        
        if recent_messages >= self.FLOOD_MESSAGES_LIMIT:
            action = self._get_action_by_violations(history.spam_violations)
            return SpamDetectionResult(
                is_spam=True,
                spam_type="flood",
                confidence=0.9,
                reason=f"Отправлено {recent_messages} сообщений за {self.FLOOD_TIME_WINDOW} секунд",
                action=action
            )
        
        return None
    
    def _check_duplicates(self, history: UserMessageHistory, message_text: str, current_time: float) -> Optional[SpamDetectionResult]:
        """Проверка на дублированные сообщения"""
        message_lower = message_text.lower().strip()
        
        duplicate_count = 0
        for i, (msg, timestamp) in enumerate(zip(history.messages, history.timestamps)):
            if current_time - timestamp <= self.DUPLICATE_TIME_WINDOW:
                if msg == message_lower:
                    duplicate_count += 1
        
        if duplicate_count >= 2:  # Уже есть 2+ одинаковых сообщения
            action = self._get_action_by_violations(history.spam_violations)
            return SpamDetectionResult(
                is_spam=True,
                spam_type="duplicate",
                confidence=1.0,
                reason=f"Дублированное сообщение (найдено {duplicate_count} копий)",
                action=action
            )
        
        return None
    
    def _check_similar_messages(self, history: UserMessageHistory, message_text: str, current_time: float) -> Optional[SpamDetectionResult]:
        """Проверка на похожие сообщения"""
        message_lower = message_text.lower().strip()
        
        similar_count = 0
        for msg, timestamp in zip(history.messages, history.timestamps):
            if current_time - timestamp <= self.DUPLICATE_TIME_WINDOW:
                similarity = SequenceMatcher(None, message_lower, msg).ratio()
                if similarity >= self.SIMILARITY_THRESHOLD and len(message_lower) <= 20:
                    similar_count += 1
        
        if similar_count >= 2:
            action = self._get_action_by_violations(history.spam_violations)
            return SpamDetectionResult(
                is_spam=True,
                spam_type="similar",
                confidence=0.8,
                reason=f"Похожие сообщения ({similar_count} найдено)",
                action=action
            )
        
        return None
    
    def _check_short_message_spam(self, history: UserMessageHistory, message_text: str, current_time: float) -> Optional[SpamDetectionResult]:
        """Проверка на спам короткими сообщениями"""
        message_lower = message_text.lower().strip()
        
        # Проверяем, является ли сообщение коротким спамом
        is_spam_pattern = any(pattern in message_lower for pattern in self.SPAM_PATTERNS)
        is_short = len(message_text) <= self.SHORT_MESSAGE_LENGTH
        
        if not (is_spam_pattern or is_short):
            return None
        
        # Считаем короткие сообщения за последнее время
        short_messages_count = 0
        for msg, timestamp in zip(history.messages, history.timestamps):
            if current_time - timestamp <= self.SHORT_MESSAGE_TIME_WINDOW:
                if len(msg) <= self.SHORT_MESSAGE_LENGTH or any(pattern in msg for pattern in self.SPAM_PATTERNS):
                    short_messages_count += 1
        
        if short_messages_count >= self.SHORT_MESSAGE_LIMIT:
            action = self._get_action_by_violations(history.spam_violations)
            return SpamDetectionResult(
                is_spam=True,
                spam_type="short_spam",
                confidence=0.7,
                reason=f"Спам короткими сообщениями ({short_messages_count} за {self.SHORT_MESSAGE_TIME_WINDOW//60} мин)",
                action=action
            )
        
        return None
    
    def _add_violation(self, history: UserMessageHistory, current_time: float):
        """Добавляет нарушение пользователю"""
        history.spam_violations += 1
        history.last_violation_time = current_time
    
    def _get_action_by_violations(self, violations: int) -> str:
        """Определяет действие на основе количества нарушений"""
        if violations == 0:
            return "warn"
        elif violations == 1:
            return "mute"
        else:
            return "ban"
    
    def cleanup_old_data(self):
        """Очистка старых данных"""
        current_time = time.time()
        users_to_remove = []
        
        for user_id, history in self.user_histories.items():
            # Если пользователь не активен 24 часа, удаляем его историю
            if history.timestamps and current_time - history.timestamps[-1] > 86400:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.user_histories[user_id]
        
        if users_to_remove:
            self.logger.info(f"Очищена история для {len(users_to_remove)} неактивных пользователей")
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Получение статистики пользователя"""
        history = self.user_histories.get(user_id)
        if not history:
            return {"messages": 0, "violations": 0, "last_activity": None}
        
        return {
            "messages": len(history.messages),
            "violations": history.spam_violations,
            "last_activity": history.timestamps[-1] if history.timestamps else None
        }

# Глобальный экземпляр антиспам системы
antispam = AntiSpamSystem()