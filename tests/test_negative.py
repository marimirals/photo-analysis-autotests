"""Негативные тесты и граничные значения: неправильные запросы дают понятную ошибку, а не 500."""
import pytest

from framework import images
from framework.api_client import API, PhotoApi

MAX_UPLOAD = 20 * 1024 * 1024          # лимит сервиса: 20 МБ (MAX_UPLOAD_MB=20)
MISSING_ID = "00000000-0000-4000-8000-000000000000"


def assert_error(r, status: int, text: str | None = None) -> None:
    """Ошибка должна быть в едином формате: {"error": "...", "request_id": "..."}."""
    assert r.status_code == status, f"ожидали {status}, получили {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("error"), f"нет текста ошибки: {body}"
    assert body.get("request_id"), f"нет request_id — по нему ищут ошибку в логах: {body}"
    if text is not None:
        assert text in body["error"], f"ожидали в ошибке «{text}», получили «{body['error']}»"


# ---------- загрузка ----------

@pytest.mark.slow
def test_upload_exactly_max_size_accepted(api):
    """UPL-02: файл ровно 20 МБ — на границе, принимается."""
    r = api.upload(images.png_of_exact_size(MAX_UPLOAD), "max.png", "image/png")
    assert r.status_code == 202, r.text
    assert r.json()["size_bytes"] == MAX_UPLOAD


@pytest.mark.slow
def test_upload_one_byte_over_max_rejected(api):
    """UPL-03: 20 МБ + 1 байт — за границей, 413."""
    r = api.upload(images.png_of_exact_size(MAX_UPLOAD + 1), "too-big.png", "image/png")
    assert_error(r, 413, "too large")


def test_upload_empty_file(api):
    """UPL-04: пустой файл — 400."""
    assert_error(api.upload(b"", "empty.jpg"), 400, "empty")


@pytest.mark.parametrize("content, name, mime", [
    pytest.param(images.TEXT, "notes.txt", "text/plain", id="text"),
    pytest.param(images.gif(), "anim.gif", "image/gif", id="gif"),
])
def test_upload_unsupported_type(api, content, name, mime):
    """UPL-05: не JPEG/PNG/WebP — 415."""
    assert_error(api.upload(content, name, mime), 415, "only JPEG, PNG and WebP")


def test_upload_broken_image(api):
    """UPL-06: заголовок JPEG, а внутри мусор — 400."""
    assert_error(api.upload(images.BROKEN_JPEG, "broken.jpg"), 400, "not a valid image")


def test_upload_type_detected_by_content_not_extension(api):
    """Подмена расширения: PNG под именем .jpg и с типом image/jpeg.
    Сервис определяет тип по содержимому, а не верит клиенту."""
    r = api.upload(images.sharp(fmt="PNG"), "fake.jpg", "image/jpeg")
    assert r.status_code == 202, r.text
    assert r.json()["content_type"] == "image/png"


def test_upload_wrong_field_name(api):
    """UPL-07: файл в поле photo вместо file — 400."""
    assert_error(api.upload(images.sharp(), field="photo"), 400, '"file"')


def test_upload_json_instead_of_multipart(api):
    """UPL-07: тело JSON вместо multipart — 400."""
    r = api.request("POST", f"{API}/photos", json={"file": "photo.jpg"})
    assert_error(r, 400, "multipart")


# ---------- X-User-ID ----------

@pytest.mark.parametrize("user", [
    pytest.param(None, id="no-header"),
    pytest.param("", id="empty"),
    pytest.param("x" * 65, id="len-65"),
    pytest.param("masha!", id="exclamation"),
    pytest.param("ma sha", id="space"),
    pytest.param("../admin", id="path-traversal"),
])
def test_invalid_user_id_rejected(user):
    """USR-02: заголовок отсутствует, пустой, длиннее 64 или с запрещёнными символами — 400."""
    client = PhotoApi(None)
    headers = {} if user is None else {"X-User-ID": user}
    r = client.request("GET", f"{API}/photos", headers=headers)
    assert_error(r, 400, "X-User-ID")


# ---------- чужие и несуществующие фото ----------

@pytest.mark.parametrize("call", [
    pytest.param(lambda c, pid: c.get_photo(pid), id="get"),
    pytest.param(lambda c, pid: c.get_file(pid), id="file"),
    pytest.param(lambda c, pid: c.get_analysis(pid), id="analysis"),
    pytest.param(lambda c, pid: c.reanalyze(pid), id="reanalyze"),
    pytest.param(lambda c, pid: c.delete(pid), id="delete"),
])
def test_foreign_photo_not_accessible(api, other_api, uploaded_photo, call):
    """GET-02: чужое фото — 404 на любой операции (не 403: не выдаём, что такой id существует)."""
    assert_error(call(other_api, uploaded_photo["id"]), 404, "not found")
    # и владелец по-прежнему видит своё фото — чужой DELETE ничего не удалил
    assert api.get_photo(uploaded_photo["id"]).status_code == 200


@pytest.mark.parametrize("photo_id", [
    pytest.param(MISSING_ID, id="unknown-uuid"),
    pytest.param("not-a-uuid", id="not-uuid"),
    pytest.param("1", id="number"),
])
@pytest.mark.parametrize("call", [
    pytest.param(lambda c, pid: c.get_photo(pid), id="get"),
    pytest.param(lambda c, pid: c.get_file(pid), id="file"),
    pytest.param(lambda c, pid: c.get_analysis(pid), id="analysis"),
    pytest.param(lambda c, pid: c.delete(pid), id="delete"),
])
def test_missing_photo_404(api, call, photo_id):
    """GET-03: несуществующий id и id не в формате UUID — 404."""
    assert_error(call(api, photo_id), 404, "not found")


# ---------- фильтры списка ----------

@pytest.mark.parametrize("params, text", [
    pytest.param({"status": "deleted"}, "unknown status", id="status"),
    pytest.param({"blurry": "maybe"}, "blurry", id="blurry"),
    pytest.param({"bad_shot": "yes"}, "bad_shot", id="bad_shot"),
    pytest.param({"duplicates": "2"}, "duplicates", id="duplicates"),
])
def test_list_invalid_filters(api, params, text):
    """LST-04: неизвестный статус и не true/false в фильтрах — 400."""
    assert_error(api.list_photos(**params), 400, text)


@pytest.mark.xfail(strict=True, reason=(
    "Расхождение с документацией: в OpenAPI limit 1..100 и offset ≥ 0, "
    "а сервис молча подменяет неверные значения (0 → 1, abc → 20, -1 → 0) вместо 400"))
@pytest.mark.parametrize("params", [
    pytest.param({"limit": 0}, id="limit-0"),
    pytest.param({"limit": "abc"}, id="limit-abc"),
    pytest.param({"offset": -1}, id="offset-negative"),
])
def test_list_invalid_pagination(api, params):
    """LST-04: limit/offset вне допустимого диапазона по документации — ожидаем 400."""
    assert_error(api.list_photos(**params), 400)


# ---------- состояния и методы ----------

def test_reanalyze_while_in_queue_conflict(api, uploaded_photo):
    """RAN-02: повторный анализ фото, которое ещё в очереди, — 409.
    Запрос идёт сразу после загрузки: outbox отправляет событие раз в 0,5 с,
    так что фото гарантированно ещё pending или processing."""
    assert_error(api.reanalyze(uploaded_photo["id"]), 409, "already queued")


def test_method_not_allowed(api):
    """PUT на /photos не поддерживается — 405 и список разрешённых методов в Allow."""
    r = api.request("PUT", f"{API}/photos")
    assert r.status_code == 405
    allowed = {m.strip() for m in r.headers.get("Allow", "").split(",")}
    assert {"GET", "POST"} <= allowed
