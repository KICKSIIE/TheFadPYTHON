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
