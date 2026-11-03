"""
问数相关路由

- GET  /health  健康检查
- POST /stream  SSE 逐节点推送
- POST /ask     同步一次问数
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .deps import get_graph

router = APIRouter()


class StreamRequest(BaseModel):
    question: str
    thread_id: str | None = None


def _new_thread_id(thread_id: str | None) -> str:
    return thread_id or f"thread-{uuid.uuid4().hex[:8]}"


@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok"}


@router.post("/stream")
async def stream_question(payload: StreamRequest, graph=Depends(get_graph)):
    """
    SSE 端点 —— LangGraph 逐节点推送更新

    前端 EventSource 订阅后会收到：
        data: {"node": "text2sql", "output": {...}}
        data: {"node": "run_sql",   "output": {...}}
        data: {"done": true, "thread_id": "..."}
    """
    thread_id = _new_thread_id(payload.thread_id)

    def event_generator():
        try:
            for event in graph.stream(
                {"messages": [{"role": "user", "content": payload.question}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode="updates",
            ):
                # event: {"node_name": {output_dict}}
                for node_name, output in event.items():
                    yield f"data: {json.dumps({'node': node_name, 'output': output}, ensure_ascii=False, default=str)}\n\n"

            yield f"data: {json.dumps({'done': True, 'thread_id': thread_id})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/ask")
async def ask_once(payload: StreamRequest, graph=Depends(get_graph)):
    """
    同步一次问数 —— 返回完整结果 JSON（不需要流式的场景）
    """
    thread_id = _new_thread_id(payload.thread_id)

    try:
        result = graph.invoke(
            {"messages": [{"role": "user", "content": payload.question}]},
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.get("sql_error"):
        return {"error": result["sql_error"], "sql": result.get("generated_sql")}

    return {
        "sql": result.get("generated_sql"),
        "result": result.get("sql_result"),
        "thread_id": thread_id,
    }
