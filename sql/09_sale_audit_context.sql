BEGIN;
-- Link stock snapshots to the receipt in the same business transaction.
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
    PERFORM set_config('app.stock_receipt', COALESCE(p_sale_id::text, ''), true);
    UPDATE thefad.product SET current_stock = v_new WHERE product_id = p_product_id;
    INSERT INTO thefad.inventory_logs (product_id, sale_id, user_id, transaction_type, quantity_changed, balance_after)
    VALUES (p_product_id, p_sale_id, p_user_id, p_type, p_delta, v_new);
    PERFORM set_config('app.stock_receipt', '', true);
    RETURN v_new;
END;
$$;
CREATE OR REPLACE FUNCTION thefad.fn_audit_change() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_old JSONB; v_new JSONB; v_actor TEXT; v_name TEXT; v_role TEXT;
BEGIN
    IF TG_OP <> 'INSERT' THEN v_old := fn_audit_snapshot(to_jsonb(OLD)); END IF;
    IF TG_OP <> 'DELETE' THEN v_new := fn_audit_snapshot(to_jsonb(NEW)); END IF;
    IF TG_OP = 'UPDATE' AND v_old = v_new AND (TG_TABLE_NAME <> 'users' OR to_jsonb(OLD) = to_jsonb(NEW)) THEN RETURN NEW; END IF;
    IF TG_TABLE_NAME = 'product' AND NULLIF(current_setting('app.stock_receipt', true), '') IS NOT NULL THEN
        v_new := v_new || jsonb_build_object('sale_id', current_setting('app.stock_receipt')::int);
    END IF;
    v_actor := COALESCE(NULLIF(current_setting('app.current_user', true), ''), 'system');
    SELECT concat_ws(' ', first_name, last_name), user_type INTO v_name, v_role FROM users WHERE username=v_actor;
    INSERT INTO change_audit(actor, approved_by, entity, action, before_data, after_data, actor_name, actor_role)
    VALUES (v_actor, NULLIF(current_setting('app.approved_by', true), ''), TG_TABLE_NAME, TG_OP,
            v_old, v_new, v_name, v_role);
    RETURN COALESCE(NEW, OLD);
END;
$$;
COMMIT;
