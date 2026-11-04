"""
report 节点 —— LLM 基于查询结果生成文字分析报告
"""
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from ...core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

REPORT_PROMPT = """你是数据分析师。根据用户问题、执行的 SQL 和查询结果，写一份简短分析报告。

要求:
1. 2-4 句话，直接回答用户问题，突出关键数字。
2. 如有趋势/对比，指出最明显的发现。
3. 不要复述 SQL，不要罗列全部数据。

执行的 SQL:
```sql
{sql}
```

查询结果（共 {row_count} 行）:
{data}
"""


def report_node(state: dict) -> dict[str, Any]:
    sql_result = state.get("sql_result") or {}
    columns = sql_result.get("columns", [])
    rows = sql_result.get("rows", [])

    # 拼一个紧凑的数据文本（最多 30 行）
    lines = [" | ".join(columns)]
    for r in rows[:30]:
        lines.append(" | ".join(str(r.get(c, "")) for c in columns))
    data_text = "\n".join(lines)

    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=0.3,
    )
    response = llm.invoke([
        SystemMessage(content=REPORT_PROMPT.format(
            sql=state.get("generated_sql", ""),
            row_count=sql_result.get("row_count", 0),
            data=data_text,
        )),
        state["messages"][-1],
    ])

    print(f"[report] 报告 {len(response.content)} 字")
    return {"report": response.content}
