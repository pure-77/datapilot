"""
LangGraph 图定义 —— M2 多 Agent + 人工确认

    supervisor ──┬── chat ──→ chat_reply ──→ END
                 └── query/report ──→ text2sql ──→ sql_check ──┬── 通过 ──→ wait_approval ──interrupt──┬── approve/modify ──→ run_sql ──→ Send(chart, report) ──→ END
                                                      ↑            │                                      └── reject ──→ END
                                                      └── 失败重试 ──┘ (超过 MAX_RETRY → END)
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, END
from langgraph.types import Send

from ..core.config import PROJECT_ROOT
from .state import AgentState
from .nodes.supervisor import supervisor_node, chat_reply_node, route_by_intent
from .nodes.text2sql import text2sql_node
from .nodes.sql_check import sql_check_node, route_after_check
from .nodes.wait_approval import wait_approval_node, route_after_approval
from .nodes.run_sql import run_sql_node
from .nodes.chart import chart_node
from .nodes.report import report_node

CHECKPOINT_DB = str(PROJECT_ROOT / "backend" / "data" / "checkpoints.db")


def after_run_sql(state: AgentState):
    """run_sql 成功后用 Send 并行派发 chart / report"""
    if state.get("sql_error"):
        return END
    return [
        Send("chart", dict(state)),
        Send("report", dict(state)),
    ]


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)

    # ---- 节点 ----
    g.add_node("supervisor", supervisor_node)
    g.add_node("chat_reply", chat_reply_node)
    g.add_node("text2sql", text2sql_node)
    g.add_node("sql_check", sql_check_node)
    g.add_node("wait_approval", wait_approval_node)
    g.add_node("run_sql", run_sql_node)
    g.add_node("chart", chart_node)
    g.add_node("report", report_node)

    # ---- 边 ----
    g.set_entry_point("supervisor")

    g.add_conditional_edges("supervisor", route_by_intent, {
        "chat_reply": "chat_reply",
        "text2sql": "text2sql",
    })
    g.add_edge("chat_reply", END)

    g.add_edge("text2sql", "sql_check")

    g.add_conditional_edges("sql_check", route_after_check, {
        "wait_approval": "wait_approval",
        "text2sql": "text2sql",   # 校验失败回环重试
        "__end__": END,           # 重试耗尽
    })

    g.add_conditional_edges("wait_approval", route_after_approval, {
        "run_sql": "run_sql",
        "__end__": END,           # 用户拒绝
    })

    g.add_conditional_edges("run_sql", after_run_sql, ["chart", "report", END])
    g.add_edge("chart", END)
    g.add_edge("report", END)

    return g.compile(checkpointer=checkpointer)


# ---- 模块级单例（带 SqliteSaver，FastAPI 多线程需 check_same_thread=False）----
_conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
_checkpointer = SqliteSaver(_conn)
graph = build_graph(checkpointer=_checkpointer)


if __name__ == "__main__":
    # 命令行快速验证（interrupt 前的部分）
    from langchain_core.messages import HumanMessage

    question = "上个月销量最高的10个商品是什么"
    config = {"configurable": {"thread_id": "cli-test"}}
    print(f"用户问题: {question}\n{'='*50}\n")

    result = graph.invoke({"messages": [HumanMessage(question)]}, config=config)

    print("\n" + "=" * 50)
    print(f"intent: {result.get('intent')}")
    print(f"生成 SQL:\n  {result.get('generated_sql', 'N/A')}")
    if result.get("sql_error"):
        print(f"❌ SQL 错误: {result['sql_error']}")
    elif r := result.get("sql_result"):
        print(f"返回 {r['row_count']} 行, 列: {r['columns']}")
        for row in r["rows"][:5]:
            print(f"  {row}")
