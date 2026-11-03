"""
全局配置 —— 从 .env 加载
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 加载 .env（项目根目录）
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


# ---------- 大模型 ----------
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# ---------- 数据库 ----------
_duckdb_raw = os.getenv("DUCKDB_PATH", str(PROJECT_ROOT / "backend" / "data" / "demo.duckdb"))
# 如果是相对路径，拼到 PROJECT_ROOT；如果已经是绝对路径，直接用
DUCKDB_PATH = str((PROJECT_ROOT / _duckdb_raw).resolve()) if not Path(_duckdb_raw).is_absolute() else _duckdb_raw


def get_llm_config() -> dict:
    """返回 dict 形式的 LLM 配置，便于调试时打印（注意不要打印 API_KEY）"""
    return {
        "base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "api_key_set": bool(LLM_API_KEY),
    }


if __name__ == "__main__":
    print("配置加载结果:")
    for k, v in get_llm_config().items():
        print(f"  {k}: {v}")
    print(f"  duckdb_path: {DUCKDB_PATH}")
    print(f"  api_key 前 4 位: {LLM_API_KEY[:4] if LLM_API_KEY else '(未配置)'}")
