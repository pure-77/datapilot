"""
MCP Server —— 把 DuckDB 暴露成 MCP tools

三个 tool:
    list_tables()               → 所有表名 + 行数
    get_schema(table_name)      → 指定表的列名、类型、中文注释
    run_sql(sql)                → 只读执行 SQL，返回 {columns, rows, row_count}

启动:
    python -m app.mcp_server.server

默认监听: http://127.0.0.1:8081/mcp
"""
from __future__ import annotations

import json
import sqlite3  # noqa: F401  (打包时显式引入 duckdb 依赖链)
from pathlib import Path
from typing import Any

import duckdb
from mcp.server.fastmcp import FastMCP

# ---- 数据库连接（只读）----
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DUCKDB_PATH = str(
    _PROJECT_ROOT / "backend" / "data" / "demo.duckdb"
)
con = duckdb.connect(_DUCKDB_PATH, read_only=True)

mcp = FastMCP(
    "datapilot-db",
    host="127.0.0.1",
    port=8081,
    streamable_http_path="/mcp",
    mount_path="/",
)


@mcp.tool()
def list_tables() -> str:
    """列出所有可用表及其行数，返回 JSON 字符串。"""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    result = []
    for (table_name,) in rows:
        (count,) = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
        result.append({"name": table_name, "row_count": count})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_schema(table_name: str) -> str:
    """
    返回指定表的列信息（JSON 字符串）。包含列名、类型和中文注释。

    Args:
        table_name: 表名，如 'orders'、'products'、'regions'
    """
    cols = con.execute(f'DESCRIBE "{table_name}"').fetchall()
    comments = con.execute(
        "SELECT column_name, comment "
        "FROM duckdb_columns() "
        "WHERE table_name = ? AND comment IS NOT NULL AND comment != ''",
        [table_name],
    ).fetchall()
    comment_map = {c[0]: c[1] for c in comments}
    result = {
        "table": table_name,
        "columns": [
            {
                "name": c[0],
                "type": str(c[1]),
                "nullable": c[2] == "YES",
                "comment": comment_map.get(c[0], ""),
            }
            for c in cols
        ],
    }
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def run_sql(sql: str) -> str:
    """
    在 DuckDB 中只读执行 SQL，返回 JSON 字符串 {columns, rows, row_count, error?}。

    Args:
        sql: 要执行的 SQL 语句（只读 SELECT）
    """
    try:
        df = con.execute(sql).fetchdf()
    except Exception as e:
        return json.dumps({"error": f"SQL 执行失败: {e}", "columns": [], "rows": [], "row_count": 0})

    def _normalize(v):
        try:
            import pandas as pd
            if isinstance(v, (pd.Timestamp,)):
                return v.isoformat()
        except Exception:
            pass
        if hasattr(v, "item"):
            try:
                return v.item()
            except Exception:
                return str(v)
        if v is None:
            return None
        if isinstance(v, (int, float, str, bool)):
            return v
        return str(v)

    rows = []
    for record in df.to_dict(orient="records"):
        rows.append({k: _normalize(v) for k, v in record.items()})

    return json.dumps({
        "columns": list(df.columns),
        "rows": rows,
        "row_count": len(df),
    }, ensure_ascii=False)


if __name__ == "__main__":
    print(f"MCP Server starting at http://127.0.0.1:8081/mcp")
    print(f"DuckDB: {_DUCKDB_PATH}")
    mcp.run(transport="streamable-http")
