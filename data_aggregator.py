# data_aggregator.py
"""
Модуль Агрегации и Анализа Рыночных Данных

Этот модуль собирает, обрабатывает и структурирует статистику по рыночным данным
для дальнейшего анализа и принятия решений по автоматическому переключению стратегий.

Функционал:
- Расчет ежедневной, еженедельной, ежемесячной статистики
- Метрики волатильности, тренда, настроения рынка
- Сохранение в Supabase (таблица aggregated_stats)
"""

import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from supabase import Client

logger = logging.getLogger(__name__)


class DataAggregator:
    """Агрегатор рыночных данных для анализа и статистики."""
    
    def __init__(self, supabase_client: Optional[Client] = None):
        """
        Инициализация агрегатора.
        
        Args:
            supabase_client: Клиент Supabase для сохранения данных
        """
        self.supabase = supabase_client
        
    def calculate_volatility(self, prices: pd.Series) -> float:
        """
        Вычисляет волатильность (стандартное отклонение доходности).
        
        Args:
            prices: Серия цен
            
        Returns:
            Значение волатильности (в %)
        """
        try:
            if prices is None or len(prices) < 2:
                return 0.0
            
            # Расчет доходности (returns)
            returns = prices.pct_change().dropna()
            
            if len(returns) == 0:
                return 0.0
            
            # Стандартное отклонение доходности (волатильность)
            volatility = returns.std() * 100  # В процентах
            
            return float(volatility)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при расчете волатильности: {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            return 0.0
    
    def calculate_trend(self, prices: pd.Series) -> Dict[str, Any]:
        """
        Определяет тренд рынка.
        
        Args:
            prices: Серия цен
            
        Returns:
            Словарь с информацией о тренде:
            - direction: 'up', 'down', 'sideways'
            - strength: сила тренда (0-100)
            - change_percent: изменение цены в %
        """
        try:
            if prices is None or len(prices) < 2:
                return {
                    'direction': 'sideways',
                    'strength': 0.0,
                    'change_percent': 0.0
                }
            
            # Изменение цены от начала к концу периода
            first_price = prices.iloc[0]
            last_price = prices.iloc[-1]
            change_percent = ((last_price - first_price) / first_price) * 100
            
            # Определяем направление тренда
            if change_percent > 1.0:
                direction = 'up'
            elif change_percent < -1.0:
                direction = 'down'
            else:
                direction = 'sideways'
            
            # Сила тренда (на основе линейной регрессии)
            x = np.arange(len(prices))
            y = prices.values
            
            # Удаляем NaN
            mask = ~np.isnan(y)
            x = x[mask]
            y = y[mask]
            
            if len(x) < 2:
                strength = 0.0
            else:
                # Линейная регрессия
                coefficients = np.polyfit(x, y, 1)
                slope = coefficients[0]
                
                # R-квадрат (коэффициент детерминации)
                y_pred = np.polyval(coefficients, x)
                ss_res = np.sum((y - y_pred) ** 2)
                ss_tot = np.sum((y - np.mean(y)) ** 2)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                
                # Сила тренда = R^2 * 100 (0-100%)
                strength = abs(r_squared) * 100
            
            return {
                'direction': direction,
                'strength': float(strength),
                'change_percent': float(change_percent)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при определении тренда: {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            return {
                'direction': 'sideways',
                'strength': 0.0,
                'change_percent': 0.0
            }
    
    def calculate_market_sentiment(self, df: pd.DataFrame) -> str:
        """
        Определяет настроение рынка на основе различных индикаторов.
        
        Args:
            df: DataFrame с рыночными данными (Open, High, Low, Close, Volume)
            
        Returns:
            Настроение рынка: 'bullish', 'bearish', 'neutral'
        """
        try:
            if df is None or df.empty or len(df) < 10:
                return 'neutral'
            
            scores = []
            
            # 1. Анализ тренда
            trend = self.calculate_trend(df['Close'])
            if trend['direction'] == 'up' and trend['strength'] > 50:
                scores.append(1)
            elif trend['direction'] == 'down' and trend['strength'] > 50:
                scores.append(-1)
            else:
                scores.append(0)
            
            # 2. Анализ объема (если доступен)
            if 'Volume' in df.columns:
                volume_trend = self.calculate_trend(df['Volume'])
                if volume_trend['direction'] == 'up':
                    # Растущий объем усиливает тренд
                    scores.append(1 if trend['direction'] == 'up' else -1)
                else:
                    scores.append(0)
            
            # 3. Анализ свечей (последние 5)
            recent_data = df.tail(5)
            bullish_candles = 0
            bearish_candles = 0
            
            for _, row in recent_data.iterrows():
                if row['Close'] > row['Open']:
                    bullish_candles += 1
                elif row['Close'] < row['Open']:
                    bearish_candles += 1
            
            if bullish_candles > bearish_candles:
                scores.append(1)
            elif bearish_candles > bullish_candles:
                scores.append(-1)
            else:
                scores.append(0)
            
            # Суммируем все оценки
            total_score = sum(scores)
            
            if total_score > 0:
                return 'bullish'
            elif total_score < 0:
                return 'bearish'
            else:
                return 'neutral'
                
        except Exception as e:
            logger.error(f"❌ Ошибка при определении настроения рынка: {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            return 'neutral'
    
    def aggregate_market_data(self, asset: str, df: pd.DataFrame, period: str = 'daily') -> Optional[Dict[str, Any]]:
        """
        Агрегирует рыночные данные для указанного актива и периода.
        
        Args:
            asset: Название актива
            df: DataFrame с рыночными данными
            period: Период агрегации ('daily', 'weekly', 'monthly')
            
        Returns:
            Словарь с агрегированной статистикой или None при ошибке
        """
        try:
            if df is None or df.empty:
                logger.warning(f"⚠️ Нет данных для агрегации актива {asset}")
                return None
            
            # Базовая статистика
            stats = {
                'asset': asset,
                'period': period,
                'timestamp': datetime.utcnow().isoformat(),
                'data_points': len(df),
                
                # Цены
                'price_open': float(df['Open'].iloc[0]) if 'Open' in df.columns else None,
                'price_close': float(df['Close'].iloc[-1]) if 'Close' in df.columns else None,
                'price_high': float(df['High'].max()) if 'High' in df.columns else None,
                'price_low': float(df['Low'].min()) if 'Low' in df.columns else None,
                'price_mean': float(df['Close'].mean()) if 'Close' in df.columns else None,
                
                # Объем
                'volume_total': float(df['Volume'].sum()) if 'Volume' in df.columns else None,
                'volume_mean': float(df['Volume'].mean()) if 'Volume' in df.columns else None,
            }
            
            # Расчет дополнительных метрик
            if 'Close' in df.columns:
                prices = df['Close']
                
                # Волатильность
                stats['volatility'] = self.calculate_volatility(prices)
                
                # Тренд
                trend = self.calculate_trend(prices)
                stats['trend_direction'] = trend['direction']
                stats['trend_strength'] = trend['strength']
                stats['price_change_percent'] = trend['change_percent']
                
                # Настроение рынка
                stats['market_sentiment'] = self.calculate_market_sentiment(df)
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Ошибка при агрегации данных для {asset}: {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            return None
    
    async def save_to_database(self, stats: Dict[str, Any]) -> bool:
        """
        Сохраняет агрегированную статистику в Supabase.
        
        Args:
            stats: Словарь с агрегированной статистикой
            
        Returns:
            True если успешно, False в противном случае
        """
        if not self.supabase:
            logger.debug("Supabase клиент не инициализирован, пропускаем сохранение")
            return False
        
        try:
            # Сохраняем в таблицу aggregated_stats
            response = self.supabase.table("aggregated_stats").insert(stats).execute()
            
            if response.data:
                logger.info(f"✅ Статистика сохранена в БД: {stats['asset']} ({stats['period']})")
                return True
            else:
                logger.warning(f"⚠️ Не удалось сохранить статистику для {stats['asset']}")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при сохранении в Supabase (таблица может не существовать): {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            logger.info(f"📊 Статистика: {stats['asset']} - волатильность: {stats.get('volatility', 0):.2f}%, "
                       f"тренд: {stats.get('trend_direction', 'unknown')} ({stats.get('trend_strength', 0):.1f}%), "
                       f"настроение: {stats.get('market_sentiment', 'unknown')}")
            return False
    
    async def process_and_save(self, asset: str, market_data: pd.DataFrame, periods: List[str] = None) -> bool:
        """
        Обрабатывает рыночные данные и сохраняет агрегированную статистику.
        
        Args:
            asset: Название актива
            market_data: DataFrame с рыночными данными
            periods: Список периодов для агрегации (по умолчанию ['daily'])
            
        Returns:
            True если хотя бы одна запись успешно сохранена
        """
        if periods is None:
            periods = ['daily']
        
        success = False
        
        for period in periods:
            # Агрегируем данные
            stats = self.aggregate_market_data(asset, market_data, period)
            
            if stats:
                # Сохраняем в БД
                if await self.save_to_database(stats):
                    success = True
        
        return success


# SQL для создания таблицы (справочно)
SQL_CREATE_TABLE = """
-- Таблица для хранения агрегированной статистики
CREATE TABLE IF NOT EXISTS aggregated_stats (
    id BIGSERIAL PRIMARY KEY,
    asset TEXT NOT NULL,
    period TEXT NOT NULL, -- 'daily', 'weekly', 'monthly'
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Базовая статистика
    data_points INTEGER,
    price_open NUMERIC,
    price_close NUMERIC,
    price_high NUMERIC,
    price_low NUMERIC,
    price_mean NUMERIC,
    
    -- Объем
    volume_total NUMERIC,
    volume_mean NUMERIC,
    
    -- Анализ
    volatility NUMERIC, -- Волатильность в %
    trend_direction TEXT, -- 'up', 'down', 'sideways'
    trend_strength NUMERIC, -- 0-100
    price_change_percent NUMERIC,
    market_sentiment TEXT, -- 'bullish', 'bearish', 'neutral'
    
    -- Индексы для быстрого поиска
    CONSTRAINT unique_asset_period_time UNIQUE (asset, period, timestamp)
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_asset ON aggregated_stats(asset);
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_timestamp ON aggregated_stats(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_period ON aggregated_stats(period);
"""
