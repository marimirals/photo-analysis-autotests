"""Клиент API photo-analysis.

Тесты не собирают URL и заголовки сами, а вызывают понятные методы:
api.upload(...), api.get_photo(...). Если путь в API поменяется, правим
одно место, а не сто тестов.
"""
from __future__ import annotations

import requests

from framework import config

API = "/api/v1"


class PhotoApi:
    def __init__(self, user_id: str | None, base_url: str = config.BASE_URL):
        self.base_url = base_url
        self.user_id = user_id
        self.session = requests.Session()
        if user_id is not None:
            self.session.headers["X-User-ID"] = user_id
        self.created: list[str] = []   # id загруженных фото — удалим после теста

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", config.REQUEST_TIMEOUT)
        return self.session.request(method, self.base_url + path, **kwargs)

    # ---------- служебные ----------
    def healthz(self) -> requests.Response:
        return self.request("GET", "/healthz")

    def readyz(self) -> requests.Response:
        return self.request("GET", "/readyz")

    def openapi(self) -> requests.Response:
        return self.request("GET", "/openapi.yaml")

    # ---------- фото ----------
    def upload(self, content: bytes, filename: str = "photo.jpg",
               content_type: str = "image/jpeg", field: str = "file",
               **kwargs) -> requests.Response:
        r = self.request("POST", f"{API}/photos",
                         files={field: (filename, content, content_type)}, **kwargs)
        if r.status_code == 202:
            self.created.append(r.json()["id"])
        return r

    def upload_ok(self, content: bytes, filename: str = "photo.jpg",
                  content_type: str = "image/jpeg") -> dict:
        """Загрузка как предусловие теста: сразу проверяет, что прошла, и отдаёт фото."""
        r = self.upload(content, filename, content_type)
        assert r.status_code == 202, f"загрузка {filename} вернула {r.status_code}: {r.text}"
        return r.json()

    def get_photo(self, photo_id: str, **kwargs) -> requests.Response:
        return self.request("GET", f"{API}/photos/{photo_id}", **kwargs)

    def list_photos(self, **params) -> requests.Response:
        return self.request("GET", f"{API}/photos", params=params)

    def get_file(self, photo_id: str) -> requests.Response:
        return self.request("GET", f"{API}/photos/{photo_id}/file")

    def delete(self, photo_id: str) -> requests.Response:
        return self.request("DELETE", f"{API}/photos/{photo_id}")

    def get_analysis(self, photo_id: str) -> requests.Response:
        return self.request("GET", f"{API}/photos/{photo_id}/analysis")

    def reanalyze(self, photo_id: str) -> requests.Response:
        return self.request("POST", f"{API}/photos/{photo_id}/reanalyze")

    def reanalyze_failed(self) -> requests.Response:
        return self.request("POST", f"{API}/photos/reanalyze-failed")

    # ---------- уборка ----------
    def cleanup(self) -> None:
        """Удаляет всё, что загрузил этот клиент. Ошибки не важны: фото мог удалить сам тест."""
        for photo_id in self.created:
            try:
                self.delete(photo_id)
            except requests.RequestException:
                pass
        self.created.clear()
