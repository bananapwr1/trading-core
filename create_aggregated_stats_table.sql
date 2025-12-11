-- SQL скрипт для создания таблицы aggregated_stats
-- Эта таблица хранит агрегированную статистику по рыночным данным
-- для анализа и автоматического переключения стратегий

-- Создание таблицы
CREATE TABLE IF NOT EXISTS aggregated_stats (
    id BIGSERIAL PRIMARY KEY,
    asset TEXT NOT NULL,
    period TEXT NOT NULL, -- 'daily', 'weekly', 'monthly'
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Базовая статистика по ценам
    data_points INTEGER,
    price_open NUMERIC,
    price_close NUMERIC,
    price_high NUMERIC,
    price_low NUMERIC,
    price_mean NUMERIC,
    
    -- Статистика по объему
    volume_total NUMERIC,
    volume_mean NUMERIC,
    
    -- Аналитические метрики
    volatility NUMERIC, -- Волатильность в %
    trend_direction TEXT, -- 'up', 'down', 'sideways'
    trend_strength NUMERIC, -- 0-100
    price_change_percent NUMERIC,
    market_sentiment TEXT, -- 'bullish', 'bearish', 'neutral'
    
    -- Уникальность записи: один актив, один период, одна временная метка
    CONSTRAINT unique_asset_period_time UNIQUE (asset, period, timestamp)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_asset ON aggregated_stats(asset);
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_timestamp ON aggregated_stats(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_period ON aggregated_stats(period);
CREATE INDEX IF NOT EXISTS idx_aggregated_stats_sentiment ON aggregated_stats(market_sentiment);

-- Комментарии к таблице
COMMENT ON TABLE aggregated_stats IS 'Агрегированная статистика по рыночным данным';
COMMENT ON COLUMN aggregated_stats.asset IS 'Название актива (например, EURUSD, BTC)';
COMMENT ON COLUMN aggregated_stats.period IS 'Период агрегации: daily, weekly, monthly';
COMMENT ON COLUMN aggregated_stats.volatility IS 'Волатильность (стандартное отклонение доходности) в %';
COMMENT ON COLUMN aggregated_stats.trend_direction IS 'Направление тренда: up, down, sideways';
COMMENT ON COLUMN aggregated_stats.trend_strength IS 'Сила тренда (R-квадрат) от 0 до 100';
COMMENT ON COLUMN aggregated_stats.market_sentiment IS 'Настроение рынка: bullish, bearish, neutral';

-- Пример запроса: последняя статистика по активу
-- SELECT * FROM aggregated_stats WHERE asset = 'EURUSD' ORDER BY timestamp DESC LIMIT 10;

-- Пример запроса: активы с высокой волатильностью
-- SELECT asset, volatility, market_sentiment FROM aggregated_stats 
-- WHERE volatility > 2.0 AND period = 'daily' 
-- ORDER BY timestamp DESC LIMIT 20;

-- Пример запроса: тренды по всем активам
-- SELECT DISTINCT ON (asset) asset, trend_direction, trend_strength, price_change_percent
-- FROM aggregated_stats 
-- WHERE period = 'daily'
-- ORDER BY asset, timestamp DESC;
