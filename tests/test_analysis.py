"""Асинхронная обработка: загрузили фото — дождались анализа — проверили результат.
Все тесты ждут worker и analyzer, поэтому помечены slow."""
from datetime import datetime

import pytest

from framework import images
from framework.waiters import wait_for_analysis

pytestmark = pytest.mark.slow


def test_analysis_completes(api):
    """ANL-01: обычное резкое фото проходит путь pending → done, плохим кадром не считается."""
    photo = api.upload_ok(images.sharp(seed=31), "sharp.jpg")
    a = wait_for_analysis(api, photo["id"])

    assert a["photo_id"] == photo["id"]
    assert a["blur"]["is_blurry"] is False
    assert a["exposure"]["is_underexposed"] is False
    assert a["exposure"]["is_overexposed"] is False
    assert a["is_bad_shot"] is False
    assert a["bad_shot_reasons"] == []
    assert a["duplicate"]["has_duplicates"] is False
    assert len(a["duplicate"]["phash"]) == 16          # 64 бита в hex
    assert a["analyzer_version"]
    assert api.get_photo(photo["id"]).json()["status"] == "done"


def test_analysis_not_ready_returns_202(api):
    """ANL-02: сразу после загрузки анализа ещё нет — 202 и фото со статусом."""
    photo = api.upload_ok(images.sharp(seed=32))
    r = api.get_analysis(photo["id"])
    assert r.status_code == 202, r.text
    assert r.json()["status"] in ("pending", "processing")


def test_blurred_photo_detected(api):
    """ANL-03: размытое фото — is_blurry, причина blurry."""
    photo = api.upload_ok(images.blurred(seed=33), "blurred.jpg")
    a = wait_for_analysis(api, photo["id"])
    assert a["blur"]["is_blurry"] is True
    assert a["blur"]["score"] < 50
    assert a["is_bad_shot"] is True
    assert "blurry" in a["bad_shot_reasons"]


def test_dark_photo_detected(api):
    """ANL-04: тёмное (но резкое) фото — is_underexposed, и только эта причина."""
    photo = api.upload_ok(images.dark(seed=34), "dark.jpg")
    a = wait_for_analysis(api, photo["id"])
    assert a["exposure"]["is_underexposed"] is True
    assert a["exposure"]["mean_brightness"] < 40
    assert a["bad_shot_reasons"] == ["underexposed"]


def test_resized_copy_is_duplicate(api):
    """ANL-05: уменьшенная пересжатая копия находится как дубликат, связь видна с обеих сторон."""
    original = api.upload_ok(images.sharp(seed=35), "original.jpg")
    wait_for_analysis(api, original["id"])
    copy = api.upload_ok(images.resized_copy(seed=35), "copy.jpg")
    a = wait_for_analysis(api, copy["id"])

    assert a["duplicate"]["has_duplicates"] is True
    assert a["duplicate"]["duplicate_of"] == [original["id"]]
    b = api.get_analysis(original["id"]).json()
    assert copy["id"] in b["duplicate"]["duplicate_of"]


def test_duplicates_are_per_user(api, other_api):
    """Дубликаты ищутся только среди своих фото: копия у другого пользователя — не дубликат."""
    original = api.upload_ok(images.sharp(seed=35))
    wait_for_analysis(api, original["id"])
    copy = other_api.upload_ok(images.resized_copy(seed=35))
    a = wait_for_analysis(other_api, copy["id"])
    assert a["duplicate"]["has_duplicates"] is False


def test_reanalyze_done_photo(api):
    """RAN-01: повторный анализ готового фото — 202, снова pending, потом done с новым временем."""
    photo = api.upload_ok(images.sharp(seed=36))
    first = wait_for_analysis(api, photo["id"])

    r = api.reanalyze(photo["id"])
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "pending"

    second = wait_for_analysis(api, photo["id"])
    assert datetime.fromisoformat(second["analyzed_at"]) > datetime.fromisoformat(first["analyzed_at"])
    assert second["blur"]["score"] == pytest.approx(first["blur"]["score"])   # то же фото — тот же результат


def test_reanalyze_failed_nothing_to_queue(api, uploaded_photo):
    """RAN-03: у пользователя нет упавших фото — в очередь ничего не ставится."""
    r = api.reanalyze_failed()
    assert r.status_code == 202, r.text
    assert r.json() == {"queued": 0}


def test_list_filters_after_analysis(api):
    """LST-03: фильтры списка по результатам анализа."""
    ids = {}
    for name, content in [("sharp", images.sharp(seed=41)),
                          ("blurred", images.blurred(seed=42)),
                          ("dark", images.dark(seed=43)),
                          ("original", images.sharp(seed=44)),
                          ("copy", images.resized_copy(seed=44))]:
        ids[name] = api.upload_ok(content, f"{name}.jpg")["id"]
    for photo_id in ids.values():
        wait_for_analysis(api, photo_id)

    def listed(**filters) -> set:
        r = api.list_photos(limit=100, **filters)
        assert r.status_code == 200, r.text
        return {p["id"] for p in r.json()["items"]}

    everything = set(ids.values())
    assert listed(status="done") == everything
    assert listed(blurry="true") == {ids["blurred"]}
    assert listed(blurry="false") == everything - {ids["blurred"]}
    assert listed(bad_shot="true") == {ids["blurred"], ids["dark"]}
    assert listed(duplicates="true") == {ids["original"], ids["copy"]}
    assert listed(bad_shot="false", duplicates="false") == {ids["sharp"]}
