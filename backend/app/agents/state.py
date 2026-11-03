"""
LangGraph 图状态定义
"""
from typing import TypedDict, Annotated, Any

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """M1 单 Agent 状态 —— 后续 M2/M3 逐步扩展"""
    # ---- 对话 ----
    messages: Annotated[list, add_messages]  # 对话历史，add_messages reducer 自动追加

    # ---- text2sql ----
    schema_text: str          # 注入给 LLM 的表结构（DDL + 列注释）
    generated_sql: str        # LLM 生成的 SQL

    # ---- run_sql ----
    sql_result: Any           # DuckDB 执行结果（pd.DataFrame）
    sql_error: str            # 执行失败时的错误信息

    # ---- 会话 ----
    thread_id: str            # 会话 ID（Checkpointer 用）
