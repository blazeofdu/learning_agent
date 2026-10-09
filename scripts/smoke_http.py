"""检查真实 HTTP 服务；只有 --live 才调用模型并保存一组演示聊天记录。"""

import argparse

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--live", action="store_true", help="增加真实聊天和历史查询，会消耗额度并写入数据库")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=10, trust_env=False) as client:
        response = client.get("/health")
        assert response.status_code == 200 and response.json() == {"status": "ok"}
        response = client.post("/chat", json={})
        assert response.status_code == 422
        response = client.post("/files/upload", files={"file": ("note.txt", "你好，Agent".encode())})
        assert response.status_code == 200
        assert response.json()["preview"] == "你好，Agent"
        response = client.post("/files/upload", files={"file": ("bad.exe", b"test")})
        assert response.status_code == 415
        response = client.post("/files/upload", files={"file": ("bad.txt", b"\xff")})
        assert response.status_code == 400
        response = client.post("/files/upload", files={"file": ("large.txt", b"a" * 1_000_001)})
        assert response.status_code == 413
        print("HTTP smoke: 6 non-model checks passed")
        if args.live:
            response = client.post("/chat", json={"message": "请用计算器计算 12 * 8，只回答结果。"}, timeout=180)
            if response.status_code != 200:
                raise RuntimeError(f"真实聊天失败：HTTP {response.status_code}; {response.text}")
            result = response.json()
            assert "96" in result["reply"]
            history = client.get(f"/chat/history/{result['session_id']}").json()
            assert history["message_count"] == 2
            assert history["messages"][1]["content"] == result["reply"]
            print("Live HTTP: reply contains 96; both messages persisted and returned by history API")


if __name__ == "__main__":
    main()
