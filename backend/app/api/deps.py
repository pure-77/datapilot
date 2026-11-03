"""
API 层依赖注入

graph 用延迟导入 + 单例缓存，避免 api 模块与 agents 模块在导入期互相牵引。
M2 接入 Checkpointer 后，只需改这里，路由代码无需变动。
"""
from functools import lru_cache


@lru_cache(maxsize=1)
def get_graph():
    """返回编译后的 LangGraph 图单例"""
    from ..agents.graph import graph
    return graph
