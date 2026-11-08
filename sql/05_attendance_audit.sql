-- Fixed, local shop-time attendance windows, approval credentials and redacted audit trail.
ALTER TABLE thefad.daily_time_record ADD COLUMN IF NOT EXISTS scheduled_end TIMESTAMP;
UPDATE thefad.daily_time_record t SET scheduled_end = t.time_in::date +
    CASE WHEN t.shift_type = 'Overtime' THEN
        (SELECT p.end_time FROM thefad.overtime_permit p WHERE p.permit_id=t.permit_id)
    ELSE (SELECT s.shift_end FROM thefad.shift_setting s WHERE s.setting_id=1) END
WHERE t.scheduled_end IS NULL;
-- Legacy after-hours clock-ins are closed with zero rounded hours for admin review.
UPDATE thefad.daily_time_record SET scheduled_end=time_in+INTERVAL '1 second',
    note=left(concat_ws('; ',NULLIF(note,''),'Legacy clock-in outside schedule; admin review required'),200)
WHERE time_out IS NULL AND scheduled_end <= time_in;

CREATE INDEX IF NOT EXISTS attendance_due ON thefad.daily_time_record(scheduled_end) WHERE time_out IS NULL;

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

CREATE OR REPLACE FUNCTION thefad.fn_audit_change() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_old JSONB; v_new JSONB;
BEGIN
    -- Exclude credentials and binary photos from all snapshots.
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

CREATE OR REPLACE FUNCTION thefad.fn_close_expired_shifts() RETURNS INT
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_count INT;
BEGIN
    UPDATE daily_time_record SET time_out = scheduled_end,
        total_hours = round(GREATEST(0, EXTRACT(EPOCH FROM (scheduled_end - time_in))) / 3600, 2),
        note = left(concat_ws('; ', NULLIF(note, ''), 'Automatically closed at scheduled end'), 200)
    WHERE time_out IS NULL AND scheduled_end <= LOCALTIMESTAMP(0);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
DROP FUNCTION IF EXISTS thefad.fn_staff_access(INT);
CREATE OR REPLACE FUNCTION thefad.fn_staff_access(p_user_id INT)
RETURNS TABLE(active BOOLEAN, allowed BOOLEAN, can_clock_in BOOLEAN, shop_now TIMESTAMP, shift_end TIMESTAMP, user_type VARCHAR)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_now TIMESTAMP := LOCALTIMESTAMP(0); v_start TIMESTAMP; v_end TIMESTAMP; v_work BOOLEAN;
BEGIN
    PERFORM fn_close_expired_shifts();
    SELECT v_now::date + s.shift_start, v_now::date + s.shift_end INTO v_start, v_end FROM shift_setting s WHERE setting_id = 1;
    v_work := EXTRACT(ISODOW FROM v_now) IN (1,2,3,4,5,6);
    RETURN QUERY SELECT u.is_active,
      u.is_active AND EXISTS(SELECT 1 FROM daily_time_record t WHERE t.user_id = u.user_id
           AND t.time_out IS NULL AND v_now >= t.time_in AND v_now < t.scheduled_end),
      u.is_active AND v_work AND v_now >= v_start AND v_now < v_end
           AND NOT EXISTS(SELECT 1 FROM daily_time_record t WHERE t.user_id=u.user_id AND t.shift_type='Regular' AND t.time_in::date=v_now::date),
      v_now, COALESCE((SELECT t.scheduled_end FROM daily_time_record t WHERE t.user_id=u.user_id AND t.shift_type='Regular' AND t.time_out IS NULL LIMIT 1),v_end), u.user_type FROM users u WHERE u.user_id = p_user_id;
END;
$$;
CREATE OR REPLACE FUNCTION thefad.fn_attendance_window() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    IF NEW.scheduled_end IS NULL THEN
        IF NEW.shift_type = 'Overtime' THEN
            SELECT work_date + end_time INTO NEW.scheduled_end FROM overtime_permit WHERE permit_id = NEW.permit_id;
        ELSE
            SELECT NEW.time_in::date + shift_end INTO NEW.scheduled_end FROM shift_setting WHERE setting_id = 1;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS attendance_window ON thefad.daily_time_record;
CREATE TRIGGER attendance_window BEFORE INSERT ON thefad.daily_time_record FOR EACH ROW EXECUTE FUNCTION thefad.fn_attendance_window();

CREATE OR REPLACE PROCEDURE thefad.sp_clock_in(IN p_user_id INT, IN p_shift_start TIME, IN p_grace_minutes INT, IN p_max_hours NUMERIC, INOUT p_dtr_id INT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_access RECORD; v_start TIME; v_grace INT;
BEGIN
    PERFORM 1 FROM users WHERE user_id = p_user_id FOR UPDATE;
    SELECT * INTO v_access FROM fn_staff_access(p_user_id);
    IF NOT COALESCE(v_access.can_clock_in, FALSE) THEN RAISE EXCEPTION 'Clock in is available once per workday, during the scheduled shift only.'; END IF;
    IF EXISTS(SELECT 1 FROM daily_time_record WHERE user_id=p_user_id AND time_out IS NULL) THEN RAISE EXCEPTION 'Close your current shift first.'; END IF;
    SELECT shift_start, grace_minutes INTO v_start, v_grace FROM shift_setting WHERE setting_id=1;
    INSERT INTO daily_time_record(user_id, time_in, status, scheduled_end)
    VALUES(p_user_id, v_access.shop_now, CASE WHEN v_access.shop_now::time > v_start + make_interval(mins=>v_grace) THEN 'Late' ELSE 'Present' END, v_access.shift_end)
    RETURNING dtr_id INTO p_dtr_id;
END;
$$;
CREATE OR REPLACE PROCEDURE thefad.sp_clock_out(IN p_user_id INT, IN p_shift_hours NUMERIC, IN p_max_hours NUMERIC, IN p_time_out TIMESTAMP, INOUT p_dtr_id INT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    IF p_time_out IS NOT NULL THEN RAISE EXCEPTION 'Ask an admin to correct attendance with a reason.'; END IF;
    PERFORM fn_close_expired_shifts();
    SELECT dtr_id INTO p_dtr_id FROM daily_time_record WHERE user_id=p_user_id AND shift_type='Regular'
      AND time_in::date=CURRENT_DATE AND time_out IS NOT NULL ORDER BY dtr_id DESC LIMIT 1;
    IF p_dtr_id IS NULL THEN RAISE EXCEPTION 'Your shift closes automatically at the scheduled end. Ask an admin for corrections.'; END IF;
END;
$$;
-- Prevent concurrent double starts for overtime and reject inactive accounts.
CREATE OR REPLACE FUNCTION thefad.fn_overtime_guard() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    PERFORM 1 FROM users WHERE user_id=NEW.user_id AND is_active FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Staff account is inactive.'; END IF;
    IF NEW.time_out IS NULL AND EXISTS(SELECT 1 FROM daily_time_record WHERE user_id=NEW.user_id AND time_out IS NULL) THEN RAISE EXCEPTION 'You are already clocked in.'; END IF;
    IF NEW.permit_id IS NOT NULL AND EXISTS(SELECT 1 FROM daily_time_record WHERE permit_id=NEW.permit_id) THEN RAISE EXCEPTION 'Overtime was already recorded.'; END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS attendance_guard ON thefad.daily_time_record;
CREATE TRIGGER attendance_guard BEFORE INSERT ON thefad.daily_time_record FOR EACH ROW EXECUTE FUNCTION thefad.fn_overtime_guard();

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

CREATE OR REPLACE FUNCTION thefad.fn_reject_audit_mutation() RETURNS TRIGGER
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit history cannot be edited or deleted.'; END $$;
DROP TRIGGER IF EXISTS protect_audit ON thefad.change_audit;
CREATE TRIGGER protect_audit BEFORE UPDATE OR DELETE OR TRUNCATE ON thefad.change_audit FOR EACH STATEMENT EXECUTE FUNCTION thefad.fn_reject_audit_mutation();

CREATE OR REPLACE PROCEDURE thefad.sp_overtime_out(IN p_user_id INT, INOUT p_dtr_id INT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    PERFORM fn_close_expired_shifts();
    SELECT dtr_id INTO p_dtr_id FROM daily_time_record WHERE user_id=p_user_id AND shift_type='Overtime'
      AND time_in::date=CURRENT_DATE AND time_out IS NOT NULL ORDER BY dtr_id DESC LIMIT 1;
    IF p_dtr_id IS NULL THEN RAISE EXCEPTION 'Overtime closes automatically at its approved end.'; END IF;
END;
$$;
-- A running permit may be extended with admin approval; past records stay fixed.
CREATE OR REPLACE PROCEDURE thefad.sp_update_overtime(IN p_permit_id INT, IN p_start TIME, IN p_end TIME, IN p_grace_minutes INT, IN p_note VARCHAR)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_p overtime_permit%ROWTYPE;
BEGIN
    SELECT * INTO v_p FROM overtime_permit WHERE permit_id=p_permit_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Overtime not found.'; END IF;
    IF p_start IS NULL OR p_end IS NULL OR p_end <= p_start OR p_end - p_start > INTERVAL '8 hours' THEN RAISE EXCEPTION 'Choose an overtime window of up to 8 hours.'; END IF;
    IF COALESCE(p_grace_minutes,0) NOT BETWEEN 0 AND 120 THEN RAISE EXCEPTION 'Grace must be 0–120 minutes.'; END IF;
    IF EXISTS(SELECT 1 FROM daily_time_record WHERE permit_id=p_permit_id) THEN
        IF v_p.work_date + v_p.end_time <= LOCALTIMESTAMP OR p_start <> v_p.start_time OR p_end <= v_p.end_time OR length(trim(COALESCE(p_note,''))) < 3
           OR EXISTS(SELECT 1 FROM daily_time_record WHERE permit_id=p_permit_id AND time_out IS NOT NULL) THEN
            RAISE EXCEPTION 'Running overtime can only be extended before it ends, with the same start and a reason.';
        END IF;
    END IF;
    UPDATE overtime_permit SET start_time=p_start, end_time=p_end, grace_minutes=COALESCE(p_grace_minutes,grace_minutes), note=NULLIF(trim(p_note),'') WHERE permit_id=p_permit_id;
    UPDATE daily_time_record SET scheduled_end=v_p.work_date + p_end WHERE permit_id=p_permit_id AND time_out IS NULL;
END;
$$;
CREATE OR REPLACE FUNCTION thefad.fn_permit_window_guard() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    IF EXTRACT(ISODOW FROM NEW.work_date) IN (1,2,3,4,5,6) AND NEW.start_time < (SELECT shift_end FROM shift_setting WHERE setting_id=1)
      AND NEW.end_time > (SELECT shift_start FROM shift_setting WHERE setting_id=1) THEN
        RAISE EXCEPTION 'Overtime cannot overlap the regular shift.';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS permit_window_guard ON thefad.overtime_permit;
CREATE TRIGGER permit_window_guard BEFORE INSERT OR UPDATE ON thefad.overtime_permit FOR EACH ROW EXECUTE FUNCTION thefad.fn_permit_window_guard();

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
