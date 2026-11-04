"""
run_sql 节点 —— 通过 MCP Server 只读执行 DuckDB SQL

所有 DB 调用都走 MCP 协议，换数据库只需改 MCP Server，图代码零改动。
"""
from typing import Any

from ...core.mcp_client import run_sql as mcp_run_sql


def run_sql_node(state: dict) -> dict[str, Any]:
    """
    LangGraph 节点：执行 state['generated_sql']（通过 MCP run_sql tool）

    输入 state 字段:
        - generated_sql: 要执行的 SQL
    输出 state 字段:
        - sql_result:  {columns, rows, row_count}
        - sql_error:   执行失败时填错误信息
    """
    sql = state.get("generated_sql", "")
    if not sql:
        return {"sql_error": "SQL 为空，未执行"}

    result = mcp_run_sql(sql)

    if "error" in result:
        print(f"[run_sql] {result['error']}")
        return {"sql_error": result["error"]}

    print(f"[run_sql] 返回 {result['row_count']} 行 × {len(result['columns'])} 列")
    return {"sql_result": result}
