# AI Agent Learning API

个人学习项目：基于 FastAPI 的工具调用聊天 API。模型提出工具调用，本地 Python 校验参数并执行，再把执行结果传给模型生成回答。第一版侧重可运行、可测试和可解释的后端工程流程。

## 已实现与边界

- 异步聊天接口，计算器和时间工具，工具结果按调用 ID 回传。
- 工具参数本地 Pydantic 校验，拒绝未知工具、非对象 JSON、缺少/额外/错误类型参数。
- 默认最多 5 轮模型请求，每轮最多 8 个工具；模型请求设 20 秒超时、最多重试 1 次。SDK 超时不是整条任务的总耗时上限。
- SQLite 成对保存用户消息和回答，事务回滚，历史查询。
- TXT/Markdown 上传预览；文件字节限制、UTF-8 校验。
- 请求耗时日志、模型失败分类、统一服务器错误。
- Docker / Compose、持久化数据卷、健康检查、离线自动化测试。

当前**没有**多轮模型记忆：保存的聊天记录尚未传入下一次模型请求。上传文件仅返回预览，不会存入知识库；尚未实现 RAG、鉴权或公开服务所需的限流。简历分析是独立练习接口，JSON 输出尚未做业务字段级验证。

## 目录

```text
main.py                 HTTP 接口、启动初始化和异常处理
agent.py                工具调用循环、参数校验、命令行入口
tools.py                有边界限制的 AST 计算器、时间工具
llm.py                  模型配置、客户端生命周期和上游错误映射
database.py             SQLite 连接、事务与聊天记录
tests/conftest.py       临时数据库、测试客户端、禁止真实网络请求
tests/                  接口、工具、Agent、数据库、模型边界测试
scripts/smoke_model.py  可选真实模型验收，不写聊天数据库
requirements.txt       服务依赖
requirements-dev.txt   服务依赖 + 测试工具
```

## 本地运行（WSL）

现有虚拟环境可以继续使用；全新环境建议 Python 3.12，与 Docker 一致。

```bash
cd ~/projects/agent-learning/week01
# 只有还没有 .venv 时，才创建：python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

已有 `.env` 不要覆盖。首次配置可以用 `cp -n .env.example .env`，在编辑器里填写：

```dotenv
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=服务商给出的兼容地址
MODEL=你账号可用且支持工具调用的模型名
```

`OPENAI_BASE_URL` 留空时使用 SDK 默认地址。不要复制示例占位文字作为实际配置；不要提交 `.env`。没有密钥也可以启动 `/health`、上传接口和离线测试；调用模型相关接口时返回 503。

```bash
.venv/bin/python -m uvicorn main:app --reload
```

接口文档：<http://127.0.0.1:8000/docs>。已有 Docker 占用 8000 时，本地启动加 `--port 8001`。

命令行运行 Agent：

```bash
.venv/bin/python agent.py
```

## 接口示例

```bash
curl http://127.0.0.1:8000/health

# 保存 Cookie，连续请求关联到同一份聊天记录。
curl -c /tmp/agent-demo-cookies -b /tmp/agent-demo-cookies \
  -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"计算 12 * 8"}'

# 将下面的占位符替换为上一条响应返回的 session_id。
curl http://127.0.0.1:8000/chat/history/返回的session_id

curl -X POST http://127.0.0.1:8000/files/upload -F 'file=@README.md'
```

聊天成功返回 `session_id` 和 `reply`，回答措辞由模型决定。Cookie 只用于关联历史，不代表用户身份；此学习版仅建议在本机演示。

| 场景 | HTTP 状态码 |
| --- | --- |
| 正常请求 | 200 |
| 缺少 message、空白文本、类型或长度错误 | 422 |
| 非法 UTF-8 文件 | 400 |
| 文件字节数超过 1,000,000 | 413 |
| 不支持的文件后缀 | 415 |
| 上游模型请求失败或空响应 | 502 |
| 模型未配置、无法连接、额度/限流错误 | 503 |
| 模型请求超时 | 504 |
| 未预期的内部异常 | 500 |

检查顺序是文件名、后缀、字节大小、UTF-8 解码。如果同时违反多项规则，返回先触发的错误。接口最多读取 1,000,001 字节，但 multipart 解析层可能已接收数据；公开部署还需要网关请求体限制。

## 测试

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest --cov --cov-config=pytest.ini --cov-report=term-missing -q
```

`tests/conftest.py` 由 pytest 自动读取，负责给每个测试准备独立临时数据库。测试里 `client` 参数由该文件中的 fixture 提供，不需要再创建全局客户端。`.env` 和真实模型不参与测试；真实 HTTP 传输会被阻止。

测试实际运行计算器、Agent 循环、API 路由、SQLite 提交/回滚；只有模型响应被模拟。模拟测试不能证明真实模型必然正确选择工具。

可选真实验收（会消耗少量 API 额度，不写入数据库）：

```bash
.venv/bin/python -m scripts.smoke_model --live
```

验收脚本会记录真实计算器的执行结果，并检查模型最终回答。`success: true` 要求真实工具得到 96，且最终回答包含 96；如果服务不可用，会返回非零退出码和不含密钥的错误。

## Docker / Compose

容器使用 Python 3.12；本地旧 `.venv` 不会被自动替换。

```bash
docker compose config -q
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 api
```

已启动服务的无模型 HTTP 验收：

```bash
.venv/bin/python -m scripts.smoke_http --url http://127.0.0.1:8000
```

加 `--live` 会额外验证真实聊天和历史查询，消耗 API 额度并写入一组演示记录。

默认只绑定本机 `127.0.0.1:8000`。可以在 `.env` 设置 `API_PORT=8001` 后重建容器。SQLite 默认位于 `/app/data/agent.db`，挂载到命名卷。修改 `.env` 或代码后执行 `docker compose up --build -d`。

`docker compose down` 会停止并移除容器，但保留命名数据卷；**不要用 `down -v` 清理有用数据**。

`/health` 只表示应用可以响应，不探测模型、额度或数据库健康。Docker 显示 healthy 也不能证明模型调用可用。需要代理时，确保容器也能连接代理；容器中的 `127.0.0.1` 不是宿主机。

### 2026-10-07 代理排查记录

本次验收中，原 `.env` 的代理连接超时；临时清空代理变量后，真实工具调用成功。没有修改 `.env`。如果你的代理已恢复，无需清空；若模型地址可以直连，可用以下命令仅对本次进程禁用代理：

```bash
env HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
  .venv/bin/python -m scripts.smoke_model --live
```

若要默认直连，在 `.env` 中移除或清空 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`（以及小写同名变量），并确认终端没有继承相同代理配置；如果需要代理，则填写可访问的地址。Docker 需要重建容器才能读取变更。不要把 API 连接失败误认为项目没有启动成功。

## 计算器限制

支持 `+ - * / **`、负号和括号，不使用 `eval()` 执行输入。表达式最多 100 字符、64 个 AST 节点、递归深度 12；常量和中间结果的绝对值不超过 `10^12`，指数绝对值不超过 100。拒绝布尔值、复数及无穷值。这是受限算术工具，不是任意代码沙箱。

## 第一版演示顺序

1. 展示 `/docs` 和健康接口。
2. 用聊天接口计算 `12 * 8`，观察工具执行日志与回复。
3. 查询返回的 session_id，展示两条已保存记录。
4. 展示未知工具、除零、模型故障的离线测试。
5. 解释 `llm.py → agent.py → tools.py → 模型回答 → database.py` 的执行流程。

项目定位应写“工具调用聊天 API”，不要声称已实现 RAG、多轮记忆、生产级高并发或真实模型效果评估。

## 本次验收记录

详见 [VERIFICATION.md](VERIFICATION.md)，区分离线测试、真实模型、容器验证及尚未验证的内容。
