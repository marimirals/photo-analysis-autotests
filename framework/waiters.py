"""Ожидание асинхронного результата: опрос с таймаутом вместо sleep."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

import allure

from framework import config
from framework.api_client import PhotoApi, attach_exchange


def wait_for_analysis(api: PhotoApi, photo_id: str,
                      timeout: float = config.ANALYSIS_TIMEOUT,
                      interval: float = config.POLL_INTERVAL) -> dict:
    """Спрашивает /analysis, пока не придёт 200. Падает, если не дождались за timeout."""
    with allure.step(f"Ждём анализ фото {photo_id} (до {timeout:.0f} с)"):
        deadline = time.monotonic() + timeout
        start = time.monotonic()
        polls, last = 0, None
        with api.quiet():                      # опрос не засоряет отчёт
            while time.monotonic() < deadline:
                polls += 1
                last = api.get_analysis(photo_id)
                if last.status_code == 200:
                    break
                if last.status_code == 202 and last.json().get("status") == "failed":
                    raise AssertionError(f"анализ фото {photo_id} завершился ошибкой: {last.json().get('error')}")
                if last.status_code not in (200, 202):
                    raise AssertionError(f"неожиданный ответ {last.status_code}: {last.text}")
                time.sleep(interval)
            else:
                status = last.json().get("status") if last is not None else "нет ответа"
                raise TimeoutError(f"анализ фото {photo_id} не готов за {timeout:.0f} с (последний статус: {status})")
        allure.attach(f"готово за {time.monotonic() - start:.1f} с, запросов: {polls}",
                      name="ожидание", attachment_type=allure.attachment_type.TEXT)
        attach_exchange(last)
        return last.json()


T = TypeVar("T")


def wait_until(check: Callable[[], T], what: str, timeout: float = 15,
               interval: float = config.POLL_INTERVAL) -> T:
    """Общий вариант: вызывает check(), пока он не вернёт что-то истинное, и возвращает это."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise TimeoutError(f"не дождались за {timeout:.0f} с: {what}")
