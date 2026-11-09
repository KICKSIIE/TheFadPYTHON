import crypto from 'node:crypto';

/** One token per session; every state-changing request must echo it. */
export function csrfToken(req) {
  if (!req.session.csrf) req.session.csrf = crypto.randomBytes(24).toString('base64url');
  return req.session.csrf;
}

export function verifyCsrf(req) {
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method)) return true;
  const sent = (req.body && req.body._csrf) || req.get('X-CSRF-Token') || '';
  const expected = req.session.csrf || '';
  if (!sent || !expected || sent.length !== expected.length) return false;
  return crypto.timingSafeEqual(Buffer.from(sent), Buffer.from(expected));
}
