"""
sql_check 节点 —— sqlglot AST 静态校验（非 LLM）

规则:
    1. 必须是单条 SELECT（禁 INSERT/UPDATE/DELETE/DROP 等）
    2. 表必须在白名单内
    3. 必须带 LIMIT 子句
校验失败时把错误写入 validation_errors 并累加 retry_count，
让 text2sql 重试时能读到根因错误做自我修正。
"""
from typing import Any

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"orders", "products", "regions"}
MAX_RETRY = 2  # 最多重试 2 次（即共生成 3 次 SQL）


def validate_sql(sql: str) -> str | None:
    """
    校验 SQL，返回 None 表示通过，否则返回错误描述（供 LLM 重试修正）。
    """
    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
    except Exception as e:
        return f"SQL 语法错误: {e}"

    # 规则 1: 只允许单条 SELECT
    if not isinstance(parsed, exp.Select):
        return f"只允许 SELECT 查询语句，检测到: {type(parsed).__name__}"

    # 规则 2: 表白名单（含子查询里的表；排除 CTE 别名）
    cte_names = {cte.alias.lower() for cte in parsed.find_all(exp.CTE)}
    tables = {t.name.lower() for t in parsed.find_all(exp.Table)} - cte_names
    illegal = tables - ALLOWED_TABLES
    if illegal:
        return f"访问了不允许的表: {sorted(illegal)}，可用表: {sorted(ALLOWED_TABLES)}"

    # 规则 3: 顶层必须有 LIMIT
    if parsed.args.get("limit") is None:
        return "查询缺少 LIMIT 子句，请加上 LIMIT（如 LIMIT 100）"

    return None


def sql_check_node(state: dict) -> dict[str, Any]:
    """
    LangGraph 节点：校验 state['generated_sql']

    通过 → 清空 validation_errors（不动 retry_count，留给 wait_approval 后自然结束）
    失败 → 追加 validation_errors，retry_count + 1
    """
    sql = state.get("generated_sql", "")
    error = validate_sql(sql)
    retry_count = state.get("retry_count", 0)

    if error is None:
        print(f"[sql_check] ✅ 校验通过")
        return {"validation_errors": []}

    print(f"[sql_check] ❌ 校验失败(第{retry_count + 1}次): {error}")
    return {
        "validation_errors": state.get("validation_errors", []) + [error],
        "retry_count": retry_count + 1,
    }


def route_after_check(state: dict) -> str:
    """
    条件边：sql_check → wait_approval / text2sql(重试) / END(重试耗尽)
    """
    if not state.get("validation_errors"):
        return "wait_approval"
    if state.get("retry_count", 0) <= MAX_RETRY:
        return "text2sql"
    return END_SENTINEL


END_SENTINEL = "__end__"  # graph.py 里映射到 END
