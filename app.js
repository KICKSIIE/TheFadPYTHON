import path from 'node:path';
import { fileURLToPath } from 'node:url';

import express from 'express';
import session from 'express-session';
import multer from 'multer';
import nunjucks from 'nunjucks';

import { config } from './config.js';
import { storage } from './context.js';
import { verifyCsrf, csrfToken } from './csrf.js';
import * as db from './db.js';
import { colorHex } from './utils.js';
import { strftime } from './time.js';
import { renderPage } from './render.js';
import { urlFor } from './urls.js';
import { makeRouter } from './modules/_router.js';
import { registerAll } from './modules/index.js';

const root = path.dirname(fileURLToPath(import.meta.url));
const { SafeString } = nunjucks.runtime;

/** Python-style % formatting used by the templates ("%.2f"|format(value)). */
function sprintf(format, ...args) {
  let index = 0;
  return String(format).replace(/%([-+ 0]*)(\d+)?(?:\.(\d+))?([sdif])/g, (match, flags, width, precision, type) => {
    if (index >= args.length) return match;
    const value = args[index++];
    if (type === 's') return width ? String(value).padStart(Number(width)) : String(value);
    if (type === 'd' || type === 'i') {
      const whole = String(Math.trunc(Number(value) || 0));
      return width ? whole.padStart(Number(width)) : whole;
    }
    const number = Number(value) || 0;
    const digits = precision === undefined ? 6 : Number(precision);
    let text = number.toFixed(digits);
    if (width) text = text.padStart(Number(width), flags.includes('0') ? '0' : ' ');
    return text;
  });
}

function configureViews(app) {
  const env = nunjucks.configure(path.join(root, 'templates'), {
    express: app,
    autoescape: true,
    noCache: process.env.NODE_ENV !== 'production',
    watch: false,
  });
  app.set('view engine', 'html');
  // Macros do not see render-local values in Nunjucks, so the URL helper is a global.
  env.addGlobal('url_for', urlFor);

  env.addFilter('peso', (value) => (value === null || value === undefined || value === ''
    ? ''
    : `\u20b1${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`));
  env.addFilter('dt', (value) => (value === null || value === undefined
    ? ''
    : strftime(value, '%b %d, %Y \u00b7 %I:%M %p')));
  env.addFilter('label', (value) => String(value || '').replaceAll('_', ' '));
  env.addFilter('time12', (value) => {
    const match = /^(\d{1,2}):(\d{2})/.exec(String(value || ''));
    if (!match) return '';
    const hours = Number(match[1]);
    const hour12 = ((hours + 11) % 12) + 1;
    return `${String(hour12).padStart(2, '0')}:${match[2]} ${hours < 12 ? 'AM' : 'PM'}`;
  });
  env.addFilter('color_hex', colorHex);
  env.addFilter('format', sprintf);
  env.addFilter('min', (values) => Math.min(...values));
  env.addFilter('max', (values) => Math.max(...values));
  env.addFilter('map', (values, attribute) => (values || []).map((value) => value[attribute]));
  env.addFilter('limit', (values, count) => (values || []).slice(0, count));
  // Nunjucks' own `string` filter calls toString(), which throws for null/undefined.
  env.addFilter('string', (value) => (value === null || value === undefined ? '' : String(value)));
  env.addFilter('tojson', (value) => {
    const text = JSON.stringify(value ?? null)
      .replaceAll('<', '\\u003c').replaceAll('>', '\\u003e').replaceAll('&', '\\u0026');
    return new SafeString(text);
  });
}

export function createApp() {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', 1);

  configureViews(app);

  app.use('/static', express.static(path.join(root, 'static'), { maxAge: '7d' }));
  app.use(express.urlencoded({ extended: false, limit: config.maxContentLength }));
  app.use(express.json({ limit: config.maxContentLength }));
  app.use(multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: 3 * 1024 * 1024, files: 8 },
  }).any());

  app.use(session({
    secret: config.secretKey,
    resave: false,
    saveUninitialized: true,
    cookie: { httpOnly: true, sameSite: 'lax', maxAge: config.sessionMaxAge },
  }));

  // Per-request context so the database layer can read the session without it being passed around.
  app.use((req, res, next) => storage.run({ req, res, session: req.session }, next));

  // Every POST must carry the session's CSRF token.
  app.use((req, res, next) => {
    if (verifyCsrf(req)) return next();
    return renderPage(req, res, 'error.html', {
      code: 400, heading: 'Request could not be verified', message: 'Reload the page and try again.',
    }, 400);
  });

  app.get('/health', async (req, res) => {
    const ok = await db.ping();
    res.status(ok ? 200 : 503).json({ database: ok ? 'ok' : 'unreachable' });
  });

  const router = makeRouter(app);
  registerAll(router);

  app.use((req, res) => renderPage(req, res, 'error.html', {
    code: 404, heading: 'Page not found', message: 'Check the address or use the menu.',
  }, 404));

  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    if (error instanceof multer.MulterError || error.type === 'entity.too.large') {
      return renderPage(req, res, 'error.html', {
        code: 413, heading: 'That file is too large',
        message: 'Each photo must be 3 MB or smaller, and a product can have up to 8. Resize the photos and try again.',
      }, 413);
    }
    console.error(error);
    return renderPage(req, res, 'error.html', {
      code: 500, heading: 'Something went wrong', message: 'Try again, or contact an admin if it keeps happening.',
    }, 500);
  });

  return app;
}

export { csrfToken };
