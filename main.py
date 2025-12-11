import os
import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
import pandas as pd

# Внешние библиотеки
from dotenv import load_dotenv
from supabase import create_client, Client
import yfinance as yf # Для получения данных
import httpx 

# Наши модули
from autotrader_service import execute_auto_trade
# pocket_option_api будет реализован позже
# crypto_utils.py мы уже написали

# --- Настройка ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY_FOR_CORE")
# Интервал анализа в секундах (можно настраивать через Admin Bot)
ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", 60)) 

# --- Класс Ядра Анализа ---

class TradingCore:
    def __init__(self):
        # 1. Инициализация Supabase
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("🚫 Supabase keys not set.")
            self.supabase: Optional[Client] = None
        else:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 2. Мониторинг активов (пока задаем жестко, потом будем читать из Supabase)
        self.monitored_assets = ["EURUSD=X", "GBPJPY=X"] 

    # --- 1. Логика Сбора Данных ---
    async def fetch_market_data(self) -> Dict[str, pd.DataFrame]:
        """Получает текущие данные по всем активам."""
        market_data = {}
        logger.info(f"⏳ Fetching data for {len(self.monitored_assets)} assets...")
        
        for asset in self.monitored_assets:
            try:
                # Получаем последние 50 точек за 1 минуту
                data = yf.download(asset, period="5h", interval="1m", progress=False)
                if not data.empty:
                    market_data[asset] = data
            except Exception as e:
                logger.error(f"❌ Error fetching {asset}: {e}")
        
        return market_data

    # --- 2. Логика Анализа и Генерации Сигналов ---
    def analyze_and_generate_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Проводит анализ (RSI, MA и т.д.) и генерирует сигналы."""
        signals = []
        
        for asset, df in market_data.items():
            if df.empty or len(df) < 14: # Для RSI нужно мин. 14 точек
                continue

            # ПРИМЕР МИНИМАЛЬНОГО АНАЛИЗА: RSI(14)
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = (-delta).where(delta < 0, 0)
            
            avg_gain = gain.ewm(com=13, adjust=False).mean()
            avg_loss = loss.ewm(com=13, adjust=False).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            current_rsi = rsi.iloc[-1]
            
            if current_rsi < 30:
                direction = "BUY"
                reason = f"RSI({asset})={current_rsi:.2f}: strong oversold condition."
                signals.append({"asset": asset, "direction": direction, "confidence": 0.8, "reason": reason})
            elif current_rsi > 70:
                direction = "SELL"
                reason = f"RSI({asset})={current_rsi:.2f}: strong overbought condition."
                signals.append({"asset": asset, "direction": direction, "confidence": 0.8, "reason": reason})

        logger.info(f"Generated {len(signals)} raw signals.")
        return signals

    # --- 3. Логика AI-Рассуждений и Записи ---
    async def process_signals_and_log(self, signals: List[Dict[str, Any]]):
        """Отправляет сигналы на AI-анализ (заглушка) и логирует в Supabase."""
        if not self.supabase: return
        
        for signal in signals:
            # Здесь должна быть логика вызова AI-модели (ai_engine.py, который мы объединили)
            # AI_REASONING = await self.call_ai_model(signal) 
            AI_REASONING = signal['reason'] # Пока используем причину из анализа
            
            # Запись в таблицу ai_signals
            try:
                self.supabase.table("ai_signals").insert({
                    'asset': signal['asset'],
                    'direction': signal['direction'],
                    'confidence': signal['confidence'],
                    'ai_reasoning': AI_REASONING,
                    'created_at': 'now()'
                }).execute()
                logger.info(f"✅ Logged AI signal for {signal['asset']}.")
            except Exception as e:
                logger.error(f"❌ Supabase logging error: {e}")

    # --- 4. Логика Автоторговли (Чтение запросов) ---
    async def check_and_execute_trades(self, signals: List[Dict[str, Any]]):
        """Проверяет Supabase на наличие пользовательских запросов на торговлю."""
        if not self.supabase: return
        
        # Получаем ожидающие запросы от UI-Бота
        try:
            response = self.supabase.table("signal_requests").select("user_id", "request_type", "id").eq("status", "pending").execute()
            pending_requests = response.data
            logger.info(f"Found {len(pending_requests)} pending user requests.")
        except Exception as e:
            logger.error(f"❌ Error fetching signal requests: {e}")
            return

        for req in pending_requests:
            user_id = req['user_id']
            request_id = req['id']
            
            # 1. Находим сигнал, который соответствует запросу (простейший случай: берем первый)
            if not signals:
                logger.warning(f"No active signals found for user {user_id}'s request.")
                continue

            target_signal = signals[0] 
            
            # 2. Вызываем сервис автоторговли (HTTP-запрос к UI-Bot)
            trade_success = await execute_auto_trade(user_id, target_signal, self.supabase)
            
            # 3. Обновляем статус запроса в Supabase
            new_status = "executed" if trade_success else "failed"
            try:
                self.supabase.table("signal_requests").update({"status": new_status}).eq("id", request_id).execute()
                logger.info(f"Updated request {request_id} to {new_status}.")
            except Exception as e:
                logger.error(f"❌ Error updating request status: {e}")

    # --- ГЛАВНЫЙ ЦИКЛ ---
    async def run(self):
        """Бесконечный цикл Ядра."""
        logger.info(f"Core started with analysis interval: {ANALYSIS_INTERVAL} seconds.")
        
        while True:
            start_time = time.time()
            
            # 1. Сбор данных
            market_data = await self.fetch_market_data()
            
            # 2. Анализ и генерация сырых сигналов
            signals = self.analyze_and_generate_signals(market_data)
            
            # 3. Логирование сигналов (AI-рассуждения)
            await self.process_signals_and_log(signals)
            
            # 4. Проверка и выполнение автоторговли по запросам
            await self.check_and_execute_trades(signals)
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            # Пауза до следующего цикла
            sleep_time = max(0, ANALYSIS_INTERVAL - elapsed)
            logger.info(f"Cycle completed in {elapsed:.2f}s. Sleeping for {sleep_time:.2f}s...")
            
            await asyncio.sleep(sleep_time)


async def main():
    core = TradingCore()
    await core.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Ядро остановлено вручную.")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка Ядра: {e}")

