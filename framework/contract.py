"""Контрактные проверки: ответ сервиса сверяется со схемой из его же документации (OpenAPI).

OpenAPI 3.0 описывает тела ответов почти на языке JSON Schema, но с отличиями.
Здесь схема приводится к обычной JSON Schema, чтобы её проверила библиотека jsonschema:
  * $ref («смотри схему там-то») подставляются на место;
  * allOf из нескольких объектов склеивается в один объект;
  * nullable: true превращается в «эта схема ИЛИ null»;
  * в объектах запрещаются поля, которых нет в документации (additionalProperties: false) —
    иначе сервис мог бы отдавать незадокументированные поля, а тесты бы молчали.
"""
from __future__ import annotations

import copy

import jsonschema
import requests
import yaml


class Contract:
    def __init__(self, spec: dict):
        self.spec = spec

    @classmethod
    def from_service(cls, api) -> "Contract":
        """Берём документацию у самого сервиса — проверяем то, что он реально обещает."""
        r = api.openapi()
        assert r.status_code == 200, f"/openapi.yaml недоступен: {r.status_code}"
        return cls(yaml.safe_load(r.text))

    # ---------- схема ответа ----------
    def response_schema(self, method: str, path: str, status: int,
                        content_type: str = "application/json") -> dict | None:
        """Схема тела для ответа `status` на `method path` (path — как в документации: /photos/{id}).
        None — документация обещает ответ без тела."""
        ops = self.spec["paths"].get(path)
        assert ops is not None, f"в документации нет пути {path}"
        op = ops.get(method.lower())
        assert op is not None, f"в документации нет операции {method} {path}"
        response = op["responses"].get(str(status))
        assert response is not None, (
            f"ответ {status} на {method} {path} не задокументирован "
            f"(есть: {', '.join(op['responses'])})")
        response = self._resolve(response)
        content = response.get("content")
        if not content:
            return None
        assert content_type in content, f"{method} {path} {status}: нет описания для {content_type}"
        return self._prepare(content[content_type]["schema"])

    def check(self, r: requests.Response, method: str, path: str) -> None:
        """Проверяет код ответа (задокументирован ли) и тело (совпадает ли со схемой)."""
        schema = self.response_schema(method, path, r.status_code)
        if schema is None:
            assert r.content == b"", f"{method} {path} {r.status_code}: тела быть не должно, а пришло {r.text[:200]}"
            return
        try:
            jsonschema.validate(r.json(), schema)
        except jsonschema.ValidationError as e:
            where = "/".join(str(p) for p in e.absolute_path) or "(корень)"
            raise AssertionError(
                f"{method} {path} {r.status_code}: ответ не совпадает с документацией\n"
                f"  поле: {where}\n  проблема: {e.message}") from None

    # ---------- приведение OpenAPI → JSON Schema ----------
    def _resolve(self, node: dict) -> dict:
        while "$ref" in node:
            target = self.spec
            for part in node["$ref"].lstrip("#/").split("/"):
                target = target[part]
            rest = {k: v for k, v in node.items() if k != "$ref"}
            node = {**copy.deepcopy(target), **rest}
        return node

    def _prepare(self, node):
        if isinstance(node, list):
            return [self._prepare(x) for x in node]
        if not isinstance(node, dict):
            return node
        node = self._resolve(node)
        node = {k: self._prepare(v) for k, v in node.items()}

        if "allOf" in node:
            merged = {"type": "object", "properties": {}, "required": []}
            for part in node.pop("allOf"):
                merged["properties"].update(part.get("properties", {}))
                merged["required"] += part.get("required", [])
            node = {**merged, **node}

        if node.get("type") == "object" and "properties" in node:
            node.setdefault("additionalProperties", False)

        if node.pop("nullable", False):
            node = {"anyOf": [node, {"type": "null"}]}
        return node
