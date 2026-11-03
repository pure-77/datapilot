# DataPilot 实现路线图

> 企业级多 Agent 数据分析平台 —— 实现指南  
> 目标：求职 Agent 开发岗位，5 周完成 MVP

---

## 一、项目定位

**场景**：业务人员用自然语言问数 → 平台自动完成「理解 → 生成 SQL → 安全校验 → 人工确认 → 执行 → 图表 + 分析报告」全流程。

**技术栈总览**：

| 层 | 技术 | 覆盖 JD 关键词 |
|---|---|---|
| 编排核心 | LangGraph（Supervisor、interrupt、Checkpointer、Send API） | 多 Agent、human-in-the-loop、状态管理 |
| 数据工具层 | MCP Python SDK + DuckDB | MCP 协议开发 |
| 安全防线 | sqlglot AST 静态审查 + 白名单 + 行级权限 | 安全落地能力 |
| 可观测 | Langfuse self-host + CallbackHandler | Observability |
| 评测 | 自建 Text2SQL 评测集 + LLM-as-judge | Evals（稀缺项） |
| 前端 | Vue3 + ECharts + Pinia + SSE | 全栈、可解释性 |

---

## 二、目录结构

```
datapilot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + SSE 端点
│   │   ├── api/
│   │   │   └── routes.py        # /stream、/approve、/reject 等 REST 路由
│   │   ├── agents/
│   │   │   ├── state.py         # AgentState 定义（TypedDict + Annotated reducer）
│   │   │   ├── graph.py         # Supervisor + 图编译入口
│   │   │   └── nodes/
│   │   │       ├── supervisor.py   # 意图路由（闲聊 / 查数 / 报告）
│   │   │       ├── text2sql.py      # 表结构注入 → 生成 SQL
│   │   │       ├── sql_check.py     # sqlglot AST 规则校验
│   │   │       ├── chart.py         # structured output → ECharts spec
│   │   │       └── report.py        # LLM 分析报告
│   │   ├── mcp_server/
│   │   │   ├── server.py        # MCP Server（streamable-http）
│   │   │   └── tools.py         # list_tables / get_schema / run_sql
│   │   ├── core/
│   │   │   ├── config.py        # 配置（DB 路径、白名单、LLM 模型名）
│   │   │   └── security.py      # 行级权限、只读连接工厂
│   │   └── requirements.txt
│   ├── evals/
│   │   ├── dataset.jsonl        # 评测集（问题 + golden SQL）
│   │   └── run_eval.py          # pytest + LLM-as-judge 脚本
│   └── data/
│       ├── schema.sql           # 表结构定义
│       ├── seed.py              # 造数脚本
│       └── demo.duckdb          # 生成的数据库文件
├── frontend/                    # Vue3 + Vite
│   └── src/
│       ├── views/
│       │   ├── ChatView.vue     # 主对话页（SSE 流渲染）
│       │   ├── TraceView.vue    # 开发者 Trace 查看页
│       │   └── ApprovalCard.vue # SQL 审核卡片（批准/拒绝/修改）
│       └── stores/
│           └── chat.ts          # Pinia 会话状态
├── docker-compose.yml           # Langfuse + backend + frontend
└── README.md
```

---

## 三、M1 — 单 Agent 问数跑通（第 1 周）

### 目标
用最简单的图跑通「自然语言 → SQL → 结果表格」链路，命令行和 SSE 双验证。

### 3.1 依赖安装

```bash
cd backend
pip install fastapi uvicorn langchain langgraph langchain-openai duckdb sqlglot sse-starlette pydantic
```

### 3.2 实现清单

#### Step 1: 准备 DuckDB 数据库（半天）

1. **定义表结构**：[data/schema.sql](file:///d:/Python%20Note/web_server/datapilot/backend/data/schema.sql)
   - 至少 3 张表，每张 5+ 字段，字段加中文注释（DuckDB `COMMENT ON COLUMN`）
   - 示例表：`products`（商品）、`orders`（订单）、`regions`（区域）
2. **造数**：[data/seed.py](file:///d:/Python%20Note/web_server/datapilot/backend/data/seed.py)
   - 生成 10 万+ 行数据，保证聚合查询有意义

#### Step 2: 定义 AgentState（半天）

[agents/state.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/agents/state.py)

```python
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]     # 对话历史
    generated_sql: str                           # LLM 生成的 SQL
    sql_result: Any                              # DuckDB 执行结果
    chart_spec: dict                             # ECharts 配置
    report: str                                  # 分析报告
    thread_id: str                               # 会话 ID（Checkpointer 用）
```

> **关键经验**：`add_messages` reducer 自动处理消息追加，后续 Supervisor 路由节点会判断 `messages[-1]`。State 字段先用 `total=False`，避免初始化时必须填全。

#### Step 3: text2sql 节点（1 天）

[nodes/text2sql.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/agents/nodes/text2sql.py)

核心逻辑：
1. 读取 DuckDB 表结构（`DESCRIBE` + `COMMENT ON` 查字段注释）
2. 构造 System Prompt：注入表结构 DDL + 字段注释 + 要求输出纯 SQL
3. 调用 LLM（`with_structured_output` 或直接纯文本）
4. 正则提取 SQL（处理 LLM 可能输出的 ```sql ... ``` 包裹）

> **坑点**：LLM 常输出 Markdown 代码块，务必用 `re.search(r"```sql?\s*(.*?)```", ..., re.DOTALL)` 或更宽松的正则先清洗再执行。

#### Step 4: run_sql 工具（半天）

放在节点里直接调用 DuckDB：

```python
def run_sql(sql: str, db_path: str) -> pd.DataFrame:
    con = duckdb.connect(db_path, read_only=True)  # 只读连接！
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()
```

#### Step 5: 单节点图编排（半天）

[agents/graph.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/agents/graph.py)

```python
from langgraph.graph import StateGraph, END

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("text2sql", text2sql_node)
    g.add_node("run_sql", run_sql_node)
    g.add_edge("text2sql", "run_sql")
    g.add_edge("run_sql", END)
    g.set_entry_point("text2sql")
    return g.compile()
```

命令行验证：
```python
graph = build_graph()
result = graph.invoke({"messages": [HumanMessage("上个月销量最高的10个商品")]})
print(result["sql_result"])  # 应该输出 DataFrame
```

#### Step 6: FastAPI + SSE（1 天）

[main.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/main.py)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/stream")
async def stream_question(payload: dict):
    question = payload["question"]
    thread_id = payload.get("thread_id", "default")
    
    graph = build_graph()
    
    async def event_generator():
        async for event in graph.astream(
            {"messages": [HumanMessage(question)]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode=["messages", "updates"]
        ):
            # 格式化 SSE 推送
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

#### Step 7: 前端最小对话页（1 天）

[ChatView.vue](file:///d:/Python%20Note/web_server/datapilot/frontend/src/views/ChatView.vue)

- 输入框 + 发送按钮
- EventSource 接收 SSE，逐 token 渲染
- SQL 代码块用 `<pre>` + 语法高亮
- 结果表格用 `<table>` 渲染 DataFrame 转 JSON

### 3.3 M1 验收清单

| # | 验收项 | 预期结果 |
|---|---|---|
| 1 | 命令行问数 | 「上个月销量最高的10个商品」→ 返回正确 SQL + DataFrame |
| 2 | SSE 流式输出 | 能看到 SQL 逐 token 出现 |
| 3 | 只读连接生效 | 执行 `INSERT` / `DELETE` 应抛权限错误 |
| 4 | 前端基本可用 | 能发问题、看 SQL、看表格 |

---

## 四、M2 — 多 Agent + 人工确认（第 2~3 周，项目核心）

### 目标
实现 Supervisor 路由、规则校验、interrupt 人工确认、Checkpointer 断点恢复、Send 并行。

### 4.1 依赖新增

```bash
pip install sqlglot langgraph-checkpoint-sqlite
```

### 4.2 实现清单

#### Step 1: Supervisor 意图路由（1 天）

[nodes/supervisor.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/agents/nodes/supervisor.py)

用 `with_structured_output` 让 LLM 输出固定 JSON：

```python
from pydantic import BaseModel

class SupervisorDecision(BaseModel):
    intent: Literal["chat", "query", "report"]
    reason: str

def supervisor_node(state: AgentState) -> dict:
    llm = ChatOpenAI().with_structured_output(SupervisorDecision)
    decision = llm.invoke(state["messages"])
    return {"intent": decision.intent}
```

图里用条件边路由：
```python
g.add_conditional_edges("supervisor", route_by_intent, {
    "chat": "chat_reply",
    "query": "text2sql",
    "report": "text2sql",  # 报告也先查数
})
```

#### Step 2: sqlglot AST 规则校验（2 天）⭐ 核心面试考点

[nodes/sql_check.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/agents/nodes/sql_check.py)

**必须用 sqlglot 解析 AST，禁止用 LLM 做校验！**

```python
import sqlglot
from sqlglot import exp

def validate_sql(sql: str, allowed_tables: set) -> tuple[bool, str]:
    """返回 (是否通过, 错误信息)"""
    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
    except Exception as e:
        return False, f"SQL 语法错误: {e}"
    
    # 规则 1: 必须是单条 SELECT
    if not isinstance(parsed, exp.Select):
        return False, "只允许 SELECT 语句"
    
    # 规则 2: 禁止多语句（union all 除外，视业务定）
    # sqlglot 已自动处理，parse_one 只取第一条
    
    # 规则 3: 表白名单
    tables = parsed.find_all(exp.Table)
    table_names = {t.name for t in tables}
    if not table_names.issubset(allowed_tables):
        return False, f"非法表: {table_names - allowed_tables}"
    
    # 规则 4: 强制 LIMIT
    has_limit = any(isinstance(child, exp.Limit) for child in parsed.walk())
    if not has_limit:
        return False, "必须带 LIMIT 子句"
    
    # 规则 5: 禁 DML（INSERT/UPDATE/DELETE）
    # parse_one 成功但类型检查覆盖了这点
    
    return True, ""
```

> **关键经验**（来自 LangGraph 项目实战）：校验失败时要把错误信息写入 state，让下一轮 text2sql 能看到校验历史并自我修正。不要在 text2sql 节点"抢写" validation_history，应该在 validate 节点做短路透传。

State 扩展：
```python
class AgentState(TypedDict, total=False):
    # ... M1 字段
    validation_errors: list[str]    # 校验失败历史（供重试用）
    retry_count: int                # 重试次数
```

#### Step 3: interrupt() 人工确认（2 天）⭐ human-in-the-loop

[nodes/sql_check.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/agents/nodes/sql_check.py) 校验通过后：

```python
from langgraph.types import interrupt, Command

def wait_for_approval(state: AgentState):
    # interrupt 暂停图执行，把 SQL 卡片推给前端
    human_response = interrupt({
        "question": "请确认 SQL",
        "sql": state["generated_sql"],
        "options": ["approve", "reject", "modify"]
    })
    
    # 前端点批准后，Command(resume="approve") 恢复这里
    if human_response == "approve":
        return {"approved": True}
    elif human_response == "modify":
        return {"generated_sql": human_response["modified_sql"]}  # 用户改了 SQL
    else:
        return {"approved": False}
```

图编排：
```python
g.add_node("wait_for_approval", wait_for_approval)
g.add_node("run_sql", run_sql_node)
g.add_conditional_edges("wait_for_approval", check_approval, {
    "approved": "run_sql",
    "rejected": END,
    "modify": "run_sql",  # 直接用用户修改后的 SQL 执行
})
```

#### Step 4: FastAPI 恢复端点（1 天）

[api/routes.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/api/routes.py)

```python
@app.post("/approve")
async def approve(payload: dict):
    graph = build_graph()
    graph.update_state(
        {"configurable": {"thread_id": payload["thread_id"]}},
        Command(resume="approve")
    )
    # 重新 stream 后续节点...
```

#### Step 5: Checkpointer 断点恢复（1 天）

```python
from langgraph.checkpoint.sqlite import SqliteSaver

def build_graph():
    memory = SqliteSaver.from_conn_string("checkpoints.db")
    g = StateGraph(AgentState)
    # ... 加节点加边 ...
    return g.compile(checkpointer=memory)
```

`thread_id` 用 `ws-{id}-user-{id}` 格式，不同会话隔离。刷新页面后重新用同一个 thread_id 调用 `graph.stream` 就能续上。

#### Step 6: Send 并行生成图表 + 报告（2 天）

`run_sql` 执行后，用 `Send` API 同时派发两个节点：

```python
from langgraph.graph import Send

def after_run_sql(state: AgentState):
    # 并行发 chart 和 report
    return [
        Send("chart_node", {"sql_result": state["sql_result"], "messages": state["messages"]}),
        Send("report_node", {"sql_result": state["sql_result"], "messages": state["messages"]}),
    ]
```

图编排用 `add_conditional_edges` 把 `Send` 函数接上去。

**chart_node**：用 `with_structured_output` 让 LLM 输出 ECharts option（pydantic 定义 schema）。  
**report_node**：让 LLM 基于数据结果写 3-5 段分析。

#### Step 7: 前端审核卡片 + Trace 页（2 天）

[ApprovalCard.vue](file:///d:/Python%20Note/web_server/datapilot/frontend/src/views/ApprovalCard.vue)：
- 显示 SQL 代码块（带语法高亮）
- 三按钮：批准 / 拒绝 / 修改
- 修改时弹出 textarea 让用户改 SQL

[TraceView.vue](file:///d:/Python%20Note/web_server/datapilot/frontend/src/views/TraceView.vue)（开发者模式）：
- 显示图的执行路径（哪些节点跑了、耗时多少）
- 每个节点的输入输出 JSON

### 4.3 M2 验收清单

| # | 验收项 | 预期结果 |
|---|---|---|
| 1 | 闲聊路由 | 「你好」→ 直接回复问候，不进 text2sql |
| 2 | 规则校验 | 生成 `DROP TABLE` → 被拦截，返回友好提示 |
| 3 | LIMIT 强制 | 生成不带 LIMIT 的 SQL → 被拦截 |
| 4 | interrupt 暂停 | SQL 校验通过后图暂停，前端显示审核卡片 |
| 5 | 批准/拒绝交互 | 点批准 → 继续执行；点拒绝 → 结束会话 |
| 6 | 断点恢复 | 刷新页面后重新 stream，图从 wait_for_approval 继续 |
| 7 | 并行输出 | 一次提问同时产出 ECharts 图 + 文字报告 |

---

## 五、M3 — MCP 化（第 4 周）

### 目标
把数据库能力从本地函数替换为 MCP Server，验证「换数据库只改配置不动图代码」。

### 5.1 依赖新增

```bash
pip install mcp langchain-mcp-adapters
```

### 5.2 实现清单

#### Step 1: 写 MCP Server（1 天）

[mcp_server/server.py](file:///d:/Python%20Note/web_server/datapilot/backend/app/mcp_server/server.py)

```python
from mcp.server.fastmcp import FastMCP
import duckdb

mcp = FastMCP("datapilot-db")
con = duckdb.connect("data/demo.duckdb", read_only=True)

@mcp.tool()
def list_tables() -> list[dict]:
    """返回所有表名和行数"""
    rows = con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()
    return [{"name": r[0]} for r in rows]

@mcp.tool()
def get_schema(table_name: str) -> dict:
    """返回指定表的列名、类型、注释"""
    cols = con.execute(f"DESCRIBE {table_name}").fetchall()
    comments = con.execute(f"""
        SELECT column_name, comment 
        FROM duckdb_columns() 
        WHERE table_name = '{table_name}' AND comment IS NOT NULL AND comment != ''
    """).fetchall()
    comment_map = {c[0]: c[1] for c in comments}
    return {
        "table": table_name,
        "columns": [{"name": c[0], "type": c[1], "comment": comment_map.get(c[0], "")} for c in cols]
    }

@mcp.tool()
def run_sql(sql: str) -> str:
    """执行只读 SQL，返回 JSON 字符串结果"""
    df = con.execute(sql).fetchdf()
    return df.to_json(orient="records", force_ascii=False)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8081)
```

#### Step 2: LangGraph 加载 MCP 工具（1 天）

替换掉 M1/M2 里直接调 DuckDB 的逻辑：

```python
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.streamable_http import streamablehttp_client

async def get_db_tools():
    async with streamablehttp_client("http://localhost:8081/mcp") as client:
        session = await client.create_session()
        tools = await load_mcp_tools(session)
        # tools 里现在有 list_tables / get_schema / run_sql
        return tools
```

在 `text2sql` 节点和 `run_sql` 节点里，把这些 MCP tools 绑定给 `ToolNode` 或者直接用。

#### Step 3: 回归测试（半天）

跑 M2 的全部验收用例，确保行为不变。

### 5.3 M3 验收清单

| # | 验收项 | 预期结果 |
|---|---|---|
| 1 | MCP Server 独立运行 | `python mcp_server/server.py` 启动后可通过 `curl` 调通 |
| 2 | 图通过 MCP 取数据 | 所有 DB 调用都走 MCP 协议，后端日志可见 JSON-RPC |
| 3 | 换库只改配置 | 把 DuckDB 换成 PostgreSQL，只需改 MCP Server 里的连接串，图代码零改动 |

---

## 六、M4 — 可观测 + 评测（第 5 周，最大差异化）

### 目标
Langfuse 全链路 Trace + 自建评测集 + LLM-as-judge 自动评分。

### 6.1 Langfuse 接入（1 天）

**方案 A（推荐）**：用 Cloud 免费版，注册拿 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`  
**方案 B**：自托管，`docker-compose up langfuse`

```bash
pip install langfuse langchain-langfuse
```

在 `graph.stream` 里加 Callback：

```python
from langfuse.callback import CallbackHandler

handler = CallbackHandler(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
)

graph.stream(..., config={"callbacks": [handler]})
```

在各节点打 metadata：
```python
handler = CallbackHandler(...)
handler.start_span(name="text2sql", metadata={"thread_id": ..., "intent": ...})
# ... 节点逻辑 ...
handler.end_span(output={"sql": generated_sql})
```

### 6.2 评测集构建（持续积累）

`evals/dataset.jsonl`，每行一个 JSON：

```json
{"id": 1, "question": "上个月销量最高的10个商品", "golden_sql": "SELECT product_name, SUM(quantity) as sales FROM orders ...", "category": "aggregation"}
{"id": 2, "question": "华东区和华南区的销售额对比", "golden_sql": "...", "category": "join"}
```

从 M1 起每次调问答一个新的就随手加一行，目标 50 题。按 category 分：`aggregation` / `join` / `filter` / `time_series` / `subquery`。

### 6.3 评测脚本（2 天）

[evals/run_eval.py](file:///d:/Python%20Note/web_server/datapilot/backend/evals/run_eval.py)

核心逻辑（结果集对比，比字符串对比公平）：

```python
def evaluate_one(graph, db_path, item):
    # 1. 跑图拿模型 SQL
    result = graph.invoke({"messages": [HumanMessage(item["question"])]})
    model_sql = result["generated_sql"]
    
    # 2. 各自查一遍，比对结果集
    model_df = duckdb.connect(db_path).execute(model_sql).fetchdf()
    golden_df = duckdb.connect(db_path).execute(item["golden_sql"]).fetchdf()
    
    # 结果集相等判断（忽略列顺序）
    if model_df.equals(golden_df.sort_index(axis=1)):
        return {"pass": True, "score": 1.0}
    
    # 3. 不一致时 LLM-as-judge 兜底
    judge_prompt = f"""
    问题: {item['question']}
    模型SQL结果: {model_df.to_string()}
    标准答案SQL结果: {golden_df.to_string()}
    两个结果集在语义上是否等价？（允许列名不同、排序不同、NULL 位置不同）
    只回答 YES 或 NO，一行理由。
    """
    judge = ChatOpenAI()
    judge_result = judge.invoke(judge_prompt).content
    is_equivalent = judge_result.strip().startswith("YES")
    
    return {"pass": is_equivalent, "model_sql": model_sql, "golden_sql": item["golden_sql"]}
```

输出 Markdown 准确率报告：

```
## Text2SQL 评测报告

| 类别 | 题数 | 通过 | 准确率 |
|------|------|------|--------|
| aggregation | 20 | 17 | 85% |
| join | 15 | 12 | 80% |
| **总计** | **50** | **42** | **84%** |
```

### 6.4 GitHub Actions 自动跑（可选）

```yaml
# .github/workflows/eval.yml
name: Eval
on: [push, pull_request]
jobs:
  run-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r backend/requirements.txt
      - run: python backend/data/seed.py
      - run: python backend/evals/run_eval.py
```

### 6.5 M4 验收清单

| # | 验收项 | 预期结果 |
|---|---|---|
| 1 | Langfuse Trace 可见 | 每条对话在 Langfuse 控制台有完整 Trace，含各节点耗时和 token 数 |
| 2 | 评测集 50 题 | `dataset.jsonl` 累计 50+ 题，覆盖 5 个 category |
| 3 | 结果集对比跑通 | 模型 SQL 和 golden SQL 都能执行，比结果集不比字符串 |
| 4 | 准确率报告 | 输出 Markdown，按 category 分项统计 |
| 5 | LLM-as-judge 兜底 | 结果集不一致时自动进入 judge 分支 |

---

## 七、M5 — 前端收尾与交付（第 6 周）

### 7.1 实现清单

| 任务 | 工期 | 说明 |
|---|---|---|
| Trace 查看页打磨 | 1 天 | 开发者模式，显示节点耗时条、Token 用量 |
| SQL 审核卡片打磨 | 1 天 | Monaco Editor 内嵌，支持语法高亮 + 格式化 |
| 图表交互 | 1 天 | ECharts tooltip、下钻、导出 PNG |
| docker-compose 一键起 | 半天 | backend + frontend + langfuse + mcp_server |
| README 编写 | 2 天 | 见下 |
| 演示 GIF | 半天 | 录 30 秒问数全流程 |

### 7.2 README 结构

```markdown
# DataPilot — 企业级多 Agent 数据分析平台

## 架构图（Mermaid / draw.io）
## 快速开始（docker-compose 一键起）
## 核心特性
  - Human-in-the-loop：interrupt() 人工确认 SQL
  - 规则校验：sqlglot AST 静态审查，非 LLM
  - MCP 协议：换数据库只改配置
  - Langfuse 全链路 Trace
  - 自建评测集 + LLM-as-judge
## 演示 GIF
## 评测准确率报告截图
## 技术选型说明
## 与"手写框架"的关系
  - 为什么选 LangGraph 而非自研状态机
  - 为什么用 sqlglot 而非 LLM 做校验
  - MCP 协议 vs 直接调用的权衡
## 目录结构
## License
```

### 7.3 docker-compose.yml 核心结构

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [mcp_server, langfuse]
    
  mcp_server:
    build: ./backend
    command: python -m app.mcp_server.server
    ports: ["8081:8081"]
    
  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    
  langfuse:
    image: langfuse/langfuse:latest
    ports: ["3000:3000"]
```

---

## 八、时间线总览

| 阶段 | 周 | 交付物 |
|---|---|---|
| M1 单 Agent | W1 | DuckDB + 单节点图 + FastAPI SSE + 最小前端 |
| M2 多 Agent + 人工确认 | W2-W3 | Supervisor + sqlglot 校验 + interrupt + Checkpointer + Send 并行 |
| M3 MCP 化 | W4 | MCP Server + LangGraph MCP Client 接入 |
| M4 可观测 + 评测 | W5 | Langfuse Trace + 50 题评测集 + LLM-as-judge |
| M5 收尾交付 | W6 | 前端打磨 + docker-compose + README + 演示 GIF |

---

## 九、面试高频考点速查

| 面试官问 | 你答 |
|---|---|
| "怎么保证 SQL 安全？" | sqlglot AST 静态审查，禁止 DML，强制 LIMIT，表白名单，只读 DuckDB 连接。**不用 LLM 做校验**，因为不可控且不可审计。 |
| "Human-in-the-loop 怎么实现的？" | LangGraph 的 `interrupt()` 在 sql_check 通过后暂停，SQL 卡片推前端，用户点批准后后端 `Command(resume=...)` 恢复执行。SqliteSaver Checkpointer 保证刷新页面还能续上。 |
| "MCP 协议解决了什么问题？" | 把数据库能力从代码硬耦合变成协议化工具，图代码只调 MCP tools，换数据库只改 MCP Server 的连接配置。LangGraph 原生支持 MCP Client 接入。 |
| "怎么衡量 Agent 效果？" | 自建 Text2SQL 评测集 50 题，用**结果集对比**比模型 SQL 和 golden SQL 的执行结果（比字符串公平），不一致时 LLM-as-judge 兜底。Langfuse 看全链路 Trace 和 token 成本。 |
| "LangGraph 和自己写状态机有什么区别？" | LangGraph 提供 Checkpointer（断点恢复）、Send API（并行）、interrupt（human-in-the-loop）、多种 stream_mode，这些自研要写好几百行还容易出 bug。 |
| "并行生成图表和报告怎么做的？" | run_sql 节点返回后用 `Send` API 同时派发 chart_node 和 report_node，它们独立执行、各自产出，合并回图的 State。 |

---

## 十、踩坑备忘（从实战经验提炼）

1. **LLM 输出的 SQL 总有 Markdown 包裹**：先正则清洗 ```sql ... ``` 再执行，不要直接丢给 DuckDB。
2. **Checkpointer 初始化**：`SqliteSaver.from_conn_string("xxx.db")`，不是直接 `SqliteSaver(...)`，后者在某些版本会崩。
3. **sqlglot 方言指定**：`parse_one(sql, read="duckdb")`，否则函数名（`LIST`、`STRUCT`）解析会报错。
4. **interrupt 在 Send 并行图里**：如果 interrupt 节点后面接 Send，要确保 Send 在 `approved` 条件下才触发，不要无条件发。
5. **评测时结果集对比**：`df.equals(other.sort_index(axis=1))` 忽略列顺序差异；时间戳精度不同要先 `round`。
6. **前端 SSE 连接泄漏**：EventSource 用完要 `.close()`，页面切换时记得清理。
