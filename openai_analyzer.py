# -*- coding: utf-8 -*-
"""
Модуль анализа сообщений через OpenAI API для Telegram-бота СКВ СПб
"""

import json
import logging
import asyncio
import aiohttp
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from config import bot_config, OPENAI_ANALYSIS_PROMPT, COMPANY_RULES

@dataclass
class AnalysisResult:
    """Результат анализа сообщения"""
    violation: bool
    violation_type: Optional[str]
    confidence: float
    reason: str
    action: str
    
class OpenAIAnalyzer:
    """Класс для анализа сообщений через OpenAI API"""
    
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or bot_config.OPENAI_API_KEY
        self.model = model or bot_config.OPENAI_MODEL
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://api.openai.com/v1/chat/completions"
        
        if not self.api_key:
            self.logger.warning("OpenAI API ключ не установлен")
    
    async def analyze_message(self, message_text: str, user_info: str = None) -> Optional[AnalysisResult]:
        """
        Анализирует сообщение на нарушение правил чата
        
        Args:
            message_text (str): Текст сообщения для анализа
            user_info (str): Дополнительная информация о пользователе
            
        Returns:
            Optional[AnalysisResult]: Результат анализа или None в случае ошибки
        """
        if not self.api_key:
            self.logger.error("OpenAI API ключ не установлен")
            return None
        
        if not message_text.strip():
            return AnalysisResult(
                violation=False,
                violation_type=None,
                confidence=1.0,
                reason="Пустое сообщение",
                action="none"
            )
        
        try:
            # Формируем промпт
            prompt = OPENAI_ANALYSIS_PROMPT.format(
                rules=COMPANY_RULES,
                message=message_text
            )
            
            if user_info:
                prompt += f"\n\nДополнительная информация о пользователе: {user_info}"
            
            # Подготавливаем запрос к OpenAI
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Ты - эксперт модератор чата управляющей компании. Анализируй сообщения строго и объективно."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "temperature": 0.1,  # Низкая температура для более стабильных результатов
                "max_tokens": 500,
                "response_format": {"type": "json_object"}
            }
            
            # Выполняем запрос
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return self._parse_openai_response(result)
                    else:
                        error_text = await response.text()
                        self.logger.error(f"Ошибка OpenAI API: {response.status} - {error_text}")
                        return None
                        
        except asyncio.TimeoutError:
            self.logger.error("Таймаут при запросе к OpenAI API")
            return None
        except aiohttp.ClientError as e:
            self.logger.error(f"Ошибка сети при запросе к OpenAI: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при анализе сообщения: {e}")
            return None
    
    def _parse_openai_response(self, response: Dict) -> Optional[AnalysisResult]:
        """Парсит ответ OpenAI API"""
        try:
            # Извлекаем содержимое ответа
            content = response['choices'][0]['message']['content']
            
            # Парсим JSON
            analysis_data = json.loads(content)
            
            # Валидируем обязательные поля
            required_fields = ['violation', 'confidence', 'reason', 'action']
            for field in required_fields:
                if field not in analysis_data:
                    self.logger.error(f"Отсутствует обязательное поле в ответе OpenAI: {field}")
                    return None
            
            # Проверяем типы данных
            violation = bool(analysis_data['violation'])
            confidence = float(analysis_data['confidence'])
            reason = str(analysis_data['reason'])
            action = str(analysis_data['action'])
            violation_type = analysis_data.get('violation_type')
            
            # Валидируем диапазон confidence
            if not 0.0 <= confidence <= 1.0:
                self.logger.warning(f"Некорректное значение confidence: {confidence}, устанавливаем 0.5")
                confidence = 0.5
            
            # Валидируем action
            valid_actions = ['none', 'warn', 'delete', 'mute', 'ban']
            if action not in valid_actions:
                self.logger.warning(f"Некорректное действие: {action}, устанавливаем 'warn'")
                action = 'warn'
            
            return AnalysisResult(
                violation=violation,
                violation_type=violation_type,
                confidence=confidence,
                reason=reason,
                action=action
            )
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка парсинга JSON ответа OpenAI: {e}")
            self.logger.debug(f"Содержимое ответа: {response}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Ошибка обработки ответа OpenAI: {e}")
            self.logger.debug(f"Содержимое ответа: {response}")
            return None
    
    def is_violation_significant(self, analysis: AnalysisResult) -> bool:
        """
        Определяет, является ли нарушение значительным на основе уверенности
        
        Args:
            analysis: Результат анализа
            
        Returns:
            bool: True если нарушение значительное
        """
        if not analysis.violation:
            return False
        
        return analysis.confidence >= bot_config.OPENAI_ANALYSIS_THRESHOLD
    
    def get_recommended_action(self, analysis: AnalysisResult, user_warnings: int = 0) -> str:
        """
        Получает рекомендуемое действие на основе анализа и истории пользователя
        
        Args:
            analysis: Результат анализа
            user_warnings: Количество предупреждений у пользователя
            
        Returns:
            str: Рекомендуемое действие
        """
        if not self.is_violation_significant(analysis):
            return "none"
        
        # Если это серьезное нарушение (высокая уверенность)
        if analysis.confidence >= 0.9:
            if analysis.action in ['ban', 'mute']:
                return analysis.action
        
        # Учитываем историю нарушений пользователя
        if user_warnings >= bot_config.WARNING_THRESHOLD:
            return "ban"
        elif user_warnings >= bot_config.WARNING_THRESHOLD - 1:
            return "mute"
        else:
            return "warn" if analysis.action in ['warn', 'delete'] else analysis.action
    
    async def test_connection(self) -> bool:
        """Тестирует подключение к OpenAI API"""
        try:
            test_message = "Привет! Как дела?"
            result = await self.analyze_message(test_message)
            return result is not None
        except Exception as e:
            self.logger.error(f"Ошибка тестирования OpenAI API: {e}")
            return False

class MockAnalyzer:
    """Мок-класс для тестирования без реального API"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def analyze_message(self, message_text: str, user_info: str = None) -> AnalysisResult:
        """Возвращает фиктивный результат анализа"""
        
        # Простая эвристика для демонстрации
        violation = False
        violation_type = None
        confidence = 0.1
        reason = "Мок-анализ: сообщение соответствует правилам"
        action = "none"
        
        # Проверяем на некоторые ключевые слова
        message_lower = message_text.lower()
        
        if any(word in message_lower for word in ['реклама', 'продам', 'куплю', 'скидка']):
            violation = True
            violation_type = "advertising"
            confidence = 0.8
            reason = "Обнаружена реклама или коммерческая деятельность"
            action = "delete"
        elif len(message_text) > 500 and message_text.count('!') > 10:
            violation = True
            violation_type = "spam"
            confidence = 0.7
            reason = "Подозрение на спам: длинное сообщение с множественными восклицательными знаками"
            action = "warn"
        elif message_text.isupper() and len(message_text) > 20:
            violation = True
            violation_type = "caps"
            confidence = 0.6
            reason = "Сообщение написано заглавными буквами"
            action = "warn"
        
        return AnalysisResult(
            violation=violation,
            violation_type=violation_type,
            confidence=confidence,
            reason=reason,
            action=action
        )
    
    def is_violation_significant(self, analysis: AnalysisResult) -> bool:
        return analysis.violation and analysis.confidence >= 0.5
    
    def get_recommended_action(self, analysis: AnalysisResult, user_warnings: int = 0) -> str:
        if not self.is_violation_significant(analysis):
            return "none"
        
        if user_warnings >= 3:
            return "ban"
        elif user_warnings >= 2:
            return "mute"
        else:
            return "warn"
    
    async def test_connection(self) -> bool:
        return True

# Фабрика для создания анализатора
def create_analyzer(use_real_api: bool = None) -> OpenAIAnalyzer:
    """
    Создает анализатор сообщений
    
    Args:
        use_real_api: Использовать реальный API OpenAI или мок
        
    Returns:
        OpenAIAnalyzer: Экземпляр анализатора
    """
    if use_real_api is None:
        use_real_api = bot_config.USE_OPENAI_ANALYSIS and bool(bot_config.OPENAI_API_KEY)
    
    if use_real_api:
        return OpenAIAnalyzer()
    else:
        return MockAnalyzer()

# Глобальный экземпляр анализатора
analyzer = create_analyzer()