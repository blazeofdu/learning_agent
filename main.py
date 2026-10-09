import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import asyncio
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent import run_agent
from llm import ModelServiceError, create_sync_chat_completion
from database import (
    get_messages,
    init_db,
    save_chat_exchange,
)
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(init_db)
    yield


# 创建 FastAPI 应用
app = FastAPI(
    title="AI Agent Learning API",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000, pattern=r"\S")



class ResumeRequest(BaseModel):
    resume: str = Field(min_length=1, max_length=20_000, pattern=r"\S")


@app.exception_handler(ModelServiceError)
async def model_exception_handler(request: Request, exc: ModelServiceError):
    logger.warning("模型请求失败：path=%s, status=%s", request.url.path, exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})




@app.middleware("http") #所有的http都会先访问这个接口
async def request_logging_middleware(
        request: Request,
        call_next
):
    start = time.perf_counter()
    try:
        response = await call_next(request) #访问应该访问的接口
    except Exception:
        duration_ms = (time.perf_counter() - start)*1000
        logger.error(
            "请求处理失败：method=%s, path=%s, duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "请求完成：method=%s, path=%s, status=%s, duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    return response
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
    logger.error( #把服务器中没有被处理的异常记录到日志里，并附带完整的错误堆栈。
        "未处理的服务器异常：method=%s, path=%s, error=%s",
        request.method,
        request.url.path,
        exc,
        exc_info=(
            type(exc), #异常类型
             exc, #异常
            exc.__traceback__, #异常的追踪信息，记录错误发生在哪个文件、哪一行、经过了哪些函数。
        ),
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

    await run_in_threadpool(
        save_chat_exchange,
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

    response = create_sync_chat_completion(
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

    if not response.choices:
        raise ModelServiceError("模型服务返回了空响应")
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

    # 最多读取上限 + 1 字节即可判断超限，避免一次读入整个大文件。
    # multipart 解析层可能已经接收文件；公网部署还需要网关请求体限制。
    try:
        content = await file.read(1_000_001)
    finally:
        await file.close()

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
