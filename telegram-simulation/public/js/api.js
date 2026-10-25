/**
 * Telegram Simulation API Client
 * Interfaces directly with Express /api routes on Port 8000
 */

window.SimulatorAPI = (function () {
  const BASE_URL = "";

  async function ingestMessage(data) {
    const formData = new FormData();

    formData.append("platform", "telegram_simulation");
    formData.append("timestamp", data.timestamp || new Date().toISOString());
    formData.append("chat_type", data.chat_type || "channel");
    formData.append("chat_title", data.chat_title || "Target Channel");
    formData.append("chat_id", data.chat_id || "tg_target");
    formData.append("sender_username", data.sender_username || "@suspect");
    formData.append("sender_phone", data.sender_phone || "+91 98765 43210");
    formData.append("sender_id", data.sender_phone || "+91 98765 43210");
    formData.append("message_id", data.message_id || Math.floor(10000 + Math.random() * 90000));
    formData.append("message_body", data.message_body || data.text || "");
    formData.append("has_media", Boolean(data.file || data.preset_media_path));
    formData.append("is_analyst", Boolean(data.is_analyst));

    if (data.file) {
      formData.append("media_file", data.file);
    } else if (data.preset_media_path) {
      formData.append("preset_media_path", data.preset_media_path);
    }

    try {
      const response = await fetch(`${BASE_URL}/api/ingest/telegram`, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        throw new Error(`Ingest failed with status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.error("[SimulatorAPI] Telegram Ingest error:", err);
      throw err;
    }
  }

  async function getBootstrapData() {
    try {
      const response = await fetch(`${BASE_URL}/api/bootstrap`);
      return await response.json();
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  async function createChat(chatData) {
    try {
      const response = await fetch(`${BASE_URL}/api/chats/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chatData)
      });
      return await response.json();
    } catch (err) {
      throw err;
    }
  }

  async function getEngineStatus() {
    try {
      const response = await fetch(`${BASE_URL}/api/status`);
      return await response.json();
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  async function clearHistory() {
    try {
      const response = await fetch(`${BASE_URL}/api/clear`, { method: "POST" });
      return await response.json();
    } catch (err) {}
  }

  return {
    ingestMessage,
    getBootstrapData,
    createChat,
    getEngineStatus,
    clearHistory
  };
})();
