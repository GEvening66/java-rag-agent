"""API 冒烟测试：只测不需要 LLM 调用的接口（/ 与 /health）。

运行：python -m pytest tests -q
"""
from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


def test_root_lists_endpoints():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["docs"] == "/docs"
    assert {"rag", "tool", "qa"} == set(body["modes"])


def test_health_returns_index_and_config():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["chunks"] > 0                     # 索引已加载（磁盘缓存）
    assert body["top_k"] >= 1 and body["recall_k"] >= body["top_k"]
    assert isinstance(body["hybrid"], bool) and isinstance(body["rerank"], bool)


def test_ask_request_validation_rejects_bad_input():
    # 问题超长 / mode 非法 → 422（Pydantic 校验），不进 agent
    assert client.post("/ask", json={"question": "x" * 5000}).status_code == 422
    assert client.post("/ask", json={"question": "ok?", "mode": "unknown"}).status_code == 422
    assert client.post("/ask", json={}).status_code == 422


def test_ui_page_served_and_wired_to_api():
    r = client.get("/ui")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # 页面必须真的调用这些接口，且用的是 textContent（防模型回答里的 HTML 被执行）
    assert "fetch('/ask'" in r.text
    assert "fetch('/health')" in r.text
    assert "textContent" in r.text and "innerHTML" not in r.text
