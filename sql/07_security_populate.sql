-- Populate the security, audit and payroll routines that an older database may not have yet.
-- Run once after 00-06 (or on any database that already has the attendance part of 05).
-- Everything here is additive and safe to re-run: CREATE ... IF NOT EXISTS / CREATE OR REPLACE.
-- The attendance routines and attendance triggers stay out of this file: attendance is enforced in Flask
-- (attendance_store.py), so no database trigger is installed here.

-- Approval PIN storage and the tamper-evident audit table.
CREATE TABLE IF NOT EXISTS thefad.management_pin (
    user_id INT PRIMARY KEY REFERENCES thefad.users(user_id),
    pin_hash TEXT NOT NULL,
    failed_attempts INT NOT NULL DEFAULT 0,
    locked_until TIMESTAMP
);
CREATE TABLE IF NOT EXISTS thefad.change_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP(0),
    actor TEXT NOT NULL,
    approved_by TEXT,
    entity TEXT NOT NULL,
    action TEXT NOT NULL,
    before_data JSONB,
    after_data JSONB
);
CREATE INDEX IF NOT EXISTS change_audit_date ON thefad.change_audit(occurred_at DESC, audit_id DESC);

-- Record every change on the business tables, without credentials or binary photos.
CREATE OR REPLACE FUNCTION thefad.fn_audit_change() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_old JSONB; v_new JSONB;
BEGIN
    IF TG_OP <> 'INSERT' THEN v_old := to_jsonb(OLD) - ARRAY['password_hash','master_pin_code','pin_hash','image_data']; END IF;
    IF TG_OP <> 'DELETE' THEN v_new := to_jsonb(NEW) - ARRAY['password_hash','master_pin_code','pin_hash','image_data']; END IF;
    IF TG_OP = 'UPDATE' AND v_old = v_new THEN RETURN NEW; END IF;
    INSERT INTO change_audit(actor, approved_by, entity, action, before_data, after_data)
    VALUES (COALESCE(NULLIF(current_setting('app.current_user', true), ''), 'system'),
            NULLIF(current_setting('app.approved_by', true), ''), TG_TABLE_NAME, TG_OP, v_old, v_new);
    RETURN COALESCE(NEW, OLD);
END;
$$;
DO $$ DECLARE v_table TEXT; BEGIN
    FOREACH v_table IN ARRAY ARRAY['product','category','users','discount','sales','sale_item','refund',
                                  'inventory_logs','daily_time_record','shift_setting','overtime_permit'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS record_change ON thefad.%I', v_table);
        EXECUTE format('CREATE TRIGGER record_change AFTER INSERT OR UPDATE OR DELETE ON thefad.%I FOR EACH ROW EXECUTE FUNCTION thefad.fn_audit_change()', v_table);
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION thefad.fn_audit_logs(p_start DATE, p_end DATE, p_actor TEXT, p_entity TEXT, p_action TEXT, p_offset INT)
RETURNS SETOF thefad.change_audit LANGUAGE sql STABLE SET search_path = thefad, public, pg_temp AS $$
    SELECT * FROM change_audit WHERE occurred_at >= p_start AND occurred_at < p_end + 1
      AND (p_actor IS NULL OR actor ILIKE '%' || p_actor || '%')
      AND (p_entity IS NULL OR entity = p_entity) AND (p_action IS NULL OR action = p_action)
    ORDER BY occurred_at DESC, audit_id DESC LIMIT 51 OFFSET GREATEST(0, p_offset);
$$;
CREATE OR REPLACE FUNCTION thefad.fn_reject_audit_mutation() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit history cannot be edited or deleted.'; END $$;
DROP TRIGGER IF EXISTS protect_audit ON thefad.change_audit;
CREATE TRIGGER protect_audit BEFORE UPDATE OR DELETE OR TRUNCATE ON thefad.change_audit FOR EACH STATEMENT EXECUTE FUNCTION thefad.fn_reject_audit_mutation();

-- Approval PIN: set it with the admin password, verify it with a 5-try / 15-minute lockout.
CREATE OR REPLACE PROCEDURE thefad.sp_set_management_pin(IN p_user_id INT, IN p_password TEXT, IN p_pin TEXT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM fn_login_user((SELECT username FROM users WHERE user_id=p_user_id), p_password) WHERE user_type='AD') THEN RAISE EXCEPTION 'Verify your admin password.'; END IF;
    IF p_pin IS NULL OR p_pin !~ '^[0-9]{6,12}$' THEN RAISE EXCEPTION 'Use a PIN of 6 to 12 digits.'; END IF;
    INSERT INTO management_pin(user_id,pin_hash) VALUES(p_user_id,crypt(p_pin,gen_salt('bf')))
    ON CONFLICT(user_id) DO UPDATE SET pin_hash=EXCLUDED.pin_hash, failed_attempts=0, locked_until=NULL;
    INSERT INTO change_audit(actor,entity,action) SELECT username,'management_pin','SET_PIN' FROM users WHERE user_id=p_user_id;
END;
$$;
CREATE OR REPLACE FUNCTION thefad.fn_verify_management_pin(p_username TEXT, p_pin TEXT)
RETURNS TABLE(verified BOOLEAN) LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_pin management_pin%ROWTYPE; v_user INT;
BEGIN
    SELECT user_id INTO v_user FROM users WHERE username=p_username AND is_active AND user_type='AD';
    SELECT * INTO v_pin FROM management_pin WHERE user_id=v_user;
    IF NOT FOUND THEN RETURN QUERY SELECT FALSE; RETURN; END IF;
    RETURN QUERY SELECT COALESCE(v_pin.pin_hash = crypt(p_pin,v_pin.pin_hash),FALSE);
END;
$$;

-- Gross-pay estimate for the payroll page.
CREATE OR REPLACE FUNCTION thefad.fn_payroll(p_start DATE, p_end DATE)
RETURNS TABLE(user_id INT, full_name TEXT, hourly_rate NUMERIC, days_worked BIGINT, late_days BIGINT,
              regular_hours NUMERIC, overtime_hours NUMERIC, regular_pay NUMERIC, overtime_pay NUMERIC, gross_pay NUMERIC)
LANGUAGE sql STABLE SET search_path = thefad, public, pg_temp AS $$
    WITH hours AS (
        SELECT u.user_id, concat_ws(' ', u.first_name, u.last_name) full_name, COALESCE(u.hourly_rate,0) hourly_rate,
          count(t.dtr_id) FILTER(WHERE t.shift_type='Regular' AND t.time_out IS NOT NULL AND t.status <> 'Absent') days_worked,
          count(t.dtr_id) FILTER(WHERE t.shift_type='Regular' AND t.status='Late') late_days,
          COALESCE(sum(t.total_hours) FILTER(WHERE t.shift_type='Regular' AND t.time_out IS NOT NULL AND t.status <> 'Absent'),0) regular_hours,
          COALESCE(sum(t.total_hours) FILTER(WHERE t.shift_type='Overtime' AND t.time_out IS NOT NULL AND t.status <> 'Absent'),0) overtime_hours
        FROM users u LEFT JOIN daily_time_record t ON t.user_id=u.user_id AND t.time_in::date BETWEEN p_start AND p_end
        GROUP BY u.user_id
    ) SELECT *, round(regular_hours*hourly_rate,2), round(overtime_hours*hourly_rate,2), round((regular_hours+overtime_hours)*hourly_rate,2) FROM hours;
$$;

-- Delete a promo that no sale has used (the promo page's delete action).
CREATE OR REPLACE PROCEDURE thefad.sp_delete_unused_discount(IN p_discount_id INT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    PERFORM 1 FROM discount WHERE discount_id=p_discount_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Promo not found.'; END IF;
    IF EXISTS(SELECT 1 FROM sale_item WHERE discount_id=p_discount_id) THEN RAISE EXCEPTION 'A sale uses this promo. End it instead.'; END IF;
    UPDATE product SET discount_id=NULL,current_price=base_price WHERE discount_id=p_discount_id;
    DELETE FROM discount WHERE discount_id=p_discount_id;
END;
$$;

-- Product-level names for a promo, so the promo list shows one chip per product (not per color/size).
CREATE OR REPLACE FUNCTION thefad.fn_discount_product_names(p_discount_id INT)
RETURNS TABLE (product_name VARCHAR, variants BIGINT)
LANGUAGE sql STABLE SET search_path = thefad, public, pg_temp AS $$
    SELECT p.product_name, count(*)::BIGINT
      FROM thefad.product p
     WHERE p.discount_id = p_discount_id
     GROUP BY p.product_name
     ORDER BY p.product_name;
$$;
