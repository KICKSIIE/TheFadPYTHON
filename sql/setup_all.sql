-- THE FAD: full setup in ONE script. Open pgAdmin > THEFAD database > Query Tool,
-- paste everything, press F5. It runs as one transaction: if anything fails,
-- NOTHING is applied, and the Messages tab shows the error. Safe to re-run.

-- ===== 00_schema_changes.sql =====
-- Run FIRST. Products and staff that already have sales or logs cannot be deleted,
-- so the app "deactivates" them instead.
ALTER TABLE thefad.product ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE thefad.users   ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Product details: description, size, photo.
-- Each SIZE is its own product row (own stock), so inventory, POS, promos and refunds keep working.
-- Photos live in the database so they travel with pg_dump backups and every teammate sees them.
-- A product can have several photos; sizes of the same product share the same stored images.
CREATE TABLE IF NOT EXISTS thefad.product_image (
    image_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mime_type   VARCHAR(30) NOT NULL CHECK (mime_type IN ('image/jpeg', 'image/png', 'image/webp')),
    image_data  BYTEA NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP(0)
);

ALTER TABLE thefad.product ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE thefad.product ADD COLUMN IF NOT EXISTS size VARCHAR(20);
-- Optional color. A product (style) has one row per color and size combination.
ALTER TABLE thefad.product ADD COLUMN IF NOT EXISTS color VARCHAR(30);

-- display_name must include the color. A generated column cannot be altered, so an older one
-- (without color) is dropped here and re-created below.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute a JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE a.attrelid = 'thefad.product'::regclass AND a.attname = 'display_name'
                  AND pg_get_expr(d.adbin, d.adrelid) NOT LIKE '%color%') THEN
        ALTER TABLE thefad.product DROP COLUMN display_name;
    END IF;
END
$$;

-- "Denim Jacket - Black (M)": used wherever one variant row is shown (POS, inventory, receipts)
ALTER TABLE thefad.product ADD COLUMN IF NOT EXISTS display_name VARCHAR(200)
    GENERATED ALWAYS AS ((product_name::text ||
        CASE WHEN color IS NULL OR color = '' THEN '' ELSE ' - ' || color END ||
        CASE WHEN size  IS NULL OR size  = '' THEN '' ELSE ' (' || size || ')' END)::varchar(200)) STORED;

-- Which photos belong to which product row, in what order (lowest sort_order is the cover).
CREATE TABLE IF NOT EXISTS thefad.product_photo (
    product_id INT NOT NULL REFERENCES thefad.product(product_id) ON DELETE CASCADE,
    image_id   INT NOT NULL REFERENCES thefad.product_image(image_id) ON DELETE CASCADE,
    sort_order INT NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, image_id)
);
CREATE INDEX IF NOT EXISTS index_product_photo_image_id ON thefad.product_photo (image_id);

-- Upgrade from the earlier one-photo design (product.image_id), if it was ever installed.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'thefad' AND table_name = 'product' AND column_name = 'image_id') THEN
        INSERT INTO thefad.product_photo (product_id, image_id, sort_order)
        SELECT product_id, image_id, 1 FROM thefad.product WHERE image_id IS NOT NULL
        ON CONFLICT DO NOTHING;
        ALTER TABLE thefad.product DROP COLUMN image_id;
    END IF;
END
$$;

-- Attendance and payroll
-- A short reason when a shift is added or corrected by an admin or after a missed clock-out.
ALTER TABLE thefad.daily_time_record ADD COLUMN IF NOT EXISTS note VARCHAR(200);

-- First day a staff member works. Absent days are counted from here, never before.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'thefad' AND table_name = 'users' AND column_name = 'hired_on') THEN
        ALTER TABLE thefad.users ADD COLUMN hired_on DATE NOT NULL DEFAULT CURRENT_DATE;
        UPDATE thefad.users u
           SET hired_on = COALESCE((SELECT MIN(t.time_in)::date FROM thefad.daily_time_record t
                                     WHERE t.user_id = u.user_id), CURRENT_DATE);
    END IF;
END
$$;

-- Shift schedule and overtime permission (both managed by an admin)
-- One row holding the regular shift: time in, time out and the grace period for clocking in.
CREATE TABLE IF NOT EXISTS thefad.shift_setting (
    setting_id    SMALLINT PRIMARY KEY DEFAULT 1 CHECK (setting_id = 1),
    shift_start   TIME NOT NULL DEFAULT '09:00',
    shift_end     TIME NOT NULL DEFAULT '17:00',
    grace_minutes INT  NOT NULL DEFAULT 15 CHECK (grace_minutes BETWEEN 0 AND 120),
    updated_at    TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP(0),
    CHECK (shift_end > shift_start)
);
INSERT INTO thefad.shift_setting (setting_id) VALUES (1) ON CONFLICT DO NOTHING;

-- An admin allows one person to work overtime on one day, from start_time to end_time,
-- with a grace period for clocking in.
CREATE TABLE IF NOT EXISTS thefad.overtime_permit (
    permit_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       INT  NOT NULL REFERENCES thefad.users(user_id),
    work_date     DATE NOT NULL,
    start_time    TIME NOT NULL,
    end_time      TIME NOT NULL,
    grace_minutes INT  NOT NULL DEFAULT 15 CHECK (grace_minutes BETWEEN 0 AND 120),
    note          VARCHAR(200),
    created_by    INT REFERENCES thefad.users(user_id),
    created_at    TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP(0),
    CHECK (end_time > start_time),
    UNIQUE (user_id, work_date)
);

-- Overtime is clocked as its own record, linked to the permit that allowed it.
ALTER TABLE thefad.daily_time_record ADD COLUMN IF NOT EXISTS shift_type VARCHAR(10) NOT NULL DEFAULT 'Regular'
    CHECK (shift_type IN ('Regular', 'Overtime'));
ALTER TABLE thefad.daily_time_record ADD COLUMN IF NOT EXISTS permit_id INT REFERENCES thefad.overtime_permit(permit_id);

-- ===== 01_auth.sql =====
-- Run once against the THEFAD database (pgAdmin Query Tool or psql).
-- Gives the web app one safe way to check a login. The app never reads password_hash.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION thefad.fn_login_user(p_username VARCHAR, p_password TEXT)
RETURNS TABLE (user_id INT, username VARCHAR, first_name VARCHAR, last_name VARCHAR, user_type VARCHAR)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT u.user_id, u.username, u.first_name, u.last_name, u.user_type
      FROM thefad.users u
     WHERE u.username = p_username
       AND u.is_active
       AND u.password_hash = crypt(p_password, u.password_hash);
END;
$$;

REVOKE ALL ON FUNCTION thefad.fn_login_user(VARCHAR, TEXT) FROM PUBLIC;
-- PHASE 2: GRANT EXECUTE ON FUNCTION thefad.fn_login_user(VARCHAR, TEXT) TO fad_app;

-- ===== 02_dev_seed.sql =====
-- DEV ONLY. Two test accounts so everyone can sign in locally.
--   dev_admin    / Admin@1234
--   dev_cashier  / Cashier@1234
INSERT INTO thefad.users (username, email, first_name, last_name, user_type, password_hash, station)
SELECT 'dev_admin', 'dev_admin@thefad.local', 'Dev', 'Admin', 'AD',
       crypt('Admin@1234', gen_salt('bf')), NULL
WHERE NOT EXISTS (SELECT 1 FROM thefad.users WHERE username = 'dev_admin');

INSERT INTO thefad.users (username, email, first_name, last_name, user_type, password_hash, station)
SELECT 'dev_cashier', 'dev_cashier@thefad.local', 'Dev', 'Cashier', 'CA',
       crypt('Cashier@1234', gen_salt('bf')), 'Counter 1'
WHERE NOT EXISTS (SELECT 1 FROM thefad.users WHERE username = 'dev_cashier');

-- ===== 03_wave1_routines.sql =====
-- Wave 1: categories, products, staff, attendance. Run after 00, 01, 02.
-- Safe to re-run (CREATE OR REPLACE).

------------------------------------------------------------------ CATEGORIES
CREATE OR REPLACE FUNCTION thefad.fn_list_categories()
RETURNS TABLE (category_id INT, category_name VARCHAR, display_order INT, product_count BIGINT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT c.category_id, c.category_name, c.display_order, COUNT(p.product_id)
      FROM thefad.category c
      LEFT JOIN thefad.product p ON p.category_id = c.category_id
     GROUP BY c.category_id, c.category_name, c.display_order
     ORDER BY c.display_order, c.category_name;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_create_category(
    IN p_category_name VARCHAR, IN p_display_order INT, INOUT p_category_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF p_category_name IS NULL OR length(trim(p_category_name)) = 0 THEN
        RAISE EXCEPTION 'Category name is required.';
    END IF;
    IF COALESCE(p_display_order, 0) < 0 THEN
        RAISE EXCEPTION 'Display order cannot be negative.';
    END IF;
    INSERT INTO thefad.category (category_name, display_order)
    VALUES (trim(p_category_name), COALESCE(p_display_order, 0))
    RETURNING category_id INTO p_category_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'A category named "%" already exists.', trim(p_category_name);
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_update_category(
    IN p_category_id INT, IN p_category_name VARCHAR, IN p_display_order INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF p_category_name IS NULL OR length(trim(p_category_name)) = 0 THEN
        RAISE EXCEPTION 'Category name is required.';
    END IF;
    IF COALESCE(p_display_order, 0) < 0 THEN
        RAISE EXCEPTION 'Display order cannot be negative.';
    END IF;
    UPDATE thefad.category
       SET category_name = trim(p_category_name), display_order = COALESCE(p_display_order, 0)
     WHERE category_id = p_category_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Category not found.'; END IF;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'A category named "%" already exists.', trim(p_category_name);
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_delete_category(IN p_category_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM thefad.product WHERE category_id = p_category_id) THEN
        RAISE EXCEPTION 'This category still has products. Move or deactivate them first.';
    END IF;
    DELETE FROM thefad.category WHERE category_id = p_category_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Category not found.'; END IF;
END;
$$;

------------------------------------------------------------------- PRODUCTS
-- A "product" (style) = rows sharing product_name + category_id. Each row is one color/size
-- variant with its own stock. Old signatures are dropped so this file can be re-run after upgrades.
DROP FUNCTION  IF EXISTS thefad.fn_list_products(TEXT, INT, BOOLEAN);
DROP FUNCTION  IF EXISTS thefad.fn_get_product(INT);
DROP FUNCTION  IF EXISTS thefad.fn_list_sizes(INT);
DROP PROCEDURE IF EXISTS thefad.sp_create_product(VARCHAR, NUMERIC, INT, INT);
DROP PROCEDURE IF EXISTS thefad.sp_create_product(VARCHAR, NUMERIC, INT, TEXT, TEXT, VARCHAR, BYTEA, INT);
DROP PROCEDURE IF EXISTS thefad.sp_create_product(VARCHAR, NUMERIC, INT, TEXT, TEXT, TEXT[], BYTEA[], INT);
DROP PROCEDURE IF EXISTS thefad.sp_update_product(INT, VARCHAR, NUMERIC, INT);
DROP PROCEDURE IF EXISTS thefad.sp_update_product(INT, VARCHAR, NUMERIC, INT, VARCHAR, TEXT, VARCHAR, BYTEA, BOOLEAN, BOOLEAN);
DROP PROCEDURE IF EXISTS thefad.sp_update_product(INT, VARCHAR, NUMERIC, INT, VARCHAR, TEXT, BOOLEAN);
DROP PROCEDURE IF EXISTS thefad.sp_add_size(INT, VARCHAR, INT);

-- image_id in the results is the COVER photo (first in that variant's gallery).
-- Search: every word must appear in the name, color, size, description or category.
CREATE OR REPLACE FUNCTION thefad.fn_list_products(
    p_search TEXT DEFAULT NULL, p_category_id INT DEFAULT NULL, p_include_inactive BOOLEAN DEFAULT FALSE)
RETURNS TABLE (product_id INT, product_name VARCHAR, color VARCHAR, size VARCHAR, display_name VARCHAR,
               description TEXT, image_id INT, base_price NUMERIC, current_price NUMERIC, current_stock INT,
               category_id INT, category_name VARCHAR, discount_name VARCHAR, discount_percentage INT,
               is_active BOOLEAN)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.product_id, p.product_name, p.color, p.size, p.display_name, p.description,
           (SELECT ph.image_id FROM thefad.product_photo ph WHERE ph.product_id = p.product_id ORDER BY ph.sort_order, ph.image_id LIMIT 1),
           p.base_price,
           CASE WHEN d.discount_id IS NULL THEN p.base_price ELSE p.current_price END,
           p.current_stock, p.category_id, c.category_name, d.discount_name, d.discount_percentage, p.is_active
      FROM thefad.product p
      JOIN thefad.category c ON c.category_id = p.category_id
      LEFT JOIN thefad.discount d
             ON d.discount_id = p.discount_id
            AND CURRENT_DATE BETWEEN d.start_date AND d.end_date
     WHERE (p_include_inactive OR p.is_active)
       AND (p_category_id IS NULL OR p.category_id = p_category_id)
       AND (p_search IS NULL OR NOT EXISTS (
              SELECT 1 FROM unnest(string_to_array(trim(p_search), ' ')) AS w
               WHERE w <> ''
                 AND NOT (p.display_name ILIKE '%' || w || '%'
                          OR COALESCE(p.description, '') ILIKE '%' || w || '%'
                          OR c.category_name ILIKE '%' || w || '%')))
     ORDER BY c.display_order, c.category_name, p.product_name, p.product_id;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_product(p_product_id INT)
RETURNS TABLE (product_id INT, product_name VARCHAR, color VARCHAR, size VARCHAR, description TEXT,
               image_id INT, base_price NUMERIC, category_id INT, current_stock INT, is_active BOOLEAN)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.product_id, p.product_name, p.color, p.size, p.description,
           (SELECT ph.image_id FROM thefad.product_photo ph WHERE ph.product_id = p.product_id ORDER BY ph.sort_order, ph.image_id LIMIT 1),
           p.base_price, p.category_id, p.current_stock, p.is_active
      FROM thefad.product p WHERE p.product_id = p_product_id;
END;
$$;

-- Every color/size variant of the same product, with today's price and each variant's cover photo.
CREATE OR REPLACE FUNCTION thefad.fn_list_variants(p_product_id INT)
RETURNS TABLE (product_id INT, color VARCHAR, size VARCHAR, base_price NUMERIC, current_price NUMERIC,
               current_stock INT, is_active BOOLEAN, image_id INT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT s.product_id, s.color, s.size, s.base_price, thefad.fn_effective_price(s.product_id),
           s.current_stock, s.is_active,
           (SELECT ph.image_id FROM thefad.product_photo ph WHERE ph.product_id = s.product_id ORDER BY ph.sort_order, ph.image_id LIMIT 1)
      FROM thefad.product p
      JOIN thefad.product s ON s.product_name = p.product_name AND s.category_id = p.category_id
     WHERE p.product_id = p_product_id
     ORDER BY s.product_id;
END;
$$;

-- The gallery of one variant, cover first.
CREATE OR REPLACE FUNCTION thefad.fn_list_product_photos(p_product_id INT)
RETURNS TABLE (image_id INT, sort_order INT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT ph.image_id, ph.sort_order FROM thefad.product_photo ph
     WHERE ph.product_id = p_product_id ORDER BY ph.sort_order, ph.image_id;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_image(p_image_id INT)
RETURNS TABLE (mime_type VARCHAR, image_data BYTEA)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY SELECT i.mime_type, i.image_data FROM thefad.product_image i WHERE i.image_id = p_image_id;
END;
$$;

-- Creates one row per color x size ("Black, Blue" x "S, M, L"). Blank colors and/or sizes mean none.
-- Up to 8 photos (parallel arrays of mime types and bytes) are stored once and linked to every row.
CREATE OR REPLACE PROCEDURE thefad.sp_create_product(
    IN p_product_name VARCHAR, IN p_base_price NUMERIC, IN p_category_id INT, IN p_description TEXT,
    IN p_sizes TEXT, IN p_colors TEXT, IN p_image_mimes TEXT[], IN p_image_datas BYTEA[],
    INOUT p_product_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_name   VARCHAR := trim(p_product_name);
    v_sizes  TEXT[];
    v_colors TEXT[];
    v_size   TEXT;
    v_color  TEXT;
    v_images INT[] := ARRAY[]::INT[];
    v_img    INT;
    v_i      INT;
    v_new    INT;
    v_count  INT := COALESCE(cardinality(p_image_datas), 0);
BEGIN
    IF v_name IS NULL OR length(v_name) = 0 THEN
        RAISE EXCEPTION 'Product name is required.';
    END IF;
    IF p_base_price IS NULL OR p_base_price <= 0 THEN
        RAISE EXCEPTION 'Price must be greater than zero.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM thefad.category WHERE category_id = p_category_id) THEN
        RAISE EXCEPTION 'Choose a valid category.';
    END IF;
    IF length(COALESCE(p_description, '')) > 1000 THEN
        RAISE EXCEPTION 'Description is too long (1000 characters at most).';
    END IF;
    IF v_count > 8 THEN
        RAISE EXCEPTION 'A product can have up to 8 photos.';
    END IF;
    IF v_count <> COALESCE(cardinality(p_image_mimes), 0) THEN
        RAISE EXCEPTION 'The photo upload was incomplete. Try again.';
    END IF;

    -- keep the order the admin typed them in; blank list becomes one NULL entry
    SELECT COALESCE(array_agg(q.c ORDER BY q.n), ARRAY[NULL]::TEXT[]) INTO v_sizes
      FROM (SELECT upper(trim(u.x)) AS c, MIN(u.n) AS n
              FROM unnest(string_to_array(COALESCE(p_sizes, ''), ',')) WITH ORDINALITY AS u(x, n)
             WHERE trim(u.x) <> '' GROUP BY upper(trim(u.x))) q;
    SELECT COALESCE(array_agg(q.c ORDER BY q.n), ARRAY[NULL]::TEXT[]) INTO v_colors
      FROM (SELECT initcap(trim(u.x)) AS c, MIN(u.n) AS n
              FROM unnest(string_to_array(COALESCE(p_colors, ''), ',')) WITH ORDINALITY AS u(x, n)
             WHERE trim(u.x) <> '' GROUP BY initcap(trim(u.x))) q;

    IF cardinality(v_sizes) * cardinality(v_colors) > 60 THEN
        RAISE EXCEPTION 'That is too many variants at once (60 at most). Add fewer sizes or colors.';
    END IF;

    FOR v_i IN 1..v_count LOOP
        IF p_image_mimes[v_i] NOT IN ('image/jpeg', 'image/png', 'image/webp') THEN
            RAISE EXCEPTION 'Photos must be JPG, PNG or WebP images.';
        END IF;
        IF octet_length(p_image_datas[v_i]) > 3145728 THEN
            RAISE EXCEPTION 'Each photo must be 3 MB or smaller.';
        END IF;
        INSERT INTO thefad.product_image (mime_type, image_data) VALUES (p_image_mimes[v_i], p_image_datas[v_i])
        RETURNING image_id INTO v_img;
        v_images := v_images || v_img;
    END LOOP;

    FOREACH v_color IN ARRAY v_colors LOOP
        FOREACH v_size IN ARRAY v_sizes LOOP
            IF length(COALESCE(v_size, '')) > 20 THEN
                RAISE EXCEPTION 'A size can be at most 20 characters (got "%").', v_size;
            END IF;
            IF length(COALESCE(v_color, '')) > 30 THEN
                RAISE EXCEPTION 'A color can be at most 30 characters (got "%").', v_color;
            END IF;
            IF EXISTS (SELECT 1 FROM thefad.product x
                        WHERE lower(x.product_name) = lower(v_name)
                          AND COALESCE(x.color, '') = COALESCE(v_color, '')
                          AND COALESCE(x.size, '') = COALESCE(v_size, '')) THEN
                RAISE EXCEPTION '% already exists.',
                    v_name || COALESCE(' - ' || v_color, '') || COALESCE(' (' || v_size || ')', '');
            END IF;
            INSERT INTO thefad.product (product_name, color, size, description, base_price, current_price,
                                        current_stock, category_id)
            VALUES (v_name, v_color, v_size, NULLIF(trim(p_description), ''), round(p_base_price, 2),
                    round(p_base_price, 2), 0, p_category_id)
            RETURNING product_id INTO v_new;
            FOR v_i IN 1..v_count LOOP
                INSERT INTO thefad.product_photo (product_id, image_id, sort_order) VALUES (v_new, v_images[v_i], v_i);
            END LOOP;
            IF p_product_id IS NULL THEN
                p_product_id := v_new;
            END IF;
        END LOOP;
    END LOOP;
END;
$$;

-- Edits one variant row. With p_apply_all, name, category, price and description are also applied
-- to every other variant of the same product. p_size and p_color only change this row.
-- Photos have their own routines.
CREATE OR REPLACE PROCEDURE thefad.sp_update_product(
    IN p_product_id INT, IN p_product_name VARCHAR, IN p_base_price NUMERIC, IN p_category_id INT,
    IN p_size VARCHAR, IN p_color VARCHAR, IN p_description TEXT, IN p_apply_all BOOLEAN)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_name     VARCHAR := trim(p_product_name);
    v_size     VARCHAR := NULLIF(upper(trim(p_size)), '');
    v_color    VARCHAR := NULLIF(initcap(trim(p_color)), '');
    v_old_name VARCHAR;
    v_old_cat  INT;
BEGIN
    IF v_name IS NULL OR length(v_name) = 0 THEN
        RAISE EXCEPTION 'Product name is required.';
    END IF;
    IF p_base_price IS NULL OR p_base_price <= 0 THEN
        RAISE EXCEPTION 'Price must be greater than zero.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM thefad.category WHERE category_id = p_category_id) THEN
        RAISE EXCEPTION 'Choose a valid category.';
    END IF;
    IF length(COALESCE(p_description, '')) > 1000 THEN
        RAISE EXCEPTION 'Description is too long (1000 characters at most).';
    END IF;
    IF length(COALESCE(v_size, '')) > 20 THEN
        RAISE EXCEPTION 'A size can be at most 20 characters.';
    END IF;
    IF length(COALESCE(v_color, '')) > 30 THEN
        RAISE EXCEPTION 'A color can be at most 30 characters.';
    END IF;

    SELECT pr.product_name, pr.category_id INTO v_old_name, v_old_cat
      FROM thefad.product pr WHERE pr.product_id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;

    IF EXISTS (SELECT 1 FROM thefad.product x
                WHERE x.product_id <> p_product_id AND lower(x.product_name) = lower(v_name)
                  AND COALESCE(x.color, '') = COALESCE(v_color, '')
                  AND COALESCE(x.size, '') = COALESCE(v_size, '')) THEN
        RAISE EXCEPTION '% already exists.',
            v_name || COALESCE(' - ' || v_color, '') || COALESCE(' (' || v_size || ')', '');
    END IF;

    UPDATE thefad.product SET size = v_size, color = v_color WHERE product_id = p_product_id;

    UPDATE thefad.product pr
       SET product_name  = v_name,
           category_id   = p_category_id,
           base_price    = round(p_base_price, 2),
           description   = NULLIF(trim(p_description), ''),
           -- keep the selling price in step with any promo running today
           current_price = GREATEST(0.01, round(p_base_price * (100 - COALESCE(
                              (SELECT d.discount_percentage FROM thefad.discount d
                                WHERE d.discount_id = pr.discount_id
                                  AND CURRENT_DATE BETWEEN d.start_date AND d.end_date), 0)) / 100.0, 2))
     WHERE pr.product_id = p_product_id
        OR (COALESCE(p_apply_all, FALSE) AND pr.product_name = v_old_name AND pr.category_id = v_old_cat);
END;
$$;

-- Adds a variant next to an existing one. A blank size or color keeps the source row's value.
-- Price, description and promo are copied; stock starts at 0. Photos are copied only when the
-- color stays the same (a new color starts with no photos).
CREATE OR REPLACE PROCEDURE thefad.sp_add_variant(
    IN p_product_id INT, IN p_size VARCHAR, IN p_color VARCHAR, INOUT p_new_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_p     thefad.product%ROWTYPE;
    v_size  VARCHAR;
    v_color VARCHAR;
BEGIN
    SELECT * INTO v_p FROM thefad.product WHERE product_id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    v_size  := COALESCE(NULLIF(upper(trim(p_size)), ''), v_p.size);
    v_color := COALESCE(NULLIF(initcap(trim(p_color)), ''), v_p.color);
    IF v_size IS NOT DISTINCT FROM v_p.size AND v_color IS NOT DISTINCT FROM v_p.color THEN
        RAISE EXCEPTION 'Enter a new size or a new color.';
    END IF;
    IF length(COALESCE(v_size, '')) > 20 THEN
        RAISE EXCEPTION 'A size can be at most 20 characters.';
    END IF;
    IF length(COALESCE(v_color, '')) > 30 THEN
        RAISE EXCEPTION 'A color can be at most 30 characters.';
    END IF;
    IF EXISTS (SELECT 1 FROM thefad.product x
                WHERE lower(x.product_name) = lower(v_p.product_name)
                  AND COALESCE(x.color, '') = COALESCE(v_color, '')
                  AND COALESCE(x.size, '') = COALESCE(v_size, '')) THEN
        RAISE EXCEPTION '% already exists.',
            v_p.product_name || COALESCE(' - ' || v_color, '') || COALESCE(' (' || v_size || ')', '');
    END IF;

    INSERT INTO thefad.product (product_name, color, size, description, base_price, current_price,
                                current_stock, category_id, discount_id, is_active)
    VALUES (v_p.product_name, v_color, v_size, v_p.description, v_p.base_price, v_p.current_price,
            0, v_p.category_id, v_p.discount_id, v_p.is_active)
    RETURNING product_id INTO p_new_id;

    IF v_color IS NOT DISTINCT FROM v_p.color THEN
        INSERT INTO thefad.product_photo (product_id, image_id, sort_order)
        SELECT p_new_id, ph.image_id, ph.sort_order FROM thefad.product_photo ph WHERE ph.product_id = p_product_id;
    END IF;
END;
$$;

-- Adds one photo to a variant, and to its other sizes of the SAME color when p_apply_all. Max 8 each.
CREATE OR REPLACE PROCEDURE thefad.sp_add_product_photo(
    IN p_product_id INT, IN p_mime VARCHAR, IN p_data BYTEA, IN p_apply_all BOOLEAN, INOUT p_image_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_name  VARCHAR;
    v_cat   INT;
    v_color VARCHAR;
BEGIN
    IF p_data IS NULL OR p_mime NOT IN ('image/jpeg', 'image/png', 'image/webp') THEN
        RAISE EXCEPTION 'The photo must be a JPG, PNG or WebP image.';
    END IF;
    IF octet_length(p_data) > 3145728 THEN
        RAISE EXCEPTION 'Each photo must be 3 MB or smaller.';
    END IF;
    SELECT pr.product_name, pr.category_id, pr.color INTO v_name, v_cat, v_color
      FROM thefad.product pr WHERE pr.product_id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    IF EXISTS (SELECT 1 FROM thefad.product t
                WHERE (t.product_id = p_product_id
                       OR (COALESCE(p_apply_all, FALSE) AND t.product_name = v_name AND t.category_id = v_cat
                           AND COALESCE(t.color, '') = COALESCE(v_color, '')))
                  AND (SELECT COUNT(*) FROM thefad.product_photo ph WHERE ph.product_id = t.product_id) >= 8) THEN
        RAISE EXCEPTION 'A product can have up to 8 photos. Remove one first.';
    END IF;

    INSERT INTO thefad.product_image (mime_type, image_data) VALUES (p_mime, p_data)
    RETURNING image_id INTO p_image_id;

    INSERT INTO thefad.product_photo (product_id, image_id, sort_order)
    SELECT t.product_id, p_image_id,
           COALESCE((SELECT MAX(ph.sort_order) FROM thefad.product_photo ph WHERE ph.product_id = t.product_id), 0) + 1
      FROM thefad.product t
     WHERE t.product_id = p_product_id
        OR (COALESCE(p_apply_all, FALSE) AND t.product_name = v_name AND t.category_id = v_cat
            AND COALESCE(t.color, '') = COALESCE(v_color, ''));
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_remove_product_photo(
    IN p_product_id INT, IN p_image_id INT, IN p_apply_all BOOLEAN)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_name  VARCHAR;
    v_cat   INT;
    v_color VARCHAR;
    v_rows  INT;
BEGIN
    SELECT pr.product_name, pr.category_id, pr.color INTO v_name, v_cat, v_color
      FROM thefad.product pr WHERE pr.product_id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    DELETE FROM thefad.product_photo ph USING thefad.product t
     WHERE ph.image_id = p_image_id AND ph.product_id = t.product_id
       AND (t.product_id = p_product_id
            OR (COALESCE(p_apply_all, FALSE) AND t.product_name = v_name AND t.category_id = v_cat
                AND COALESCE(t.color, '') = COALESCE(v_color, '')));
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'That photo is not on this product.';
    END IF;
    -- delete the stored image once no product uses it
    DELETE FROM thefad.product_image i
     WHERE i.image_id = p_image_id
       AND NOT EXISTS (SELECT 1 FROM thefad.product_photo ph WHERE ph.image_id = i.image_id);
END;
$$;

-- Makes a photo the cover (first in the gallery).
CREATE OR REPLACE PROCEDURE thefad.sp_set_cover_photo(
    IN p_product_id INT, IN p_image_id INT, IN p_apply_all BOOLEAN)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_name  VARCHAR;
    v_cat   INT;
    v_color VARCHAR;
    v_rows  INT;
BEGIN
    SELECT pr.product_name, pr.category_id, pr.color INTO v_name, v_cat, v_color
      FROM thefad.product pr WHERE pr.product_id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    UPDATE thefad.product_photo ph
       SET sort_order = COALESCE((SELECT MIN(x.sort_order) FROM thefad.product_photo x
                                   WHERE x.product_id = ph.product_id), 0) - 1
      FROM thefad.product t
     WHERE ph.image_id = p_image_id AND ph.product_id = t.product_id
       AND (t.product_id = p_product_id
            OR (COALESCE(p_apply_all, FALSE) AND t.product_name = v_name AND t.category_id = v_cat
                AND COALESCE(t.color, '') = COALESCE(v_color, '')));
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows = 0 THEN
        RAISE EXCEPTION 'That photo is not on this product.';
    END IF;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_set_product_active(IN p_product_id INT, IN p_active BOOLEAN)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    UPDATE thefad.product SET is_active = p_active WHERE product_id = p_product_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Product not found.'; END IF;
END;
$$;

----------------------------------------------------------------------- STAFF
-- master_pin_code and hourly_rate are never returned (phase 2 column privileges).
DROP FUNCTION  IF EXISTS thefad.fn_list_staff();
DROP FUNCTION  IF EXISTS thefad.fn_get_staff(INT);
DROP PROCEDURE IF EXISTS thefad.sp_create_staff(VARCHAR, TEXT, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, INT);
DROP PROCEDURE IF EXISTS thefad.sp_create_staff(VARCHAR, TEXT, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, NUMERIC, DATE, INT);
DROP PROCEDURE IF EXISTS thefad.sp_update_staff(INT, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR);
DROP PROCEDURE IF EXISTS thefad.sp_update_staff(INT, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, NUMERIC, DATE);
DROP FUNCTION  IF EXISTS thefad.fn_payroll(DATE, DATE, NUMERIC, NUMERIC);

CREATE OR REPLACE FUNCTION thefad.fn_list_staff()
RETURNS TABLE (user_id INT, username VARCHAR, first_name VARCHAR, last_name VARCHAR,
               user_type VARCHAR, email VARCHAR, station VARCHAR, is_active BOOLEAN, clocked_in BOOLEAN,
               hired_on DATE)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT u.user_id, u.username, u.first_name, u.last_name, u.user_type, u.email, u.station, u.is_active,
           EXISTS (SELECT 1 FROM thefad.daily_time_record t
                    WHERE t.user_id = u.user_id AND t.time_out IS NULL),
           u.hired_on
      FROM thefad.users u
     ORDER BY u.is_active DESC, u.user_type, u.last_name, u.first_name;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_staff(p_user_id INT)
RETURNS TABLE (user_id INT, username VARCHAR, first_name VARCHAR, last_name VARCHAR,
               user_type VARCHAR, email VARCHAR, station VARCHAR, is_active BOOLEAN, hired_on DATE)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT u.user_id, u.username, u.first_name, u.last_name, u.user_type, u.email, u.station, u.is_active,
           u.hired_on
      FROM thefad.users u WHERE u.user_id = p_user_id;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_create_staff(
    IN p_username VARCHAR, IN p_password TEXT, IN p_first_name VARCHAR, IN p_last_name VARCHAR,
    IN p_user_type VARCHAR, IN p_email VARCHAR, IN p_station VARCHAR, IN p_hired_on DATE,
    INOUT p_user_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF p_username IS NULL OR length(trim(p_username)) < 3 THEN
        RAISE EXCEPTION 'Username must be at least 3 characters.';
    END IF;
    IF p_password IS NULL OR length(p_password) < 8 THEN
        RAISE EXCEPTION 'Password must be at least 8 characters.';
    END IF;
    IF p_first_name IS NULL OR length(trim(p_first_name)) = 0
       OR p_last_name IS NULL OR length(trim(p_last_name)) = 0 THEN
        RAISE EXCEPTION 'First and last name are required.';
    END IF;
    IF p_user_type NOT IN ('CA', 'AD') THEN
        RAISE EXCEPTION 'Role must be Cashier or Admin.';
    END IF;
    IF p_email IS NULL OR position('@' IN p_email) = 0 THEN
        RAISE EXCEPTION 'Enter a valid email address.';
    END IF;
    IF p_hired_on > CURRENT_DATE THEN
        RAISE EXCEPTION 'The start date cannot be in the future.';
    END IF;

    INSERT INTO thefad.users (username, first_name, last_name, user_type, password_hash, email, station, hired_on)
    VALUES (trim(p_username), trim(p_first_name), trim(p_last_name), p_user_type,
            crypt(p_password, gen_salt('bf')), trim(p_email), NULLIF(trim(p_station), ''),
            COALESCE(p_hired_on, CURRENT_DATE))
    RETURNING user_id INTO p_user_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'That username or email is already in use.';
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_update_staff(
    IN p_user_id INT, IN p_first_name VARCHAR, IN p_last_name VARCHAR,
    IN p_user_type VARCHAR, IN p_email VARCHAR, IN p_station VARCHAR, IN p_hired_on DATE)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_type   VARCHAR;
    v_active BOOLEAN;
BEGIN
    IF p_first_name IS NULL OR length(trim(p_first_name)) = 0
       OR p_last_name IS NULL OR length(trim(p_last_name)) = 0 THEN
        RAISE EXCEPTION 'First and last name are required.';
    END IF;
    IF p_user_type NOT IN ('CA', 'AD') THEN
        RAISE EXCEPTION 'Role must be Cashier or Admin.';
    END IF;
    IF p_email IS NULL OR position('@' IN p_email) = 0 THEN
        RAISE EXCEPTION 'Enter a valid email address.';
    END IF;
    IF p_hired_on > CURRENT_DATE THEN
        RAISE EXCEPTION 'The start date cannot be in the future.';
    END IF;

    SELECT u.user_type, u.is_active INTO v_type, v_active FROM thefad.users u WHERE u.user_id = p_user_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Staff account not found.'; END IF;

    IF v_type = 'AD' AND v_active AND p_user_type <> 'AD'
       AND NOT EXISTS (SELECT 1 FROM thefad.users x
                        WHERE x.user_type = 'AD' AND x.is_active AND x.user_id <> p_user_id) THEN
        RAISE EXCEPTION 'At least one active admin is required.';
    END IF;

    UPDATE thefad.users
       SET first_name = trim(p_first_name), last_name = trim(p_last_name), user_type = p_user_type,
           email = trim(p_email), station = NULLIF(trim(p_station), ''), hired_on = COALESCE(p_hired_on, hired_on)
     WHERE user_id = p_user_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'That email is already in use.';
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_set_staff_active(IN p_user_id INT, IN p_active BOOLEAN)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_type   VARCHAR;
    v_active BOOLEAN;
BEGIN
    SELECT u.user_type, u.is_active INTO v_type, v_active FROM thefad.users u WHERE u.user_id = p_user_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Staff account not found.'; END IF;

    IF NOT p_active AND v_type = 'AD' AND v_active
       AND NOT EXISTS (SELECT 1 FROM thefad.users x
                        WHERE x.user_type = 'AD' AND x.is_active AND x.user_id <> p_user_id) THEN
        RAISE EXCEPTION 'At least one active admin is required.';
    END IF;

    UPDATE thefad.users SET is_active = p_active WHERE user_id = p_user_id;
END;
$$;

------------------------------------------------------------------ ATTENDANCE
-- The regular shift (time in, time out, grace) is saved in shift_setting and edited by an admin.
-- Hours beyond a full shift only count as overtime when an admin has allowed it (overtime_permit).
DROP PROCEDURE IF EXISTS thefad.sp_clock_in(INT, INT);
DROP PROCEDURE IF EXISTS thefad.sp_clock_out(INT, INT);
DROP PROCEDURE IF EXISTS thefad.sp_save_shift(INT, INT, TIMESTAMP, TIMESTAMP, VARCHAR, TIME, INT, NUMERIC, INT);
DROP FUNCTION  IF EXISTS thefad.fn_my_attendance(INT, INT);
DROP FUNCTION  IF EXISTS thefad.fn_my_attendance(INT, INT, NUMERIC);
DROP FUNCTION  IF EXISTS thefad.fn_attendance_report(DATE, DATE, INT);
DROP FUNCTION  IF EXISTS thefad.fn_attendance_board(DATE, DATE, INT, NUMERIC, TEXT);

CREATE OR REPLACE FUNCTION thefad.fn_get_shift_setting()
RETURNS TABLE (shift_start TIME, shift_end TIME, grace_minutes INT, shift_hours NUMERIC)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT s.shift_start, s.shift_end, s.grace_minutes,
           round(EXTRACT(EPOCH FROM (s.shift_end - s.shift_start)) / 3600.0, 2)
      FROM thefad.shift_setting s WHERE s.setting_id = 1;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_save_shift_setting(
    IN p_shift_start TIME, IN p_shift_end TIME, IN p_grace_minutes INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF p_shift_start IS NULL OR p_shift_end IS NULL THEN
        RAISE EXCEPTION 'Enter the shift time in and time out.';
    END IF;
    IF p_shift_end <= p_shift_start THEN
        RAISE EXCEPTION 'The time out must be after the time in.';
    END IF;
    IF EXTRACT(EPOCH FROM (p_shift_end - p_shift_start)) / 3600.0 NOT BETWEEN 1 AND 12 THEN
        RAISE EXCEPTION 'A shift must be between 1 and 12 hours long.';
    END IF;
    IF p_grace_minutes IS NULL OR p_grace_minutes NOT BETWEEN 0 AND 120 THEN
        RAISE EXCEPTION 'Grace period must be between 0 and 120 minutes.';
    END IF;
    INSERT INTO thefad.shift_setting (setting_id, shift_start, shift_end, grace_minutes, updated_at)
    VALUES (1, p_shift_start, p_shift_end, p_grace_minutes, LOCALTIMESTAMP(0))
    ON CONFLICT (setting_id) DO UPDATE
       SET shift_start = EXCLUDED.shift_start, shift_end = EXCLUDED.shift_end,
           grace_minutes = EXCLUDED.grace_minutes, updated_at = EXCLUDED.updated_at;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_clock_in(
    IN p_user_id INT, IN p_shift_start TIME, IN p_grace_minutes INT, IN p_max_hours NUMERIC,
    INOUT p_dtr_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_open   thefad.daily_time_record%ROWTYPE;
    v_now    TIMESTAMP := LOCALTIMESTAMP(0);
    v_status VARCHAR := 'Present';
BEGIN
    SELECT * INTO v_open FROM thefad.daily_time_record t
     WHERE t.user_id = p_user_id AND t.time_out IS NULL AND t.shift_type = 'Regular'
     ORDER BY t.time_in DESC LIMIT 1;
    IF FOUND THEN
        IF v_now - v_open.time_in > make_interval(secs => (p_max_hours * 3600)::double precision) THEN
            RAISE EXCEPTION 'You did not clock out on %. Enter the time you finished first.',
                            to_char(v_open.time_in, 'Mon DD');
        END IF;
        RAISE EXCEPTION 'You are already clocked in.';
    END IF;
    IF EXISTS (SELECT 1 FROM thefad.daily_time_record t
                WHERE t.user_id = p_user_id AND t.shift_type = 'Regular' AND t.time_in::date = v_now::date) THEN
        RAISE EXCEPTION 'You already have a shift recorded for today.';
    END IF;
    IF v_now::time > p_shift_start + make_interval(mins => p_grace_minutes) THEN
        v_status := 'Late';
    END IF;
    INSERT INTO thefad.daily_time_record (user_id, time_in, status)
    VALUES (p_user_id, v_now, v_status)
    RETURNING dtr_id INTO p_dtr_id;
END;
$$;

-- Normal clock-out: only after a full shift. After a missed clock-out (open longer than p_max_hours)
-- the person gives the time they finished (p_time_out). Counted hours never exceed a full shift:
-- extra time needs overtime permission.
CREATE OR REPLACE PROCEDURE thefad.sp_clock_out(
    IN p_user_id INT, IN p_shift_hours NUMERIC, IN p_max_hours NUMERIC, IN p_time_out TIMESTAMP,
    INOUT p_dtr_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_in    TIMESTAMP;
    v_now   TIMESTAMP := LOCALTIMESTAMP(0);
    v_out   TIMESTAMP;
    v_age   NUMERIC;
    v_fixed BOOLEAN := FALSE;
BEGIN
    SELECT t.dtr_id, t.time_in INTO p_dtr_id, v_in
      FROM thefad.daily_time_record t
     WHERE t.user_id = p_user_id AND t.time_out IS NULL AND t.shift_type = 'Regular'
     ORDER BY t.time_in DESC LIMIT 1;
    IF p_dtr_id IS NULL THEN
        RAISE EXCEPTION 'You are not clocked in.';
    END IF;

    v_age := EXTRACT(EPOCH FROM (v_now - v_in)) / 3600.0;
    IF v_age > p_max_hours THEN
        IF p_time_out IS NULL THEN
            RAISE EXCEPTION 'You were clocked in for over % hours. Enter the time you finished.', p_max_hours;
        END IF;
        v_out := p_time_out;
        v_fixed := TRUE;
    ELSE
        IF p_time_out IS NOT NULL THEN
            RAISE EXCEPTION 'A finish time is only needed after a shift runs over % hours.', p_max_hours;
        END IF;
        IF v_age < p_shift_hours THEN
            RAISE EXCEPTION 'You can clock out after % hours of work, from %.', p_shift_hours,
                to_char(v_in + make_interval(secs => (p_shift_hours * 3600)::double precision), 'HH12:MI AM');
        END IF;
        v_out := v_now;
    END IF;

    IF v_out <= v_in THEN
        RAISE EXCEPTION 'The finish time must be after you clocked in (%).', to_char(v_in, 'Mon DD, HH12:MI AM');
    END IF;
    IF v_out > v_now THEN
        RAISE EXCEPTION 'The finish time cannot be in the future.';
    END IF;
    IF EXTRACT(EPOCH FROM (v_out - v_in)) / 3600.0 > p_max_hours THEN
        RAISE EXCEPTION 'A shift cannot be longer than % hours.', p_max_hours;
    END IF;

    UPDATE thefad.daily_time_record
       SET time_out = v_out,
           total_hours = LEAST(round(EXTRACT(EPOCH FROM (v_out - v_in)) / 3600.0, 2), p_shift_hours),
           note = CASE WHEN v_fixed THEN 'Finish time entered after a missed clock-out' ELSE note END
     WHERE dtr_id = p_dtr_id;
END;
$$;

-- Admin: add a missed regular shift or correct one. A short reason is required.
CREATE OR REPLACE PROCEDURE thefad.sp_save_shift(
    IN p_dtr_id INT, IN p_user_id INT, IN p_time_in TIMESTAMP, IN p_time_out TIMESTAMP, IN p_note VARCHAR,
    IN p_shift_start TIME, IN p_grace_minutes INT, IN p_shift_hours NUMERIC, IN p_max_hours NUMERIC,
    INOUT p_result_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_status VARCHAR := 'Present';
    v_hours  NUMERIC;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM thefad.users WHERE user_id = p_user_id) THEN
        RAISE EXCEPTION 'Choose a staff member.';
    END IF;
    IF p_time_in IS NULL OR p_time_out IS NULL THEN
        RAISE EXCEPTION 'Enter both the time in and the time out.';
    END IF;
    IF p_time_out <= p_time_in THEN
        RAISE EXCEPTION 'The time out must be after the time in.';
    END IF;
    IF p_time_out > LOCALTIMESTAMP THEN
        RAISE EXCEPTION 'The time out cannot be in the future.';
    END IF;
    v_hours := round(EXTRACT(EPOCH FROM (p_time_out - p_time_in)) / 3600.0, 2);
    IF v_hours > p_max_hours THEN
        RAISE EXCEPTION 'A shift cannot be longer than % hours.', p_max_hours;
    END IF;
    IF length(trim(COALESCE(p_note, ''))) < 3 THEN
        RAISE EXCEPTION 'Add a short reason.';
    END IF;
    IF EXISTS (SELECT 1 FROM thefad.daily_time_record t
                WHERE t.user_id = p_user_id AND t.shift_type = 'Regular' AND t.time_in::date = p_time_in::date
                  AND t.dtr_id IS DISTINCT FROM p_dtr_id) THEN
        RAISE EXCEPTION 'That person already has a shift on this date. Edit it instead.';
    END IF;
    IF p_time_in::time > p_shift_start + make_interval(mins => p_grace_minutes) THEN
        v_status := 'Late';
    END IF;

    IF p_dtr_id IS NULL THEN
        INSERT INTO thefad.daily_time_record (user_id, time_in, time_out, total_hours, status, note)
        VALUES (p_user_id, p_time_in, p_time_out, LEAST(v_hours, p_shift_hours), v_status, trim(p_note))
        RETURNING dtr_id INTO p_result_id;
    ELSE
        UPDATE thefad.daily_time_record
           SET user_id = p_user_id, time_in = p_time_in, time_out = p_time_out,
               total_hours = LEAST(v_hours, p_shift_hours), status = v_status, note = trim(p_note)
         WHERE dtr_id = p_dtr_id AND shift_type = 'Regular'
        RETURNING dtr_id INTO p_result_id;
        IF p_result_id IS NULL THEN
            RAISE EXCEPTION 'Shift not found.';
        END IF;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_shift(p_dtr_id INT)
RETURNS TABLE (dtr_id INT, user_id INT, full_name TEXT, time_in TIMESTAMP, time_out TIMESTAMP,
               status VARCHAR, note VARCHAR)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT t.dtr_id, t.user_id, u.first_name || ' ' || u.last_name, t.time_in, t.time_out, t.status, t.note
      FROM thefad.daily_time_record t JOIN thefad.users u ON u.user_id = t.user_id
     WHERE t.dtr_id = p_dtr_id AND t.shift_type = 'Regular';
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_my_attendance(p_user_id INT, p_limit INT)
RETURNS TABLE (dtr_id INT, shift_type VARCHAR, time_in TIMESTAMP, time_out TIMESTAMP, total_hours NUMERIC,
               overtime_hours NUMERIC, status VARCHAR, note VARCHAR)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT t.dtr_id, t.shift_type, t.time_in, t.time_out, t.total_hours,
           CASE WHEN t.shift_type = 'Overtime' THEN COALESCE(t.total_hours, 0) ELSE 0 END,
           t.status, t.note
      FROM thefad.daily_time_record t
     WHERE t.user_id = p_user_id
     ORDER BY t.time_in DESC
     LIMIT p_limit;
END;
$$;

-- Everyone's attendance for a date range. Real shifts come from the table; work days with no regular
-- shift are worked out here as Absent (or "Not in yet" for today) and are never stored.
CREATE OR REPLACE FUNCTION thefad.fn_attendance_board(
    p_start DATE, p_end DATE, p_user_id INT, p_work_days TEXT)
RETURNS TABLE (dtr_id INT, user_id INT, full_name TEXT, work_day DATE, shift_type TEXT, time_in TIMESTAMP,
               time_out TIMESTAMP, total_hours NUMERIC, overtime_hours NUMERIC, status TEXT, note VARCHAR)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
DECLARE
    v_days INT[] := string_to_array(COALESCE(NULLIF(p_work_days, ''), '1,2,3,4,5,6,7'), ',')::int[];
BEGIN
    RETURN QUERY
    SELECT t.dtr_id, t.user_id, u.first_name || ' ' || u.last_name, t.time_in::date, t.shift_type::text,
           t.time_in, t.time_out, t.total_hours,
           CASE WHEN t.shift_type = 'Overtime' THEN COALESCE(t.total_hours, 0) ELSE 0 END,
           t.status::text, t.note
      FROM thefad.daily_time_record t
      JOIN thefad.users u ON u.user_id = t.user_id
     WHERE t.time_in::date BETWEEN p_start AND p_end
       AND (p_user_id IS NULL OR t.user_id = p_user_id)
    UNION ALL
    SELECT NULL::int, s.user_id, s.first_name || ' ' || s.last_name, d.wd, 'Regular'::text,
           NULL::timestamp, NULL::timestamp, NULL::numeric, NULL::numeric,
           CASE WHEN d.wd = CURRENT_DATE THEN 'Not in yet' ELSE 'Absent' END, NULL::varchar
      FROM thefad.users s
     CROSS JOIN (SELECT g::date AS wd FROM generate_series(p_start, p_end, INTERVAL '1 day') AS g) d
     WHERE s.is_active
       AND (p_user_id IS NULL OR s.user_id = p_user_id)
       AND d.wd >= s.hired_on AND d.wd <= CURRENT_DATE
       AND EXTRACT(ISODOW FROM d.wd)::int = ANY (v_days)
       AND NOT EXISTS (SELECT 1 FROM thefad.daily_time_record x
                        WHERE x.user_id = s.user_id AND x.shift_type = 'Regular' AND x.time_in::date = d.wd)
    ORDER BY 4 DESC, 3, 5 DESC;
END;
$$;

------------------------------------------------------------------- OVERTIME
-- An admin allows one person to work overtime on one day, with a time in, a time out and a grace
-- period for clocking in. The person then clocks the overtime in and out like a shift.
CREATE OR REPLACE PROCEDURE thefad.sp_allow_overtime(
    IN p_admin_id INT, IN p_user_id INT, IN p_work_date DATE, IN p_start TIME, IN p_end TIME,
    IN p_grace_minutes INT, IN p_note VARCHAR, INOUT p_permit_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM thefad.users WHERE user_id = p_user_id AND is_active) THEN
        RAISE EXCEPTION 'Choose a staff member.';
    END IF;
    IF p_work_date IS NULL OR p_work_date < CURRENT_DATE THEN
        RAISE EXCEPTION 'Choose today or a later date.';
    END IF;
    IF p_start IS NULL OR p_end IS NULL OR p_end <= p_start THEN
        RAISE EXCEPTION 'The overtime time out must be after the time in.';
    END IF;
    IF EXTRACT(EPOCH FROM (p_end - p_start)) / 3600.0 > 8 THEN
        RAISE EXCEPTION 'Overtime can be at most 8 hours.';
    END IF;
    IF COALESCE(p_grace_minutes, 0) NOT BETWEEN 0 AND 120 THEN
        RAISE EXCEPTION 'Grace period must be between 0 and 120 minutes.';
    END IF;
    INSERT INTO thefad.overtime_permit (user_id, work_date, start_time, end_time, grace_minutes, note, created_by)
    VALUES (p_user_id, p_work_date, p_start, p_end,
            COALESCE(p_grace_minutes, (SELECT s.grace_minutes FROM thefad.shift_setting s WHERE s.setting_id = 1), 15),
            NULLIF(trim(p_note), ''), p_admin_id)
    RETURNING permit_id INTO p_permit_id;
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION 'That person already has overtime on that day. Edit it instead.';
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_update_overtime(
    IN p_permit_id INT, IN p_start TIME, IN p_end TIME, IN p_grace_minutes INT, IN p_note VARCHAR)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM thefad.overtime_permit WHERE permit_id = p_permit_id) THEN
        RAISE EXCEPTION 'Overtime not found.';
    END IF;
    IF EXISTS (SELECT 1 FROM thefad.daily_time_record WHERE permit_id = p_permit_id) THEN
        RAISE EXCEPTION 'This overtime has already started, so it cannot be changed.';
    END IF;
    IF p_start IS NULL OR p_end IS NULL OR p_end <= p_start THEN
        RAISE EXCEPTION 'The overtime time out must be after the time in.';
    END IF;
    IF EXTRACT(EPOCH FROM (p_end - p_start)) / 3600.0 > 8 THEN
        RAISE EXCEPTION 'Overtime can be at most 8 hours.';
    END IF;
    IF COALESCE(p_grace_minutes, 0) NOT BETWEEN 0 AND 120 THEN
        RAISE EXCEPTION 'Grace period must be between 0 and 120 minutes.';
    END IF;
    UPDATE thefad.overtime_permit
       SET start_time = p_start, end_time = p_end, grace_minutes = COALESCE(p_grace_minutes, grace_minutes),
           note = NULLIF(trim(p_note), '')
     WHERE permit_id = p_permit_id;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_cancel_overtime(IN p_permit_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM thefad.daily_time_record WHERE permit_id = p_permit_id) THEN
        RAISE EXCEPTION 'This overtime has already started, so it cannot be cancelled.';
    END IF;
    DELETE FROM thefad.overtime_permit WHERE permit_id = p_permit_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Overtime not found.';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_list_overtime(p_start DATE, p_end DATE)
RETURNS TABLE (permit_id INT, user_id INT, full_name TEXT, work_date DATE, start_time TIME, end_time TIME,
               grace_minutes INT, note VARCHAR, status TEXT, hours_worked NUMERIC)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.permit_id, p.user_id, u.first_name || ' ' || u.last_name, p.work_date, p.start_time, p.end_time,
           p.grace_minutes, p.note,
           CASE WHEN t.dtr_id IS NOT NULL AND t.time_out IS NULL THEN 'In progress'
                WHEN t.dtr_id IS NOT NULL THEN 'Done'
                WHEN (p.work_date + p.end_time) < LOCALTIMESTAMP THEN 'Not used'
                ELSE 'Allowed' END,
           t.total_hours
      FROM thefad.overtime_permit p
      JOIN thefad.users u ON u.user_id = p.user_id
      LEFT JOIN thefad.daily_time_record t ON t.permit_id = p.permit_id
     WHERE p.work_date BETWEEN p_start AND p_end
     ORDER BY p.work_date DESC, 3;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_overtime(p_permit_id INT)
RETURNS TABLE (permit_id INT, user_id INT, full_name TEXT, work_date DATE, start_time TIME, end_time TIME,
               grace_minutes INT, note VARCHAR, started BOOLEAN)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.permit_id, p.user_id, u.first_name || ' ' || u.last_name, p.work_date, p.start_time, p.end_time,
           p.grace_minutes, p.note,
           EXISTS (SELECT 1 FROM thefad.daily_time_record t WHERE t.permit_id = p.permit_id)
      FROM thefad.overtime_permit p JOIN thefad.users u ON u.user_id = p.user_id
     WHERE p.permit_id = p_permit_id;
END;
$$;

-- Today's and upcoming overtime for one person, with the clock record if it was started.
CREATE OR REPLACE FUNCTION thefad.fn_my_overtime(p_user_id INT)
RETURNS TABLE (permit_id INT, work_date DATE, start_time TIME, end_time TIME, grace_minutes INT, note VARCHAR,
               dtr_id INT, time_in TIMESTAMP, time_out TIMESTAMP)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.permit_id, p.work_date, p.start_time, p.end_time, p.grace_minutes, p.note,
           t.dtr_id, t.time_in, t.time_out
      FROM thefad.overtime_permit p
      LEFT JOIN thefad.daily_time_record t ON t.permit_id = p.permit_id
     WHERE p.user_id = p_user_id AND p.work_date >= CURRENT_DATE
     ORDER BY p.work_date;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_overtime_in(IN p_user_id INT, INOUT p_dtr_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_p     thefad.overtime_permit%ROWTYPE;
    v_now   TIMESTAMP := LOCALTIMESTAMP(0);
    v_start TIMESTAMP;
    v_end   TIMESTAMP;
BEGIN
    SELECT * INTO v_p FROM thefad.overtime_permit p WHERE p.user_id = p_user_id AND p.work_date = v_now::date;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'You have no overtime allowed today.';
    END IF;
    v_start := v_p.work_date + v_p.start_time;
    v_end   := v_p.work_date + v_p.end_time;
    IF EXISTS (SELECT 1 FROM thefad.daily_time_record t WHERE t.permit_id = v_p.permit_id) THEN
        RAISE EXCEPTION 'You already started this overtime.';
    END IF;
    IF EXISTS (SELECT 1 FROM thefad.daily_time_record t
                WHERE t.user_id = p_user_id AND t.shift_type = 'Regular' AND t.time_out IS NULL) THEN
        RAISE EXCEPTION 'Clock out of your regular shift first.';
    END IF;
    IF v_now < v_start THEN
        RAISE EXCEPTION 'Your overtime starts at %.', to_char(v_start, 'HH12:MI AM');
    END IF;
    IF v_now >= v_end THEN
        RAISE EXCEPTION 'Your overtime window has ended.';
    END IF;
    INSERT INTO thefad.daily_time_record (user_id, time_in, status, shift_type, permit_id)
    VALUES (p_user_id, v_now,
            CASE WHEN v_now > v_start + make_interval(mins => v_p.grace_minutes) THEN 'Late' ELSE 'Present' END,
            'Overtime', v_p.permit_id)
    RETURNING dtr_id INTO p_dtr_id;
END;
$$;

-- Overtime ends at the time out the admin set at the latest, even if the person forgets to end it.
CREATE OR REPLACE PROCEDURE thefad.sp_overtime_out(IN p_user_id INT, INOUT p_dtr_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_in  TIMESTAMP;
    v_end TIMESTAMP;
    v_out TIMESTAMP;
BEGIN
    SELECT t.dtr_id, t.time_in, p.work_date + p.end_time INTO p_dtr_id, v_in, v_end
      FROM thefad.daily_time_record t
      JOIN thefad.overtime_permit p ON p.permit_id = t.permit_id
     WHERE t.user_id = p_user_id AND t.shift_type = 'Overtime' AND t.time_out IS NULL
     ORDER BY t.time_in DESC LIMIT 1;
    IF p_dtr_id IS NULL THEN
        RAISE EXCEPTION 'You are not on overtime.';
    END IF;
    v_out := GREATEST(LEAST(LOCALTIMESTAMP(0), v_end), v_in + INTERVAL '1 second');
    UPDATE thefad.daily_time_record
       SET time_out = v_out, total_hours = round(EXTRACT(EPOCH FROM (v_out - v_in)) / 3600.0, 2)
     WHERE dtr_id = p_dtr_id;
END;
$$;

-- ===== 04_waves2_5.sql =====
-- Waves 2-5: inventory, promos, POS + orders, refunds, dashboard.
-- Run after 00-03 (or just use setup_all.sql). Safe to re-run.

--------------------------------------------------------------- SHARED HELPERS
-- Price a customer pays today: promo price only while the promo is running.
CREATE OR REPLACE FUNCTION thefad.fn_effective_price(p_product_id INT)
RETURNS NUMERIC
LANGUAGE sql STABLE
SET search_path = thefad, public, pg_temp
AS $$
    SELECT CASE WHEN d.discount_id IS NULL THEN p.base_price
                ELSE GREATEST(0.01, ROUND(p.base_price * (100 - d.discount_percentage) / 100.0, 2)) END
      FROM thefad.product p
      LEFT JOIN thefad.discount d
             ON d.discount_id = p.discount_id
            AND CURRENT_DATE BETWEEN d.start_date AND d.end_date
     WHERE p.product_id = p_product_id;
$$;

-- The ONLY place stock changes. Locks the product, blocks negative stock, writes the log.
CREATE OR REPLACE FUNCTION thefad.fn_apply_stock_change(
    p_product_id INT, p_user_id INT, p_type VARCHAR, p_delta INT, p_sale_id INT DEFAULT NULL)
RETURNS INT
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_stock INT;
    v_name  VARCHAR;
    v_new   INT;
BEGIN
    IF p_delta = 0 THEN
        RAISE EXCEPTION 'Quantity cannot be zero.';
    END IF;
    SELECT pr.current_stock, pr.display_name INTO v_stock, v_name
      FROM thefad.product pr WHERE pr.product_id = p_product_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    v_new := v_stock + p_delta;
    IF v_new < 0 THEN
        RAISE EXCEPTION 'Not enough stock for %: % in stock, % needed.', v_name, v_stock, -p_delta;
    END IF;
    UPDATE thefad.product SET current_stock = v_new WHERE product_id = p_product_id;
    INSERT INTO thefad.inventory_logs (product_id, sale_id, user_id, transaction_type, quantity_changed, balance_after)
    VALUES (p_product_id, p_sale_id, p_user_id, p_type, p_delta, v_new);
    RETURN v_new;
END;
$$;

------------------------------------------------------------------- INVENTORY
CREATE OR REPLACE FUNCTION thefad.fn_list_inventory(
    p_search TEXT DEFAULT NULL, p_low_only BOOLEAN DEFAULT FALSE, p_threshold INT DEFAULT 5)
RETURNS TABLE (product_id INT, product_name VARCHAR, category_name VARCHAR, current_stock INT,
               is_active BOOLEAN, is_low BOOLEAN)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.product_id, p.display_name, c.category_name, p.current_stock, p.is_active,
           (p.current_stock <= p_threshold)
      FROM thefad.product p
      JOIN thefad.category c ON c.category_id = p.category_id
     WHERE (p_search IS NULL OR p.display_name ILIKE '%' || p_search || '%')
       AND (NOT p_low_only OR p.current_stock <= p_threshold)
     ORDER BY (p.current_stock <= p_threshold) DESC, p.current_stock, p.display_name;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_inventory_history(p_product_id INT DEFAULT NULL, p_limit INT DEFAULT 100)
RETURNS TABLE (log_id INT, logged_at TIMESTAMP, product_id INT, product_name VARCHAR,
               transaction_type VARCHAR, quantity_changed INT, balance_after INT, sale_id INT, staff_name TEXT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT l.log_id, l.logged_at, l.product_id, p.display_name, l.transaction_type,
           l.quantity_changed, l.balance_after, l.sale_id, u.first_name || ' ' || u.last_name
      FROM thefad.inventory_logs l
      JOIN thefad.product p ON p.product_id = l.product_id
      JOIN thefad.users u ON u.user_id = l.user_id
     WHERE (p_product_id IS NULL OR l.product_id = p_product_id)
     ORDER BY l.logged_at DESC, l.log_id DESC
     LIMIT p_limit;
END;
$$;

CREATE OR REPLACE PROCEDURE thefad.sp_stock_in(
    IN p_user_id INT, IN p_product_id INT, IN p_quantity INT, INOUT p_balance INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity to add must be at least 1.';
    END IF;
    p_balance := thefad.fn_apply_stock_change(p_product_id, p_user_id, 'IN', p_quantity);
END;
$$;

-- Manual removal: damaged, lost, given away. Sales remove stock through sp_create_sale.
CREATE OR REPLACE PROCEDURE thefad.sp_stock_out(
    IN p_user_id INT, IN p_product_id INT, IN p_quantity INT, INOUT p_balance INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity to remove must be at least 1.';
    END IF;
    p_balance := thefad.fn_apply_stock_change(p_product_id, p_user_id, 'OUT', -p_quantity);
END;
$$;

-- Set stock to a counted number (stock take).
CREATE OR REPLACE PROCEDURE thefad.sp_adjust_stock(
    IN p_user_id INT, IN p_product_id INT, IN p_new_count INT, INOUT p_balance INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_stock INT;
BEGIN
    IF p_new_count IS NULL OR p_new_count < 0 THEN
        RAISE EXCEPTION 'Counted stock cannot be negative.';
    END IF;
    SELECT pr.current_stock INTO v_stock FROM thefad.product pr WHERE pr.product_id = p_product_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    IF p_new_count = v_stock THEN
        RAISE EXCEPTION 'Stock is already %. Nothing to adjust.', v_stock;
    END IF;
    p_balance := thefad.fn_apply_stock_change(p_product_id, p_user_id, 'ADJUSTMENT', p_new_count - v_stock);
END;
$$;

---------------------------------------------------------------------- PROMOS
-- Create / edit / end promos with your existing sp_create_discount and sp_update_discount.
CREATE OR REPLACE FUNCTION thefad.fn_list_discounts()
RETURNS TABLE (discount_id INT, discount_name VARCHAR, discount_percentage INT, start_date DATE,
               end_date DATE, status TEXT, products_linked BIGINT, linked_products TEXT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT d.discount_id, d.discount_name, d.discount_percentage, d.start_date, d.end_date,
           CASE WHEN CURRENT_DATE < d.start_date THEN 'Upcoming'
                WHEN CURRENT_DATE > d.end_date THEN 'Ended' ELSE 'Active' END,
           COUNT(p.product_id),
           string_agg(p.display_name, ', ' ORDER BY p.display_name)
      FROM thefad.discount d
      LEFT JOIN thefad.product p ON p.discount_id = d.discount_id
     GROUP BY d.discount_id, d.discount_name, d.discount_percentage, d.start_date, d.end_date
     ORDER BY CASE WHEN CURRENT_DATE BETWEEN d.start_date AND d.end_date THEN 0
                   WHEN CURRENT_DATE < d.start_date THEN 1 ELSE 2 END,
              d.start_date DESC, d.discount_id DESC;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_discount(p_discount_id INT)
RETURNS TABLE (discount_id INT, discount_name VARCHAR, discount_percentage INT, start_date DATE,
               end_date DATE, status TEXT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT d.discount_id, d.discount_name, d.discount_percentage, d.start_date, d.end_date,
           CASE WHEN CURRENT_DATE < d.start_date THEN 'Upcoming'
                WHEN CURRENT_DATE > d.end_date THEN 'Ended' ELSE 'Active' END
      FROM thefad.discount d WHERE d.discount_id = p_discount_id;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_discount_products(p_discount_id INT)
RETURNS TABLE (product_id INT, product_name VARCHAR, base_price NUMERIC, current_price NUMERIC)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.product_id, p.display_name, p.base_price, p.current_price
      FROM thefad.product p WHERE p.discount_id = p_discount_id ORDER BY p.display_name;
END;
$$;

-- Put an existing, running promo on one product (ALL its colors and sizes) or the whole store.
CREATE OR REPLACE PROCEDURE thefad.sp_apply_discount(
    IN p_discount_id INT, IN p_scope VARCHAR, IN p_product_id INT, INOUT p_products_updated INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_d     thefad.discount%ROWTYPE;
    v_scope VARCHAR := UPPER(COALESCE(TRIM(p_scope), ''));
    v_name  VARCHAR;
    v_cat   INT;
BEGIN
    SELECT * INTO v_d FROM thefad.discount WHERE discount_id = p_discount_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Promo not found.';
    END IF;
    IF CURRENT_DATE NOT BETWEEN v_d.start_date AND v_d.end_date THEN
        RAISE EXCEPTION 'This promo is not running today, so it cannot be applied to products.';
    END IF;
    IF v_d.discount_percentage >= 100 THEN
        RAISE EXCEPTION 'A 100 percent promo would make the price zero.';
    END IF;
    IF v_scope = 'PRODUCT' THEN
        SELECT pr.product_name, pr.category_id INTO v_name, v_cat
          FROM thefad.product pr WHERE pr.product_id = p_product_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Choose a product.';
        END IF;
        UPDATE thefad.product
           SET discount_id = v_d.discount_id,
               current_price = GREATEST(0.01, ROUND(base_price * (100 - v_d.discount_percentage) / 100.0, 2))
         WHERE product_name = v_name AND category_id = v_cat;
    ELSIF v_scope = 'STORE' THEN
        UPDATE thefad.product
           SET discount_id = v_d.discount_id,
               current_price = GREATEST(0.01, ROUND(base_price * (100 - v_d.discount_percentage) / 100.0, 2));
    ELSE
        RAISE EXCEPTION 'Choose one product or the whole store.';
    END IF;
    GET DIAGNOSTICS p_products_updated = ROW_COUNT;
END;
$$;

-- Removes the promo from a product (all its colors and sizes).
CREATE OR REPLACE PROCEDURE thefad.sp_clear_product_discount(IN p_product_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_name VARCHAR;
    v_cat  INT;
BEGIN
    SELECT pr.product_name, pr.category_id INTO v_name, v_cat
      FROM thefad.product pr WHERE pr.product_id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found.';
    END IF;
    UPDATE thefad.product SET discount_id = NULL, current_price = base_price
     WHERE product_name = v_name AND category_id = v_cat;
END;
$$;

-- Promos do not end by themselves in the database; this resets prices for ended ones.
CREATE OR REPLACE PROCEDURE thefad.sp_expire_promos(INOUT p_cleared INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    UPDATE thefad.product p
       SET discount_id = NULL, current_price = p.base_price
      FROM thefad.discount d
     WHERE d.discount_id = p.discount_id AND d.end_date < CURRENT_DATE;
    GET DIAGNOSTICS p_cleared = ROW_COUNT;
END;
$$;

------------------------------------------------------------------- POS / ORDERS
-- p_items is JSON: [{"product_id": 1, "quantity": 2}, ...]. Prices come from the database.
CREATE OR REPLACE PROCEDURE thefad.sp_create_sale(
    IN p_user_id INT, IN p_fulfillment_type VARCHAR, IN p_payment_method VARCHAR,
    IN p_customer_name VARCHAR, IN p_customer_contact VARCHAR, IN p_delivery_address VARCHAR,
    IN p_items JSONB, INOUT p_sale_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_item     RECORD;
    v_expected INT;
    v_found    INT;
    v_subtotal NUMERIC;
    v_total    NUMERIC;
    v_status   VARCHAR;
    v_base     NUMERIC;
    v_price    NUMERIC;
    v_disc     INT;
BEGIN
    IF p_fulfillment_type NOT IN ('Walk-in', 'Delivery') THEN
        RAISE EXCEPTION 'Choose Walk-in or Delivery.';
    END IF;
    IF p_payment_method NOT IN ('Cash', 'GCash') THEN
        RAISE EXCEPTION 'Choose Cash or GCash.';
    END IF;
    IF p_fulfillment_type = 'Delivery'
       AND (COALESCE(trim(p_customer_name), '') = '' OR COALESCE(trim(p_customer_contact), '') = ''
            OR COALESCE(trim(p_delivery_address), '') = '') THEN
        RAISE EXCEPTION 'Delivery orders need the customer name, contact number and address.';
    END IF;
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Add at least one item to the cart.';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_items) e
                WHERE (e->>'product_id') IS NULL OR COALESCE((e->>'quantity')::INT, 0) <= 0) THEN
        RAISE EXCEPTION 'Every item needs a product and a quantity of at least 1.';
    END IF;

    SELECT COUNT(*), COALESCE(SUM(p.base_price * i.quantity), 0),
           COALESCE(SUM(thefad.fn_effective_price(i.product_id) * i.quantity), 0)
      INTO v_found, v_subtotal, v_total
      FROM (SELECT (e->>'product_id')::INT AS product_id, SUM((e->>'quantity')::INT)::INT AS quantity
              FROM jsonb_array_elements(p_items) e GROUP BY 1) i
      JOIN thefad.product p ON p.product_id = i.product_id AND p.is_active;

    SELECT COUNT(DISTINCT (e->>'product_id')::INT) INTO v_expected FROM jsonb_array_elements(p_items) e;
    IF v_found <> v_expected THEN
        RAISE EXCEPTION 'A product in the cart is no longer available. Remove it and try again.';
    END IF;

    v_status := CASE WHEN p_fulfillment_type = 'Walk-in' THEN 'Completed' ELSE 'Pending' END;
    INSERT INTO thefad.sales (user_id, fulfillment_type, customer_name, customer_contact, delivery_address,
                              subtotal, discount_amount, total_amount, payment_method, order_status)
    VALUES (p_user_id, p_fulfillment_type, NULLIF(trim(p_customer_name), ''), NULLIF(trim(p_customer_contact), ''),
            NULLIF(trim(p_delivery_address), ''), v_subtotal, v_subtotal - v_total, v_total,
            p_payment_method, v_status)
    RETURNING sale_id INTO p_sale_id;

    -- lowest product id first, so two cashiers never lock products in opposite order
    FOR v_item IN
        SELECT (e->>'product_id')::INT AS product_id, SUM((e->>'quantity')::INT)::INT AS quantity
          FROM jsonb_array_elements(p_items) e GROUP BY 1 ORDER BY 1
    LOOP
        SELECT p.base_price, thefad.fn_effective_price(p.product_id), d.discount_id
          INTO v_base, v_price, v_disc
          FROM thefad.product p
          LEFT JOIN thefad.discount d
                 ON d.discount_id = p.discount_id AND CURRENT_DATE BETWEEN d.start_date AND d.end_date
         WHERE p.product_id = v_item.product_id;

        INSERT INTO thefad.sale_item (sale_id, product_id, discount_id, quantity, base_price, unit_price_at_sale)
        VALUES (p_sale_id, v_item.product_id, v_disc, v_item.quantity, v_base, v_price);

        PERFORM thefad.fn_apply_stock_change(v_item.product_id, p_user_id, 'OUT', -v_item.quantity, p_sale_id);
    END LOOP;
END;
$$;

-- Pending -> Out_for_Delivery -> Completed, or Cancelled (stock goes back).
CREATE OR REPLACE PROCEDURE thefad.sp_update_order_status(
    IN p_user_id INT, IN p_sale_id INT, IN p_new_status VARCHAR,
    IN p_rider_service VARCHAR, IN p_rider_contact VARCHAR)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_status VARCHAR;
    v_type   VARCHAR;
    v_item   RECORD;
BEGIN
    SELECT s.order_status, s.fulfillment_type INTO v_status, v_type
      FROM thefad.sales s WHERE s.sale_id = p_sale_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order not found.';
    END IF;

    IF p_new_status = 'Out_for_Delivery' AND v_status = 'Pending' AND v_type = 'Delivery' THEN
        IF COALESCE(trim(p_rider_service), '') = '' OR COALESCE(trim(p_rider_contact), '') = '' THEN
            RAISE EXCEPTION 'Enter the rider service and the rider contact number.';
        END IF;
        UPDATE thefad.sales
           SET order_status = 'Out_for_Delivery', rider_service = trim(p_rider_service),
               rider_contact = trim(p_rider_contact)
         WHERE sale_id = p_sale_id;
    ELSIF p_new_status = 'Completed' AND v_status = 'Out_for_Delivery' THEN
        UPDATE thefad.sales SET order_status = 'Completed' WHERE sale_id = p_sale_id;
    ELSIF p_new_status = 'Cancelled' AND v_status IN ('Pending', 'Out_for_Delivery') THEN
        UPDATE thefad.sales SET order_status = 'Cancelled' WHERE sale_id = p_sale_id;
        FOR v_item IN
            SELECT si.product_id, si.quantity FROM thefad.sale_item si
             WHERE si.sale_id = p_sale_id ORDER BY si.product_id
        LOOP
            PERFORM thefad.fn_apply_stock_change(v_item.product_id, p_user_id, 'RETURN', v_item.quantity, p_sale_id);
        END LOOP;
    ELSE
        RAISE EXCEPTION 'An order that is % cannot be changed to %.', v_status, p_new_status;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_list_sales(
    p_start DATE, p_end DATE, p_status VARCHAR DEFAULT NULL)
RETURNS TABLE (sale_id INT, sale_date TIMESTAMP, cashier TEXT, fulfillment_type VARCHAR,
               customer_name VARCHAR, payment_method VARCHAR, total_amount NUMERIC,
               order_status VARCHAR, item_count BIGINT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT s.sale_id, s.sale_date, u.first_name || ' ' || u.last_name, s.fulfillment_type,
           s.customer_name, s.payment_method, s.total_amount, s.order_status,
           (SELECT COALESCE(SUM(si.quantity), 0) FROM thefad.sale_item si WHERE si.sale_id = s.sale_id)
      FROM thefad.sales s
      JOIN thefad.users u ON u.user_id = s.user_id
     WHERE s.sale_date >= p_start AND s.sale_date < (p_end + 1)
       AND (p_status IS NULL OR s.order_status = p_status)
     ORDER BY s.sale_date DESC, s.sale_id DESC;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_get_sale(p_sale_id INT)
RETURNS TABLE (sale_id INT, user_id INT, cashier TEXT, sale_date TIMESTAMP, fulfillment_type VARCHAR,
               customer_name VARCHAR, customer_contact VARCHAR, delivery_address VARCHAR,
               subtotal NUMERIC, discount_amount NUMERIC, total_amount NUMERIC, payment_method VARCHAR,
               order_status VARCHAR, rider_service VARCHAR, rider_contact VARCHAR)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT s.sale_id, s.user_id, u.first_name || ' ' || u.last_name, s.sale_date, s.fulfillment_type,
           s.customer_name, s.customer_contact, s.delivery_address, s.subtotal, s.discount_amount,
           s.total_amount, s.payment_method, s.order_status, s.rider_service, s.rider_contact
      FROM thefad.sales s JOIN thefad.users u ON u.user_id = s.user_id
     WHERE s.sale_id = p_sale_id;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_sale_items(p_sale_id INT)
RETURNS TABLE (item_id INT, product_id INT, product_name VARCHAR, quantity INT, base_price NUMERIC,
               unit_price_at_sale NUMERIC, line_total NUMERIC, discount_name VARCHAR, quantity_refunded BIGINT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT si.item_id, si.product_id, p.display_name, si.quantity, si.base_price, si.unit_price_at_sale,
           si.unit_price_at_sale * si.quantity, d.discount_name,
           COALESCE((SELECT SUM(r.quantity_refunded) FROM thefad.refund r WHERE r.item_id = si.item_id), 0)
      FROM thefad.sale_item si
      JOIN thefad.product p ON p.product_id = si.product_id
      LEFT JOIN thefad.discount d ON d.discount_id = si.discount_id
     WHERE si.sale_id = p_sale_id
     ORDER BY si.item_id;
END;
$$;

-------------------------------------------------------------------- REFUNDS
CREATE OR REPLACE PROCEDURE thefad.sp_process_refund(
    IN p_user_id INT, IN p_sale_id INT, IN p_item_id INT, IN p_quantity INT,
    IN p_reason TEXT, IN p_method VARCHAR, INOUT p_refund_id INT)
LANGUAGE plpgsql
SET search_path = thefad, public, pg_temp
AS $$
DECLARE
    v_status    VARCHAR;
    v_item      thefad.sale_item%ROWTYPE;
    v_refunded  INT;
    v_open      INT;
BEGIN
    IF p_method NOT IN ('Cash', 'GCash') THEN
        RAISE EXCEPTION 'Choose Cash or GCash for the refund.';
    END IF;
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Refund quantity must be at least 1.';
    END IF;

    SELECT s.order_status INTO v_status FROM thefad.sales s WHERE s.sale_id = p_sale_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order not found.';
    END IF;
    IF v_status NOT IN ('Completed', 'Partially_Refunded') THEN
        RAISE EXCEPTION 'Only completed orders can be refunded (this one is %).', v_status;
    END IF;

    SELECT * INTO v_item FROM thefad.sale_item WHERE item_id = p_item_id AND sale_id = p_sale_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'That item is not part of this order.';
    END IF;

    SELECT COALESCE(SUM(r.quantity_refunded), 0) INTO v_refunded FROM thefad.refund r WHERE r.item_id = p_item_id;
    IF p_quantity > v_item.quantity - v_refunded THEN
        RAISE EXCEPTION 'Only % unit(s) of this item can still be refunded.', v_item.quantity - v_refunded;
    END IF;

    INSERT INTO thefad.refund (sale_id, item_id, quantity_refunded, refund_amount, reason, refund_method, processed_by)
    VALUES (p_sale_id, p_item_id, p_quantity, ROUND(v_item.unit_price_at_sale * p_quantity, 2),
            NULLIF(trim(p_reason), ''), p_method, p_user_id)
    RETURNING refund_id INTO p_refund_id;

    PERFORM thefad.fn_apply_stock_change(v_item.product_id, p_user_id, 'RETURN', p_quantity, p_sale_id);

    SELECT COUNT(*) INTO v_open
      FROM thefad.sale_item si
     WHERE si.sale_id = p_sale_id
       AND si.quantity > COALESCE((SELECT SUM(r.quantity_refunded) FROM thefad.refund r WHERE r.item_id = si.item_id), 0);

    UPDATE thefad.sales
       SET order_status = CASE WHEN v_open = 0 THEN 'Refunded' ELSE 'Partially_Refunded' END
     WHERE sale_id = p_sale_id;
END;
$$;

CREATE OR REPLACE FUNCTION thefad.fn_list_refunds(p_start DATE, p_end DATE)
RETURNS TABLE (refund_id INT, refund_date TIMESTAMP, sale_id INT, product_name VARCHAR,
               quantity_refunded INT, refund_amount NUMERIC, refund_method VARCHAR, reason TEXT,
               processed_by TEXT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT r.refund_id, r.refund_date, r.sale_id, p.display_name, r.quantity_refunded, r.refund_amount,
           r.refund_method, r.reason, u.first_name || ' ' || u.last_name
      FROM thefad.refund r
      LEFT JOIN thefad.sale_item si ON si.item_id = r.item_id
      LEFT JOIN thefad.product p ON p.product_id = si.product_id
      JOIN thefad.users u ON u.user_id = r.processed_by
     WHERE r.refund_date >= p_start AND r.refund_date < (p_end + 1)
     ORDER BY r.refund_date DESC, r.refund_id DESC;
END;
$$;

------------------------------------------------------------------- DASHBOARD
CREATE OR REPLACE FUNCTION thefad.fn_dashboard_summary(p_threshold INT DEFAULT 5)
RETURNS TABLE (sales_today NUMERIC, orders_today BIGINT, pending_deliveries BIGINT, low_stock BIGINT,
               active_promos BIGINT, refunds_today NUMERIC, staff_clocked_in BIGINT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    RETURN QUERY
    SELECT (SELECT COALESCE(SUM(s.total_amount), 0) FROM thefad.sales s
             WHERE s.sale_date::date = CURRENT_DATE AND s.order_status NOT IN ('Cancelled', 'Refunded')),
           (SELECT COUNT(*) FROM thefad.sales s
             WHERE s.sale_date::date = CURRENT_DATE AND s.order_status NOT IN ('Cancelled', 'Refunded')),
           (SELECT COUNT(*) FROM thefad.sales s WHERE s.order_status IN ('Pending', 'Out_for_Delivery')),
           (SELECT COUNT(*) FROM thefad.product p WHERE p.is_active AND p.current_stock <= p_threshold),
           (SELECT COUNT(*) FROM thefad.discount d WHERE CURRENT_DATE BETWEEN d.start_date AND d.end_date),
           (SELECT COALESCE(SUM(r.refund_amount), 0) FROM thefad.refund r WHERE r.refund_date::date = CURRENT_DATE),
           (SELECT COUNT(*) FROM thefad.daily_time_record t WHERE t.time_out IS NULL);
END;
$$;

-- Sales per day for the dashboard chart (days with no sales show as 0).
CREATE OR REPLACE FUNCTION thefad.fn_sales_by_day(p_days INT DEFAULT 7)
RETURNS TABLE (sale_day DATE, total_sales NUMERIC, order_count BIGINT)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
BEGIN
    RETURN QUERY
    SELECT g.d::date, COALESCE(SUM(s.total_amount), 0), COUNT(s.sale_id)
      FROM generate_series(CURRENT_DATE - (p_days - 1), CURRENT_DATE, INTERVAL '1 day') AS g(d)
      LEFT JOIN thefad.sales s
             ON s.sale_date::date = g.d::date AND s.order_status NOT IN ('Cancelled', 'Refunded')
     GROUP BY g.d
     ORDER BY g.d;
END;
$$;

-- Best sellers by units, all colors and sizes of a product counted together.
CREATE OR REPLACE FUNCTION thefad.fn_top_products(p_days INT DEFAULT 7, p_limit INT DEFAULT 5)
RETURNS TABLE (product_name VARCHAR, units BIGINT, revenue NUMERIC)
LANGUAGE plpgsql STABLE
SET search_path = thefad, public, pg_temp
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    SELECT p.product_name, SUM(si.quantity), SUM(si.unit_price_at_sale * si.quantity)
      FROM thefad.sale_item si
      JOIN thefad.sales s ON s.sale_id = si.sale_id
      JOIN thefad.product p ON p.product_id = si.product_id
     WHERE s.sale_date >= CURRENT_DATE - (p_days - 1)
       AND s.order_status NOT IN ('Cancelled', 'Refunded')
     GROUP BY p.product_name
     ORDER BY SUM(si.quantity) DESC, p.product_name
     LIMIT p_limit;
END;
$$;

