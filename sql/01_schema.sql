-- АС планирования рациона питания
-- Схема БД. PostgreSQL 14+

DROP TABLE IF EXISTS menu_categories CASCADE;
DROP TABLE IF EXISTS menu_items     CASCADE;
DROP TABLE IF EXISTS menu           CASCADE;
DROP TABLE IF EXISTS ration_items   CASCADE;
DROP TABLE IF EXISTS ration         CASCADE;
DROP TABLE IF EXISTS dish_products  CASCADE;
DROP TABLE IF EXISTS dish           CASCADE;
DROP TABLE IF EXISTS user_excludes  CASCADE;
DROP TABLE IF EXISTS user_favorites CASCADE;
DROP TABLE IF EXISTS product        CASCADE;
DROP TABLE IF EXISTS category       CASCADE;
DROP TABLE IF EXISTS app_user       CASCADE;

CREATE TABLE app_user (
    id              SERIAL PRIMARY KEY,
    login           VARCHAR(50)  UNIQUE NOT NULL,
    password_hash   VARCHAR(128) NOT NULL,
    role            VARCHAR(20)  NOT NULL CHECK (role IN ('admin','user')),
    full_name       VARCHAR(100) NOT NULL,
    age             INTEGER      CHECK (age > 0 AND age < 130),
    sex             VARCHAR(10)  CHECK (sex IN ('М','Ж')),
    weight          NUMERIC(5,2) CHECK (weight > 0),
    height          NUMERIC(5,2) CHECK (height > 0),
    activity_level  VARCHAR(50),
    goal            VARCHAR(50)
);

CREATE TABLE category (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE product (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    calories      NUMERIC(7,2) NOT NULL CHECK (calories >= 0),
    proteins      NUMERIC(6,2) NOT NULL CHECK (proteins >= 0),
    fats          NUMERIC(6,2) NOT NULL CHECK (fats     >= 0),
    carbs         NUMERIC(6,2) NOT NULL CHECK (carbs    >= 0),
    category_id   INTEGER NOT NULL REFERENCES category(id) ON DELETE RESTRICT
);

CREATE TABLE dish (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    description  VARCHAR(500),
    dish_type    VARCHAR(50)
);

CREATE TABLE dish_products (
    dish_id      INTEGER NOT NULL REFERENCES dish(id)    ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES product(id) ON DELETE RESTRICT,
    grams        NUMERIC(7,2) NOT NULL CHECK (grams > 0),
    PRIMARY KEY (dish_id, product_id)
);

CREATE TABLE ration (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,
    date_start    DATE NOT NULL,
    date_end      DATE NOT NULL,
    CHECK (date_start <= date_end)
);

CREATE TABLE menu (
    id          SERIAL PRIMARY KEY,
    ration_id   INTEGER NOT NULL REFERENCES ration(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    meal_type   VARCHAR(50)  NOT NULL  -- завтрак/обед/ужин/перекус
);

CREATE TABLE menu_items (
    menu_id   INTEGER NOT NULL REFERENCES menu(id) ON DELETE CASCADE,
    dish_id   INTEGER NOT NULL REFERENCES dish(id) ON DELETE RESTRICT,
    portion_g NUMERIC(7,2) NOT NULL CHECK (portion_g > 0),
    PRIMARY KEY (menu_id, dish_id)
);

CREATE TABLE menu_categories (
    menu_id     INTEGER NOT NULL REFERENCES menu(id)     ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
    PRIMARY KEY (menu_id, category_id)
);

CREATE TABLE user_excludes (
    user_id    INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES product(id)  ON DELETE CASCADE,
    PRIMARY KEY (user_id, product_id)
);

CREATE TABLE user_favorites (
    user_id INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    dish_id INTEGER NOT NULL REFERENCES dish(id)     ON DELETE CASCADE,
    PRIMARY KEY (user_id, dish_id)
);

-- Представление: КБЖУ блюда (на 100 г порции, агрегированные значения)
CREATE OR REPLACE VIEW dish_nutrition AS
SELECT d.id          AS dish_id,
       d.name        AS dish_name,
       COALESCE(SUM(dp.grams * p.calories / 100.0), 0) AS total_calories,
       COALESCE(SUM(dp.grams * p.proteins / 100.0), 0) AS total_proteins,
       COALESCE(SUM(dp.grams * p.fats     / 100.0), 0) AS total_fats,
       COALESCE(SUM(dp.grams * p.carbs    / 100.0), 0) AS total_carbs,
       COALESCE(SUM(dp.grams), 0)                       AS total_grams
FROM   dish d
LEFT JOIN dish_products dp ON dp.dish_id = d.id
LEFT JOIN product       p  ON p.id       = dp.product_id
GROUP BY d.id, d.name;

-- Представление: суммарная калорийность рациона
CREATE OR REPLACE VIEW ration_nutrition AS
SELECT r.id AS ration_id,
       r.name AS ration_name,
       r.user_id,
       COALESCE(SUM(mi.portion_g * dn.total_calories / NULLIF(dn.total_grams,0)),0) AS total_calories,
       COALESCE(SUM(mi.portion_g * dn.total_proteins / NULLIF(dn.total_grams,0)),0) AS total_proteins,
       COALESCE(SUM(mi.portion_g * dn.total_fats     / NULLIF(dn.total_grams,0)),0) AS total_fats,
       COALESCE(SUM(mi.portion_g * dn.total_carbs    / NULLIF(dn.total_grams,0)),0) AS total_carbs
FROM   ration r
LEFT JOIN menu       m  ON m.ration_id = r.id
LEFT JOIN menu_items mi ON mi.menu_id  = m.id
LEFT JOIN dish_nutrition dn ON dn.dish_id = mi.dish_id
GROUP BY r.id, r.name, r.user_id;
