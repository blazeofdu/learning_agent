"""显式 --live 才访问真实模型。只提交固定算术题，不读写聊天数据库。"""

import argparse
import asyncio
import json
import logging

import agent
from llm import ModelServiceError


async def verify():
    observed = []
    real_calculator = agent.TOOL_FUNCTIONS["calculator"]

    def spy_calculator(expression):
        result = real_calculator(expression)
        observed.append({"expression": expression, "result": result})
        return result

    agent.TOOL_FUNCTIONS["calculator"] = spy_calculator
    try:
        # 模型响应没有被模拟，spy 仍调用真实计算器。
        reply = await agent.run_agent("请使用 calculator 计算 12 * 8，并用一句话给出结果。", max_steps=3)
    finally:
        agent.TOOL_FUNCTIONS["calculator"] = real_calculator

    success = any(call["result"] == 96 for call in observed) and "96" in reply
    print(json.dumps({"success": success, "tool_calls": observed, "reply": reply}, ensure_ascii=False))
    return success


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="允许少量真实模型调用，可能消耗 API 额度")
    args = parser.parse_args()
    if not args.live:
        parser.error("请显式传入 --live；自动测试不会运行此检查")
    logging.basicConfig(level=logging.WARNING)
    try:
        success = asyncio.run(verify())
    except ModelServiceError as exc:
        print(json.dumps({"success": False, "status": exc.status_code, "detail": exc.detail}, ensure_ascii=False))
        raise SystemExit(1) from None
    except Exception as exc:
        # 不打印上游请求对象，避免把配置和认证信息写到终端。
        print(json.dumps({"success": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
