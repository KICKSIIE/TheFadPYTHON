/** Shared router helper: tags each request with its endpoint, checks approval, catches async errors. */
import { approvalGuard } from '../approval.js';

const wrap = (handler) => (req, res, next) => {
  try {
    const result = handler(req, res, next);
    if (result && typeof result.catch === 'function') result.catch(next);
  } catch (error) {
    next(error);
  }
};

export function makeRouter(app) {
  const add = (method) => (path, endpoint, ...handlers) => {
    app[method](
      path,
      (req, res, next) => { req.endpoint = endpoint; next(); },
      wrap(approvalGuard),
      ...handlers.map(wrap),
    );
  };
  return { get: add('get'), post: add('post') };
}
