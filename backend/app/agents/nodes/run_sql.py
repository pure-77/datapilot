"""
run_sql 节点 —— DuckDB 只读执行
"""
from typing import Any

import duckdb

from ...core.config import DUCKDB_PATH


def run_sql_node(state: dict) -> dict[str, Any]:
    """
    LangGraph 节点：执行 state['generated_sql']

    输入 state 字段:
        - generated_sql: 要执行的 SQL
    输出 state 字段:
        - sql_result:  pd.DataFrame 或 list[dict]
        - sql_error:   执行失败时填错误信息
    """
    sql = state.get("generated_sql", "")
    if not sql:
        return {"sql_error": "SQL 为空，未执行"}

    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        df = con.execute(sql).fetchdf()
        print(f"[run_sql] 返回 {len(df)} 行 × {len(df.columns)} 列")
        # 转成 list[dict] 方便前端 JSON 渲染
        rows = df.to_dict(orient="records")
        return {
            "sql_result": {
                "columns": list(df.columns),
                "rows": rows,
                "row_count": len(df),
            }
        }
    except Exception as e:
        err = f"SQL 执行错误: {e}"
        print(f"[run_sql] {err}")
        return {"sql_error": err}
    finally:
        con.close()
