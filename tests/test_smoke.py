"""Смоук: сервис жив и его зависимости доступны. Запускаются первыми: pytest -m smoke"""
import pytest

from framework import images

pytestmark = pytest.mark.smoke


def test_healthz(anon):
    """SMK-01: /healthz отвечает 200."""
    r = anon.healthz()
    assert r.status_code == 200


def test_readyz_dependencies_ok(anon):
    """SMK-02: /readyz — Postgres и S3 доступны (Kafka показывается, но на статус не влияет)."""
    r = anon.readyz()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["postgres"] == "ok"
    assert body["s3"] == "ok"


def test_upload_and_cleanup_work(api):
    """Проверка каркаса: загрузка проходит, фото попадает в список на уборку."""
    r = api.upload(images.sharp(), "sharp.jpg")
    assert r.status_code == 202, r.text
    assert r.json()["id"] in api.created
