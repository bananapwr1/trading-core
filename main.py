#!/usr/bin/env python3
"""
PYTHONANYWHERE: Торговое ядро 24/7
Анализ рынка, генерация сигналов, AI-рассуждения
"""

import os
import sys
import asyncio
import logging
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from supabase import create_client, Client
from dotenv import load_dotenv

# Наши модули
from analyzer import MarketAnalyzer
from ai_engine import AIEngine
from data_fetcher import DataFetcher
from strategy_manager import StrategyManager
from config import (
    SUPABASE_URL, SUPABASE_KEY, 
    ANTHROPIC_API_KEY, MONITORED_ASSETS,
    ANALYSIS_INTERVAL, MAX_CONCURRENT_TASKS
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('trading_core.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class TradingCore:
    """Главный класс торгового ядра"""
    
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.analyzer: Optional[MarketAnalyzer] = None
        self.ai_engine: Optional[AIEngine] = None
        self.data_fetcher: Optional[DataFetcher] = None
        self.strategy_manager: Optional[StrategyManager] = None
        
        self.is_running = True
        self.cycle_count = 0
        self.start_time = datetime.now()
        
    async def initialize(self):
        """Инициализация всех компонентов"""
        logger.info("🧠 Инициализация торгового ядра...")
        
        # 1. Инициализация Supabase
        try:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("✅ Supabase подключен")
        except Exception as e:
            logger.error(f"❌ Ошибка Supabase: {e}")
            return False
            
        # 2. Инициализация менеджера стратегий
        try:
            self.strategy_manager = StrategyManager(self.supabase)
            await self.strategy_manager.load_strategies()
            logger.info(f"✅ Загружено стратегий: {len(self.strategy_manager.strategies)}")
        except Exception as e:
            logger.error(f"❌ Ошибка StrategyManager: {e}")
            return False
            
        # 3. Инициализация сборщика данных
        try:
            self.data_fetcher = DataFetcher(MONITORED_ASSETS)
            logger.info("✅ DataFetcher инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка DataFetcher: {e}")
            return False
            
        # 4. Инициализация анализатора рынка
        try:
            self.analyzer = MarketAnalyzer(self.strategy_manager)
            logger.info("✅ MarketAnalyzer инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка MarketAnalyzer: {e}")
            return False
            
        # 5. Инициализация AI движка (если есть ключ)
        if ANTHROPIC_API_KEY:
            try:
                self.ai_engine = AIEngine(ANTHROPIC_API_KEY)
                logger.info("✅ AIEngine инициализирован (Claude API)")
            except Exception as e:
                logger.error(f"⚠️ AIEngine не инициализирован: {e}")
                self.ai_engine = None
        else:
            logger.warning("⚠️ ANTHROPIC_API_KEY не задан, AI-рассуждения отключены")
            
        logger.info("🎯 Торговое ядро успешно инициализировано!")
        return True
        
    async def run_cycle(self):
        """Один цикл анализа рынка"""
        self.cycle_count += 1
        logger.info(f"🔄 Цикл #{self.cycle_count} начат")
        
        try:
            # 1. Сбор рыночных данных
            market_data = await self.data_fetcher.fetch_all()
            
            if not market_data:
                logger.warning("⚠️ Нет рыночных данных, пропускаю цикл")
                return
                
            # 2. Анализ по каждой стратегии
            all_signals = []
            
            for strategy in self.strategy_manager.get_active_strategies():
                logger.debug(f"Анализ стратегии: {strategy['strategy_name']}")
                
                signals = await self.analyzer.analyze_with_strategy(
                    market_data=market_data,
                    strategy=strategy
                )
                
                if signals:
                    all_signals.extend(signals)
                    
            # 3. Генерация AI-рассуждений для сигналов
            if self.ai_engine and all_signals:
                await self.add_ai_reasonings(all_signals, market_data)
                
            # 4. Сохранение сигналов в Supabase
            if all_signals:
                await self.save_signals_to_supabase(all_signals)
                logger.info(f"📨 Сохранено сигналов: {len(all_signals)}")
            else:
                logger.info("📭 Сигналов не найдено")
                
            # 5. Проверка запросов от пользователей
            await self.check_user_requests()
            
            # 6. Очистка старых данных
            await self.cleanup_old_data()
            
            logger.info(f"✅ Цикл #{self.cycle_count} завершен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка в цикле #{self.cycle_count}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    async def add_ai_reasonings(self, signals: List[Dict], market_data: Dict):
        """Добавление AI-рассуждений к сигналам"""
        logger.info("🤖 Генерация AI-рассуждений...")
        
        tasks = []
        for signal in signals:
            if signal.get('confidence', 0) > 70:  # Только для уверенных сигналов
                tasks.append(
                    self.ai_engine.generate_reasoning(signal, market_data)
                )
                
        # Ограничиваем количество одновременных запросов
        if tasks:
            results = []
            for i in range(0, len(tasks), MAX_CONCURRENT_TASKS):
                batch = tasks[i:i+MAX_CONCURRENT_TASKS]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)
                
            # Добавляем рассуждения к сигналам
            for signal, reasoning in zip(signals, results):
                if not isinstance(reasoning, Exception):
                    signal['ai_reasoning'] = reasoning
                    signal['has_ai'] = True
                else:
                    logger.error(f"Ошибка AI для сигнала: {reasoning}")
                    
    async def save_signals_to_supabase(self, signals: List[Dict]):
        """Сохранение сигналов в базу данных"""
        try:
            for signal in signals:
                # Подготавливаем данные для Supabase
                supabase_signal = {
                    'symbol': signal.get('symbol'),
                    'signal_type': signal.get('action'),  # buy/sell
                    'direction': signal.get('direction', signal.get('action')),
                    'confidence': signal.get('confidence', 0),
                    'entry_price': signal.get('entry_price'),
                    'tp_price': signal.get('tp_price'),
                    'sl_price': signal.get('sl_price'),
                    'timeframe': signal.get('timeframe', '1h'),
                    'strategy_used': signal.get('strategy_name'),
                    'ai_reasoning': signal.get('ai_reasoning'),
                    'has_ai': signal.get('has_ai', False),
                    'for_autotrade': signal.get('for_autotrade', False),
                    'status': 'new',
                    'created_at': datetime.utcnow().isoformat()
                }
                
                # Сохраняем в таблицу ai_signals
                self.supabase.table("ai_signals").insert(supabase_signal).execute()
                
                # Логируем важные сигналы
                if supabase_signal['confidence'] > 80:
                    logger.info(
                        f"🎯 Сильный сигнал: {supabase_signal['symbol']} "
                        f"{supabase_signal['signal_type']} "
                        f"({supabase_signal['confidence']:.1f}%)"
                    )
                    
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сигналов: {e}")
            
    async def check_user_requests(self):
        """Проверка запросов от пользователей (от бота #1)"""
        try:
            # Ищем непрочитанные запросы
            requests = self.supabase.table("signal_requests") \
                .select("*") \
                .eq("status", "pending") \
                .order("created_at", asc=True) \
                .limit(10) \
                .execute()
                
            if requests.data:
                logger.info(f"👤 Запросов от пользователей: {len(requests.data)}")
                
                for req in requests.data:
                    # Находим лучший сигнал для пользователя
                    best_signal = await self.find_best_signal_for_user(req)
                    
                    if best_signal:
                        # Отправляем сигнал пользователю
                        await self.send_signal_to_user(req['user_id'], best_signal)
                        
                        # Помечаем запрос как обработанный
                        self.supabase.table("signal_requests") \
                            .update({
                                "status": "processed",
                                "signal_id": best_signal.get('id'),
                                "processed_at": datetime.utcnow().isoformat()
                            }) \
                            .eq("id", req["id"]) \
                            .execute()
                            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки запросов: {e}")
            
    async def find_best_signal_for_user(self, user_request: Dict) -> Optional[Dict]:
        """Поиск лучшего сигнала для пользователя"""
        try:
            # Получаем последние сигналы
            signals = self.supabase.table("ai_signals") \
                .select("*") \
                .eq("status", "new") \
                .gte("confidence", 70) \
                .order("confidence", desc=True) \
                .limit(5) \
                .execute()
                
            if signals.data:
                # Выбираем сигнал с наибольшей уверенностью
                return signals.data[0]
                
        except Exception as e:
            logger.error(f"❌ Ошибка поиска сигнала: {e}")
            
        return None
        
    async def send_signal_to_user(self, user_id: int, signal: Dict):
        """Отправка сигнала пользователю (через бота #1)"""
        try:
            # Сохраняем в таблицу user_signals для бота #1
            user_signal = {
                'user_id': user_id,
                'signal_id': signal['id'],
                'signal_data': signal,
                'delivered': False,
                'created_at': datetime.utcnow().isoformat()
            }
            
            self.supabase.table("user_signals").insert(user_signal).execute()
            logger.info(f"📤 Сигнал отправлен пользователю {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сигнала: {e}")
            
    async def cleanup_old_data(self):
        """Очистка старых данных"""
        try:
            # Удаляем старые сигналы (старше 7 дней)
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            
            self.supabase.table("ai_signals") \
                .delete() \
                .lt("created_at", week_ago) \
                .execute()
                
            # Удаляем старые запросы
            self.supabase.table("signal_requests") \
                .delete() \
                .lt("created_at", week_ago) \
                .execute()
                
            logger.debug("🧹 Очистка старых данных выполнена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки данных: {e}")
            
    async def run(self):
        """Главный цикл работы ядра"""
        logger.info("🚀 Запуск торгового ядра...")
        
        while self.is_running:
            try:
                await self.run_cycle()
                
                # Ждем перед следующим циклом
                logger.info(f"⏳ Следующий цикл через {ANALYSIS_INTERVAL} секунд...")
                await asyncio.sleep(ANALYSIS_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("⏸️ Цикл прерван")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в главном цикле: {e}")
                await asyncio.sleep(60)  # Ждем минуту при критической ошибке
                
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Завершение работы торгового ядра...")
        self.is_running = False
        
        # Закрываем соединения
        if self.data_fetcher:
            await self.data_fetcher.close()
            
        logger.info(f"📊 Итоги работы:")
        logger.info(f"   • Выполнено циклов: {self.cycle_count}")
        logger.info(f"   • Время работы: {datetime.now() - self.start_time}")
        logger.info("✅ Торговое ядро остановлено")
        

async def main():
    """Главная функция"""
    # Обработка сигналов для корректного завершения
    def signal_handler(signum, frame):
        logger.info(f"📶 Получен сигнал {signum}")
        raise KeyboardInterrupt
        
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Создаем и запускаем ядро
    core = TradingCore()
    
    try:
        # Инициализация
        if not await core.initialize():
            logger.error("❌ Не удалось инициализировать торговое ядро")
            return
            
        # Запуск главного цикла
        await core.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Корректное завершение
        await core.shutdown()
        

if __name__ == "__main__":
    load_dotenv()
    
    # Проверка обязательных переменных
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("❌ SUPABASE_URL или SUPABASE_KEY не заданы!")
        sys.exit(1)
        
    # Запускаем асинхронное приложение
    asyncio.run(main())
