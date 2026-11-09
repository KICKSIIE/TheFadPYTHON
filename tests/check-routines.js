/** Static cross-check (no database needed): every routine the code calls must be defined in sql/*.sql
 *  (or be one of the routines that already existed in the database) with a matching number of arguments.
 *  Run: node tests/check-routines.js
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Routines that already exist in the THEFAD database: name -> [min, max]
const EXISTING = { sp_create_discount: [7, 7], sp_update_discount: [7, 7], fn_refund_report: [2, 2] };

function splitTop(text) {
  const parts = [];
  let depth = 0;
  let quote = null;
  let current = '';
  for (const char of text) {
    if (quote) {
      current += char;
      if (char === quote) quote = null;
      continue;
    }
    if (char === "'" || char === '"') { quote = char; current += char; }
    else if ('(['.includes(char)) { depth += 1; current += char; }
    else if (')]'.includes(char)) { depth -= 1; current += char; }
    else if (char === ',' && depth === 0) { parts.push(current.trim()); current = ''; }
    else current += char;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

function sqlRoutines() {
  const found = new Map();
  const files = fs.readdirSync(path.join(ROOT, 'sql')).filter((name) => /^0.*\.sql$/.test(name));
  const text = files.map((name) => fs.readFileSync(path.join(ROOT, 'sql', name), 'utf8')).join('\n');
  const pattern = /CREATE OR REPLACE (FUNCTION|PROCEDURE)\s+thefad\.(\w+)\s*\(([\s\S]*?)\)\s*(?:RETURNS|LANGUAGE|AS)/gi;
  let match;
  while ((match = pattern.exec(text))) {
    const kind = match[1].toUpperCase();
    const name = match[2];
    const params = splitTop(match[3]).filter(Boolean);
    const required = params.filter((param) => !/\bDEFAULT\b/i.test(param)).length;
    found.set(name, { kind, required, total: params.length });
  }
  return found;
}

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (['node_modules', 'legacy-python', 'tests', 'prototype', '.git', 'venv', '.tmp_shots'].includes(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (entry.name.endsWith('.js')) out.push(full);
  }
  return out;
}

function calls() {
  const out = [];
  for (const file of walk(ROOT)) {
    const source = fs.readFileSync(file, 'utf8');
    const regex = /db\.(callFunctionOne|callFunction|callProcedure|callProcedureOne)\(/g;
    let match;
    while ((match = regex.exec(source))) {
      let pos = match.index + match[0].length;
      let depth = 1;
      let quote = null;
      const start = pos;
      while (pos < source.length && depth > 0) {
        const char = source[pos];
        if (quote) { if (char === quote && source[pos - 1] !== '\\') quote = null; }
        else if (char === "'" || char === '"' || char === '`') quote = char;
        else if (char === '(') depth += 1;
        else if (char === ')') depth -= 1;
        pos += 1;
      }
      const args = splitTop(source.slice(start, pos - 1));
      if (!args.length || !/^['"]/.test(args[0])) continue;
      const name = args[0].slice(1, -1);
      out.push({ file: path.relative(ROOT, file), line: source.slice(0, match.index).split('\n').length, how: match[1], name, argc: args.length - 1 });
    }
  }
  return out;
}

const defined = sqlRoutines();
const problems = [];
const seen = new Set();
for (const call of calls()) {
  seen.add(call.name);
  if (call.name in EXISTING) {
    const [lo, hi] = EXISTING[call.name];
    if (call.argc < lo || call.argc > hi) problems.push(`${call.file}:${call.line} ${call.name} called with ${call.argc} args, expects ${lo}..${hi}`);
    continue;
  }
  const sql = defined.get(call.name);
  if (!sql) { problems.push(`${call.file}:${call.line} ${call.name} is not defined in sql/`); continue; }
  const asProcedure = ['callProcedure', 'callProcedureOne'].includes(call.how);
  if (asProcedure !== (sql.kind === 'PROCEDURE')) problems.push(`${call.file}:${call.line} ${call.name} is a ${sql.kind} but called with ${call.how}`);
  if (call.argc < sql.required || call.argc > sql.total) {
    problems.push(`${call.file}:${call.line} ${call.name} called with ${call.argc} args, SQL takes ${sql.required}..${sql.total}`);
  }
}

console.log(`${seen.size} routines called from JavaScript, ${defined.size} defined in sql/.`);
const unused = [...defined.keys()].filter((name) => !seen.has(name)).sort();
if (unused.length) console.log('defined but not called (helper routines):', unused.join(', '));
for (const problem of problems) console.log('PROBLEM:', problem);
process.exit(problems.length ? 1 : 0);
