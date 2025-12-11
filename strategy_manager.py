#!/usr/bin/env python3
"""
Менеджер стратегий для торгового ядра
"""

import logging
from typing import Dict, List
from supabase import Client

logger = logging.getLogger(__name__)

class StrategyManager:
    """Менеджер торговых стратегий"""
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
        self.strategies = []
        self.last_update = None
        
    async def load_strategies(self):
        """Загрузка стратегий из Supabase"""
        try:
            response = self.supabase.table("strategy_settings") \
                .select("*") \
                .eq("is_active", True) \
                .order("updated_at", desc=True) \
                .execute()
                
            self.strategies = response.data
            self.last_update = response.data[0]['updated_at'] if response.data else None
            
            logger.info(f"📋 Загружено {len(self.strategies)} активных стратегий")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки стратегий: {e}")
            self.strategies = []
            
    def get_active_strategies(self) -> List[Dict]:
        """Получение активных стратегий"""
        return self.strategies
        
    def get_strategy_by_name(self, name: str) -> Optional[Dict]:
        """Поиск стратегии по имени"""
        for strategy in self.strategies:
            if strategy['strategy_name'] == name:
                return strategy
        return None
        
    def get_autotrade_strategies(self) -> List[Dict]:
        """Получение стратегий для авто-торговли"""
        return [s for s in self.strategies if s.get('for_autotrade', False)]
        
    async def check_for_updates(self) -> bool:
        """Проверка обновлений стратегий"""
        try:
            response = self.supabase.table("strategy_settings") \
                .select("updated_at") \
                .eq("is_active", True) \
                .order("updated_at", desc=True) \
                .limit(1) \
                .execute()
                
            if response.data and response.data[0]['updated_at'] != self.last_update:
                logger.info("🔄 Обнаружены обновления стратегий")
                await self.load_strategies()
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки обновлений: {e}")
            
        return False