/* Loaded before application scripts. Account journals use separate browser keys.
 * This prevents accidental cross-account display, not access by a device owner.
 * Server authorization, not browser storage, protects the cloud copy.
 */
'use strict';
(() => {
  const owner = window.LokiStorageOwner;
  const prefix = owner && owner !== 'guest' ? `member:${owner}:` : '';
  const native = { getItem: Storage.prototype.getItem, setItem: Storage.prototype.setItem, removeItem: Storage.prototype.removeItem };
  const scoped = (store, key) => store === window.localStorage && /^loki[_.-]/.test(String(key)) && key !== 'loki_guest';
  for (const method of Object.keys(native)) {
    Storage.prototype[method] = function (key, ...args) {
      if (scoped(this, key)) {
        if (!owner) throw new Error('Account context is unavailable; reload before using saved data.');
        key = prefix + key;
      }
      return native[method].call(this, key, ...args);
    };
  }
  // If another tab signs into a different account, stop using the stale owner
  // before that tab can save a workspace to the wrong signed-in account.
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('loki-account') : null;
  if (channel) channel.onmessage = () => location.reload();
  window.LokiAccountChanged = () => channel?.postMessage('changed');
})();
