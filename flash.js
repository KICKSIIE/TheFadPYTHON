/** Session-backed flash messages, the same shape the templates expect. */

export function flash(req, category, message) {
  if (!req.session.flashes) req.session.flashes = [];
  req.session.flashes.push({ category, message });
}

export function takeFlashes(req) {
  const messages = req.session.flashes || [];
  delete req.session.flashes;
  return messages;
}
