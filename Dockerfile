FROM python:3.9-slim
# 准备一个安装了 Python 3.9 的 Linux 环境

WORKDIR /app
#在容器中创建 /app 工作目录
COPY requirements.txt ./
#把 requirements.txt 复制进去
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
#项目文件复制到容器的/app目录
#把项目代码复制进去
EXPOSE 8000
#声明程序使用 8000 端口
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
#