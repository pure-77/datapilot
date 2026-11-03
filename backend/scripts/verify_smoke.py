"""
快速验证脚本 —— 不调用 LLM，只测 DuckDB + 图结构能不能跑

用法:
    python backend/scripts/verify_smoke.py
"""
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def main():
    db_path = PROJECT_ROOT / "backend" / "data" / "demo.duckdb"

    # 1. 检查 DB 是否存在
    if not db_path.exists():
        print("❌ demo.duckdb 还没生成，请先跑: python backend/data/seed.py")
        return

    con = duckdb.connect(str(db_path), read_only=True)

    # 2. 检查表
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()]
    print(f"✅ 数据库表: {tables}")

    # 3. 检查表行数
    for t in tables:
        cnt = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"   {t}: {cnt:,} 行")

    # 4. 跑一条模拟 SQL 验证链路
    sql = """
        SELECT p.product_name, SUM(o.quantity) AS total_sold
        FROM orders o JOIN products p ON o.product_id = p.product_id
        WHERE o.order_date >= '2024-12-01' AND o.order_date < '2025-01-01'
        GROUP BY p.product_name
        ORDER BY total_sold DESC
        LIMIT 5
    """
    print("\n✅ 模拟 SQL 查询 (上个月 TOP 5):")
    print(f"   {sql.strip()[:80]}...")
    df = con.execute(sql).fetchdf()
    print(df.to_string(index=False))

    con.close()
    print("\n🎉 烟雾测试通过！可以用真实 LLM 调 graph.py 了")


if __name__ == "__main__":
    main()
