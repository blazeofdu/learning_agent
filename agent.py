import json
import os
import time
from dotenv import load_dotenv
from openai import AsyncOpenAI
from tools import calculator, get_current_time


load_dotenv()


client_config = {
    "api_key": os.getenv("OPENAI_API_KEY"),
}

base_url = os.getenv("OPENAI_BASE_URL")

if base_url:
    client_config["base_url"] = base_url

client = AsyncOpenAI(**client_config)

MODEL = os.getenv("MODEL")


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
            },
        },
    },
]
TOOL_FUNCTIONS = {
    "calculator": calculator,
    "get_current_time": get_current_time,
}

async def run_agent(user_input: str, max_steps: int = 5):
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个可靠的助手。"
                "如果用户需要计算，必须调用 calculator 工具。"
                "如果用户询问时间，必须调用 get_current_time 工具。"
                "工具只能加减乘除，出现其他运算符你先计算出不支持的结果"
                "不要自己猜测工具结果。"
            ),
        },
        {
            "role": "user",
            "content": user_input,
        },
    ]

    print("\n[Agent] 收到用户问题：", user_input)

    for step in range(max_steps):
        print(f"\n[Agent] 开始第 {step + 1} 步")

        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        assistant_message = response.choices[0].message

        messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        print(
            "[Agent] 模型工具调用：",
            assistant_message.tool_calls,
        )

        # 没有工具调用，说明模型已经准备好直接回答
        if not assistant_message.tool_calls:
            print("[Agent] 任务完成")
            return assistant_message.content

        # 执行模型请求的工具
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name

            try:
                arguments = json.loads(
                    tool_call.function.arguments
                )
            except json.JSONDecodeError:
                result = "工具参数不是合法 JSON"
                arguments = {}

                print("[Agent] 参数解析失败")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

                continue

            print("[Agent] 准备调用工具：", tool_name)
            print("[Agent] 工具参数：", arguments)

            tool_function = TOOL_FUNCTIONS.get(tool_name)

            tool_function = TOOL_FUNCTIONS.get(tool_name)

            if tool_function is None:
                tool_result = {
                    "success": False,
                    "tool": tool_name,
                    "arguments": arguments,
                    "error": f"未知工具：{tool_name}",
                }
            else:
                try:
                    raw_result = tool_function(**arguments)

                    tool_result = {
                        "success": True,
                        "tool": tool_name,
                        "arguments": arguments,
                        "result": raw_result,
                    }
                except Exception as exc: #执行失败
                    tool_result = {
                        "success": False,
                        "tool": tool_name,
                        "arguments": arguments,
                        "error": str(exc),
                    }

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

    print("[Agent] 超过最大执行步骤")
    return "任务执行步骤超过上限，已停止。"

if __name__ == "__main__":
    question = input("请输入问题：")
    answer = run_agent(question)
    print(answer)