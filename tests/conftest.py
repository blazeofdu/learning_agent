"""pytest 自动读取此文件：不需要在测试文件里 import。

每个测试使用独立临时数据库；任何意外的真实 HTTP 请求都会立即报错。
这些 fixture 参数由 pytest 注入，并不是普通函数调用者手动传参。
"""

import os

# 在收集测试、导入业务模块之前设置，不读取开发者的 .env 和真实密钥。
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["OPENAI_API_KEY"] = "test-placeholder"
os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:9/v1"
os.environ["MODEL"] = "test-model"

import httpx
import pytest
from fastapi.testclient import TestClient

import database
from main import app


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", database_path)
    database.init_db()
    return database_path


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("测试禁止真实网络请求，请模拟模型响应")

    async def async_blocked(*args, **kwargs):
        raise AssertionError("测试禁止真实网络请求，请模拟模型响应")

    # TestClient 使用自己的内存 transport，不受这两个补丁影响。
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)


@pytest.fixture
def client():
    # with 会运行应用 lifespan，yield 后退出 with 并关闭客户端。
    with TestClient(app) as test_client:
        yield test_client
