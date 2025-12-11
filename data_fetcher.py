#!/usr/bin/env python3
"""
Сбор рыночных данных с бирж
"""

import logging
import aiohttp
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)

class DataFetcher:
    """Сборщик рыночных данных"""
    
    def __init__(self, assets: List[str], timeframe: str = '1h'):
        self.assets = assets
        self.timeframe = timeframe
        self.exchanges = {
            'binance': ccxt.binance(),
            'bybit': ccxt.bybit()
        }
        self.cache = {}
        self.cache_ttl = 300  # 5 минут
        
    async def fetch_all(self) -> Dict[str, List]:
        """Сбор данных по всем активам"""
        market_data = {}
        
        try:
            tasks = []
            for asset in self.assets:
                # Проверяем кэш
                if self._is_cached(asset):
                    market_data[asset] = self.cache[asset]['data']
                else:
                    tasks.append(self.fetch_asset_data(asset))
                    
            # Запускаем параллельный сбор данных
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for asset, result in zip(self.assets, results):
                    if not isinstance(result, Exception) and result:
                        market_data[asset] = result
                        self._update_cache(asset, result)
                        
        except Exception as e:
            logger.error(f"❌ Ошибка сбора данных: {e}")
            
        return market_data
        
    async def fetch_asset_data(self, asset: str) -> Optional[List]:
        """Сбор данных для одного актива"""
        for exchange_name, exchange in self.exchanges.items():
            try:
                # Пытаемся получить данные с биржи
                symbol = self._format_symbol(asset, exchange_name)
                
                if not symbol:
                    continue
                    
                # Получаем OHLCV данные
                ohlcv = await exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    limit=100
                )
                
                if ohlcv:
                    data = self._process_ohlcv(ohlcv)
                    logger.debug(f"📊 Данные {asset} получены с {exchange_name}")
                    return data
                    
            except Exception as e:
                logger.debug(f"❌ {exchange_name} для {asset}: {e}")
                continue
                
        logger.warning(f"⚠️ Не удалось получить данные для {asset}")
        return None
        
    def _format_symbol(self, asset: str, exchange: str) -> Optional[str]:
        """Форматирование символа для биржи"""
        if exchange == 'binance':
            return f"{asset}/USDT"
        elif exchange == 'bybit':
            return f"{asset}USDT"
        return None
        
    def _process_ohlcv(self, ohlcv: List) -> List[Dict]:
        """Обработка OHLCV данных"""
        data = []
        for candle in ohlcv:
            data.append({
                'timestamp': candle[0],
                'open': float(candle[1]),
                'high': float(candle[2]),
                'low': float(candle[3]),
                'close': float(candle[4]),
                'volume': float(candle[5]),
                'time': datetime.fromtimestamp(candle[0] / 1000).isoformat()
            })
        return data
        
    def _is_cached(self, asset: str) -> bool:
        """Проверка кэша"""
        if asset in self.cache:
            cache_time = self.cache[asset]['timestamp']
            if (datetime.now() - cache_time).seconds < self.cache_ttl:
                return True
        return False
        
    def _update_cache(self, asset: str, data: List):
        """Обновление кэша"""
        self.cache[asset] = {
            'timestamp': datetime.now(),
            'data': data
        }
        
    async def close(self):
        """Закрытие соединений"""
        for exchange in self.exchanges.values():
            try:
                await exchange.close()
            except:
                pass
        logger.info("🔌 Соединения с биржами закрыты")