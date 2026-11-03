"""
FastAPI 入口 —— 只做应用装配

路由实现见 api/routes.py，业务编排见 agents/graph.py
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router

app = FastAPI(title="DataPilot", version="0.1.0")

# CORS（前端开发期间允许任意来源，生产需收窄）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
