"""
问数相关路由

- GET  /health  健康检查
- POST /stream  SSE 逐节点推送（遇 interrupt 推送审核卡片事件）
- POST /resume  人工确认后恢复执行（approve / modify / reject），SSE 推送后续节点
- POST /ask     同步一次问数（M1 遗留，M2 起主要走 /stream + /resume）
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from .deps import get_graph

router = APIRouter()


class StreamRequest(BaseModel):
    question: str
    thread_id: str | None = None


class ResumeRequest(BaseModel):
    thread_id: str
    action: str                # approve / modify / reject
    sql: str | None = None     # modify 时的新 SQL
    reason: str | None = None  # reject 时的理由


def _new_thread_id(thread_id: str | None) -> str:
    return thread_id or f"thread-{uuid.uuid4().hex[:8]}"


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"


def _stream_graph(graph, graph_input, config, thread_id: str):
    """统一的 SSE 生成器：逐节点推送 + interrupt 卡片事件"""
    try:
        for event in graph.stream(graph_input, config=config, stream_mode="updates"):
            for node_name, output in event.items():
                # interrupt 事件：推送审核卡片数据给前端
                if node_name == "__interrupt__":
                    for intr in output:
                        yield _sse({"node": "interrupt", "output": intr.value, "thread_id": thread_id})
                    continue
                yield _sse({"node": node_name, "output": output})

        yield _sse({"done": True, "thread_id": thread_id})

    except Exception as e:
        yield _sse({"error": str(e)})


@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok"}


@router.get("/state")
def get_thread_state(thread_id: str, graph=Depends(get_graph)):
    """
    查询线程状态 —— 前端刷新页面后调用，恢复待确认的审核卡片

    返回:
        {"pending": true, "interrupt": {...}}  有待确认中断
        {"pending": false}                     无
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if snapshot.next and snapshot.tasks:
        for task in snapshot.tasks:
            if task.interrupts:
                return {"pending": True, "interrupt": task.interrupts[0].value}
    return {"pending": False}


@router.post("/stream")
async def stream_question(payload: StreamRequest, graph=Depends(get_graph)):
    """
    SSE 端点 —— 发起一次问数，逐节点推送更新

    前端 EventSource 订阅后可能收到：
        data: {"node": "supervisor", "output": {...}}
        data: {"node": "text2sql",   "output": {...}}
        data: {"node": "interrupt",  "output": {"type":"sql_approval","sql":"..."}, "thread_id": "..."}
        data: {"done": true, "thread_id": "..."}
    """
    thread_id = _new_thread_id(payload.thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {"messages": [{"role": "user", "content": payload.question}]}

    return StreamingResponse(
        _stream_graph(graph, graph_input, config, thread_id),
        media_type="text/event-stream",
    )


@router.post("/resume")
async def resume_approval(payload: ResumeRequest, graph=Depends(get_graph)):
    """
    人工确认后恢复执行 —— Command(resume=...) 唤醒 interrupt 处

    body:
        {"thread_id": "...", "action": "approve"}
        {"thread_id": "...", "action": "modify", "sql": "SELECT ... LIMIT 10"}
        {"thread_id": "...", "action": "reject", "reason": "..."}
    """
    if payload.action not in ("approve", "modify", "reject"):
        raise HTTPException(status_code=400, detail=f"非法 action: {payload.action}")

    config = {"configurable": {"thread_id": payload.thread_id}}

    # 确认线程确实停在 interrupt 处
    state_snapshot = graph.get_state(config)
    if not state_snapshot.next:
        raise HTTPException(status_code=409, detail="该会话没有待确认的中断")

    resume_value = {"action": payload.action}
    if payload.action == "modify":
        resume_value["sql"] = payload.sql or ""
    if payload.action == "reject":
        resume_value["reason"] = payload.reason or "用户拒绝了 SQL 执行"

    return StreamingResponse(
        _stream_graph(graph, Command(resume=resume_value), config, payload.thread_id),
        media_type="text/event-stream",
    )


@router.post("/ask")
async def ask_once(payload: StreamRequest, graph=Depends(get_graph)):
    """
    同步一次问数 —— 返回完整结果 JSON；遇 interrupt 返回 pending 状态和审核数据
    """
    thread_id = _new_thread_id(payload.thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = graph.invoke(
            {"messages": [{"role": "user", "content": payload.question}]},
            config=config,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 检查是否停在 interrupt
    snapshot = graph.get_state(config)
    if snapshot.next and snapshot.tasks:
        for task in snapshot.tasks:
            if task.interrupts:
                return {
                    "pending": True,
                    "thread_id": thread_id,
                    "interrupt": task.interrupts[0].value,
                    "intent": result.get("intent"),
                }

    if result.get("chat_reply"):
        return {"intent": "chat", "reply": result["chat_reply"], "thread_id": thread_id}

    if result.get("sql_error"):
        return {
            "error": result["sql_error"],
            "sql": result.get("generated_sql"),
            "validation_errors": result.get("validation_errors"),
            "thread_id": thread_id,
        }

    return {
        "intent": result.get("intent"),
        "sql": result.get("generated_sql"),
        "result": result.get("sql_result"),
        "chart_spec": result.get("chart_spec"),
        "report": result.get("report"),
        "thread_id": thread_id,
    }
