"""Общие фикстуры. pytest находит этот файл сам и даёт фикстуры всем тестам в папке."""
from __future__ import annotations

import uuid

import pytest
import requests

from framework import config, images
from framework.api_client import PhotoApi


@pytest.fixture(scope="session", autouse=True)
def service_is_up():
    """Один раз перед всеми тестами: если сервис не отвечает, нет смысла гонять сотню тестов."""
    try:
        r = requests.get(f"{config.BASE_URL}/healthz", timeout=5)
        ok = r.status_code == 200
    except requests.RequestException as e:
        ok, r = False, e
    if not ok:
        pytest.exit(f"Сервис {config.BASE_URL} недоступен ({r}). Запусти photo-analysis.", returncode=3)


@pytest.fixture
def user_id() -> str:
    """Свой пользователь на каждый тест — тесты не видят данных друг друга."""
    return f"at-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def api(user_id):
    """Клиент от имени пользователя теста. После теста удаляет всё, что тот загрузил."""
    client = PhotoApi(user_id)
    yield client
    client.cleanup()


@pytest.fixture
def other_api():
    """Второй пользователь — для проверок «чужое фото не видно»."""
    client = PhotoApi(f"at-other-{uuid.uuid4().hex[:8]}")
    yield client
    client.cleanup()


@pytest.fixture
def anon():
    """Клиент без X-User-ID: для служебных эндпоинтов и негативных тестов."""
    return PhotoApi(None)


@pytest.fixture
def uploaded_photo(api) -> dict:
    """Готовое загруженное фото — для тестов, которым загрузка нужна как предусловие."""
    r = api.upload(images.sharp(), "sharp.jpg")
    assert r.status_code == 202, f"предусловие не выполнено: загрузка вернула {r.status_code} {r.text}"
    return r.json()
