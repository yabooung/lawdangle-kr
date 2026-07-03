"""LawClient 단위 테스트 — 행 헬퍼 + HTTP(재시도/HTML 감지), 네트워크 mock."""

from __future__ import annotations

import json

import pytest

from lawdangle.client import (
    LawApiError,
    LawClient,
    _as_rows,
    _exact,
    _latest,
    _looks_like_html,
    _mst_of,
    _norm,
)


# --- 행 헬퍼 ------------------------------------------------------------- #


def test_norm_strips_dots_and_spaces():
    assert _norm("가나 다ㆍ라·마") == "가나다라마"


def test_as_rows_normalizes_dict_and_missing():
    assert _as_rows({"LawSearch": {"law": {"법령명한글": "민법"}}}) == [{"법령명한글": "민법"}]
    assert _as_rows({"LawSearch": {"law": [{"a": 1}]}}) == [{"a": 1}]
    assert _as_rows({"LawSearch": {}}) == []
    assert _as_rows({}) == []


def test_exact_and_latest():
    rows = [
        {"법령명한글": "민법", "시행일자": "20200101"},
        {"법령명한글": "민 법", "시행일자": "20230101"},  # 공백 무시 → 매칭
        {"법령명한글": "상법", "시행일자": "20240101"},
    ]
    assert len(_exact(rows, "민법")) == 2
    assert _latest(rows)["시행일자"] == "20240101"


def test_mst_of_from_field_and_link():
    assert _mst_of({"법령일련번호": 999}) == "999"
    assert _mst_of({"법령상세링크": "/DRF/lawService.do?MST=12345&type=JSON"}) == "12345"
    assert _mst_of({}) is None


# --- HTML 에러페이지 감지 ------------------------------------------------ #


class _Resp:
    def __init__(self, *, json_data=None, text="", ctype="application/json", status=200):
        self._json = json_data
        self.text = text
        self.headers = {"Content-Type": ctype}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(str(self.status_code))

    def json(self):
        if self._json is None:
            raise json.JSONDecodeError("no json", "", 0)
        return self._json


def test_looks_like_html_by_ctype_and_body():
    assert _looks_like_html(_Resp(text="", ctype="text/html; charset=utf-8"))
    assert _looks_like_html(_Resp(text="  <!DOCTYPE html><html>", ctype="text/plain"))
    assert not _looks_like_html(_Resp(text='{"ok":1}', ctype="application/json"))


def test_get_returns_json(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(json_data={"ok": 1}))
    assert LawClient("OC").get("lawSearch", {"target": "law"}) == {"ok": 1}


def test_get_raises_on_html(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: _Resp(text="<html>error</html>", ctype="text/html"),
    )
    with pytest.raises(LawApiError):
        LawClient("OC").get("lawSearch", {"target": "law"}, retries=0)


def test_get_empty_body_is_zero_result(monkeypatch):
    import requests

    # 200 + JSON 아님 + HTML 아님 → 정상 0건으로 빈 dict.
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp(text="", ctype="application/json"))
    assert LawClient("OC").get("lawSearch", {"target": "law"}, retries=0) == {}


def test_get_retries_then_raises(monkeypatch):
    import requests

    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)  # 백오프 스킵
    with pytest.raises(LawApiError):
        LawClient("OC").get("lawSearch", {"target": "law"}, retries=2)
    assert calls["n"] == 3  # 최초 + 재시도 2회
