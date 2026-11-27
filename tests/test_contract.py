"""Контрактные тесты: каждый ответ сервиса совпадает с его документацией OpenAPI —
код ответа задокументирован, обязательные поля есть, типы и значения верные, лишних полей нет."""
import pytest

from framework import images
from framework.api_client import PhotoApi
from framework.contract import Contract
from framework.waiters import wait_for_analysis

MISSING_ID = "00000000-0000-4000-8000-000000000000"


@pytest.fixture(scope="session")
def contract() -> Contract:
    """Документация загружается один раз на весь прогон."""
    return Contract.from_service(PhotoApi(None))


def test_contract_system(contract, anon):
    """CTR-01: служебные эндпоинты."""
    contract.check(anon.healthz(), "GET", "/healthz")
    contract.check(anon.readyz(), "GET", "/readyz")


def test_contract_upload(contract, api):
    """CTR-01: загрузка — успех и ошибки."""
    contract.check(api.upload(images.sharp(seed=51)), "POST", "/photos")                     # 202
    contract.check(api.upload(b"", "empty.jpg"), "POST", "/photos")                          # 400
    contract.check(api.upload(images.TEXT, "notes.txt", "text/plain"), "POST", "/photos")    # 415


def test_contract_photo_lifecycle(contract, api, uploaded_photo):
    """CTR-01: операции с фото, пока анализ не готов, и удаление."""
    pid = uploaded_photo["id"]
    contract.check(api.get_photo(pid), "GET", "/photos/{id}")                         # 200
    contract.check(api.get_photo(MISSING_ID), "GET", "/photos/{id}")                  # 404
    contract.check(api.get_analysis(pid), "GET", "/photos/{id}/analysis")             # 202
    contract.check(api.reanalyze(pid), "POST", "/photos/{id}/reanalyze")              # 409
    contract.check(api.reanalyze_failed(), "POST", "/photos/reanalyze-failed")        # 202
    contract.check(api.list_photos(), "GET", "/photos")                               # 200, analysis: null
    contract.check(api.list_photos(status="nope"), "GET", "/photos")                  # 400
    contract.check(api.delete(pid), "DELETE", "/photos/{id}")                         # 204
    contract.check(api.delete(pid), "DELETE", "/photos/{id}")                         # 404


@pytest.mark.slow
def test_contract_analysis(contract, api):
    """CTR-01: ответы с готовым анализом — в том числе с дубликатами."""
    original = api.upload_ok(images.sharp(seed=52))
    wait_for_analysis(api, original["id"])
    copy = api.upload_ok(images.resized_copy(seed=52))
    wait_for_analysis(api, copy["id"])

    contract.check(api.get_analysis(copy["id"]), "GET", "/photos/{id}/analysis")      # 200 + duplicate_of
    contract.check(api.list_photos(), "GET", "/photos")                               # 200, analysis заполнен
    contract.check(api.reanalyze(copy["id"]), "POST", "/photos/{id}/reanalyze")       # 202
