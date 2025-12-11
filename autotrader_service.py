# autotrader_service.py
import os
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Импортируем модули, которые будут использоваться в main.py
from crypto_utils import decrypt_data
from pocket_option_api import PocketOptionAPI

logger = logging.getLogger(__name__)

# URL API-сервера на Bothost
BOTHOST_UI_API_URL = os.getenv("API_ENDPOINT")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")


async def get_encrypted_credentials(user_id: int) -> Optional[Dict[str, str]]:
    """
    Отправляет запрос UI-Боту Bothost, чтобы получить зашифрованные
    логин/пароль пользователя PO.
    """
    if not BOTHOST_UI_API_URL:
        logger.error("🚫 Переменная API_ENDPOINT не задана в настройках окружения!")
        return None

    api_endpoint = f"{BOTHOST_UI_API_URL}/get_po_credentials"

    payload = {
        "user_id": user_id,
        "request_source": "trading_core_render"
    }

    try:
        # Асинхронный запрос к API на Bothost
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_endpoint,
                json=payload,
                timeout=5.0
            )
            # Вызовет исключение при ошибке 4xx/5xx
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "success":
                # Возвращает зашифрованные данные
                return {
                    'login_enc': data['login_enc'],
                    'password_enc': data['password_enc']
                }
            else:
                msg = data.get('message', 'Неизвестная ошибка')
                logger.warning(f"⚠️ UI-Bot не вернул данные для {user_id}: {msg}")
                return None

    except httpx.RequestError as e:
        logger.error(f"❌ Ошибка соединения или таймаута с UI-Bot Bothost: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка при запросе к UI-Bot: {e}")
        return None


async def execute_auto_trade(user_id: int, signal: Dict[str, Any], supabase_client) -> bool:
    """
    Получает данные PO с Bothost, дешифрует их и размещает сделку.
    """
    if not ENCRYPTION_KEY:
        logger.error("🚫 ENCRYPTION_KEY не задан для дешифровки!")
        return False

    # 1. Получаем зашифрованные данные с Bothost
    encrypted_creds = await get_encrypted_credentials(user_id)

    if not encrypted_creds:
        logger.warning(f"Trade skipped for {user_id}: Could not retrieve credentials.")
        return False

    # 2. Дешифровка
    try:
        po_login = decrypt_data(encrypted_creds['login_enc'], ENCRYPTION_KEY)
        po_password = decrypt_data(encrypted_creds['password_enc'], ENCRYPTION_KEY)

    except Exception as e:
        logger.error(f"❌ Ошибка дешифровки для {user_id}: {e}")
        return False

    # 3. Подключение и Торговля
    po_api: Optional[PocketOptionAPI] = None
    try:
        logger.info(f"💰 Connecting to PO and placing trade for {user_id}...")

        # Инициализация и аутентификация
        po_api = PocketOptionAPI(po_login, po_password)
        if not await po_api.authenticate():
            logger.warning(f"Trade failed for {user_id}: PO authentication failed.")
            return False

        # Размещение сделки (используем данные из сигнала)
        trade_result = await po_api.place_trade(
            asset=signal.get('asset', 'EURUSD'),
            direction=signal.get('direction', 'CALL'),
            amount=signal.get('amount', 10.0),
            timeframe=signal.get('timeframe', 60)
        )

        if trade_result and trade_result.get("status") != "error":
            # Логирование успешной сделки в Supabase (таблица 'trades')
            supabase_client.table("trades").insert({
                'user_id': user_id,
                'trade_id': trade_result.get('trade_id'),
                'asset': signal['asset'],
                'direction': signal['direction'],
                'status': 'open',
                'amount': signal.get('amount', 10.0),
                'timeframe': signal.get('timeframe', 60),
                'created_at': datetime.utcnow().isoformat()
            }).execute()

            logger.info(f"✅ Trade placed and logged: {trade_result.get('trade_id')}")
            return True
        else:
            logger.warning(f"Trade failed on PO for {user_id}.")
            return False

    except Exception as e:
        logger.error(f"❌ Критическая ошибка торговли для {user_id}: {e}")
        return False
    finally:
        if po_api:
            await po_api.close()
