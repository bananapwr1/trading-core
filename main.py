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
from data_aggregator import DataAggregator

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
# КРИТИЧНО: Очищаем ключи от пробелов - частая причина ошибки 401!
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip() if os.getenv("SUPABASE_URL") else None
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else None
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
                # Дополнительная валидация перед созданием клиента
                logger.info(f"🔍 Инициализация Supabase клиента...")
                logger.debug(f"   URL: {SUPABASE_URL}")
                logger.debug(f"   Key length: {len(SUPABASE_KEY)} chars")
                logger.debug(f"   Key starts with: {SUPABASE_KEY[:10]}...")
                
                # Проверка формата ключа
                if not SUPABASE_KEY.startswith("eyJ"):
                    logger.warning("⚠️ ВНИМАНИЕ: Service Role Key обычно начинается с 'eyJ'")
                    logger.warning("   Убедитесь, что вы используете service_role key, а НЕ anon key!")
                
                if SUPABASE_KEY.count('.') < 2:
                    logger.warning("⚠️ ВНИМАНИЕ: Ключ не похож на JWT токен (должен содержать точки)")
                
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info(f"✅ Supabase клиент успешно инициализирован: {SUPABASE_URL}")
            except Exception as e:
                logger.error(f"❌ Ошибка при создании Supabase клиента: {e}")
                logger.error(f"Stack trace:\n{traceback.format_exc()}")
                
                # Дополнительная диагностика для ошибки 401
                error_str = str(e)
                if "401" in error_str or "Unauthorized" in error_str:
                    logger.error("\n🚨 КРИТИЧЕСКАЯ ПРОБЛЕМА: Ошибка авторизации 401 Unauthorized")
                    logger.error("=" * 70)
                    logger.error("Возможные причины:")
                    logger.error("  1. Используется ANON key вместо SERVICE_ROLE key")
                    logger.error("  2. Ключ был сброшен в Supabase, но не обновлен в Render")
                    logger.error("  3. Ключ содержит опечатку или скопирован не полностью")
                    logger.error("  4. В ключе есть пробелы в начале/конце (уже исправлено в коде)")
                    logger.error("\n💡 РЕШЕНИЕ:")
                    logger.error("  1. Откройте Supabase Dashboard → Settings → API")
                    logger.error("  2. Найдите 'Project API keys' → скопируйте 'service_role' key")
                    logger.error("  3. В Render: Environment Variables → SUPABASE_SERVICE_ROLE_KEY")
                    logger.error("  4. Замените на новый ключ и сохраните")
                    logger.error("  5. Перезапустите: Manual Deploy → Clear build cache & deploy")
                    logger.error("=" * 70)
                
                self.supabase = None

        # Дефолтная стратегия (используется когда нет активной в БД)
        self.default_strategy = {
            'name': 'Default RSI Strategy',
            'description': 'Базовая стратегия на основе RSI индикатора',
            'allow_trading': False,  # По умолчанию только мониторинг, НЕ торговля
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'default_amount': 10.0,
            'default_timeframe': 60,
            'assets_to_monitor': [DEFAULT_ASSET]
        }
        
        self.current_strategy = None
        self.monitored_assets = [DEFAULT_ASSET]
        self.using_default_strategy = False
        
        # Инициализация агрегатора данных
        self.data_aggregator = DataAggregator(self.supabase)
        self.aggregation_counter = 0  # Счетчик для периодической агрегации
        self.aggregation_interval = 6  # Агрегировать каждые N циклов

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
            error_str = str(e)
            
            # Детальный анализ ошибки
            if "401" in error_str or "Unauthorized" in error_str:
                logger.error("❌ Supabase connection test: FAILED (401 Unauthorized)")
                logger.error("=" * 70)
                logger.error("🚨 ОШИБКА АВТОРИЗАЦИИ!")
                logger.error("   Supabase отклоняет ваш ключ авторизации.")
                logger.error("\n📋 Контрольный список:")
                logger.error("   ☐ Проверьте, что используется SERVICE_ROLE key (не anon)")
                logger.error("   ☐ Убедитесь, что ключ скопирован полностью без пробелов")
                logger.error("   ☐ Проверьте, что ключ не был сброшен в Supabase")
                logger.error("   ☐ Убедитесь, что переменная называется SUPABASE_SERVICE_ROLE_KEY")
                logger.error("\n💡 Как получить правильный ключ:")
                logger.error("   1. Supabase Dashboard → Project Settings → API")
                logger.error("   2. Раздел 'Project API keys'")
                logger.error("   3. Скопируйте 'service_role' (секретный ключ, НЕ публичный!)")
                logger.error("   4. Обновите SUPABASE_SERVICE_ROLE_KEY в Render")
                logger.error("=" * 70)
                logger.debug(f"Full error: {e}")
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")
                return False
            elif "404" in error_str or "Not Found" in error_str:
                logger.info("ℹ️ Function 'version' not found - trying alternative test...")
                # Пробуем альтернативный способ проверки
                try:
                    # Просто проверяем, что можем обратиться к API
                    test_response = self.supabase.table("_connection_test").select("*").limit(1).execute()
                    logger.info("✅ Supabase connection test: SUCCESS (alternative method)")
                    return True
                except Exception as e2:
                    error_str2 = str(e2)
                    if "404" in error_str2 or "not found" in error_str2.lower():
                        # Таблица не найдена, но мы получили ответ - значит авторизация прошла!
                        logger.info("✅ Supabase connection test: SUCCESS (table not found, but auth OK)")
                        return True
                    elif "401" in error_str2:
                        logger.error("❌ Alternative test also failed with 401 - key is invalid!")
                        return False
                    else:
                        logger.warning(f"⚠️ Alternative test failed: {e2}")
                        return False
            else:
                # Другая ошибка
                logger.warning(f"⚠️ Supabase connection test failed: {e}")
                logger.info("📍 Core will continue, but database operations may fail.")
                logger.info("💡 Make sure your Supabase tables (strategy_settings, signal_requests, trades) exist and RLS policies allow service_role access.")
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")
                return False

    async def fetch_strategy(self):
        """Читает активный алгоритм из Supabase (задается Admin Bot)."""
        if not self.supabase:
            logger.debug("Supabase client not initialized, using default strategy.")
            self._activate_default_strategy()
            return

        try:
            # Читаем последнюю активную стратегию из БД
            response = self.supabase.table("strategy_settings").select("*").eq("is_active", True).limit(1).execute()

            if response.data:
                strategy = response.data[0]
                self.current_strategy = strategy
                self.monitored_assets = strategy.get('assets_to_monitor', [DEFAULT_ASSET])
                self.using_default_strategy = False
                logger.info(f"✨ Активна стратегия из БД: '{strategy.get('name', 'Unnamed')}'. Активы: {self.monitored_assets}")
            else:
                # Нет активной стратегии в БД - используем дефолтную
                self._activate_default_strategy()
                logger.info(f"📋 Активна дефолтная стратегия: '{self.default_strategy['name']}' (Admin Bot еще не настроил стратегию)")
                
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить стратегию из Supabase (возможно, таблица еще не создана): {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            self._activate_default_strategy()
            logger.info(f"📍 Используется дефолтная стратегия: '{self.default_strategy['name']}'")

    def _activate_default_strategy(self):
        """Активирует встроенную дефолтную стратегию."""
        self.current_strategy = self.default_strategy
        self.monitored_assets = self.default_strategy['assets_to_monitor']
        self.using_default_strategy = True

    async def aggregate_market_data(self, market_data: Dict[str, pd.DataFrame]):
        """
        Агрегирует и анализирует рыночные данные, сохраняет статистику в БД.
        
        Args:
            market_data: Словарь с рыночными данными по активам
        """
        if not market_data:
            logger.debug("Нет рыночных данных для агрегации")
            return
        
        try:
            for asset, df in market_data.items():
                if df is None or df.empty:
                    continue
                
                # Обрабатываем и сохраняем агрегированные данные
                await self.data_aggregator.process_and_save(
                    asset=asset.replace('=X', ''),  # Убираем суффиксы
                    market_data=df,
                    periods=['daily']  # Пока только дневная агрегация
                )
                
            logger.info("✅ Агрегация данных завершена")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при агрегации данных: {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")

    async def fetch_market_data(self) -> Dict[str, pd.DataFrame]:
        """Получает текущие данные по активам."""
        market_data = {}

        for asset in self.monitored_assets:
            try:
                # Получаем последние 50 точек за 1 минуту
                logger.info(f"📊 Fetching market data for {asset}...")
                data = yf.download(asset, period="1d", interval="1m", progress=False)
                
                if data is None or data.empty:
                    logger.warning(f"⚠️ No data received for {asset}")
                    continue
                
                # Обработка MultiIndex columns от yfinance
                # yfinance иногда возвращает MultiIndex когда запрашивается один актив
                if isinstance(data.columns, pd.MultiIndex):
                    logger.debug(f"MultiIndex columns detected for {asset}, flattening...")
                    data.columns = data.columns.get_level_values(0)
                
                # Проверяем наличие обязательных колонок
                required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                missing_columns = [col for col in required_columns if col not in data.columns]
                
                if missing_columns:
                    logger.warning(f"⚠️ Missing columns for {asset}: {missing_columns}")
                    continue
                
                # Удаляем строки с NaN в колонке Close
                data = data.dropna(subset=['Close'])
                
                if len(data) == 0:
                    logger.warning(f"⚠️ No valid data points for {asset} after cleaning")
                    continue
                
                market_data[asset] = data
                logger.info(f"✅ Fetched {len(data)} valid data points for {asset}")
                
            except Exception as e:
                logger.error(f"❌ Error fetching {asset}: {e}")
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")

        return market_data

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Вычисляет RSI индикатор."""
        try:
            # Валидация входных данных
            if prices is None or len(prices) == 0:
                logger.warning("⚠️ Empty prices series provided to calculate_rsi")
                return pd.Series(dtype=float)
            
            if len(prices) < period + 1:
                logger.debug(f"Insufficient data for RSI calculation: {len(prices)} points (need {period + 1}+)")
                return pd.Series(dtype=float)
            
            # Расчет RSI
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            # Защита от деления на ноль
            rs = gain / loss.replace(0, pd.NA)
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"❌ Error calculating RSI: {e}")
            logger.debug(f"Stack trace:\n{traceback.format_exc()}")
            return pd.Series(dtype=float)

    def apply_algorithm(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Применяет алгоритм (стратегию) и генерирует целевые сигналы."""
        signals = []

        if not market_data:
            logger.debug("No market data available for analysis.")
            return signals

        if not self.current_strategy:
            logger.error("⚠️ КРИТИЧЕСКАЯ ОШИБКА: current_strategy не инициализирована!")
            return signals

        # Получаем параметры из текущей стратегии (дефолтной или из БД)
        strategy_name = self.current_strategy.get('name', 'Unknown')
        allow_trading = self.current_strategy.get('allow_trading', False)
        default_amount = self.current_strategy.get('default_amount', 10.0)
        default_timeframe = self.current_strategy.get('default_timeframe', 60)
        rsi_period = self.current_strategy.get('rsi_period', 14)
        rsi_oversold = self.current_strategy.get('rsi_oversold', 30)
        rsi_overbought = self.current_strategy.get('rsi_overbought', 70)

        # Логирование режима работы
        if self.using_default_strategy:
            logger.info(f"🔍 Применяется дефолтная стратегия '{strategy_name}' (режим: {'торговля' if allow_trading else 'мониторинг'})")
        else:
            logger.info(f"✨ Применяется стратегия из БД '{strategy_name}' (режим: {'торговля' if allow_trading else 'мониторинг'})")

        # Единая логика для всех стратегий (дефолтной и кастомных)
        for asset, df in market_data.items():
            try:
                # Валидация данных
                if df is None or df.empty:
                    logger.debug(f"Empty data for {asset}, skipping.")
                    continue
                
                if len(df) < 20:
                    logger.debug(f"Insufficient data for {asset}: {len(df)} points (need 20+)")
                    continue
                
                # Проверяем наличие колонки Close
                if 'Close' not in df.columns:
                    logger.warning(f"⚠️ 'Close' column not found for {asset}. Available columns: {list(df.columns)}")
                    continue

                # Вычисляем RSI
                rsi = self.calculate_rsi(df['Close'], period=rsi_period)
                
                if rsi is None or rsi.empty or len(rsi) == 0:
                    logger.debug(f"RSI calculation returned no data for {asset}")
                    continue
                
                current_rsi = rsi.iloc[-1]

                if pd.isna(current_rsi):
                    logger.debug(f"Current RSI is NaN for {asset}")
                    continue
                    
            except KeyError as e:
                logger.warning(f"⚠️ Column access error for {asset}: {e}")
                continue
            except Exception as e:
                logger.error(f"❌ Error processing {asset}: {e}")
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")
                continue

            # Генерация сигналов на основе RSI
            signal_generated = False
            
            if current_rsi < rsi_oversold:  # Перепроданность
                signals.append({
                    "asset": asset.replace('=X', ''),
                    "direction": "CALL",
                    "amount": default_amount,
                    "timeframe": default_timeframe,
                    "indicator": "RSI",
                    "value": float(current_rsi),
                    "strategy": strategy_name
                })
                logger.info(f"📈 CALL сигнал для {asset}: RSI={current_rsi:.2f} (< {rsi_oversold})")
                signal_generated = True
                
            elif current_rsi > rsi_overbought:  # Перекупленность
                signals.append({
                    "asset": asset.replace('=X', ''),
                    "direction": "PUT",
                    "amount": default_amount,
                    "timeframe": default_timeframe,
                    "indicator": "RSI",
                    "value": float(current_rsi),
                    "strategy": strategy_name
                })
                logger.info(f"📉 PUT сигнал для {asset}: RSI={current_rsi:.2f} (> {rsi_overbought})")
                signal_generated = True

            if not signal_generated:
                logger.debug(f"📊 {asset}: RSI={current_rsi:.2f} (норма, сигналов нет)")

        # Итоговое логирование
        if signals:
            logger.info(f"✅ Сгенерировано {len(signals)} сигнал(ов) по стратегии '{strategy_name}'")
            if not allow_trading:
                logger.warning(f"⚠️ ТОРГОВЛЯ ВЫКЛЮЧЕНА (allow_trading=False). Сигналы только для мониторинга!")
        else:
            logger.info(f"📊 Сигналы не сгенерированы (рыночные условия не соответствуют стратегии)")
            
        return signals

    async def check_and_execute_trades(self, signals: List[Dict[str, Any]]):
        """Проверяет Supabase на наличие пользовательских запросов (от UI-Бота) и выполняет торговлю."""
        if not self.supabase:
            logger.debug("Supabase client not initialized, skipping trade execution.")
            return

        # Проверяем, разрешена ли торговля текущей стратегией
        if not self.current_strategy or not self.current_strategy.get('allow_trading', False):
            logger.debug("⚠️ Торговля отключена в текущей стратегии. Пропускаем выполнение сделок.")
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

        logger.info(f"💼 Найдено {len(pending_requests)} запрос(ов) на торговлю")

        for req in pending_requests:
            user_id = req.get('user_id')
            request_id = req.get('id')

            if not user_id or not request_id:
                logger.warning(f"⚠️ Invalid request format: {req}")
                continue

            if not signals:
                logger.warning(f"Торговля пропущена для пользователя {user_id}: Нет сигналов в этом цикле.")
                continue

            # Берем первый сгенерированный целевой сигнал
            target_signal = signals[0]
            logger.info(f"🎯 Выполнение сделки для пользователя {user_id}: {target_signal['direction']} {target_signal['asset']}")

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
                logger.info(f"✅ Запрос {request_id} обновлен: статус '{new_status}'")
            except Exception as e:
                logger.error(f"❌ Error updating request status for {request_id}: {e}")
                logger.debug(f"Stack trace:\n{traceback.format_exc()}")

    async def run(self):
        """Главный цикл Ядра."""
        logger.info("🚀 Trading Core (Bot-1) запускается...")
        logger.info("=" * 60)
        logger.info(f"📋 Дефолтная стратегия: '{self.default_strategy['name']}'")
        logger.info(f"   - Режим: {'Торговля' if self.default_strategy['allow_trading'] else 'Мониторинг (торговля отключена)'}")
        logger.info(f"   - RSI период: {self.default_strategy['rsi_period']}")
        logger.info(f"   - RSI перепродан: < {self.default_strategy['rsi_oversold']}")
        logger.info(f"   - RSI перекуплен: > {self.default_strategy['rsi_overbought']}")
        logger.info(f"   - Активы: {self.default_strategy['assets_to_monitor']}")
        logger.info("=" * 60)
        
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

                # 3. Агрегация и анализ данных (периодически)
                self.aggregation_counter += 1
                if self.aggregation_counter >= self.aggregation_interval:
                    logger.info("📊 Запуск агрегации и анализа рыночных данных...")
                    await self.aggregate_market_data(market_data)
                    self.aggregation_counter = 0

                # 4. Применение алгоритма и генерация целевых сигналов
                signals = self.apply_algorithm(market_data)

                # 5. Выполнение торговли (если есть запросы)
                await self.check_and_execute_trades(signals)

                elapsed = time.time() - start_time
                sleep_time = max(0, ANALYSIS_INTERVAL - elapsed)
                logger.info(f"✅ Цикл завершен за {elapsed:.2f}с. Ожидание {sleep_time:.2f}с...")

            except Exception as e:
                logger.error(f"❌ Критическая ошибка в главном цикле: {e}")
                logger.error(f"Stack trace:\n{traceback.format_exc()}")
                logger.info("📍 Продолжаем работу несмотря на ошибку...")
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
