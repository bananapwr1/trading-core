-- Supabase Tables Setup для Trading Core
-- Выполните этот скрипт в Supabase Dashboard → SQL Editor

-- ============================================================
-- 1. Таблица настроек стратегий (для Admin Bot)
-- ============================================================
CREATE TABLE IF NOT EXISTS strategy_settings (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT false,
    assets_to_monitor TEXT[] DEFAULT ARRAY['EURUSD'],
    allow_trading BOOLEAN DEFAULT false,
    default_amount DECIMAL DEFAULT 10.0,
    default_timeframe INTEGER DEFAULT 60,
    rsi_period INTEGER DEFAULT 14,
    rsi_oversold INTEGER DEFAULT 30,
    rsi_overbought INTEGER DEFAULT 70,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Комментарии к колонкам
COMMENT ON TABLE strategy_settings IS 'Настройки торговых стратегий, управляемые Admin Bot';
COMMENT ON COLUMN strategy_settings.name IS 'Название стратегии';
COMMENT ON COLUMN strategy_settings.is_active IS 'Активная стратегия (только одна может быть активной)';
COMMENT ON COLUMN strategy_settings.assets_to_monitor IS 'Массив активов для мониторинга';
COMMENT ON COLUMN strategy_settings.allow_trading IS 'Разрешена ли автоматическая торговля';
COMMENT ON COLUMN strategy_settings.default_amount IS 'Сумма сделки по умолчанию';
COMMENT ON COLUMN strategy_settings.default_timeframe IS 'Таймфрейм сделки (секунды)';

-- ============================================================
-- 2. Таблица запросов на сигналы (от UI Bot к Trading Core)
-- ============================================================
CREATE TABLE IF NOT EXISTS signal_requests (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Комментарии
COMMENT ON TABLE signal_requests IS 'Запросы пользователей на получение торговых сигналов';
COMMENT ON COLUMN signal_requests.user_id IS 'Telegram ID пользователя';
COMMENT ON COLUMN signal_requests.status IS 'Статус: pending, executed, failed';

-- Индекс для быстрого поиска ожидающих запросов
CREATE INDEX IF NOT EXISTS idx_signal_requests_status 
ON signal_requests(status) WHERE status = 'pending';

-- ============================================================
-- 3. Таблица сделок (лог всех выполненных трейдов)
-- ============================================================
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    trade_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    amount DECIMAL NOT NULL,
    timeframe INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    profit DECIMAL
);

-- Комментарии
COMMENT ON TABLE trades IS 'История всех выполненных торговых сделок';
COMMENT ON COLUMN trades.user_id IS 'Telegram ID пользователя';
COMMENT ON COLUMN trades.trade_id IS 'Уникальный ID сделки от PocketOption';
COMMENT ON COLUMN trades.asset IS 'Торговый актив (например, EURUSD)';
COMMENT ON COLUMN trades.direction IS 'Направление: CALL или PUT';
COMMENT ON COLUMN trades.status IS 'Статус: open, win, loss';

-- Индексы для аналитики
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at DESC);

-- ============================================================
-- 4. RLS (Row Level Security) политики
-- ============================================================

-- Включаем RLS для всех таблиц
ALTER TABLE strategy_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE signal_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;

-- Политика для service_role (Trading Core использует service_role key)
-- service_role имеет полный доступ ко всем таблицам

CREATE POLICY "Service role full access" ON strategy_settings
FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON signal_requests
FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON trades
FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Политика для authenticated пользователей (если UI Bot будет напрямую работать с БД)
-- Пользователи могут видеть только свои данные

CREATE POLICY "Users can view own requests" ON signal_requests
FOR SELECT TO authenticated USING (auth.uid()::text::bigint = user_id);

CREATE POLICY "Users can create own requests" ON signal_requests
FOR INSERT TO authenticated WITH CHECK (auth.uid()::text::bigint = user_id);

CREATE POLICY "Users can view own trades" ON trades
FOR SELECT TO authenticated USING (auth.uid()::text::bigint = user_id);

-- ============================================================
-- 5. Тестовые данные (опционально)
-- ============================================================

-- Вставка дефолтной стратегии
INSERT INTO strategy_settings (
    name, 
    is_active, 
    assets_to_monitor, 
    allow_trading,
    default_amount,
    default_timeframe,
    rsi_period,
    rsi_oversold,
    rsi_overbought
) VALUES (
    'Default RSI Strategy',
    true,
    ARRAY['EURUSD', 'GBPUSD', 'USDJPY'],
    true,
    10.0,
    60,
    14,
    30,
    70
) ON CONFLICT DO NOTHING;

-- ============================================================
-- 6. Функции для обслуживания
-- ============================================================

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры для автоматического обновления updated_at
CREATE TRIGGER update_strategy_settings_updated_at 
    BEFORE UPDATE ON strategy_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_signal_requests_updated_at 
    BEFORE UPDATE ON signal_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Готово! 
-- ============================================================

-- Проверьте созданные таблицы:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Проверьте политики RLS:
-- SELECT * FROM pg_policies WHERE schemaname = 'public';
