-- Standalone implementations of routines previously supplied only by the external database backup.
CREATE OR REPLACE PROCEDURE thefad.sp_create_discount(IN p_name VARCHAR, IN p_percent INT, IN p_start DATE, IN p_end DATE,
    IN p_scope VARCHAR, IN p_product_id INT, INOUT p_discount_id INT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_applied INT;
BEGIN
    IF COALESCE(length(trim(p_name)),0)=0 THEN RAISE EXCEPTION 'Promo name is required.'; END IF;
    IF p_percent IS NULL OR p_percent NOT BETWEEN 1 AND 99 THEN RAISE EXCEPTION 'Discount must be 1–99 percent.'; END IF;
    IF p_start IS NULL OR p_end IS NULL OR p_end < p_start THEN RAISE EXCEPTION 'Choose a valid date range.'; END IF;
    IF p_scope IS NULL OR p_scope NOT IN ('NONE','STORE','PRODUCT') THEN RAISE EXCEPTION 'Choose a valid promo scope.'; END IF;
    INSERT INTO discount(discount_name,discount_percentage,start_date,end_date) VALUES(trim(p_name),p_percent,p_start,p_end) RETURNING discount_id INTO p_discount_id;
    IF p_scope <> 'NONE' THEN CALL sp_apply_discount(p_discount_id,p_scope,p_product_id,v_applied); END IF;
END;
$$;
CREATE OR REPLACE PROCEDURE thefad.sp_update_discount(IN p_discount_id INT, IN p_name VARCHAR, IN p_percent INT,
    IN p_start DATE, IN p_end DATE, IN p_end_now BOOLEAN, INOUT p_updated INT)
LANGUAGE plpgsql SET search_path = thefad, public, pg_temp AS $$
DECLARE v_d discount%ROWTYPE;
BEGIN
    SELECT * INTO v_d FROM discount WHERE discount_id=p_discount_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Promo not found.'; END IF;
    IF p_end_now THEN
        -- end_date is inclusive; yesterday ends an active promo immediately.
        UPDATE discount SET end_date=GREATEST(start_date,CURRENT_DATE-1) WHERE discount_id=p_discount_id;
        UPDATE product SET current_price=base_price,discount_id=NULL WHERE discount_id=p_discount_id;
        -- For future campaigns, move the entire interval to yesterday to ensure it cannot reactivate.
        IF v_d.start_date >= CURRENT_DATE THEN UPDATE discount SET start_date=CURRENT_DATE-1,end_date=CURRENT_DATE-1 WHERE discount_id=p_discount_id; END IF;
    ELSE
        IF COALESCE(length(trim(p_name)),0)=0 OR p_percent IS NULL OR p_percent NOT BETWEEN 1 AND 99
           OR p_start IS NULL OR p_end IS NULL OR p_end < p_start THEN RAISE EXCEPTION 'Enter a name, 1–99 percent, and a valid date range.'; END IF;
        UPDATE discount SET discount_name=trim(p_name),discount_percentage=p_percent,start_date=p_start,end_date=p_end WHERE discount_id=p_discount_id;
        UPDATE product SET current_price=CASE WHEN CURRENT_DATE BETWEEN p_start AND p_end THEN round(base_price*(1-p_percent/100.0),2) ELSE base_price END WHERE discount_id=p_discount_id;
    END IF;
    GET DIAGNOSTICS p_updated=ROW_COUNT;
END;
$$;
CREATE OR REPLACE FUNCTION thefad.fn_refund_report(p_start DATE,p_end DATE)
RETURNS TABLE(refund_method VARCHAR,refund_count BIGINT,units_refunded BIGINT,total_refunded NUMERIC,gross_sales NUMERIC,net_sales NUMERIC)
LANGUAGE sql STABLE SET search_path = thefad, public, pg_temp AS $$
    WITH refunds AS (
      SELECT r.refund_method,count(*) n,sum(r.quantity_refunded)::BIGINT units,sum(r.refund_amount) amount
      FROM refund r WHERE r.refund_date >= p_start AND r.refund_date < p_end+1 GROUP BY r.refund_method
    ), gross AS (
      SELECT COALESCE(sum(s.total_amount),0) amount FROM sales s WHERE s.sale_date >= p_start AND s.sale_date < p_end+1
        AND s.order_status IN ('Completed','Refunded','Partially_Refunded')
    ) SELECT refund_method,n,units,amount,NULL::NUMERIC,NULL::NUMERIC FROM refunds
      UNION ALL SELECT 'TOTAL'::VARCHAR,COALESCE(sum(n),0)::BIGINT,COALESCE(sum(units),0)::BIGINT,
        COALESCE(sum(amount),0),(SELECT amount FROM gross),(SELECT amount FROM gross)-COALESCE(sum(amount),0) FROM refunds;
$$;
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
