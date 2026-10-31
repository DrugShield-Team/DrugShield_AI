/** Send newly composed Telegram simulation events to the local analysis API. */
window.SimulatorAPI = (function () {
  const API_BASE = window.DRUGSHIELD_API_URL || "http://127.0.0.1:8000";
  const LOCAL_BASE = "";

  async function ingestMessage(data) {
    const conversationId = String(data.chat_id || "telegram-conversation");
    const isAnalyst = Boolean(data.is_analyst);
    const participantId = String(data.participant_id || data.sender_id || data.sender_phone || data.sender_username || `participant:${conversationId}`);
    const senderId = isAnalyst ? `analyst:${conversationId}` : participantId;
    const senderName = String(data.sender_display_name || data.sender_username || (isAnalyst ? "You" : "Fictional participant"));
    const event = {
      schema_version: 1,
      channel: "telegram",
      message_id: String(data.message_id || crypto.randomUUID()),
      conversation_id: conversationId,
      sender_id: isAnalyst ? `analyst:${conversationId}` : senderId,
      sender_display_name: isAnalyst ? "You" : senderName,
      recipient_id: isAnalyst ? participantId : `analyst:${conversationId}`,
      recipient_display_name: isAnalyst ? String(data.recipient_name || data.chat_title || "Fictional participant") : "You",
      timestamp: data.timestamp || new Date().toISOString(),
      text: String(data.message_body || data.text || "")
    };
    const form = new FormData();
    form.append("event_json", JSON.stringify(event));
    let file = data.file || null;
    if (!file && data.preset_media_path) {
      const mediaResponse = await fetch(`/${String(data.preset_media_path).replace(/^\/+/, "")}`);
      if (!mediaResponse.ok) throw new Error("Could not load the selected simulation attachment.");
      const blob = await mediaResponse.blob();
      const name = String(data.preset_media_path).split("/").pop() || "attachment.png";
      file = new File([blob], name, { type: blob.type || "image/png" });
    }
    if (file) form.append("files", file, file.name || "attachment");

    const response = await fetch(`${API_BASE}/api/v1/simulation-events`, { method: "POST", body: form });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof result.detail === "string" ? result.detail : result.detail?.error;
      throw new Error(detail || `Analysis API returned HTTP ${response.status}`);
    }
    return result;
  }

  async function getBootstrapData() {
    const response = await fetch(`${LOCAL_BASE}/api/bootstrap`);
    if (!response.ok) throw new Error(`Simulation server returned HTTP ${response.status}`);
    return response.json();
  }

  async function createChat(chatData) {
    const response = await fetch(`${LOCAL_BASE}/api/chats/create`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(chatData)
    });
    if (!response.ok) throw new Error(`Simulation server returned HTTP ${response.status}`);
    return response.json();
  }

  async function getEngineStatus() {
    const response = await fetch(`${LOCAL_BASE}/api/status`);
    return response.ok ? response.json() : { ok: false };
  }

  function showAnalysisResult(result) {
    // Secret backend monitoring: log to debug console only, never display to the suspect
    console.debug("[DrugShield Secret Backend Analysis]", result);
    const existingNotice = document.getElementById("backend-analysis-notice");
    if (existingNotice) {
      existingNotice.style.display = "none";
    }
  }

  return { ingestMessage, getBootstrapData, createChat, getEngineStatus, showAnalysisResult };
})();
