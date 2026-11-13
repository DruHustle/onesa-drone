const operations = new WeakMap();

export function inOrder(store, operation) {
  const pending = operations.get(store) || Promise.resolve();
  const next = pending.then(operation);
  operations.set(store, next.catch(() => {}));
  return next;
}
