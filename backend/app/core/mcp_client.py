"""
MCP Client —— 同步封装，供 LangGraph sync 节点调用 MCP Server

使用方式 (asyncio.run 包装每次调用，MCP server 是独立 HTTP 进程)::

    from app.core.mcp_client import list_tables, get_schema, run_sql
    tables = list_tables()
    orders_schema = get_schema("orders")
    result = run_sql("SELECT COUNT(*) FROM orders LIMIT 1")
"""
from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

_MCP_URL = "http://127.0.0.1:8081/mcp"


async def _call_tool_async(tool_name: str, arguments: dict) -> Any:
    """单次 MCP streamable-http 调用，返回解析后的 JSON（或 str）"""
    async with streamable_http_client(_MCP_URL) as (recv, send, _get_sid):
        async with ClientSession(recv, send) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool = next((t for t in tools.tools if t.name == tool_name), None)
            if tool is None:
                raise RuntimeError(f"MCP tool '{tool_name}' 未找到")
            result = await session.call_tool(tool_name, arguments)
            # MCP CallToolResult.content 是 list[TextContent | ...]
            text = result.content[0].text if result.content else ""
            # 尝试解析 JSON（我们的 tool 都返回 JSON 字符串）
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text


def _call_tool(tool_name: str, arguments: dict) -> Any:
    """同步入口：asyncio.run 包装，每次新建 HTTP 连接"""
    return asyncio.run(_call_tool_async(tool_name, arguments))


# ---- 暴露给 LangGraph 节点的三个同步函数 ----

def list_tables() -> list[dict]:
    """返回 [{name, row_count}] 列表"""
    return _call_tool("list_tables", {})


def get_schema(table_name: str) -> dict:
    """返回 {table, columns: [{name, type, nullable, comment}]}"""
    return _call_tool("get_schema", {"table_name": table_name})


def run_sql(sql: str) -> dict:
    """
    返回 {columns, rows, row_count} 或 {error, ...}

    和 DuckDB 直连版本格式一致，便于 run_sql_node 无缝切换。
    """
    return _call_tool("run_sql", {"sql": sql})


# ---- 辅助：构建注入给 text2sql 的 schema 文本 ----
def build_schema_text() -> str:
    """
    通过 MCP 获取所有表的 schema，拼成 DDL + 中文注释文本，
    替代原来 core.schema_loader.get_schema_text() 里直接 DuckDB 读取。
    """
    tables = list_tables()
    parts: list[str] = []
    for t in tables:
        name = t["name"]
        schema = get_schema(name)
        col_lines = []
        for c in schema["columns"]:
            comment = c.get("comment", "")
            null = "NULL" if c.get("nullable") else "NOT NULL"
            line = f"    {c['name']:<20} {c['type']:<12} {null}"
            if comment:
                line += f"  -- {comment}"
            col_lines.append(line)
        parts.append(f"-- 行数 ~{t['row_count']}\nCREATE TABLE {name} (\n" + ",\n".join(col_lines) + "\n);")
    return "\n\n".join(parts)


@lru_cache(maxsize=1)
def build_schema_text_cached() -> str:
    """缓存版本，text2sql 每次调用时用；schema 不变就不用重复查"""
    return build_schema_text()
