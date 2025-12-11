#!/usr/bin/env python3
"""
WSGI файл для PythonAnywhere
Позволяет запускать ядро как веб-приложение
"""

import sys
import os

# Добавляем путь к проекту
path = '/home/ваш_username/trading-core'
if path not in sys.path:
    sys.path.append(path)

# Импортируем и запускаем ядро
from main import TradingCore
import asyncio

# Создаем event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Функция для запуска ядра (вызывается WSGI)
def run_core(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'text/plain')]
    start_response(status, response_headers)
    
    # Запускаем ядро в фоне
    core = TradingCore()
    
    # Запускаем в отдельном потоке
    import threading
    thread = threading.Thread(target=lambda: asyncio.run(core.run()))
    thread.daemon = True
    thread.start()
    
    return [b'Trading Core is running on PythonAnywhere!\n']

# WSGI application
application = run_core