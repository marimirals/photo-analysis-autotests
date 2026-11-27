"""Клиент API photo-analysis.

Тесты не собирают URL и заголовки сами, а вызывают понятные методы:
api.upload(...), api.get_photo(...). Если путь в API поменяется, правим
одно место, а не сто тестов.
"""
from __future__ import annotations

import contextlib
import json

import allure
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
        self._report = True             # писать ли запросы в Allure-отчёт

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", config.REQUEST_TIMEOUT)
        if not self._report:
            return self.session.request(method, self.base_url + path, **kwargs)
        with allure.step(f"{method} {path}"):
            r = self.session.request(method, self.base_url + path, **kwargs)
            attach_exchange(r)
        return r

    @contextlib.contextmanager
    def quiet(self):
        """Временно не писать запросы в отчёт — например, при опросе /analysis каждые 0,5 с."""
        self._report = False
        try:
            yield self
        finally:
            self._report = True

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
        attach_image(content, filename)
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


# ---------- Allure: что именно отправили и что получили ----------
MAX_TEXT = 5000


def _describe_body(req: requests.PreparedRequest) -> str:
    if req.body is None:
        return "(без тела)"
    ctype = req.headers.get("Content-Type", "")
    if ctype.startswith("multipart/form-data"):
        return f"multipart/form-data, {len(req.body)} байт"
    body = req.body.decode(errors="replace") if isinstance(req.body, bytes) else str(req.body)
    return body[:MAX_TEXT]


def attach_exchange(r: requests.Response) -> None:
    req = r.request
    headers = "\n".join(f"{k}: {v}" for k, v in req.headers.items()
                        if k in ("X-User-ID", "Content-Type", "Accept"))
    allure.attach(f"{req.method} {req.url}\n{headers}\n\n{_describe_body(req)}",
                  name="запрос", attachment_type=allure.attachment_type.TEXT)

    ctype = r.headers.get("Content-Type", "")
    meta = f"{r.status_code} {r.reason}, {r.elapsed.total_seconds() * 1000:.0f} мс"
    if "application/json" in ctype:
        try:
            body = json.dumps(r.json(), ensure_ascii=False, indent=2)
        except ValueError:
            body = r.text
        allure.attach(body[:MAX_TEXT], name=f"ответ {meta}", attachment_type=allure.attachment_type.JSON)
    elif ctype.startswith("image/"):
        allure.attach(f"{len(r.content)} байт, {ctype}", name=f"ответ {meta}",
                      attachment_type=allure.attachment_type.TEXT)
    else:
        allure.attach(r.text[:MAX_TEXT] or "(пустое тело)", name=f"ответ {meta}",
                      attachment_type=allure.attachment_type.TEXT)


def attach_image(content: bytes, filename: str) -> None:
    """Загружаемую картинку прикладываем к отчёту — видно, что именно тестировали.
    Большие и «не картинки» не прикладываем."""
    if len(content) > 2 * 1024 * 1024:
        return
    if content[:3] == b"\xff\xd8\xff":
        kind = allure.attachment_type.JPG
    elif content[:8] == b"\x89PNG\r\n\x1a\n":
        kind = allure.attachment_type.PNG
    else:
        return
    allure.attach(content, name=f"картинка {filename}", attachment_type=kind)
