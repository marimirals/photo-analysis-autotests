"""Настройки тестов. Всё берётся из переменных окружения, чтобы одни и те же
тесты запускались и на ноутбуке, и в CI без правок кода."""
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
DB_DSN = os.getenv("DB_DSN", "postgresql://photo:photo@localhost:5433/photo")

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))    # на один HTTP-запрос, с
ANALYSIS_TIMEOUT = float(os.getenv("ANALYSIS_TIMEOUT", "60"))  # ожидание анализа, с
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "0.5"))       # как часто спрашивать, с
STARTUP_TIMEOUT = float(os.getenv("STARTUP_TIMEOUT", "90"))     # сколько ждать готовности сервиса перед тестами, с
