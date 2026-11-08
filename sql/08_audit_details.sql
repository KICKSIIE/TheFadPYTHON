BEGIN;

-- Add staff identity snapshots without changing attendance enforcement.
ALTER TABLE thefad.change_audit ADD COLUMN IF NOT EXISTS actor_name TEXT;
ALTER TABLE thefad.change_audit ADD COLUMN IF NOT EXISTS actor_role TEXT;

-- Redact credentials at storage as well as at the presentation boundary.
CREATE OR REPLACE FUNCTION thefad.fn_audit_snapshot(p_row JSONB) RETURNS JSONB
LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(jsonb_object_agg(key, value), '{}'::jsonb)
    FROM jsonb_each(p_row)
    WHERE key !~* '(password|passwd|pin|secret|token|image_data)';
$$;
CREATE OR REPLACE FUNCTION thefad.fn_audit_change() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_old JSONB; v_new JSONB; v_actor TEXT; v_name TEXT; v_role TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN v_old := fn_audit_snapshot(to_jsonb(OLD)); END IF;
    IF TG_OP <> 'DELETE' THEN v_new := fn_audit_snapshot(to_jsonb(NEW)); END IF;
    IF TG_OP = 'UPDATE' AND v_old = v_new AND (TG_TABLE_NAME <> 'users' OR to_jsonb(OLD) = to_jsonb(NEW)) THEN RETURN NEW; END IF;
    v_actor := COALESCE(NULLIF(current_setting('app.current_user', true), ''), 'system');
    SELECT concat_ws(' ', first_name, last_name), user_type INTO v_name, v_role FROM users WHERE username=v_actor;
    INSERT INTO change_audit(actor, approved_by, entity, action, before_data, after_data, actor_name, actor_role)
    VALUES (v_actor, NULLIF(current_setting('app.approved_by', true), ''), TG_TABLE_NAME, TG_OP,
            v_old, v_new, v_name, v_role);
    RETURN COALESCE(NEW, OLD);
END;
$$;


-- PIN events use a dedicated routine; enrich all event types at insertion.
CREATE OR REPLACE FUNCTION thefad.fn_audit_identity() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
BEGIN
    SELECT concat_ws(' ', first_name, last_name), user_type INTO NEW.actor_name, NEW.actor_role
    FROM users WHERE username=NEW.actor;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS audit_identity ON thefad.change_audit;
CREATE TRIGGER audit_identity BEFORE INSERT ON thefad.change_audit FOR EACH ROW EXECUTE FUNCTION thefad.fn_audit_identity();

-- Photo metadata is useful history; binary contents are always excluded.
DO $$ DECLARE v_table TEXT; BEGIN
    FOREACH v_table IN ARRAY ARRAY['product_photo', 'product_image'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS record_change ON thefad.%I', v_table);
        EXECUTE format('CREATE TRIGGER record_change AFTER INSERT OR UPDATE OR DELETE ON thefad.%I FOR EACH ROW EXECUTE FUNCTION thefad.fn_audit_change()', v_table);
    END LOOP;
END $$;

COMMIT;
