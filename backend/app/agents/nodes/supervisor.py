"""
supervisor 节点 —— LLM 意图路由（structured output）

意图分三类:
    chat   闲聊 / 打招呼 / 问助手能力 → 直接回复，不进问数链路
    query  需要查数据库的问题        → text2sql
    report 需要查数 + 生成分析报告    → text2sql（后续并行出图 + 报告）
"""
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from ...core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

SUPERVISOR_PROMPT = """你是一个数据分析平台的意图路由器。判断用户最新消息属于哪类意图:

- chat: 闲聊、打招呼、询问你是谁/你能做什么、与数据分析无关的问题
- query: 需要查询数据库并用表格/数字回答的问题
- report: 需要查询数据库并进一步生成图表或分析报告的问题（含"报告""分析""图表""趋势图"等词时优先选这个）

数据库里有三张表: orders(订单明细)、products(商品)、regions(区域)。

只输出一个 JSON 对象，格式如下（不要输出任何其他内容）:
{"intent": "chat 或 query 或 report", "reason": "一句话分类理由"}"""


class SupervisorDecision(BaseModel):
    intent: Literal["chat", "query", "report"] = Field(description="意图分类")
    reason: str = Field(description="分类理由，一句话")


def supervisor_node(state: dict) -> dict[str, Any]:
    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=0,
        # deepseek 思考模式不支持 json_schema / tool_choice，用 json_mode
    ).with_structured_output(SupervisorDecision, method="json_mode")

    decision: SupervisorDecision = llm.invoke(
        [SystemMessage(content=SUPERVISOR_PROMPT), *state["messages"]]
    )
    print(f"[supervisor] intent={decision.intent} reason={decision.reason}")
    return {"intent": decision.intent}


CHAT_PROMPT = """你是 DataPilot 数据分析助手，基于 DuckDB 提供自然语言问数能力。
数据库有 orders(订单明细)、products(商品)、regions(区域) 三张表。
用户发了闲聊消息，请用一两句话友好回复，并引导用户提数据分析类问题。"""


def chat_reply_node(state: dict) -> dict[str, Any]:
    """闲聊分支：LLM 直接回复，不进 text2sql"""
    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=0.3,
    )
    response = llm.invoke([SystemMessage(content=CHAT_PROMPT), *state["messages"]])
    print(f"[chat_reply] {response.content[:50]}...")
    return {"chat_reply": response.content, "messages": [response]}


def route_by_intent(state: dict) -> str:
    """条件边：supervisor → chat_reply / text2sql"""
    if state.get("intent") == "chat":
        return "chat_reply"
    return "text2sql"
