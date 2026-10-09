import asyncio
import json
from types import SimpleNamespace
import pytest

import agent


class FakeMessage:
    """
    模拟 OpenAI 返回的 message 对象。
    """

    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        result = {
            "role": "assistant",
            "content": self.content,
        }

        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ]

        return result


class FakeResponse:
    """
    模拟 OpenAI 返回的 response 对象。
    """

    def __init__(self, message):
        self.choices = [
            SimpleNamespace(message=message)
        ]


def make_tool_call(
    name,
    arguments,
    call_id="call_test",
):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


def get_tool_messages(messages):
    return [
        message
        for message in messages
        if message.get("role") == "tool"
    ]


def test_agent_executes_calculator(monkeypatch):
    """
    测试正常的工具调用流程：

    第一次模型请求工具
    → Python执行calculator
    → 第二次模型返回最终答案
    """

    tool_call = make_tool_call(
        name="calculator",
        arguments='{"expression": "2 + 3"}',
        call_id="call_calculator",
    )

    called_expressions = []

    real_calculator = agent.TOOL_FUNCTIONS["calculator"]

    def spy_calculator(expression):
        called_expressions.append(expression)
        return real_calculator(expression)

    monkeypatch.setitem(
        agent.TOOL_FUNCTIONS,
        "calculator",
        spy_calculator,
    )

    calls = []

    async def fake_create(**kwargs):
        messages_snapshot = list(kwargs["messages"])
        calls.append(messages_snapshot)

        if len(calls) == 1:
            return FakeResponse(
                FakeMessage(
                    content=None,
                    tool_calls=[tool_call],
                )
            )

        tool_messages = get_tool_messages(
            messages_snapshot
        )

        return FakeResponse(
            FakeMessage(
                content="模型收到了计算结果",
                tool_calls=None,
            )
        )

    monkeypatch.setattr(
        agent,
        "create_chat_completion",
        fake_create,
    )

    result = asyncio.run(
        agent.run_agent("计算 2 + 3")
    )

    assert result == "模型收到了计算结果"
    assert called_expressions == ["2 + 3"]
    assert len(calls) == 2

    second_tool_messages = get_tool_messages(
        calls[1]
    )

    assert len(second_tool_messages) == 1
    assert '"success": true' in (
        second_tool_messages[0]["content"]
    )
    assert '"result": 5' in (
        second_tool_messages[0]["content"]
    )


def test_agent_stops_after_max_steps(monkeypatch):
    """
    测试模型一直请求工具时，Agent能够停止。
    """

    tool_call = make_tool_call(
        name="calculator",
        arguments='{"expression": "1 + 1"}',
        call_id="call_loop",
    )

    calls = []

    async def fake_create(**kwargs):
        calls.append(
            list(kwargs["messages"])
        )

        return FakeResponse(
            FakeMessage(
                content=None,
                tool_calls=[tool_call],
            )
        )

    monkeypatch.setattr(
        agent,
        "create_chat_completion",
        fake_create,
    )

    result = asyncio.run(
        agent.run_agent(
            "不断计算",
            max_steps=2,
        )
    )

    assert result == (
        "任务执行步骤超过上限，已停止。"
    )
    assert len(calls) == 2


def test_agent_handles_unknown_tool(monkeypatch):
    """
    测试模型请求不存在的工具时，Agent不会崩溃。
    """

    unknown_tool_call = make_tool_call(
        name="not_exists",
        arguments="{}",
        call_id="call_unknown",
    )

    calls = []

    async def fake_create(**kwargs):
        messages_snapshot = list(kwargs["messages"])
        calls.append(messages_snapshot)

        if len(calls) == 1:
            return FakeResponse(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        unknown_tool_call
                    ],
                )
            )

        return FakeResponse(
            FakeMessage(
                content="模型收到了未知工具错误",
                tool_calls=None,
            )
        )

    monkeypatch.setattr(
        agent,
        "create_chat_completion",
        fake_create,
    )

    result = asyncio.run(
        agent.run_agent(
            "调用不存在的工具"
        )
    )

    assert result == (
        "模型收到了未知工具错误"
    )

    tool_messages = get_tool_messages(
        calls[1]
    )

    assert len(tool_messages) == 1

    tool_content = tool_messages[0]["content"]

    assert tool_messages[0]["role"] == "tool"
    assert '"success": false' in tool_content
    assert '"tool": "not_exists"' in tool_content
    assert "未知工具" in tool_content


def test_agent_handles_invalid_tool_arguments(
    monkeypatch,
):
    """
    测试工具参数不是合法JSON时，Agent不会崩溃。
    """

    invalid_tool_call = make_tool_call(
        name="calculator",
        arguments="this is not json",
        call_id="call_invalid_json",
    )

    calls = []

    async def fake_create(**kwargs):
        messages_snapshot = list(kwargs["messages"])
        calls.append(messages_snapshot)

        if len(calls) == 1:
            return FakeResponse(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        invalid_tool_call
                    ],
                )
            )

        return FakeResponse(
            FakeMessage(
                content="模型收到了参数错误",
                tool_calls=None,
            )
        )

    monkeypatch.setattr(
        agent,
        "create_chat_completion",
        fake_create,
    )

    result = asyncio.run(
        agent.run_agent(
            "使用错误参数调用计算器"
        )
    )

    assert result == (
        "模型收到了参数错误"
    )

    tool_messages = get_tool_messages(
        calls[1]
    )

    assert len(tool_messages) == 1
    error = json.loads(tool_messages[0]["content"])
    assert error["success"] is False
    assert error["error"] == "工具参数不是合法 JSON"


def test_agent_handles_tool_execution_error(
    monkeypatch,
):
    """
    测试JSON合法，但工具执行失败。

    1 / 0 是合法参数格式，
    但计算器执行时会发生除零错误。
    """

    failing_tool_call = make_tool_call(
        name="calculator",
        arguments='{"expression": "1 / 0"}',
        call_id="call_divide_by_zero",
    )

    called_expressions = []

    real_calculator = agent.TOOL_FUNCTIONS["calculator"]

    def spy_calculator(expression):
        called_expressions.append(expression)
        return real_calculator(expression)

    monkeypatch.setitem(
        agent.TOOL_FUNCTIONS,
        "calculator",
        spy_calculator,
    )

    calls = []

    async def fake_create(**kwargs):
        messages_snapshot = list(kwargs["messages"])
        calls.append(messages_snapshot)

        if len(calls) == 1:
            return FakeResponse(
                FakeMessage(
                    content=None,
                    tool_calls=[
                        failing_tool_call
                    ],
                )
            )

        tool_messages = get_tool_messages(
            messages_snapshot
        )

        tool_content = tool_messages[0][
            "content"
        ]

        return FakeResponse(
            FakeMessage(
                content=tool_content,
                tool_calls=None,
            )
        )

    monkeypatch.setattr(
        agent,
        "create_chat_completion",
        fake_create,
    )

    result = asyncio.run(
        agent.run_agent("计算 1 / 0")
    )

    assert "division by zero" in result
    assert called_expressions == ["1 / 0"]

    tool_messages = get_tool_messages(
        calls[1]
    )

    assert len(tool_messages) == 1

    tool_content = tool_messages[0][
        "content"
    ]

    assert '"success": false' in tool_content
    assert '"tool": "calculator"' in tool_content
    assert "division by zero" in tool_content


@pytest.mark.parametrize("arguments", [
    "[]", "null", "123", '"text"', "{}", '{"expression": 123}',
    '{"expression": "1 + 1", "extra": true}',
])
def test_invalid_arguments_never_execute_tool(monkeypatch, arguments):
    def must_not_run(**kwargs):
        pytest.fail("参数校验失败时不应该执行工具")

    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "calculator", must_not_run)
    result = agent.execute_tool("calculator", arguments)
    assert result["success"] is False
    assert result["tool"] == "calculator"
    assert result["error"]


def test_multiple_tool_results_match_call_ids(monkeypatch):
    calls = []

    async def fake_create(**kwargs):
        calls.append(list(kwargs["messages"]))
        if len(calls) == 1:
            return FakeResponse(FakeMessage(None, [
                make_tool_call("calculator", '{"expression": "2+3"}', "call-a"),
                make_tool_call("calculator", '{"expression": "4*5"}', "call-b"),
            ]))
        return FakeResponse(FakeMessage("完成", None))

    monkeypatch.setattr(agent, "create_chat_completion", fake_create)
    assert asyncio.run(agent.run_agent("分别计算")) == "完成"
    messages = get_tool_messages(calls[1])
    assert [(m["tool_call_id"], json.loads(m["content"])["result"]) for m in messages] == [
        ("call-a", 5), ("call-b", 20),
    ]


@pytest.mark.parametrize("content", [None, "", "  "])
def test_empty_final_answer_is_an_error(monkeypatch, content):
    async def fake_create(**kwargs):
        return FakeResponse(FakeMessage(content, None))

    monkeypatch.setattr(agent, "create_chat_completion", fake_create)
    with pytest.raises(agent.ModelServiceError, match="有效回答"):
        asyncio.run(agent.run_agent("你好"))


def test_empty_choices_is_an_error(monkeypatch):
    async def fake_create(**kwargs):
        return SimpleNamespace(choices=[])

    monkeypatch.setattr(agent, "create_chat_completion", fake_create)
    with pytest.raises(agent.ModelServiceError, match="空响应"):
        asyncio.run(agent.run_agent("你好"))


def test_cli_actually_runs_coroutine(monkeypatch, capsys):
    received = []

    async def fake_agent(question):
        received.append(question)
        return "14"

    monkeypatch.setattr("builtins.input", lambda prompt: "计算 2*(3+4)")
    monkeypatch.setattr(agent, "run_agent", fake_agent)
    agent.main()
    assert received == ["计算 2*(3+4)"]
    assert capsys.readouterr().out.strip() == "14"


def test_tool_call_count_is_bounded(monkeypatch):
    async def fake_create(**kwargs):
        return FakeResponse(FakeMessage(None, [
            make_tool_call("calculator", '{"expression": "1+1"}', str(i))
            for i in range(9)
        ]))

    monkeypatch.setattr(agent, "create_chat_completion", fake_create)
    with pytest.raises(agent.ModelServiceError, match="数量超过上限"):
        asyncio.run(agent.run_agent("计算"))
