"""Проверки в базе данных (серый ящик) и подготовка тестовых данных через SQL.
Нужен доступ к Postgres сервиса (по умолчанию localhost:5433, переменная DB_DSN)."""
import pytest

from framework import images
from framework.db import Db, phash_hex_to_db
from framework.waiters import wait_for_analysis, wait_until

pytestmark = [pytest.mark.db, pytest.mark.slow]


@pytest.fixture(scope="session")
def db():
    """Одно подключение на весь прогон. Нет доступа к базе — тесты пропускаются, а не падают:
    например, сервис запущен в Kubernetes и Postgres снаружи не виден."""
    try:
        conn = Db()
    except Exception as e:   # noqa: BLE001 — любая ошибка подключения = пропуск
        pytest.skip(f"нет доступа к PostgreSQL ({e.__class__.__name__}): проверки в БД пропущены")
    yield conn
    conn.close()


def test_upload_writes_photo_and_outbox_event(api, user_id, db):
    """DB-01: загрузка = запись в photos + событие в outbox; relay отправляет событие в Kafka."""
    photo = api.upload_ok(images.sharp(seed=61), "db.jpg")

    row = db.one("SELECT user_id, object_key, status, size_bytes FROM photos WHERE id = %s",
                 photo["id"])
    assert row is not None, "фото нет в таблице photos"
    assert row["user_id"] == user_id
    assert row["object_key"] == f"{user_id}/{photo['id']}"
    assert row["size_bytes"] == photo["size_bytes"]
    assert row["status"] in ("pending", "processing", "done")   # worker мог уже взять фото в работу

    event = db.one("""SELECT topic, key, payload FROM outbox
                      WHERE payload->>'photo_id' = %s ORDER BY id LIMIT 1""", photo["id"])
    assert event is not None, "события в outbox нет — фото не попадёт в обработку"
    assert event["topic"] == "photos.uploaded"
    assert event["key"] == user_id                                   # ключ Kafka = пользователь
    assert event["payload"]["object_key"] == row["object_key"]
    assert event["payload"]["bucket"] == "photos"

    wait_until(lambda: db.one("""SELECT 1 FROM outbox WHERE payload->>'photo_id' = %s
                                 AND sent_at IS NOT NULL""", photo["id"]),
               "outbox relay отправит событие в Kafka (sent_at заполнится)")


def test_analysis_saved_to_db(api, db):
    """DB-02: результат анализа в БД совпадает с ответом API, у фото статус done и 1 попытка."""
    photo = api.upload_ok(images.blurred(seed=62))
    a = wait_for_analysis(api, photo["id"])

    p = db.one("SELECT status, attempts, error FROM photos WHERE id = %s", photo["id"])
    assert (p["status"], p["attempts"], p["error"]) == ("done", 1, None)

    row = db.one("SELECT * FROM analysis WHERE photo_id = %s", photo["id"])
    assert row is not None, "результата нет в таблице analysis"
    assert row["is_blurry"] is a["blur"]["is_blurry"] is True
    assert row["blur_score"] == pytest.approx(a["blur"]["score"], abs=0.01)
    assert row["is_bad_shot"] is a["is_bad_shot"]
    assert row["phash"] == phash_hex_to_db(a["duplicate"]["phash"])


def test_duplicate_pair_stored_once(api, db):
    """DB-03: пара дубликатов хранится одной строкой (photo_a < photo_b), расстояние ≤ 6."""
    original = api.upload_ok(images.sharp(seed=63))
    wait_for_analysis(api, original["id"])
    copy = api.upload_ok(images.resized_copy(seed=63))
    wait_for_analysis(api, copy["id"])

    rows = db.all("""SELECT photo_a::text AS a, photo_b::text AS b, distance FROM duplicates
                     WHERE %s IN (photo_a, photo_b)""", copy["id"])
    assert len(rows) == 1, f"ожидали одну строку пары, получили {rows}"
    pair = rows[0]
    assert {pair["a"], pair["b"]} == {original["id"], copy["id"]}
    assert pair["a"] < pair["b"]
    assert pair["distance"] <= 6


def test_delete_cascades(api, db):
    """DB-04: удаление фото удаляет и анализ, и пары дубликатов (ON DELETE CASCADE)."""
    original = api.upload_ok(images.sharp(seed=64))
    wait_for_analysis(api, original["id"])
    copy = api.upload_ok(images.resized_copy(seed=64))
    wait_for_analysis(api, copy["id"])

    assert api.delete(copy["id"]).status_code == 204
    assert db.one("SELECT 1 FROM photos WHERE id = %s", copy["id"]) is None
    assert db.one("SELECT 1 FROM analysis WHERE photo_id = %s", copy["id"]) is None
    assert db.one("SELECT 1 FROM duplicates WHERE %s IN (photo_a, photo_b)", copy["id"]) is None
    # у оригинала после этого дубликатов нет и в API
    assert api.get_analysis(original["id"]).json()["duplicate"]["has_duplicates"] is False


def test_reanalyze_failed_with_sql_prepared_data(api, db):
    """RAN-03 (позитивный): упавшее фото готовим через SQL — через API его не получить.
    reanalyze-failed ставит его в очередь, фото снова анализируется."""
    photo = api.upload_ok(images.sharp(seed=65))
    wait_for_analysis(api, photo["id"])

    # подготовка данных: делаем вид, что анализ упал
    changed = db.execute("""UPDATE photos SET status = 'failed', error = 'autotest: simulated failure',
                            attempts = 3 WHERE id = %s""", photo["id"])
    assert changed == 1
    assert api.get_analysis(photo["id"]).status_code == 202        # API видит failed

    r = api.reanalyze_failed()
    assert r.status_code == 202, r.text
    assert r.json() == {"queued": 1}

    wait_for_analysis(api, photo["id"])
    p = db.one("SELECT status, attempts, error FROM photos WHERE id = %s", photo["id"])
    assert (p["status"], p["attempts"], p["error"]) == ("done", 1, None)
    events = db.one("SELECT count(*) AS n FROM outbox WHERE payload->>'photo_id' = %s", photo["id"])
    assert events["n"] == 2, "ожидали второе событие в outbox после повторной постановки"
