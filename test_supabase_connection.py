#!/usr/bin/env python3
"""
Диагностический скрипт для проверки подключения к Supabase
Помогает выявить проблемы с авторизацией 401 Unauthorized
"""
import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 80)
    logger.info("🔍 ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ К SUPABASE")
    logger.info("=" * 80)
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # 1. Проверка наличия переменных окружения
    logger.info("\n📋 Шаг 1: Проверка переменных окружения")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url:
        logger.error("❌ SUPABASE_URL не установлена!")
        sys.exit(1)
    else:
        logger.info(f"✅ SUPABASE_URL: {supabase_url}")
    
    if not supabase_key:
        logger.error("❌ SUPABASE_SERVICE_ROLE_KEY не установлена!")
        sys.exit(1)
    else:
        # Показываем только первые и последние символы ключа для безопасности
        key_preview = f"{supabase_key[:20]}...{supabase_key[-10:]}" if len(supabase_key) > 30 else "***"
        logger.info(f"✅ SUPABASE_SERVICE_ROLE_KEY: {key_preview}")
        logger.info(f"   Длина ключа: {len(supabase_key)} символов")
    
    # 2. Проверка на пробелы и невидимые символы
    logger.info("\n🔍 Шаг 2: Проверка формата ключей")
    
    url_has_spaces = supabase_url != supabase_url.strip()
    key_has_spaces = supabase_key != supabase_key.strip()
    
    if url_has_spaces:
        logger.warning("⚠️ ВНИМАНИЕ: SUPABASE_URL содержит пробелы в начале или конце!")
        logger.info(f"   Оригинал: '{supabase_url}'")
        logger.info(f"   После trim: '{supabase_url.strip()}'")
    else:
        logger.info("✅ SUPABASE_URL не содержит лишних пробелов")
    
    if key_has_spaces:
        logger.warning("⚠️ ВНИМАНИЕ: SUPABASE_SERVICE_ROLE_KEY содержит пробелы в начале или конце!")
        logger.info("   Это может быть причиной ошибки 401!")
    else:
        logger.info("✅ SUPABASE_SERVICE_ROLE_KEY не содержит лишних пробелов")
    
    # 3. Проверка формата URL
    logger.info("\n🌐 Шаг 3: Проверка формата URL")
    if not supabase_url.startswith("https://"):
        logger.error("❌ SUPABASE_URL должен начинаться с https://")
    elif ".supabase.co" not in supabase_url:
        logger.warning("⚠️ SUPABASE_URL не содержит .supabase.co - возможно, это неправильный URL")
    else:
        logger.info("✅ Формат SUPABASE_URL выглядит корректно")
    
    # 4. Проверка формата ключа
    logger.info("\n🔑 Шаг 4: Проверка формата ключа")
    
    # Service Role Key обычно начинается с определенного префикса
    if supabase_key.startswith("eyJ"):
        logger.info("✅ Ключ начинается с 'eyJ' (JWT токен) - формат корректный")
    else:
        logger.warning("⚠️ Ключ не начинается с 'eyJ' - возможно, это не Service Role Key")
        logger.warning("   Убедитесь, что вы используете именно service_role key, а не anon key!")
    
    # Проверяем, что ключ содержит точки (характерно для JWT)
    if supabase_key.count('.') >= 2:
        logger.info("✅ Ключ содержит точки (JWT структура)")
    else:
        logger.warning("⚠️ Ключ не похож на JWT токен")
    
    # 5. Попытка подключения к Supabase
    logger.info("\n🔌 Шаг 5: Попытка подключения к Supabase")
    
    try:
        from supabase import create_client, Client
        logger.info("✅ Библиотека supabase успешно импортирована")
        
        # Очищаем ключи от пробелов перед использованием
        clean_url = supabase_url.strip()
        clean_key = supabase_key.strip()
        
        logger.info("Создание клиента Supabase...")
        supabase: Client = create_client(clean_url, clean_key)
        logger.info("✅ Клиент Supabase создан успешно")
        
        # Попытка выполнить простой запрос
        logger.info("Выполнение тестового запроса...")
        
        try:
            # Пробуем получить версию PostgreSQL
            response = supabase.rpc('version', {}).execute()
            logger.info("✅ УСПЕХ! Подключение к Supabase работает!")
            logger.info(f"   Ответ: {response}")
        except Exception as e:
            error_message = str(e)
            logger.error(f"❌ Ошибка при выполнении запроса: {error_message}")
            
            # Анализ ошибки
            if "401" in error_message or "Unauthorized" in error_message:
                logger.error("\n🚨 ПРОБЛЕМА: Ошибка авторизации 401")
                logger.error("   Возможные причины:")
                logger.error("   1. Используется неправильный ключ (anon вместо service_role)")
                logger.error("   2. Ключ был сброшен в Supabase, но не обновлен в Render")
                logger.error("   3. Ключ содержит опечатку или скопирован не полностью")
                logger.error("   4. RLS (Row Level Security) блокирует доступ")
                logger.error("\n💡 РЕШЕНИЕ:")
                logger.error("   1. Зайдите в Supabase Dashboard → Settings → API")
                logger.error("   2. Найдите раздел 'Project API keys'")
                logger.error("   3. Скопируйте 'service_role' key (НЕ 'anon' key!)")
                logger.error("   4. В Render: Environment → SUPABASE_SERVICE_ROLE_KEY → Edit")
                logger.error("   5. Вставьте новый ключ БЕЗ пробелов в начале/конце")
                logger.error("   6. Нажмите Save Changes")
                logger.error("   7. Вручную перезапустите сервис (Manual Deploy → Clear build cache & deploy)")
            elif "404" in error_message or "Not Found" in error_message:
                logger.warning("⚠️ Функция version() не найдена - это нормально для некоторых проектов")
                logger.info("   Попробуем другой способ проверки...")
                
                # Пробуем просто получить список таблиц
                try:
                    # Это должно работать, даже если таблица не существует
                    test_response = supabase.table("_test_connection").select("*").limit(1).execute()
                    logger.info("✅ УСПЕХ! Подключение работает (получен ответ от API)")
                except Exception as e2:
                    if "404" in str(e2) or "not found" in str(e2).lower():
                        logger.info("✅ УСПЕХ! Подключение работает (таблица не найдена, но авторизация прошла)")
                    elif "401" in str(e2):
                        logger.error("❌ Ошибка 401 сохраняется - проблема с ключом!")
                    else:
                        logger.warning(f"⚠️ Получена другая ошибка: {e2}")
            else:
                logger.error(f"   Неизвестная ошибка: {error_message}")
    
    except ImportError as e:
        logger.error(f"❌ Не удалось импортировать библиотеку supabase: {e}")
        logger.error("   Установите её: pip install supabase")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        sys.exit(1)
    
    logger.info("\n" + "=" * 80)
    logger.info("🏁 ДИАГНОСТИКА ЗАВЕРШЕНА")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()
