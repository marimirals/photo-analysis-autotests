"""Позитивные тесты: правильные запросы дают правильный результат."""
import pytest

from framework import images
from framework.api_client import PhotoApi


def upload_ok(api: PhotoApi, content: bytes, name: str = "photo.jpg",
              mime: str = "image/jpeg") -> dict:
    """Вспомогательная функция, не тест (имя не начинается с test_).
    Загружает фото и сразу проверяет, что загрузка прошла."""
    r = api.upload(content, name, mime)
    assert r.status_code == 202, f"загрузка {name} вернула {r.status_code}: {r.text}"
    return r.json()


@pytest.mark.parametrize("fmt, mime, name", [
    pytest.param("JPEG", "image/jpeg", "photo.jpg", id="jpeg"),
    pytest.param("PNG", "image/png", "photo.png", id="png"),
    pytest.param("WEBP", "image/webp", "photo.webp", id="webp"),
])
def test_upload_supported_formats(api, fmt, mime, name):
    """UPL-01: JPEG, PNG и WebP принимаются, в ответе верные метаданные."""
    content = images.sharp(640, 480, fmt=fmt)
    r = api.upload(content, name, mime)
    assert r.status_code == 202, r.text
    photo = r.json()
    assert photo["status"] == "pending"
    assert photo["filename"] == name
    assert photo["content_type"] == mime
    assert photo["size_bytes"] == len(content)
    assert (photo["width"], photo["height"]) == (640, 480)
    assert photo["error"] is None


def test_get_uploaded_photo(api, uploaded_photo):
    """GET-01: загруженное фото доступно по id с теми же данными."""
    r = api.get_photo(uploaded_photo["id"])
    assert r.status_code == 200, r.text
    got = r.json()
    for key in ("id", "filename", "content_type", "size_bytes", "width", "height", "created_at"):
        assert got[key] == uploaded_photo[key], f"поле {key} изменилось"


def test_download_returns_same_bytes(api):
    """FIL-01: скачанный файл побайтно совпадает с загруженным."""
    content = images.sharp(seed=5)
    photo = upload_ok(api, content, "original.jpg")
    r = api.get_file(photo["id"])
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/jpeg"
    assert r.content == content


def test_list_contains_only_own_photos(api, other_api):
    """LST-01: в списке только свои фото, total верный."""
    mine = {upload_ok(api, images.sharp(seed=s))["id"] for s in (1, 2, 3)}
    upload_ok(other_api, images.sharp(seed=4))          # чужое фото

    r = api.list_photos()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert {p["id"] for p in body["items"]} == mine


def test_list_pagination(api):
    """LST-02: limit/offset делят список на страницы, новые фото первыми."""
    ids = [upload_ok(api, images.sharp(seed=s))["id"] for s in range(5)]
    newest_first = ids[::-1]

    pages = [api.list_photos(limit=2, offset=off).json() for off in (0, 2, 4)]
    assert [len(p["items"]) for p in pages] == [2, 2, 1]
    assert all(p["total"] == 5 for p in pages)
    got = [item["id"] for page in pages for item in page["items"]]
    assert got == newest_first


def test_delete_photo(api, uploaded_photo):
    """DEL-01: после удаления фото нет ни по id, ни в списке, ни файла."""
    photo_id = uploaded_photo["id"]
    r = api.delete(photo_id)
    assert r.status_code == 204
    assert r.content == b""
    assert api.get_photo(photo_id).status_code == 404
    assert api.get_file(photo_id).status_code == 404
    assert photo_id not in [p["id"] for p in api.list_photos().json()["items"]]


@pytest.mark.parametrize("user", [
    pytest.param("a", id="len-1"),
    pytest.param("x" * 64, id="len-64"),
    pytest.param("Masha_Test-01", id="allowed-chars"),
])
def test_valid_user_ids_accepted(user):
    """USR-01: X-User-ID на границах допустимого (1 и 64 символа) принимается."""
    r = PhotoApi(user).list_photos()
    assert r.status_code == 200, r.text
