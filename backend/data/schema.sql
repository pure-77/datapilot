-- ============================================================
-- DataPilot Demo 数据库 Schema
-- 三张表：产品、区域、订单 —— 覆盖常见 Text2SQL 查询场景
-- ============================================================

-- 区域表
CREATE TABLE IF NOT EXISTS regions (
    region_id   INTEGER PRIMARY KEY,          -- 区域 ID
    region_name VARCHAR(32),                 -- 区域名称（如：华东、华南）
    province    VARCHAR(32)                  -- 省份
);

COMMENT ON TABLE regions IS '销售区域表';
COMMENT ON COLUMN regions.region_id   IS '区域唯一标识';
COMMENT ON COLUMN regions.region_name IS '区域名称：华东/华南/华北/西南';
COMMENT ON COLUMN regions.province    IS '省份';

-- 产品表
CREATE TABLE IF NOT EXISTS products (
    product_id    INTEGER PRIMARY KEY,       -- 产品 ID
    product_name  VARCHAR(128),              -- 产品名称
    category      VARCHAR(32),               -- 产品品类
    unit_price    DECIMAL(12, 2),            -- 单价
    cost_price    DECIMAL(12, 2)             -- 成本价
);

COMMENT ON TABLE products IS '产品主数据表';
COMMENT ON COLUMN products.product_id   IS '产品唯一标识';
COMMENT ON COLUMN products.product_name IS '产品名称';
COMMENT ON COLUMN products.category     IS '品类：电子产品/服饰/食品/家居';
COMMENT ON COLUMN products.unit_price   IS '销售单价（元）';
COMMENT ON COLUMN products.cost_price   IS '成本价（元）';

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    order_id    INTEGER PRIMARY KEY,         -- 订单 ID
    product_id  INTEGER,                     -- 关联产品
    region_id   INTEGER,                     -- 关联区域
    quantity    INTEGER,                     -- 购买数量
    amount      DECIMAL(12, 2),              -- 订单金额（元）
    order_date  DATE                         -- 下单日期
);

COMMENT ON TABLE orders IS '销售订单表（事实表）';
COMMENT ON COLUMN orders.order_id   IS '订单唯一标识';
COMMENT ON COLUMN orders.product_id IS '外键 → products.product_id';
COMMENT ON COLUMN orders.region_id  IS '外键 → regions.region_id';
COMMENT ON COLUMN orders.quantity   IS '购买数量';
COMMENT ON COLUMN orders.amount     IS '订单实际金额（元）';
COMMENT ON COLUMN orders.order_date IS '下单日期';
