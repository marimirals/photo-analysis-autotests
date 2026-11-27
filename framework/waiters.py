"""Ожидание асинхронного результата: опрос с таймаутом вместо sleep."""
from __future__ import annotations

import time

from framework import config
from framework.api_client import PhotoApi


def wait_for_analysis(api: PhotoApi, photo_id: str,
                      timeout: float = config.ANALYSIS_TIMEOUT,
                      interval: float = config.POLL_INTERVAL) -> dict:
    """Спрашивает /analysis, пока не придёт 200. Падает, если не дождались за timeout."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = api.get_analysis(photo_id)
        if last.status_code == 200:
            return last.json()
        if last.status_code == 202 and last.json().get("status") == "failed":
            raise AssertionError(f"анализ фото {photo_id} завершился ошибкой: {last.json().get('error')}")
        if last.status_code not in (200, 202):
            raise AssertionError(f"неожиданный ответ {last.status_code}: {last.text}")
        time.sleep(interval)
    status = last.json().get("status") if last is not None else "нет ответа"
    raise TimeoutError(f"анализ фото {photo_id} не готов за {timeout:.0f} с (последний статус: {status})")
