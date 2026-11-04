"""
LangGraph 图状态定义
"""
from typing import TypedDict, Annotated, Any, Literal

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """M2 多 Agent 状态"""
    # ---- 对话 ----
    messages: Annotated[list, add_messages]  # 对话历史，add_messages reducer 自动追加

    # ---- supervisor 意图路由 ----
    intent: Literal["chat", "query", "report"]  # chat=闲聊 / query=查数 / report=查数+报告
    chat_reply: str                              # 闲聊时直接回复的内容

    # ---- text2sql ----
    schema_text: str          # 注入给 LLM 的表结构（DDL + 列注释）
    generated_sql: str        # LLM 生成的 SQL

    # ---- sql_check ----
    validation_errors: list[str]  # 校验失败历史（供 text2sql 重试自我修正）
    retry_count: int              # 已重试次数

    # ---- 人工确认 ----
    approved: bool            # 用户是否批准了 SQL

    # ---- run_sql ----
    sql_result: Any           # DuckDB 执行结果 {"columns": [...], "rows": [...], "row_count": n}
    sql_error: str            # 执行失败时的错误信息

    # ---- 并行产出 ----
    chart_spec: dict          # ECharts option（chart 节点）
    report: str               # 分析报告（report 节点）

    # ---- 会话 ----
    thread_id: str            # 会话 ID（Checkpointer 用）
