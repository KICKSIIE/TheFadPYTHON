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
    PERFORM set_config('app.stock_receipt', COALESCE(p_sale_id::text, ''), true);
    UPDATE thefad.product SET current_stock = v_new WHERE product_id = p_product_id;
    INSERT INTO thefad.inventory_logs (product_id, sale_id, user_id, transaction_type, quantity_changed, balance_after)
    VALUES (p_product_id, p_sale_id, p_user_id, p_type, p_delta, v_new);
    PERFORM set_config('app.stock_receipt', '', true);
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
     WHERE (p_search IS NULL OR p.display_name ILIKE '%' || p_search || '%'
            OR p.product_id::text = btrim(p_search))
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

    -- Lock all cart products before reading prices and computing totals.
    PERFORM p.product_id FROM thefad.product p
      WHERE p.product_id IN (SELECT (e->>'product_id')::INT FROM jsonb_array_elements(p_items) e)
      ORDER BY p.product_id FOR UPDATE;

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
