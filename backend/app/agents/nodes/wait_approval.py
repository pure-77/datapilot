"""
wait_approval 节点 —— interrupt() 人工确认 SQL

图执行到这里会暂停，把 SQL 卡片数据推给前端；
前端用户选择后，后端用 Command(resume=...) 恢复，返回值就是 interrupt() 的返回。

resume 协议:
    {"action": "approve"}                      → 批准，执行原 SQL
    {"action": "modify", "sql": "SELECT ..."}  → 用用户改过的 SQL 执行
    {"action": "reject", "reason": "..."}      → 拒绝，结束
"""
from typing import Any

from langgraph.types import interrupt


def wait_approval_node(state: dict) -> dict[str, Any]:
    sql = state.get("generated_sql", "")

    human = interrupt({
        "type": "sql_approval",
        "sql": sql,
        "question": state["messages"][-1].content,
    })

    action = human.get("action")
    print(f"[wait_approval] 用户操作: {action}")

    if action == "approve":
        return {"approved": True}

    if action == "modify":
        modified_sql = human.get("sql", "").strip()
        if not modified_sql:
            return {"approved": False, "sql_error": "修改后的 SQL 为空"}
        return {"approved": True, "generated_sql": modified_sql}

    # reject 或未知操作
    reason = human.get("reason", "用户拒绝了 SQL 执行")
    return {"approved": False, "sql_error": reason}


def route_after_approval(state: dict) -> str:
    """条件边：wait_approval → run_sql / END"""
    if state.get("approved"):
        return "run_sql"
    return "__end__"
