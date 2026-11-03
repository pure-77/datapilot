"""
从 DuckDB 提取表结构（DDL + 字段中文注释）
"""
import duckdb
import pandas as pd

from ..core.config import DUCKDB_PATH


def get_schema_text(db_path: str = DUCKDB_PATH) -> str:
    """
    读取 DuckDB 全量表结构，拼成 LLM 能理解的文本格式：

    CREATE TABLE products (
        product_id   INTEGER,        -- 产品唯一标识
        product_name VARCHAR(128),    -- 产品名称
        ...
    );

    CREATE TABLE orders (...);
    ...
    """
    con = duckdb.connect(db_path, read_only=True)

    # 1. 拿到所有表名
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()

    ddl_parts = []

    for (table_name,) in tables:
        # 2. DESCRIBE 拿列信息
        cols = con.execute(f"DESCRIBE {table_name}").fetchall()
        # cols: [(col_name, col_type, null, key, default, extra), ...]

        # 3. 拿字段注释（duckdb_columns() 系统表）
        try:
            comments = con.execute(f"""
                SELECT column_name, comment
                FROM duckdb_columns()
                WHERE table_name = '{table_name}'
            """).fetchall()
            comment_map = {c[0]: c[1] for c in comments if c[1]}
        except Exception:
            comment_map = {}

        # 4. 拼 DDL
        col_lines = []
        for col_name, col_type, *_ in cols:
            comment = comment_map.get(col_name, "")
            line = f"    {col_name:<16s} {col_type.upper()}"
            if comment:
                line += f"  -- {comment}"
            col_lines.append(line)

        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(col_lines) + "\n);"
        ddl_parts.append(ddl)

    con.close()
    return "\n\n".join(ddl_parts)


def get_allowed_tables(db_path: str = DUCKDB_PATH) -> list[str]:
    """返回表白名单"""
    con = duckdb.connect(db_path, read_only=True)
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()]
    con.close()
    return tables


if __name__ == "__main__":
    schema = get_schema_text()
    print(schema)
    print(f"\n表白名单: {get_allowed_tables()}")
