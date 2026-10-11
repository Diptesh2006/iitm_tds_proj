from fastapi.testclient import TestClient
import main

client = TestClient(main.app)


def test_health_and_success_without_ai(monkeypatch):
    monkeypatch.setattr(main, "analyze_error_with_ai", lambda *_: (_ for _ in ()).throw(AssertionError("AI called")))
    response = client.post("/code-interpreter", json={"code": "print('a')\nprint('b')"})
    assert response.json() == {"error": [], "result": "a\nb\n"}


def test_empty_stdout():
    assert client.post("/code-interpreter", json={"code": "x = 1"}).json() == {"error": [], "result": ""}


def test_runtime_error_line_and_ai_only_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "analyze_error_with_ai", lambda code, tb: calls.append((code, tb)) or [2])
    response = client.post("/code-interpreter", json={"code": "x = 1\nprint(1 / 0)"})
    assert response.json()["error"] == [2]
    assert "ZeroDivisionError" in response.json()["result"]
    assert len(calls) == 1


def test_syntax_error_and_invalid_body():
    response = client.post("/code-interpreter", json={"code": "if True print('x')"})
    assert response.json()["error"] == [1]
    assert "SyntaxError" in response.json()["result"]
    assert client.post("/code-interpreter", json={}).status_code == 422


def test_timeout(monkeypatch):
    monkeypatch.setattr(main, "execute_python_code", lambda _: {"success": False, "output": "Traceback (most recent call last):\nExecutionTimeout: code execution exceeded the time limit\n"})
    monkeypatch.setattr(main, "analyze_error_with_ai", lambda *_: [])
    assert client.post("/code-interpreter", json={"code": "while True: pass"}).json()["error"] == []
