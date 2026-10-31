/* Browser-only persistence for the Telegram simulation. */
(() => {
  const STORAGE_KEY = "drugshield-telegram-local-v1";
  const DB_NAME = "drugshield-telegram-media-v1";
  const STORE_NAME = "attachments";

  function openDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function mediaRequest(mode, operation) {
    return openDb().then(db => new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode);
      const result = operation(tx.objectStore(STORE_NAME));
      tx.oncomplete = () => { db.close(); resolve(result && result.result); };
      tx.onerror = () => { db.close(); reject(tx.error); };
      tx.onabort = () => { db.close(); reject(tx.error); };
    }));
  }

  function clean(value) {
    if (Array.isArray(value)) return value.map(clean);
    if (!value || typeof value !== "object") return value;
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      if (typeof item === "string" && item.startsWith("blob:")) continue;
      result[key] = clean(item);
    }
    return result;
  }

  window.TelegramLocalStore = {
    load() {
      try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); }
      catch { return null; }
    },
    save(state) { localStorage.setItem(STORAGE_KEY, JSON.stringify(clean(state))); },
    clear() {
      try { localStorage.removeItem(STORAGE_KEY); } catch(e) {}
      try { indexedDB.deleteDatabase(DB_NAME); } catch(e) {}
    },
    async saveAttachment(blob) {
      const id = crypto.randomUUID ? crypto.randomUUID() : `tg_${Date.now()}_${Math.random().toString(16).slice(2)}`;
      await mediaRequest("readwrite", store => store.put(blob, id));
      return id;
    },
    async getAttachment(id) { return mediaRequest("readonly", store => store.get(id)); }
  };
})();
