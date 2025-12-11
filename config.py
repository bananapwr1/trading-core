#!/usr/bin/env python3
"""
Конфигурация торгового ядра
"""

import os
from typing import List

# ============== SUPABASE ==============
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ============== AI ENGINE ==============
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ============== НАСТРОЙКИ АНАЛИЗА ==============
MONITORED_ASSETS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "AVAX", "DOT", "DOGE", "LINK"
]

ANALYSIS_INTERVAL = 60  # Интервал анализа в секундах
MAX_CONCURRENT_TASKS = 3  # Макс. одновременных AI запросов

# ============== НАСТРОЙКИ ЛОГИРОВАНИЯ ==============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "trading_core.log"

# ============== ПРОВЕРКА КОНФИГУРАЦИИ ==============
def validate_config():
    """Проверка конфигурации"""
    errors = []
    
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL не задан")
    if not SUPABASE_KEY:
        errors.append("SUPABASE_KEY не задан")
        
    return errors