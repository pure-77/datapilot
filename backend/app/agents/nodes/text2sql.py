"""
text2sql 节点 —— 注入表结构 → 生成 SQL
"""
import re
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from ...core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from ...core.mcp_client import build_schema_text_cached

# System Prompt 模板
SYSTEM_PROMPT_TEMPLATE = """你是一个专业的数据分析 SQL 助手。
请根据用户的自然语言问题，生成一条可在 DuckDB 中执行的 SQL。

## 数据库表结构

{schema_text}

## 规则

1. 只输出一条 SELECT 语句，不要输出任何解释、Markdown 代码块标记（```sql 之类的）。
2. 必须加 LIMIT，默认 LIMIT 100；但如果用户明确要 TOP N，就用 LIMIT N。
3. 聚合查询必须给计算列起有意义的别名（如 sales_total、product_name）。
4. 日期字段比较请用 ISO 格式字符串 'YYYY-MM-DD'。
5. 大小写敏感：产品名、区域名区分中文字面量，如 '华东'、'华南'、'电子产品'。
6. 如果问题涉及多表，用 JOIN 关联（products.product_id = orders.product_id）。

## 输出格式

直接输出 SQL 语句，不要带任何包裹。
"""


def _build_llm() -> ChatOpenAI:
    """统一的 LLM 构建器"""
    return ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=0,          # SQL 要确定性，temperature=0
    )


def _clean_sql(raw: str) -> str:
    """去掉 LLM 可能加的 Markdown 包裹（```sql ... ```）和前后空白"""
    # 匹配 ```sql 或 ``` 包裹
    m = re.search(r"```(?:sql)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return raw.strip()


def text2sql_node(state: dict) -> dict[str, Any]:
    """
    LangGraph 节点：把 messages 里的用户问题转成 SQL

    输入 state 字段:
        - messages: [HumanMessage(...), ...]
    输出 state 字段:
        - schema_text: 注入给 LLM 的表结构
        - generated_sql: 生成的 SQL
    """
    # 1. 通过 MCP Server 加载表结构（build_schema_text_cached 带 lru_cache）
    schema_text = build_schema_text_cached()

    # 2. 构建 LLM 和 Prompt
    llm = _build_llm()
    prompt = SYSTEM_PROMPT_TEMPLATE.format(schema_text=schema_text)

    # 重试时把上一次校验失败的根因错误注入，让 LLM 自我修正
    validation_errors = state.get("validation_errors") or []
    if validation_errors:
        last_sql = state.get("generated_sql", "")
        prompt += f"""
## ⚠️ 上一次生成未通过安全校验

上一次生成的 SQL:
{last_sql}

校验失败原因（必须修正）:
""" + "\n".join(f"- {e}" for e in validation_errors) + "\n\n请根据错误原因重新生成合规的 SQL。\n"

    system_msg = SystemMessage(content=prompt)

    # 只传 system + 最后一条用户消息（M1 暂不做多轮上下文）
    user_msg = state["messages"][-1]
    response = llm.invoke([system_msg, user_msg])

    # 3. 清洗 SQL
    sql = _clean_sql(response.content)

    print(f"[text2sql] 生成 SQL:\n{sql}\n")
    return {
        "schema_text": schema_text,
        "generated_sql": sql,
    }
