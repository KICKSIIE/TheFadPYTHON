-- Run after setup_all.sql. Every row should say OK.
SELECT 'column product.is_active' AS item,
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema='thefad' AND table_name='product' AND column_name='is_active') THEN 'OK' ELSE 'MISSING' END AS status
UNION ALL
SELECT 'column users.is_active',
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_schema='thefad' AND table_name='users' AND column_name='is_active') THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT 'columns product.description, size, color, display_name',
       CASE WHEN (SELECT count(*) FROM information_schema.columns WHERE table_schema='thefad' AND table_name='product'
                   AND column_name IN ('description','size','color','display_name')) = 4
             AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='thefad'
                   AND table_name='product' AND column_name='image_id') THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT 'tables product_image, product_photo',
       CASE WHEN to_regclass('thefad.product_image') IS NOT NULL
             AND to_regclass('thefad.product_photo') IS NOT NULL THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT 'columns users.hired_on, daily_time_record.note',
       CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='thefad' AND table_name='users' AND column_name='hired_on')
             AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='thefad' AND table_name='daily_time_record' AND column_name='note')
            THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT 'tables shift_setting, overtime_permit + 1 schedule row',
       CASE WHEN to_regclass('thefad.shift_setting') IS NOT NULL AND to_regclass('thefad.overtime_permit') IS NOT NULL
             AND (SELECT count(*) FROM thefad.shift_setting) = 1 THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT 'columns daily_time_record.shift_type, permit_id',
       CASE WHEN (SELECT count(*) FROM information_schema.columns WHERE table_schema='thefad' AND table_name='daily_time_record'
                   AND column_name IN ('shift_type','permit_id')) = 2 THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT 'extension pgcrypto',
       CASE WHEN EXISTS (SELECT 1 FROM pg_extension WHERE extname='pgcrypto') THEN 'OK' ELSE 'MISSING' END
UNION ALL
SELECT r.name,
       CASE WHEN EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='thefad' AND p.proname=r.name) THEN 'OK' ELSE 'MISSING' END
  FROM (VALUES ('fn_login_user'),('fn_list_categories'),('sp_create_category'),('sp_update_category'),
               ('sp_delete_category'),('fn_list_products'),('fn_get_product'),('sp_create_product'),
               ('sp_update_product'),('sp_set_product_active'),('fn_list_staff'),('fn_get_staff'),
               ('sp_create_staff'),('sp_update_staff'),('sp_set_staff_active'),('sp_clock_in'),
               ('fn_list_variants'),('sp_save_shift'),('fn_get_shift_setting'),('sp_save_shift_setting'),('sp_allow_overtime'),('sp_update_overtime'),('sp_cancel_overtime'),('fn_list_overtime'),('fn_get_overtime'),('fn_my_overtime'),('sp_overtime_in'),('sp_overtime_out'),('fn_get_shift'),('fn_attendance_board'),('sp_add_variant'),('fn_sales_by_day'),('fn_top_products'),('fn_list_product_photos'),('sp_add_product_photo'),('sp_remove_product_photo'),('sp_set_cover_photo'),('fn_get_image'),('sp_clock_out'),('fn_my_attendance'),
               ('fn_effective_price'),('fn_apply_stock_change'),('fn_list_inventory'),('fn_inventory_history'),('sp_stock_in'),('sp_stock_out'),('sp_adjust_stock'),('fn_list_discounts'),('fn_get_discount'),('fn_discount_products'),('sp_apply_discount'),('sp_clear_product_discount'),('sp_expire_promos'),('sp_create_discount'),('sp_update_discount'),('sp_create_sale'),('sp_update_order_status'),('fn_list_sales'),('fn_get_sale'),('fn_sale_items'),('sp_process_refund'),('fn_list_refunds'),('fn_refund_report'),('fn_dashboard_summary'),('fn_audit_logs'),('fn_verify_management_pin'),('sp_set_management_pin'),('fn_payroll'),('sp_delete_unused_discount')) AS r(name)
UNION ALL
SELECT 'dev accounts (need 2)',
       CASE WHEN (SELECT count(*) FROM thefad.users WHERE username IN ('dev_admin','dev_cashier')) = 2
            THEN 'OK' ELSE 'MISSING' END;

-- Direct login test: should return one row for dev_admin.
SELECT * FROM thefad.fn_login_user('dev_admin', 'Admin@1234');
