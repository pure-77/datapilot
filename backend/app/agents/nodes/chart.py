"""
chart 节点 —— LLM structured output 生成 ECharts option
"""
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from ...core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

CHART_PROMPT = """你是数据可视化专家。根据用户问题和查询结果，生成一个 ECharts 配置。

要求:
1. 选择合适的图表类型: bar(对比)、line(趋势)、pie(占比)、scatter(散点)。
2. x_field / y_field 必须是查询结果 columns 中真实存在的列名。
3. title 要简洁概括图表内容。
4. 数据点太多时（>50）只用前 50 行。

只输出一个 JSON 对象，格式如下（不要输出任何其他内容）:
{{"chart_type": "bar|line|pie|scatter", "title": "...", "x_field": "列名", "y_field": "列名"}}

查询结果列: {columns}
查询结果前 {n} 行示例:
{sample}
"""


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "pie", "scatter"] = Field(description="图表类型")
    title: str = Field(description="图表标题")
    x_field: str = Field(description="X 轴（或饼图的 name 字段）对应的列名")
    y_field: str = Field(description="Y 轴（或饼图的 value 字段）对应的列名")


def chart_node(state: dict) -> dict[str, Any]:
    sql_result = state.get("sql_result") or {}
    columns = sql_result.get("columns", [])
    rows = sql_result.get("rows", [])

    if not columns or not rows:
        return {"chart_spec": {}}

    sample = rows[:50]
    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        temperature=0,
        # deepseek 思考模式不支持 json_schema / tool_choice，用 json_mode
    ).with_structured_output(ChartSpec, method="json_mode")

    spec: ChartSpec = llm.invoke([
        SystemMessage(content=CHART_PROMPT.format(
            columns=columns, n=len(sample), sample=sample[:10],
        )),
        state["messages"][-1],
    ])

    # 组装成 ECharts option
    x_data = [r.get(spec.x_field) for r in sample]
    y_data = [r.get(spec.y_field) for r in sample]

    if spec.chart_type == "pie":
        option = {
            "title": {"text": spec.title},
            "tooltip": {},
            "series": [{
                "type": "pie",
                "data": [{"name": str(x), "value": y} for x, y in zip(x_data, y_data)],
            }],
        }
    else:
        option = {
            "title": {"text": spec.title},
            "tooltip": {},
            "xAxis": {"type": "category", "data": [str(x) for x in x_data]},
            "yAxis": {"type": "value"},
            "series": [{"type": spec.chart_type, "data": y_data}],
        }

    print(f"[chart] {spec.chart_type} | {spec.title} | x={spec.x_field} y={spec.y_field}")
    return {"chart_spec": option}
