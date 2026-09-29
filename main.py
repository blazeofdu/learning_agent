import json
import logging
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4
import asyncio

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel

from agent import run_agent
from database import (
    get_messages,
    init_db,
    save_chat_exchange,
)


# 读取 .env 文件
load_dotenv()


# 配置模型客户端
client_config = {
    "api_key": os.getenv("OPENAI_API_KEY"),
}

base_url = os.getenv("OPENAI_BASE_URL")

if base_url:
    client_config["base_url"] = base_url

client = OpenAI(**client_config)

MODEL = os.getenv("MODEL")


# 创建 FastAPI 应用
app = FastAPI(
    title="AI Agent Learning API"
)


# 创建日志对象
logger = logging.getLogger("uvicorn.error")


# 初始化数据库
init_db()


class ChatRequest(BaseModel):
    message: str
    # session_id: Optional[str] = None



class ResumeRequest(BaseModel):
    resume: str


@app.get("/async_test") #测试并发
async def async_test():
    await asyncio.sleep(3)

    return {
        "message" : "等待完成"
    }


@app.exception_handler(Exception)
def global_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "未处理的服务器异常：method=%s, path=%s",
        request.method,
        request.url.path,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请稍后重试",
        },
    )


@app.get("/")
def root():
    return {
        "message": "AI Agent Learning API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.post("/chat")
async def chat(
    request: ChatRequest,
    http_request: Request,
    response: Response,
):
    # 从 Cookie 中读取 session_id
    session_id = http_request.cookies.get("session_id")

    # 第一次访问时自动生成
    if not session_id:
        session_id = uuid4().hex

    # 写入 Cookie，后续请求浏览器会自动携带
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
    )

    answer = await run_agent(request.message)

    save_chat_exchange(
        session_id=session_id,
        user_message=request.message,
        assistant_message=answer,
    )

    logger.info(
        "聊天记录保存成功：session_id=%s",
        session_id,
    )

    return {
        "session_id": session_id,
        "reply": answer,
    }


@app.get("/chat/history/{session_id}")
def chat_history(session_id: str):
    messages = get_messages(session_id)

    return {
        "session_id": session_id,
        "message_count": len(messages),
        "messages": messages,
    }


@app.post("/resume/analyze")
def analyze_resume(request: ResumeRequest):
    prompt = f"""
请分析下面这份简历，并且只返回合法 JSON，不要返回 Markdown 代码块。

简历内容：
{request.resume}

返回格式必须是：
{{
  "skills": ["技能1", "技能2"],
  "has_competition_experience": true,
  "summary": "一句话总结"
}}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是一个专业的简历分析助手。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )

    content = response.choices[0].message.content or ""

    try:
        result = json.loads(content)

    except json.JSONDecodeError:
        result = {
            "skills": [],
            "has_competition_experience": False,
            "summary": content,
        }

    return result


@app.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
):
    filename = file.filename or ""

    if not filename:
        raise HTTPException(
            status_code=400,
            detail="文件名不能为空",
        )

    suffix = Path(filename).suffix.lower()

    if suffix not in {".txt", ".md"}:
        raise HTTPException(
            status_code=415,
            detail="目前只支持 TXT 和 Markdown 文件",
        )

    content = await file.read()

    if len(content) > 1_000_000:
        raise HTTPException(
            status_code=413,
            detail="文件不能超过 1 MB",
        )

    try:
        text = content.decode("utf-8")

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="文件必须使用 UTF-8 编码",
        )

    logger.info(
        "文件上传成功：filename=%s, size=%d",
        filename,
        len(content),
    )

    return {
        "filename": filename,
        "content_type": file.content_type,
        "text_length": len(text),
        "preview": text[:500],
    }