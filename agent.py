import asyncio
import json
import logging
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from llm import ModelServiceError, create_chat_completion
from tools import calculator, get_current_time
logger = logging.getLogger("uvicorn.error")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式，例如 2 * (3 + 4)",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "需要计算的数学表达式",
                    }
                },
                "required": ["expression"],#必填
                "additionalProperties": False,#不允许额外参数
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]
TOOL_FUNCTIONS = {
    "calculator": calculator,
    "get_current_time": get_current_time,
}


class CalculatorArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: StrictStr


class TimeArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


TOOL_ARGUMENT_MODELS = {
    "calculator": CalculatorArguments,
    "get_current_time": TimeArguments,
}


def execute_tool(tool_name: str, arguments_text: str):
    """模型只提出调用请求；本地代码负责校验、执行，并生成统一结果。"""
    arguments = None
    try:
        if len(arguments_text) > 4096:
            raise ValueError("工具参数太长")
        try:
            arguments = json.loads(arguments_text)
        except (json.JSONDecodeError, RecursionError):
            raise ValueError("工具参数不是合法 JSON") from None
        if not isinstance(arguments, dict):
            raise ValueError("工具参数必须是 JSON 对象")

        tool_function = TOOL_FUNCTIONS.get(tool_name)
        if tool_function is None:
            raise ValueError(f"未知工具：{tool_name}")
        try:
            validated = TOOL_ARGUMENT_MODELS[tool_name].model_validate(arguments)
        except ValidationError:
            raise ValueError("工具参数不符合要求，请检查必填字段、类型及额外字段") from None

        raw_result = tool_function(**validated.model_dump())
        logger.info("工具执行成功：tool=%s", tool_name)
        return {
            "success": True,
            "tool": tool_name,
            "arguments": arguments,
            "result": raw_result,
        }
    except Exception as exc:
        logger.warning("工具执行失败：tool=%s, error_type=%s", tool_name, type(exc).__name__)
        return {
            "success": False,
            "tool": tool_name,
            "arguments": arguments,
            "error": str(exc),
        }


async def run_agent(user_input: str, max_steps: int = 5):
    if type(max_steps) is not int or not 1 <= max_steps <= 10:
        raise ValueError("max_steps 必须是 1 到 10 之间的整数")
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个可靠的助手。"
                "如果用户需要计算，必须调用 calculator 工具。"
                "如果用户询问时间，必须调用 get_current_time 工具。"
                "不要自己猜测工具结果。"
            ),
        },
        {
            "role": "user",
            "content": user_input,
        },
    ]

    logger.info(
        "Agent收到请求：input_length=%d",
        len(user_input),
    )

    for step in range(max_steps):
        logger.info(
            "Agent开始第%d步",
            step + 1,
        )

        response = await create_chat_completion(
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        if not response.choices:
            raise ModelServiceError("模型服务返回了空响应")
        assistant_message = response.choices[0].message

        messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        # 没有工具调用，说明模型已经准备好直接回答
        if not assistant_message.tool_calls:
            if not assistant_message.content or not assistant_message.content.strip():
                raise ModelServiceError("模型服务未返回有效回答")
            logger.info("Agent任务完成：steps=%d", step + 1)
            return assistant_message.content

        if len(assistant_message.tool_calls) > 8:
            raise ModelServiceError("模型单轮请求的工具数量超过上限")

        # 执行模型请求的工具
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name

            tool_result = execute_tool(tool_name, tool_call.function.arguments)

            result_text = json.dumps(
                tool_result,
                ensure_ascii=False,
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_text,
                }
            )

    logger.warning("Agent超过最大执行步骤：max_steps=%d", max_steps)
    return "任务执行步骤超过上限，已停止。"

def main():
    logging.basicConfig(level=logging.INFO)
    question = input("请输入问题：")
    try:
        # async 函数需要由事件循环运行，不能直接把协程对象当作结果。
        print(asyncio.run(run_agent(question)))
    except ModelServiceError as exc:
        print(f"请求失败：{exc.detail}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
