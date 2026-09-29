import asyncio
import time

import httpx
from fastapi import responses


async def send_request(
    client : httpx.AsyncClient,
    number: int
):
    responses = await client.get(f"http://127.0.0.1:8000/async_test")

    print(f"{number},responses: {responses.json()}")


async def main():
    start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            send_request(client,1),
            send_request(client,2),
        )
    esapsed = time.perf_counter() - start
    print(f"总耗时：{esapsed:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())

