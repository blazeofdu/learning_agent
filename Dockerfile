FROM python:3.12-slim
# 容器使用仍在维护的 Python；不修改你本地已有的 .venv。

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app
#在容器中创建 /app 工作目录
COPY requirements.txt ./
#把 requirements.txt 复制进去
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py agent.py tools.py database.py llm.py ./
COPY scripts/ ./scripts/
#项目文件复制到容器的/app目录
#把项目代码复制进去
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
#声明程序使用 8000 端口
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
#  docker compose up -d --build 启动
#docker compose down 停止
