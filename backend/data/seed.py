"""
DataPilot Demo 数据库造数脚本
生成 products / regions / orders 三张表，共 ~12 万行订单数据（几秒完成）
"""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# 确保从项目根目录运行
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "backend" / "data" / "demo.duckdb"


def seed(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))

    # 1. 建表
    schema_sql = (PROJECT_ROOT / "backend" / "data" / "schema.sql").read_text(encoding="utf-8")
    con.execute(schema_sql)
    print("✅ 建表完成")

    # 2. regions
    regions_df = pd.DataFrame({
        "region_id":   [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "region_name": ["华东","华东","华东","华南","华南","华南",
                        "华北","华北","华北","西南","西南","西南"],
        "province":    ["上海","江苏","浙江","广东","福建","广西",
                        "北京","天津","河北","四川","重庆","云南"],
    })
    con.execute("DELETE FROM regions")
    con.register("regions_df", regions_df)
    con.execute("INSERT INTO regions SELECT * FROM regions_df")
    print("✅ regions: 12 行")

    # 3. products
    rng = np.random.default_rng(42)
    categories = ["电子产品", "服饰", "食品", "家居"]
    product_names = {
        "电子产品": ["智能手机","笔记本电脑","无线耳机","智能手表","平板",
                    "蓝牙音箱","移动电源","机械键盘","显示器","路由器"],
        "服饰":     ["男士T恤","女士连衣裙","运动外套","牛仔裤","羽绒服",
                    "休闲鞋","双肩包","皮带","袜子套装","棒球帽"],
        "食品":     ["坚果礼盒","咖啡豆","进口饼干","休闲零食礼包","蜂蜜",
                    "麦片","茶叶礼盒","方便面","瓶装水","巧克力"],
        "家居":     ["台灯","床上四件套","收纳箱","保温杯","空气净化器",
                    "扫地机器人","晾衣架","锅具套装","纸巾","香薰"],
    }

    product_rows = []
    pid = 1
    for cat in categories:
        for name in product_names[cat]:
            price = round(rng.uniform(9.9, 9999), 2)
            cost = round(price * rng.uniform(0.3, 0.7), 2)
            product_rows.append((pid, f"{cat}-{name}", cat, price, cost))
            pid += 1

    products_df = pd.DataFrame(product_rows,
                    columns=["product_id", "product_name", "category", "unit_price", "cost_price"])
    con.execute("DELETE FROM products")
    con.register("products_df", products_df)
    con.execute("INSERT INTO products SELECT * FROM products_df")
    print(f"✅ products: {len(products_df)} 行")

    # 4. orders —— 向量化生成，几秒完成
    # 把价格建成 dict，避免每行 SQL 查询
    price_map = dict(zip(products_df["product_id"], products_df["unit_price"]))

    # 滚动窗口：数据覆盖「今天往前 24 个月」到「昨天」
    # 这样无论哪天跑，「上个月/上季度/今年」这类相对时间问法都有数据
    today = pd.Timestamp.today().normalize()
    start_dt = (today - pd.DateOffset(months=24)).normalize()
    end_dt = today - pd.Timedelta(days=1)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    total_days = (end_dt - start_dt).days + 1

    # 每天 200 单（周末 240）≈ 12 万行
    daily = 200
    volumes = []
    for i in range(total_days):
        d = pd.to_datetime(start_date) + pd.Timedelta(days=i)
        volumes.append(int(daily * (1.2 if d.weekday() >= 5 else 1.0)))
    total_orders = sum(volumes)
    print(f"  orders 待生成: {total_orders:,} 行 ...", end=" ", flush=True)

    # 一次性向量化生成所有订单
    all_dates = []
    for i, d in enumerate(volumes):
        date_str = (pd.to_datetime(start_date) + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        all_dates.extend([date_str] * d)

    dates_arr   = np.array(all_dates)
    prod_arr    = rng.integers(1, 41, size=total_orders)
    region_arr  = rng.integers(1, 13, size=total_orders)
    qty_arr     = rng.integers(1, 11, size=total_orders)

    # 根据 product_id 查价格 → 金额
    price_vec = np.array([price_map[p] for p in prod_arr])
    amount_arr = np.round(price_vec * qty_arr * rng.uniform(0.9, 1.1, total_orders), 2)

    orders_df = pd.DataFrame({
        "order_id":   np.arange(1, total_orders + 1),
        "product_id": prod_arr,
        "region_id":  region_arr,
        "quantity":   qty_arr,
        "amount":     amount_arr,
        "order_date": dates_arr,
    })

    con.execute("DELETE FROM orders")
    con.register("orders_df", orders_df)
    con.execute("INSERT INTO orders SELECT * FROM orders_df")
    print("完成")

    total = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"✅ orders: {total:,} 行")

    con.close()
    print(f"\n🎉 数据库已生成: {db_path}  大小: {db_path.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    seed()
