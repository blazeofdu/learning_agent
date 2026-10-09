from fastapi.testclient import TestClient
#TestClient是 FastAPI 提供的测试客户端，可以在不启动真正服务器的情况下，模拟发送 HTTP 请求。
from main import app #main.py 中导入 FastAPI 应用对象，例如：
import pytest
import json
from types import SimpleNamespace
import database
from llm import ModelServiceError


# client 由 conftest.py 中的 fixture 提供，每个测试获得独立客户端。


def test_root(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == (
        "AI Agent Learning API is running"
    )


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok"
    }


def test_chat_requires_message(client, monkeypatch):
    async def must_not_run(*args):
        pytest.fail("缺少 message 时不应该调用 Agent")

    monkeypatch.setattr("main.run_agent", must_not_run)
    response = client.post(
        "/chat",
        json={},
    )

    assert response.status_code == 422
    #请求格式正确，但是缺少必要参数或参数验证失败。
    assert "detail" in response.json()
    assert response.json()["detail"][0]["loc"] == ["body", "message"]


def test_upload_rejects_unsupported_file(client):
    response = client.post(
        "/files/upload",
        files={
            "file": (
                # 文件名,
                # 文件内容,
                # 文件类型,
                "test.exe",
                b"not an allowed file",
                "application/octet-stream", #文件的 MIME 类型，表示普通二进制文件。
            )
        },
    )

    assert response.status_code == 415 #不支持的媒体类型或文件类型。
    assert response.json()["detail"] == (
        "目前只支持 TXT 和 Markdown 文件"
    )


def test_upload_txt_file(client):
    response = client.post(
        "/files/upload",
        files={
            "file": (
                "note.txt",
                "你好，Agent".encode("utf-8"),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["filename"] == "note.txt"
    assert result["text_length"] == 8
    assert result["preview"] == "你好，Agent"


def test_upload_rejects_large_file(client):
    large_content = b"a" * 1_000_001

    response = client.post(
        "/files/upload",
        files={
            "file": (
                "large.txt",
                large_content,
                "text/plain",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == (
        "文件不能超过 1 MB"
    )

def test_history_for_unknown_session(client):
    response = client.get(
        "/chat/history/not-existing"
    )
    #不存在的会话历史

    assert response.status_code == 200 # 依然能够成功

    result = response.json()

    assert result["message_count"] == 0
    assert result["messages"] == []

def test_chat_with_mocked_agents(client, monkeypatch): # 模型是假响应，接口和数据库实际执行。
    async def fake_run_agent(user_input):
        assert user_input == "你好"
        return "这是模型的回答"

    monkeypatch.setattr( #函数替换 把 main.py 中的 run_agent 临时替换成 fake_run_agent。
        "main.run_agent",
        fake_run_agent,
    )

    response = client.post(
    "/chat",
        json= {"message" : "你好"},
    )

    assert response.status_code == 200

    assert response.json()["reply"]  == ("这是模型的回答")
    session_id = response.json()["session_id"]
    history = client.get(f"/chat/history/{session_id}").json()
    assert history["message_count"] == 2
    assert [(row["role"], row["content"]) for row in history["messages"]] == [
        ("user", "你好"), ("assistant", "这是模型的回答")
    ]


@pytest.mark.parametrize("message", ["", "  ", "a" * 10_001, 123, None])
def test_chat_rejects_invalid_message(client, message):
    assert client.post("/chat", json={"message": message}).status_code == 422


def test_upload_rejects_invalid_utf8(client):
    response = client.post("/files/upload", files={"file": ("bad.txt", b"\xff\xfe", "text/plain")})
    assert response.status_code == 400
    assert response.json()["detail"] == "文件必须使用 UTF-8 编码"


def test_upload_accepts_exact_size_limit(client):
    response = client.post("/files/upload", files={"file": ("max.txt", b"a" * 1_000_000)})
    assert response.status_code == 200
    assert response.json()["text_length"] == 1_000_000
    assert len(response.json()["preview"]) == 500


@pytest.mark.parametrize("status", [502, 503, 504])
def test_chat_model_failure_does_not_save_messages(client, monkeypatch, status):
    async def failing_agent(*args):
        raise ModelServiceError("模型暂不可用", status)

    monkeypatch.setattr("main.run_agent", failing_agent)
    response = client.post("/chat", json={"message": "你好"})
    assert response.status_code == status
    assert response.json() == {"detail": "模型暂不可用"}
    with database.get_connection() as connection:
        assert connection.execute("SELECT count(*) FROM chat_messages").fetchone()[0] == 0


def test_unexpected_error_is_not_leaked(monkeypatch):
    async def broken_agent(*args):
        raise RuntimeError("private-test-secret")

    monkeypatch.setattr("main.run_agent", broken_agent)
    # 默认 TestClient 会把服务器异常重新抛到测试里；这里测试实际 HTTP 500 响应。
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post("/chat", json={"message": "你好"})
    assert response.status_code == 500
    assert response.json() == {"detail": "服务器内部错误，请稍后重试"}
    assert "private-test-secret" not in response.text


def test_chat_full_tool_loop_and_history(client, monkeypatch):
    from openai.types.chat import ChatCompletionMessage
    import agent

    calls = []

    async def fake_model(**kwargs):
        calls.append(list(kwargs["messages"]))
        if len(calls) == 1:
            message = ChatCompletionMessage(role="assistant", content=None, tool_calls=[{
                "id": "call-http-test", "type": "function",
                "function": {"name": "calculator", "arguments": '{"expression":"12*8"}'},
            }])
        else:
            tool_result = json.loads(kwargs["messages"][-1]["content"])
            message = ChatCompletionMessage(role="assistant", content=str(tool_result["result"]))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    # 仅替换模型边界，真实 API → Agent → 计算器 → SQLite 都会执行。
    monkeypatch.setattr(agent, "create_chat_completion", fake_model)
    response = client.post("/chat", json={"message": "计算 12 * 8"})
    assert response.status_code == 200
    assert response.json()["reply"] == "96"
    assert len(calls) == 2
    assert calls[1][-1]["tool_call_id"] == "call-http-test"
    assert json.loads(calls[1][-1]["content"])["success"] is True
    session_id = response.json()["session_id"]
    history = client.get(f"/chat/history/{session_id}").json()
    assert [row["content"] for row in history["messages"]] == ["计算 12 * 8", "96"]


@pytest.mark.parametrize("content, expected", [
    ('{"skills":["Python"],"has_competition_experience":false,"summary":"测试"}',
     {"skills": ["Python"], "has_competition_experience": False, "summary": "测试"}),
    ("not-json", {"skills": [], "has_competition_experience": False, "summary": "not-json"}),
])
def test_resume_response_and_fallback(client, monkeypatch, content, expected):
    def fake_model(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr("main.create_sync_chat_completion", fake_model)
    response = client.post("/resume/analyze", json={"resume": "学习 Python"})
    assert response.status_code == 200
    assert response.json() == expected


def test_resume_empty_response(client, monkeypatch):
    monkeypatch.setattr("main.create_sync_chat_completion", lambda **kwargs: SimpleNamespace(choices=[]))
    assert client.post("/resume/analyze", json={"resume": "测试"}).status_code == 502
