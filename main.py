# trading-core/main.py
import os
import asyncio
import time
import logging
import traceback
from typing import Dict, Any, List, Optional
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
from dotenv import load_dotenv

# Импорт наших сервисов
from autotrader_service import execute_auto_trade

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", 10))
DEFAULT_ASSET = os.getenv("DEFAULT_ASSET", "EURUSD=X")


class TradingCore:
    def __init__(self):
        # Проверка всех критических переменных окружения
        missing_vars = []
        if not SUPABASE_URL:
            missing_vars.append("SUPABASE_URL")
        if not SUPABASE_KEY:
            missing_vars.append("SUPABASE_SERVICE_ROLE_KEY")
        
        if missing_vars:
            logger.error(f"🚫 Критические переменные окружения не установлены: {', '.join(missing_vars)}")
            logger.error("Пожалуйста, установите их в настройках Render Environment Variables.")
            self.supabase: Optional[Client] = None
        else:
            try:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info(f"✅ Supabase клиент успешно инициализирован: {SUPABASE_URL}")
            except Exception as e:
                logger.error(f"❌ Ошибка при создании Supabase клиента: {e}")
                logger.error(f"Stack trace:\n{traceback.format_exc()}")
                self.supabase = None

        self.current_strategy = None
        self.monitored_assets = [DEFAULT_ASSET]

    async def test_supabase_connection(self) -> bool:
        """Проверяет соединение с Supabase при старте приложения."""
        if not self.supabase:
            logger.warning("⚠️ Supabase client not initialized. Skipping connection test.")
            return False
        
        try:
            logger.info("🔍 Testing Supabase connection...")
            # Пытаемся выполнить простой запрос к Supabase
            # Используем запрос к служебной таблице или любой запрос, который не требует наличия таблиц
            response = self.supabase.rpc('version', {}).execute()
            logger.info("✅ Supabase connection test: SUCCESS")
            return True
        except Exception as e:
            # Это не критическая ошибка - продолжаем работу
            logger.warning(f"⚠️ Supabase connection test failed: {e}")
            logger.info("📍 Core will continue, but database operations may fail.")
            logger.info("💡 Make sure your Supabase tables (strategy_settings, signal_requests, trades) exist and RLS policies allow service_role access.")
            return False

    async def fetch_strategy(self):
        """Читает активный алгоритм из Supabase (задается Admin Bot)."""
        if not self.supabase:
            logger.debug("Supabase client not initialized, skipping strategy fetch.")
            return

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
            logger.warning(f"⚠️ Could not fetch strategy from Supabase (table may not exist yet): {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            logger.info("📍 Continuing with default settings...")
            self.current_strategy = None
            self.monitored_assets = [DEFAULT_ASSET]

    async def fetch_market_data(self) -> Dict[str, pd.DataFrame]:
        """Получает текущие данные по активам."""
        market_data = {}

        for asset in self.monitored_assets:
            try:
                # Получаем последние 50 точек за 1 минуту
                logger.info(f"📊 Fetching market data for {asset}...")
                data = yf.download(asset, period="1d", interval="1m", progress=False)
                if not data.empty:
                    market_data[asset] = data
                    logger.info(f"✅ Fetched {len(data)} data points for {asset}")
                else:
                    logger.warning(f"⚠️ No data received for {asset}")
            except Exception as e:
                logger.error(f"❌ Error fetching {asset}: {e}")

        return market_data

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Вычисляет RSI индикатор."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def apply_algorithm(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Применяет чистый алгоритм (стратегию) и генерирует целевые сигналы."""
        signals = []

        # Если нет стратегии, используем минимальный RSI-алгоритм
        if not self.current_strategy:
            # Логика минимального RSI-анализа
            for asset, df in market_data.items():
                if len(df) < 20:
                    continue

                # Вычисляем RSI
                rsi = self.calculate_rsi(df['Close'])
                current_rsi = rsi.iloc[-1]

                if pd.isna(current_rsi):
                    continue

                # Генерация сигналов на основе RSI
                if current_rsi < 30:  # Перепроданность
                    signals.append({
                        "asset": asset.replace('=X', ''),
                        "direction": "CALL",
                        "amount": 10.0,
                        "timeframe": 60,
                        "indicator": "RSI",
                        "value": float(current_rsi)
                    })
                    logger.info(f"📈 CALL signal for {asset}: RSI={current_rsi:.2f}")
                elif current_rsi > 70:  # Перекупленность
                    signals.append({
                        "asset": asset.replace('=X', ''),
                        "direction": "PUT",
                        "amount": 10.0,
                        "timeframe": 60,
                        "indicator": "RSI",
                        "value": float(current_rsi)
                    })
                    logger.info(f"📉 PUT signal for {asset}: RSI={current_rsi:.2f}")

            return signals

        # *** РЕАЛЬНАЯ ЛОГИКА: Применение кастомной стратегии ***
        logger.info(f"Applying custom algorithm from strategy: {self.current_strategy.get('name')}")

        if self.current_strategy and self.current_strategy.get('allow_trading', False):
            default_amount = self.current_strategy.get('default_amount', 10.0)
            default_timeframe = self.current_strategy.get('default_timeframe', 60)

            for asset, df in market_data.items():
                if len(df) < 20:
                    continue

                # Применяем RSI из стратегии
                rsi_period = self.current_strategy.get('rsi_period', 14)
                rsi_oversold = self.current_strategy.get('rsi_oversold', 30)
                rsi_overbought = self.current_strategy.get('rsi_overbought', 70)

                rsi = self.calculate_rsi(df['Close'], period=rsi_period)
                current_rsi = rsi.iloc[-1]

                if pd.isna(current_rsi):
                    continue

                # Генерация сигналов на основе параметров стратегии
                if current_rsi < rsi_oversold:
                    signals.append({
                        "asset": asset.replace('=X', ''),
                        "direction": "CALL",
                        "amount": default_amount,
                        "timeframe": default_timeframe,
                        "indicator": "RSI",
                        "value": float(current_rsi)
                    })
                elif current_rsi > rsi_overbought:
                    signals.append({
                        "asset": asset.replace('=X', ''),
                        "direction": "PUT",
                        "amount": default_amount,
                        "timeframe": default_timeframe,
                        "indicator": "RSI",
                        "value": float(current_rsi)
                    })

        logger.info(f"Generated {len(signals)} TARGET signals based on strategy.")
        return signals

    async def check_and_execute_trades(self, signals: List[Dict[str, Any]]):
        """Проверяет Supabase на наличие пользовательских запросов (от UI-Бота) и выполняет торговлю."""
        if not self.supabase:
            logger.debug("Supabase client not initialized, skipping trade execution.")
            return

        # Получаем ожидающие запросы, которые должны быть обработаны Ядром
        try:
            response = self.supabase.table("signal_requests").select("user_id", "id").eq("status", "pending").limit(5).execute()
            pending_requests = response.data
        except Exception as e:
            logger.warning(f"⚠️ Could not fetch signal requests (table may not exist yet): {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            logger.debug("📍 Skipping trade execution for this cycle...")
            return

        if not pending_requests:
            logger.debug("No pending signal requests found.")
            return

        for req in pending_requests:
            user_id = req.get('user_id')
            request_id = req.get('id')

            if not user_id or not request_id:
                logger.warning(f"⚠️ Invalid request format: {req}")
                continue

            if not signals:
                logger.warning(f"Trade skipped for user {user_id}: No target signals generated in this cycle.")
                continue

            # Берем первый сгенерированный целевой сигнал
            target_signal = signals[0]

            # Вызываем сервис автоторговли (HTTP-запрос к UI-Bot)
            try:
                trade_success = await execute_auto_trade(user_id, target_signal, self.supabase)
            except Exception as e:
                logger.error(f"❌ Error executing auto trade for user {user_id}: {e}")
                logger.error(f"Stack trace:\n{traceback.format_exc()}")
                trade_success = False

            # Обновляем статус запроса в Supabase
            new_status = "executed" if trade_success else "failed"
            try:
                self.supabase.table("signal_requests").update({"status": new_status}).eq("id", request_id).execute()
                logger.info(f"✅ Updated request {request_id} status to '{new_status}'")
            except Exception as e:
                logger.error(f"❌ Error updating request status for {request_id}: {e}")
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")

    async def run(self):
        """Главный цикл Ядра."""
        logger.info("Core starting up...")
        
        # Проверяем соединение с Supabase при старте
        await self.test_supabase_connection()
        logger.info("=" * 60)

        while True:
            start_time = time.time()

            try:
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
                logger.info(f"✅ Cycle completed in {elapsed:.2f}s. Sleeping for {sleep_time:.2f}s...")

            except Exception as e:
                logger.error(f"❌ Critical error in main cycle: {e}")
                logger.error(f"Stack trace:\n{traceback.format_exc()}")
                logger.info("📍 Continuing to next cycle despite error...")
                sleep_time = ANALYSIS_INTERVAL

            await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 Trading Core Starting...")
    logger.info("=" * 60)
    
    # Проверка дополнительных переменных окружения (для информации)
    env_vars_status = {
        "SUPABASE_URL": "✅" if SUPABASE_URL else "❌",
        "SUPABASE_SERVICE_ROLE_KEY": "✅" if SUPABASE_KEY else "❌",
        "ANALYSIS_INTERVAL": f"✅ ({ANALYSIS_INTERVAL}s)",
        "DEFAULT_ASSET": f"✅ ({DEFAULT_ASSET})",
    }
    
    logger.info("Статус переменных окружения:")
    for var, status in env_vars_status.items():
        logger.info(f"  {var}: {status}")
    
    logger.info("=" * 60)
    
    core = TradingCore()
    asyncio.run(core.run())
