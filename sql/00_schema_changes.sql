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
