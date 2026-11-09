import { AsyncLocalStorage } from 'node:async_hooks';

/** Per-request context so the database layer can read the signed-in user without passing it around. */
export const storage = new AsyncLocalStorage();

export function currentContext() {
  return storage.getStore() || {};
}
