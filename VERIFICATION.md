# 第一版验收记录

日期：2026-10-07（北京时间）。结果仅代表本次环境和输入，不代表所有模型请求都成功。

| 检查 | 实际结果 |
| --- | --- |
| WSL 现有 Python 3.9.25 虚拟环境 | 88 项测试通过 |
| 干净 Python 3.12.15 容器，安装声明的开发依赖 | 88 项测试通过；1 条第三方 anyio 弃用提示 |
| 核心模块行和分支综合覆盖率 | 94%；database 100%、main 95%、agent 91%、tools 91%、llm 98% |
| Compose 配置解析 | `docker compose config -q` 通过 |
| Python 3.12 服务镜像构建 | 通过，镜像标签 `agent-learning-api:verified` |
| 服务依赖一致性 | 容器 `python -m pip check` 通过 |
| 临时容器启动与健康检查 | healthy |
| 真实 HTTP 检查 | 健康 200、缺字段 422、上传成功 200、后缀 415、编码 400、大小 413 全部通过 |
| WSL 真实模型 + 真实计算器 | 临时禁用失效代理后通过，实际表达式 `12 * 8`，工具结果 `96`，回答 `12 × 8 = 96。` |
| Docker 真实聊天 HTTP + 数据库 | 临时禁用失效代理后通过；日志显示 calculator 实际执行、2 轮模型请求、聊天 200、历史查询 200，两条记录正确 |

## 测试覆盖的关键行为

- HTTP 接口到真实 Agent 循环、真实计算器、真实 SQLite 的离线集成测试；仅模型响应被替换。
- 未知工具、错误 JSON、非对象 JSON、缺字段、额外字段、错误字段类型。
- 工具报错、最大步骤、单轮工具数量上限、空模型响应。
- 计算器拒绝布尔值、复数、非有限值、超限数值、深度和复杂度；巨大指数在幂函数执行前被拒绝。
- SQLite 两条消息在一个事务内提交；第二条失败时，第一条也回滚；连接关闭与会话隔离。
- API 请求校验、UTF-8 和大小边界、模型失败不保存聊天记录、500 不向客户端泄露内部异常。
- SDK 超时、连接失败、限流、认证失败映射为 504/503/502，错误消息不包含上游敏感信息。
- 命令行入口真实运行协程，而不是打印协程对象。

`tests/conftest.py` 禁止真实 HTTP transport，测试不会使用开发者 `.env`。每项测试都使用独立临时 SQLite 文件。真实模型验收脚本需要显式 `--live`，不属于 pytest 测试集。

## 环境问题：代理

原环境的代理连接超时，WSL 和 Docker 的真实模型调用均返回 504。模型地址直连检查成功；在只对验收进程/临时容器清空代理变量后，真实调用成功。

没有修改开发者 `.env`，没有切换模型、密钥或服务地址。沿用原代理启动服务仍可能超时。需要恢复代理，或确认可直连后按 README 清空代理配置。

## 保留的边界

- 现有 8000 端口上的旧容器没有自动升级。应用最新源码需运行 `docker compose up --build -d`。
- 本次没有向原数据库或原 Docker 数据卷写入测试聊天，没有清理历史记录。
- 验收临时容器及其演示记录在验收结束后清理，镜像保留以供复验。
- 未做并发压测、长期可用性评估、公开网络部署、鉴权、多轮记忆或 RAG。
- 未实测删除再创建原有 Compose 容器的数据持久性；已有命名卷配置保留。
- 简历分析仍是练习功能：只验证 JSON 解析及回退行为，不保证输出符合业务 schema。
- 未提交或推送 Git；已有用户改动保留。

## 复验命令

```bash
cd ~/projects/agent-learning/week01
.venv/bin/python -m pytest --cov --cov-config=pytest.ini --cov-report=term-missing -q
docker compose config -q
# 需要更新实际运行服务时：
docker compose up --build -d
.venv/bin/python -m scripts.smoke_http
# 以下命令会访问真实模型，可能消耗额度：
.venv/bin/python -m scripts.smoke_model --live
# 以下命令还会向当前服务数据库写入一组演示记录：
.venv/bin/python -m scripts.smoke_http --live
```
