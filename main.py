# trading-core/main.py
import os
import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
from dotenv import load_dotenv

# Импорт наших сервисов
from autotrader_service import execute_auto_trade 
# from pocket_option_api import PocketOptionAPI # Не нужен прямой импорт, так как он в autotrader_service

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY_FOR_CORE")
ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", 10)) 
DEFAULT_ASSET = os.getenv("DEFAULT_ASSET", "EURUSD=X")

class TradingCore:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("🚫 Supabase keys not set.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        self.current_strategy = None
        self.monitored_assets = [DEFAULT_ASSET]

    async def fetch_strategy(self):
        """Читает активный алгоритм из Supabase (задается Admin Bot)."""
        if not self.supabase: return

        try:
            # Читаем последнюю активную стратегию
            response = self.supabase.table("strategy_settings").select("*").eq("is_active", True).limit(1).execute()
            
            if response.data:
                strategy = response.data[0]
                self.current_strategy = strategy
                self.monitored_assets = strategy.get('assets_to_monitor', [DEFAULT_ASSET])
                logger.info(f"✨ Fetched active strategy: {strategy.get('name', 'Unnamed')}. Monitoring {self.monitored_assets}")
            else:
                self.current_strategy = None
                self.monitored_assets = [DEFAULT_ASSET]
                logger.warning("⚠️ No active strategy found. Using default asset.")
        except Exception as e:
            logger.error(f"❌ Error fetching strategy from Supabase: {e}")

    async def fetch_market_data(self) -> Dict[str, pd.DataFrame]:
        """Получает текущие данные по активам."""
        market_data = {}
        
        for asset in self.monitored_assets:
            try:
                # Получаем последние 50 точек за 1 минуту
                data = yf.download(asset, period="5h", interval="1m", progress=False)
                if not data.empty:
                    market_data[asset] = data
            except Exception as e:
                logger.error(f"❌ Error fetching {asset}: {e}")
        
        return market_data

    def apply_algorithm(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Применяет чистый алгоритм (стратегию) и генерирует целевые сигналы."""
        signals = []
        
        # Если нет стратегии, используем минимальный RSI-алгоритм
        if not self.current_strategy:
             # Логика минимального RSI-анализа
            for asset, df in market_data.items():
                # ... (вставляем код RSI из предыдущего ответа) ...
                # Если сгенерирован сигнал:
                # signals.append({"asset": asset, "direction": direction, "amount": 10.0, "timeframe": 60})
                pass # Пропускаем пока для чистоты
            
            # Заглушка для чистоты
            if market_data:
                logger.warning("No strategy applied, skipping signal generation.")
                
            return signals

        # *** РЕАЛЬНАЯ ЛОГИКА: ***
        # Здесь будет код, который читает strategy['indicators'] и strategy['rules']
        # и применяет их к market_data.
        logger.info(f"Applying custom algorithm from strategy: {self.current_strategy.get('name')}")
        
        # --- ЗАГЛУШКА (Имитация работы по алгоритму) ---
        if self.current_strategy and self.current_strategy.get('allow_trading', False):
            # Проверяем, есть ли в данных что-то похожее на условие
            for asset in market_data.keys():
                # Предположим, что алгоритм сработал:
                if time.time() % 300 < 5: # Раз в 5 минут
                    signals.append({
                        "asset": asset, 
                        "direction": "CALL" if (time.time() % 2 == 0) else "PUT", 
                        "amount": self.current_strategy.get('default_amount', 10.0), 
                        "timeframe": self.current_strategy.get('default_timeframe', 60)
                    })
            # ----------------------------------------------
            
        logger.info(f"Generated {len(signals)} TARGET signals based on strategy.")
        return signals

    async def check_and_execute_trades(self, signals: List[Dict[str, Any]]):
        """Проверяет Supabase на наличие пользовательских запросов (от UI-Бота) и выполняет торговлю."""
        if not self.supabase: return
        
        # Получаем ожидающие запросы, которые должны быть обработаны Ядром
        try:
            response = self.supabase.table("signal_requests").select("user_id", "id").eq("status", "pending").limit(5).execute()
            pending_requests = response.data
        except Exception as e:
            logger.error(f"❌ Error fetching signal requests: {e}")
            return

        for req in pending_requests:
            user_id = req['user_id']
            request_id = req['id']
            
            if not signals:
                logger.warning(f"Trade skipped for {user_id}: No target signals generated in this cycle.")
                continue

            target_signal = signals[0] # Берем первый сгенерированный целевой сигнал
            
            # Вызываем сервис автоторговли (HTTP-запрос к UI-Bot)
            trade_success = await execute_auto_trade(user_id, target_signal, self.supabase)
            
            # Обновляем статус запроса в Supabase
            new_status = "executed" if trade_success else "failed"
            try:
                self.supabase.table("signal_requests").update({"status": new_status}).eq("id", request_id).execute()
            except Exception as e:
                logger.error(f"❌ Error updating request status: {e}")


    async def run(self):
        """Главный цикл Ядра."""
        logger.info("Core starting up...")
        
        while True:
            start_time = time.time()
            
            # 1. Обновляем стратегию (чтобы видеть изменения от Admin Bot)
            await self.fetch_strategy()
            
            # 2. Сбор данных
            market_data = await self.fetch_market_data()
            
            # 3. Применение алгоритма и генерация целевых сигналов
            signals = self.apply_algorithm(market_data)
            
            # 4. Выполнение торговли (если есть запросы)
            await self.check_and_execute_trades(signals)
            
            elapsed = time.time() - start_time
            sleep_time = max(0, ANALYSIS_INTERVAL - elapsed)
            logger.info(f"Cycle completed in {elapsed:.2f}s. Sleeping for {sleep_time:.2f}s...")
            
            await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    core = TradingCore()
    asyncio.run(core.run())
