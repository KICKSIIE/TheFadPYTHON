/**
 * All database access goes through this file.
 *
 * Most screens call stored routines. Attendance is enforced in the Node backend and reads and writes
 * existing tables through withClient():
 *
 *     callFunction('fn_list_discounts')                          -> array of rows
 *     callFunctionOne('fn_get_product', 30)                      -> one row or null
 *     callProcedure('sp_create_sale', ...args)                   -> row of INOUT values
 */
import pg from 'pg';

import { config } from './config.js';
import { currentContext } from './context.js';
import { parseTimestamp } from './time.js';

const { Pool, types } = pg;

// Timestamps are shop-local wall clock; parse them with the fixed +08:00 offset.
types.setTypeParser(1114, (value) => parseTimestamp(value));
types.setTypeParser(1082, (value) => parseTimestamp(value));
types.setTypeParser(1184, (value) => new Date(value));
types.setTypeParser(20, (value) => Number(value));       // int8
types.setTypeParser(1700, (value) => Number(value));     // numeric
// 1083 (time) stays a string like "09:00:00".

export class DbError extends Error {}

let pool = null;
const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function initDb() {
  if (pool) return pool;
  pool = new Pool({
    connectionString: config.databaseUrl,
    max: 10,
    connectionTimeoutMillis: 5000,
    idleTimeoutMillis: 30000,
    options: `-c search_path=${config.dbSchema},public`,
  });
  pool.on('error', () => {});
  return pool;
}

export function closeDb() {
  if (pool) pool.end();
  pool = null;
}

function checkIdent(name) {
  if (!IDENT.test(name)) throw new Error(`Invalid routine name: ${name}`);
}

function translate(error) {
  if (error instanceof DbError) return error;
  if (error && typeof error.code === 'string' && /^[0-9A-Z]{5}$/.test(error.code)) {
    return new DbError(error.message || 'The database could not complete the request.');
  }
  return new DbError('Cannot reach the database. Try again in a moment.');
}

async function prepare(client) {
  const { session } = currentContext();
  await client.query("SELECT set_config('TimeZone', $1, true)", [config.timezone]);
  const username = session && session.username;
  if (username) {
    await client.query("SELECT set_config('app.current_user', $1, true)", [username]);
  }
  const approver = (session && session.approval_actor) || '';
  await client.query("SELECT set_config('app.approved_by', $1, true)", [approver]);
}

/** Run a function inside one transaction (commits on success, rolls back on error). */
export async function withClient(fn) {
  initDb();
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await prepare(client);
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    try { await client.query('ROLLBACK'); } catch { /* connection already gone */ }
    throw translate(error);
  } finally {
    client.release();
  }
}

function placeholders(count) {
  return Array.from({ length: count }, (_, index) => `$${index + 1}`).join(', ');
}

export async function callFunction(name, ...args) {
  checkIdent(name);
  return withClient(async (client) => {
    const result = await client.query(`SELECT * FROM ${config.dbSchema}.${name}(${placeholders(args.length)})`, args);
    return result.rows;
  });
}

export async function callFunctionOne(name, ...args) {
  const rows = await callFunction(name, ...args);
  return rows.length ? rows[0] : null;
}

export async function callProcedure(name, ...args) {
  checkIdent(name);
  return withClient(async (client) => {
    const result = await client.query(`CALL ${config.dbSchema}.${name}(${placeholders(args.length)})`, args);
    return result.rows && result.rows.length ? result.rows[0] : null;
  });
}

export async function ping() {
  try {
    const rows = await callFunction('fn_login_user', '__health_check__', '__health_check__');
    return Array.isArray(rows);
  } catch {
    return false;
  }
}
