/**
 * DrugShield AI - Simulation API Client
 * Interfaces directly with Express /api routes to stream JSON payloads and image uploads
 * to Module 1 data/raw/ landing zone.
 */

window.SimulatorAPI = (function () {
  const BASE_URL = "";

  /**
   * Posts message and optional file attachment to /api/ingest
   */
  async function ingestMessage(data) {
    const formData = new FormData();

    formData.append("timestamp", data.timestamp || new Date().toISOString());
    formData.append("sender_id", data.sender_id || "+919876543210");
    formData.append("chat_id", data.chat_id || "simulated_group_001");
    formData.append("message_body", data.message_body || "");
    formData.append("has_media", Boolean(data.file || data.preset_media_path));
    formData.append("extracted_upi_or_bank", data.extracted_upi_or_bank || "");
    formData.append("is_analyst", Boolean(data.is_analyst));

    if (data.file) {
      formData.append("media_file", data.file);
    } else if (data.preset_media_path) {
      formData.append("preset_media_path", data.preset_media_path);
    }

    try {
      const response = await fetch(`${BASE_URL}/api/ingest`, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        throw new Error(`Ingest failed with HTTP status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.error("[SimulatorAPI] Ingestion error:", err);
      throw err;
    }
  }

  /**
   * Triggers batch flush of all raw logs into data/raw/ingested_raw_data.json
   */
  async function flushToEngine() {
    try {
      const response = await fetch(`${BASE_URL}/api/flush`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      return await response.json();
    } catch (err) {
      console.error("[SimulatorAPI] Flush error:", err);
      throw err;
    }
  }

  /**
   * Retrieves ingestion engine stats (file counts, landing path)
   */
  async function getEngineStatus() {
    try {
      const response = await fetch(`${BASE_URL}/api/status`);
      return await response.json();
    } catch (err) {
      console.error("[SimulatorAPI] Status error:", err);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Clears session history
   */
  async function clearHistory() {
    try {
      const response = await fetch(`${BASE_URL}/api/clear`, { method: "POST" });
      return await response.json();
    } catch (err) {
      console.error("[SimulatorAPI] Clear error:", err);
    }
  }

  return {
    ingestMessage,
    flushToEngine,
    getEngineStatus,
    clearHistory
  };
})();
