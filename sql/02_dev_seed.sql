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
