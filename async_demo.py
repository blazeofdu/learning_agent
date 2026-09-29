import asyncio
import time



async def fake_request(name:str,seconds: int):
    print(f"{name},开始")
    await asyncio.sleep(seconds)
    print(f"{name},结束")
    return f"{name},的结果"

async def run_sequentially():
    result_a = await fake_request("任务 A",2)
    result_b = await fake_request("任务 B",3)
    return [result_a,result_b]


async def run_concurrently():
    return await asyncio.gather(
        fake_request("任务 A", 2),
        fake_request("任务 B", 3),
    )


async def main():
    start = time.perf_counter()
    sequential_resuls = await run_sequentially()
    print("顺序结果： ",sequential_resuls)
    print(f"顺序执行耗时:{time.perf_counter() - start:.2f} s")


    print("-" * 30)
    start = time.perf_counter()
    concurrent_results = await run_concurrently()
    print("并发结果：", concurrent_results)
    print(f"并发执行耗时：{time.perf_counter() - start:.2f} 秒")
if __name__ == "__main__":
    asyncio.run(main())