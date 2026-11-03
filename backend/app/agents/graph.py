"""
LangGraph 图定义 —— M1 单节点链路

    text2sql → run_sql → END
"""
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes.text2sql import text2sql_node
from .nodes.run_sql import run_sql_node


def build_graph():
    """构建 M1 单 Agent 图并编译"""
    g = StateGraph(AgentState)

    g.add_node("text2sql", text2sql_node)
    g.add_node("run_sql", run_sql_node)

    g.set_entry_point("text2sql")
    g.add_edge("text2sql", "run_sql")
    g.add_edge("run_sql", END)

    return g.compile()


# 单例，供 FastAPI 导入
graph = build_graph()


if __name__ == "__main__":
    # 命令行快速验证
    from langchain_core.messages import HumanMessage

    question = "上个月销量最高的10个商品是什么"
    print(f"用户问题: {question}\n{'='*50}\n")

    result = graph.invoke({"messages": [HumanMessage(question)]})

    print("\n" + "=" * 50)
    print("✅ 图执行完成")
    print(f"生成 SQL:\n  {result.get('generated_sql', 'N/A')}")
    if result.get("sql_error"):
        print(f"❌ SQL 错误: {result['sql_error']}")
    else:
        r = result["sql_result"]
        print(f"返回 {r['row_count']} 行, 列: {r['columns']}")
        # 打印前 5 行
        for row in r["rows"][:5]:
            print(f"  {row}")
