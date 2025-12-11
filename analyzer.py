#!/usr/bin/env python3
"""
Анализатор рынка и генератор сигналов
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class MarketAnalyzer:
    """Анализатор рыночных данных"""
    
    def __init__(self, strategy_manager):
        self.strategy_manager = strategy_manager
        self.indicators_cache = {}
        
    async def analyze_with_strategy(self, market_data: Dict, strategy: Dict) -> List[Dict]:
        """Анализ рынка с использованием конкретной стратегии"""
        signals = []
        
        try:
            parameters = strategy.get('parameters', {})
            strategy_name = strategy['strategy_name']
            
            # Анализируем каждый актив
            for symbol, data in market_data.items():
                if not data:
                    continue
                    
                # Преобразуем в DataFrame для анализа
                df = pd.DataFrame(data)
                
                # Применяем технические индикаторы
                df = self.apply_technical_indicators(df, parameters)
                
                # Генерируем сигналы на основе стратегии
                asset_signals = self.generate_signals(
                    df=df,
                    symbol=symbol,
                    strategy_name=strategy_name,
                    parameters=parameters
                )
                
                if asset_signals:
                    signals.extend(asset_signals)
                    
        except Exception as e:
            logger.error(f"❌ Ошибка анализа стратегии {strategy['strategy_name']}: {e}")
            
        return signals
        
    def apply_technical_indicators(self, df: pd.DataFrame, params: Dict) -> pd.DataFrame:
        """Применение технических индикаторов"""
        try:
            # RSI
            rsi_period = params.get('rsi_period', 14)
            df['rsi'] = self.calculate_rsi(df['close'], rsi_period)
            
            # MACD
            macd_fast = params.get('macd_fast', 12)
            macd_slow = params.get('macd_slow', 26)
            macd_signal = params.get('macd_signal', 9)
            df['macd'], df['macd_signal'], df['macd_hist'] = self.calculate_macd(
                df['close'], macd_fast, macd_slow, macd_signal
            )
            
            # Bollinger Bands
            bb_period = params.get('bb_period', 20)
            bb_std = params.get('bb_std', 2)
            df['bb_upper'], df['bb_middle'], df['bb_lower'] = self.calculate_bollinger_bands(
                df['close'], bb_period, bb_std
            )
            
            # Volume анализ
            df['volume_sma'] = df['volume'].rolling(window=20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # Простые скользящие средние
            df['sma_20'] = df['close'].rolling(window=20).mean()
            df['sma_50'] = df['close'].rolling(window=50).mean()
            df['sma_200'] = df['close'].rolling(window=200).mean()
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения индикаторов: {e}")
            
        return df
        
    def generate_signals(self, df: pd.DataFrame, symbol: str, 
                        strategy_name: str, parameters: Dict) -> List[Dict]:
        """Генерация торговых сигналов"""
        signals = []
        
        try:
            # Получаем последние данные
            latest = df.iloc[-1]
            
            # Проверяем условия для BUY
            buy_conditions = self.check_buy_conditions(latest, parameters)
            if buy_conditions['trigger']:
                signal = {
                    'symbol': symbol,
                    'action': 'buy',
                    'direction': 'long',
                    'strategy_name': strategy_name,
                    'confidence': buy_conditions['confidence'],
                    'entry_price': float(latest['close']),
                    'tp_price': self.calculate_tp_price(latest['close'], 'buy', parameters),
                    'sl_price': self.calculate_sl_price(latest['close'], 'buy', parameters),
                    'timeframe': '1h',
                    'conditions_met': buy_conditions['conditions'],
                    'for_autotrade': parameters.get('for_autotrade', False),
                    'timestamp': datetime.utcnow().isoformat()
                }
                signals.append(signal)
                
            # Проверяем условия для SELL
            sell_conditions = self.check_sell_conditions(latest, parameters)
            if sell_conditions['trigger']:
                signal = {
                    'symbol': symbol,
                    'action': 'sell',
                    'direction': 'short',
                    'strategy_name': strategy_name,
                    'confidence': sell_conditions['confidence'],
                    'entry_price': float(latest['close']),
                    'tp_price': self.calculate_tp_price(latest['close'], 'sell', parameters),
                    'sl_price': self.calculate_sl_price(latest['close'], 'sell', parameters),
                    'timeframe': '1h',
                    'conditions_met': sell_conditions['conditions'],
                    'for_autotrade': parameters.get('for_autotrade', False),
                    'timestamp': datetime.utcnow().isoformat()
                }
                signals.append(signal)
                
        except Exception as e:
            logger.error(f"❌ Ошибка генерации сигналов для {symbol}: {e}")
            
        return signals
        
    def check_buy_conditions(self, data: pd.Series, params: Dict) -> Dict:
        """Проверка условий для покупки"""
        conditions = []
        confidence = 0
        
        try:
            # RSI перепроданность
            rsi_oversold = params.get('rsi_oversold', 30)
            if data['rsi'] < rsi_oversold:
                conditions.append('rsi_oversold')
                confidence += 25
                
            # MACD бычий кроссовер
            if data['macd'] > data['macd_signal'] and data['macd_hist'] > 0:
                conditions.append('macd_bullish')
                confidence += 20
                
            # Цена ниже нижней полосы Боллинджера
            if data['close'] < data['bb_lower']:
                conditions.append('bb_oversold')
                confidence += 15
                
            # Объем выше среднего
            volume_threshold = params.get('volume_threshold', 1.5)
            if data['volume_ratio'] > volume_threshold:
                conditions.append('high_volume')
                confidence += 10
                
            # Скользящие средние (золотой крест)
            if data['sma_20'] > data['sma_50'] and data['sma_50'] > data['sma_200']:
                conditions.append('golden_cross')
                confidence += 30
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки условий покупки: {e}")
            
        return {
            'trigger': len(conditions) >= params.get('min_conditions', 2),
            'conditions': conditions,
            'confidence': min(confidence, 100)
        }
        
    def check_sell_conditions(self, data: pd.Series, params: Dict) -> Dict:
        """Проверка условий для продажи"""
        conditions = []
        confidence = 0
        
        try:
            # RSI перекупленность
            rsi_overbought = params.get('rsi_overbought', 70)
            if data['rsi'] > rsi_overbought:
                conditions.append('rsi_overbought')
                confidence += 25
                
            # MACD медвежий кроссовер
            if data['macd'] < data['macd_signal'] and data['macd_hist'] < 0:
                conditions.append('macd_bearish')
                confidence += 20
                
            # Цена выше верхней полосы Боллинджера
            if data['close'] > data['bb_upper']:
                conditions.append('bb_overbought')
                confidence += 15
                
            # Объем выше среднего на падении
            volume_threshold = params.get('volume_threshold', 1.5)
            if data['volume_ratio'] > volume_threshold and data['close'] < data['open']:
                conditions.append('high_volume_down')
                confidence += 10
                
            # Скользящие средние (мертвый крест)
            if data['sma_20'] < data['sma_50'] and data['sma_50'] < data['sma_200']:
                conditions.append('death_cross')
                confidence += 30
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки условий продажи: {e}")
            
        return {
            'trigger': len(conditions) >= params.get('min_conditions', 2),
            'conditions': conditions,
            'confidence': min(confidence, 100)
        }
        
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Расчет RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def calculate_macd(self, prices: pd.Series, fast: int = 12, 
                      slow: int = 26, signal: int = 9) -> tuple:
        """Расчет MACD"""
        exp1 = prices.ewm(span=fast, adjust=False).mean()
        exp2 = prices.ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist
        
    def calculate_bollinger_bands(self, prices: pd.Series, 
                                 period: int = 20, std: int = 2) -> tuple:
        """Расчет Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        rolling_std = prices.rolling(window=period).std()
        
        upper_band = sma + (rolling_std * std)
        lower_band = sma - (rolling_std * std)
        
        return upper_band, sma, lower_band
        
    def calculate_tp_price(self, entry_price: float, direction: str, params: Dict) -> float:
        """Расчет Take Profit"""
        tp_percent = params.get('tp_percent', 3.0)  # 3% по умолчанию
        
        if direction == 'buy':
            return entry_price * (1 + tp_percent / 100)
        else:
            return entry_price * (1 - tp_percent / 100)
            
    def calculate_sl_price(self, entry_price: float, direction: str, params: Dict) -> float:
        """Расчет Stop Loss"""
        sl_percent = params.get('sl_percent', 2.0)  # 2% по умолчанию
        
        if direction == 'buy':
            return entry_price * (1 - sl_percent / 100)
        else:
            return entry_price * (1 + sl_percent / 100)