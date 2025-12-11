#!/usr/bin/env python3
"""
AI Engine для генерации рассуждений (Claude API)
"""

import logging
import json
from typing import Dict, Optional
import aiohttp

logger = logging.getLogger(__name__)

class AIEngine:
    """Движок для работы с Claude API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
    async def generate_reasoning(self, signal: Dict, market_context: Dict) -> Optional[str]:
        """Генерация AI-рассуждений для сигнала"""
        try:
            prompt = self.create_prompt(signal, market_context)
            
            async with aiohttp.ClientSession() as session:
                data = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                    "system": self.get_system_prompt()
                }
                
                async with session.post(
                    self.base_url,
                    headers=self.headers,
                    json=data,
                    timeout=30
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        reasoning = result.get("content", [{}])[0].get("text", "")
                        
                        logger.debug(f"🤖 AI сгенерировал рассуждение для {signal['symbol']}")
                        return reasoning
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Claude API error: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка AI Engine: {e}")
            
        return None
        
    def create_prompt(self, signal: Dict, market_context: Dict) -> str:
        """Создание промпта для Claude"""
        prompt = f"""
        Ты - опытный финансовый аналитик. Проанализируй торговый сигнал и дай краткое обоснование.

        **СИГНАЛ:**
        - АКТИВ: {signal.get('symbol', 'N/A')}
        - ДЕЙСТВИЕ: {signal.get('action', 'N/A').upper()}
        - СТРАТЕГИЯ: {signal.get('strategy_name', 'N/A')}
        - УВЕРЕННОСТЬ: {signal.get('confidence', 0)}%
        - ЦЕНА ВХОДА: {signal.get('entry_price', 'N/A')}
        - ТЕЙК-ПРОФИТ: {signal.get('tp_price', 'N/A')}
        - СТОП-ЛОСС: {signal.get('sl_price', 'N/A')}

        **УСЛОВИЯ СИГНАЛА:**
        {json.dumps(signal.get('conditions_met', []), indent=2, ensure_ascii=False)}

        **КОНТЕКСТ РЫНКА:**
        {self.format_market_context(market_context.get(signal.get('symbol', ''), {}))}

        **ЗАДАНИЕ:**
        1. Оцени силу сигнала (1-10)
        2. Укажи ключевые факторы, подтверждающие сигнал
        3. Отметь потенциальные риски
        4. Дай рекомендацию по управлению позицией
        5. Объясни логику в 3-4 предложениях

        **ФОРМАТ ОТВЕТА:**
        [Сила: X/10]
        [Факторы: ...]
        [Риски: ...]
        [Рекомендация: ...]
        [Обоснование: ...]
        """
        
        return prompt
        
    def format_market_context(self, context: Dict) -> str:
        """Форматирование рыночного контекста"""
        if not context:
            return "Нет данных о рыночном контексте"
            
        try:
            latest = context[-1] if isinstance(context, list) else context
            
            return f"""
            Текущая цена: {latest.get('close', 'N/A')}
            Объем: {latest.get('volume', 'N/A')}
            Время: {latest.get('timestamp', 'N/A')}
            """
        except:
            return str(context)[:500] + "..."
            
    def get_system_prompt(self) -> str:
        """Системный промпт для Claude"""
        return """Ты - консервативный финансовый аналитик с опытом торговли. 
        Будь кратким, техничным и объективным. 
        Указывай на риски так же четко, как и на возможности.
        Избегай эмоциональных формулировок.
        Давай конкретные, практические рекомендации."""