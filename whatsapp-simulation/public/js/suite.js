/**
 * DrugShield AI - Simulation Suite Master Interactive Controller
 * ==============================================================
 * Unifies Telegram Web K/Z Simulation & WhatsApp Web Simulation:
 * - Real-time switching between Telegram and WhatsApp
 * - Live OSINT pipeline persistence to data/raw/ & data/raw/images/
 * - Automatic preloading of historical raw logs from disk
 * - Dynamic creation of target channels, groups, and direct chats
 * - Dual-perspective switcher (Target/Suspect vs Analyst)
 * - Quick inject OSINT narcotics threat scenarios
 */

document.addEventListener("DOMContentLoaded", async () => {
  // ----------------------------------------------------------------------------
  // State
  // ----------------------------------------------------------------------------
  let activePlatform = "telegram"; // "telegram" | "whatsapp"
  let isAnalystPerspective = false; // false = Target/Suspect, true = Analyst

  let telegramChats = [
    {
      id: "tg_blr_supplies",
      type: "channel",
      title: "BLR Party Supplies",
      username: "@blr_supplies_bot",
      phone: "+91 98765 43210",
      avatarText: "BP",
      avatarColor: "#2AABEE",
      verified: true,
      subscribers: "2,840 subscribers",
      status: "broadcast channel",
      lastTime: "11:45 AM",
      unreadCount: 3,
      messages: [
        {
          id: "m_tg_init_1",
          sender_username: "@blr_supplies_bot",
          sender_phone: "+91 98765 43210",
          is_analyst: false,
          text: "🚀 WEEKEND SPECIAL: Fresh MDMA 1g 3k / Pure Hydro Cannabis buds in stock! Fast dead drop delivery across Indiranagar, Koramangala & Whitefield. DM @blr_supplies_bot for menu.",
          timestamp: "10:30 AM",
          has_media: false,
          views: "1.4K",
          extracted_entities: {
            narcotics_detected: ["mdma", "cannabis", "hydro"],
            solicitation_terms: ["score", "dead drop", "fresh stock"]
          }
        },
        {
          id: "m_tg_init_2",
          sender_username: "@blr_supplies_bot",
          sender_phone: "+91 98765 43210",
          is_analyst: false,
          text: "Pay token advance to confirm slot via UPI: dealer_blr@okhdfcbank or dark_supply@paytm. GPS drop coordinates sent 10 mins post payment.",
          timestamp: "11:20 AM",
          has_media: false,
          views: "1.8K",
          extracted_entities: {
            upi_ids: ["dealer_blr@okhdfcbank", "dark_supply@paytm"]
          }
        }
      ]
    },
    {
      id: "tg_darknet_blr",
      type: "group",
      title: "NCR Secret Drops & Stash",
      username: "@ncr_drops_chat",
      phone: "+91 91234 56789",
      avatarText: "NCR",
      avatarColor: "#8e44ad",
      verified: false,
      subscribers: "148 members, 22 online",
      status: "148 members",
      lastTime: "Yesterday",
      unreadCount: 1,
      messages: [
        {
          id: "m_tg_grp_1",
          sender_username: "@plug_delhi",
          sender_phone: "+91 91234 56789",
          is_analyst: false,
          text: "M-Cat / Meow Meow scores cleared for Gurgaon cyber hub. Dead drop pin: 28.4595, 77.0266. Cash on drop or UPI accepted.",
          timestamp: "Yesterday",
          has_media: false,
          views: "92",
          extracted_entities: {
            narcotics_detected: ["m-cat", "meow meow"],
            gps_coordinates: ["28.4595, 77.0266"]
          }
        }
      ]
    },
    {
      id: "tg_aryan_direct",
      type: "private",
      title: "Aryan (Suspect Plug)",
      username: "@aryan_plug",
      phone: "+91 98765 43210",
      avatarText: "AK",
      avatarColor: "#e67e22",
      verified: false,
      subscribers: "online",
      status: "last seen recently",
      lastTime: "12:05 PM",
      unreadCount: 0,
      messages: [
        {
          id: "m_tg_priv_1",
          sender_username: "@aryan_plug",
          sender_phone: "+91 98765 43210",
          is_analyst: false,
          text: "Bhai sample verified. Pure Malana Cream charas available. Transfer advance to A/C: 981234567890 IFSC: HDFC0001234.",
          timestamp: "12:05 PM",
          has_media: false,
          extracted_entities: {
            narcotics_detected: ["malana cream", "charas"],
            bank_accounts: ["981234567890"],
            ifsc_codes: ["HDFC0001234"]
          }
        }
      ]
    }
  ];

  let currentTgChat = telegramChats[0];
  let attachedTgFile = null;

  // ----------------------------------------------------------------------------
  // DOM References
  // ----------------------------------------------------------------------------
  // Topbar
  const btnSwitchTelegram = document.getElementById("btnSwitchTelegram");
  const btnSwitchWhatsApp = document.getElementById("btnSwitchWhatsApp");
  const viewTelegram = document.getElementById("viewTelegram");
  const viewWhatsApp = document.getElementById("viewWhatsApp");
  const suiteRoleSwitcher = document.getElementById("suiteRoleSwitcher");
  const btnOpenScenarios = document.getElementById("btnOpenScenarios");
  const btnOpenCreateChat = document.getElementById("btnOpenCreateChat");
  const headerLogsCount = document.getElementById("headerLogsCount");

  // Telegram Elements
  const tgChatList = document.getElementById("tgChatList");
  const tgMessagesScroll = document.getElementById("tgMessagesScroll");
  const tgChatHeaderName = document.getElementById("tgChatHeaderName");
  const tgChatHeaderStatus = document.getElementById("tgChatHeaderStatus");
  const tgChatHeaderAvatar = document.getElementById("tgChatHeaderAvatar");
  const tgMessageInput = document.getElementById("tgMessageInput");
  const tgBtnSend = document.getElementById("tgBtnSend");
  const tgBtnAttach = document.getElementById("tgBtnAttach");
  const tgFileInput = document.getElementById("tgFileInput");
  const tgAttachPreview = document.getElementById("tgAttachPreview");
  const tgPreviewThumb = document.getElementById("tgPreviewThumb");
  const tgPreviewTitle = document.getElementById("tgPreviewTitle");
  const tgBtnRemoveAttach = document.getElementById("tgBtnRemoveAttach");
  const tgSearchInput = document.getElementById("tgSearchInput");
  const tgFolderTabs = document.querySelectorAll(".tg-tab-btn");

  // Modals
  const modalCreateChat = document.getElementById("modalCreateChat");
  const btnCloseCreateChat = document.getElementById("btnCloseCreateChat");
  const btnCancelCreateChat = document.getElementById("btnCancelCreateChat");
  const btnSubmitCreateChat = document.getElementById("btnSubmitCreateChat");
  const createChatPlatform = document.getElementById("createChatPlatform");
  const createChatType = document.getElementById("createChatType");
  const createChatTitle = document.getElementById("createChatTitle");
  const createChatUsername = document.getElementById("createChatUsername");
  const createChatPhone = document.getElementById("createChatPhone");
  const createChatAvatarColor = document.getElementById("createChatAvatarColor");

  const modalScenarios = document.getElementById("modalScenarios");
  const btnCloseScenarios = document.getElementById("btnCloseScenarios");
  const scenariosContainer = document.getElementById("scenariosContainer");

  // ----------------------------------------------------------------------------
  // Audio Synthesizer (Realistic Click Feedback)
  // ----------------------------------------------------------------------------
  function playClickSound() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(800, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.03);
      gain.gain.setValueAtTime(0.05, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.03);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.035);
    } catch (e) {}
  }

  // ----------------------------------------------------------------------------
  // Helper: Format Time
  // ----------------------------------------------------------------------------
  function getFormattedTime() {
    const now = new Date();
    let hours = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, "0");
    const ampm = hours >= 12 ? "PM" : "AM";
    hours = hours % 12 || 12;
    return `${hours}:${minutes} ${ampm}`;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // ----------------------------------------------------------------------------
  // 1. Bootstrap: Load pre-existing data from server (./data/raw/)
  // ----------------------------------------------------------------------------
  async function bootstrapSuite() {
    try {
      const data = await SimulatorAPI.getBootstrapData();
      if (data && data.ok) {
        if (data.stats && data.stats.total_raw_logs_count !== undefined) {
          headerLogsCount.textContent = `${data.stats.total_raw_logs_count} logs`;
        }

        // Reconstruct loaded Telegram messages
        if (data.preloaded && Array.isArray(data.preloaded.telegram)) {
          data.preloaded.telegram.forEach(rec => {
            let targetChat = telegramChats.find(c => c.title === rec.chat_title || c.id === rec.chat_id);
            if (!targetChat) {
              targetChat = {
                id: rec.chat_id || `tg_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
                type: rec.chat_type || "channel",
                title: rec.chat_title || "Preloaded Channel",
                username: rec.sender_username || "@suspect",
                phone: rec.sender_phone || "+91 98765 43210",
                avatarText: (rec.chat_title || "TG").slice(0, 2).toUpperCase(),
                avatarColor: "#2AABEE",
                verified: rec.chat_type === "channel",
                subscribers: rec.chat_type === "channel" ? "1,200 subscribers" : "online",
                status: rec.chat_type || "channel",
                lastTime: "Loaded",
                unreadCount: 0,
                messages: []
              };
              telegramChats.push(targetChat);
            }

            // Avoid duplicates
            if (!targetChat.messages.some(m => m.id === rec.id || (m.text === rec.message_body && m.timestamp === rec.timestamp))) {
              targetChat.messages.push({
                id: rec.id,
                sender_username: rec.sender_username,
                sender_phone: rec.sender_phone,
                is_analyst: rec.is_analyst,
                text: rec.message_body,
                timestamp: rec.timestamp ? new Date(rec.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : getFormattedTime(),
                has_media: rec.has_media,
                local_media_url: rec.local_media_url,
                extracted_entities: rec.extracted_entities
              });
            }
          });
        }

        // Add dynamic chats if any were saved
        if (data.dynamicChats && Array.isArray(data.dynamicChats)) {
          data.dynamicChats.forEach(dc => {
            if (dc.platform === "telegram" && !telegramChats.some(c => c.id === dc.id)) {
              telegramChats.push({
                id: dc.id,
                type: dc.type || "channel",
                title: dc.title,
                username: dc.username,
                phone: dc.phone,
                avatarText: dc.title.slice(0, 2).toUpperCase(),
                avatarColor: dc.avatarColor || "#2AABEE",
                verified: dc.type === "channel",
                subscribers: dc.type === "channel" ? "New Channel" : "online",
                status: dc.type,
                lastTime: "Just now",
                unreadCount: 0,
                messages: []
              });
            }
          });
        }

        renderTelegramChatList();
        renderTelegramMessages();
      }
    } catch (e) {
      console.warn("[Suite] Bootstrap fetch warning:", e.message);
    }
  }

  // ----------------------------------------------------------------------------
  // 2. Platform Switcher (Telegram <-> WhatsApp)
  // ----------------------------------------------------------------------------
  function setPlatform(platform) {
    activePlatform = platform;
    playClickSound();

    if (platform === "telegram") {
      btnSwitchTelegram.classList.add("active");
      btnSwitchWhatsApp.classList.remove("active");
      viewTelegram.classList.add("active");
      viewWhatsApp.classList.remove("active");
      renderTelegramMessages();
    } else {
      btnSwitchWhatsApp.classList.add("active");
      btnSwitchTelegram.classList.remove("active");
      viewWhatsApp.classList.add("active");
      viewTelegram.classList.remove("active");
    }
  }

  btnSwitchTelegram.addEventListener("click", () => setPlatform("telegram"));
  btnSwitchWhatsApp.addEventListener("click", () => setPlatform("whatsapp"));

  // ----------------------------------------------------------------------------
  // 3. Role Switcher (Simulate as Target/Suspect vs Analyst)
  // ----------------------------------------------------------------------------
  function toggleRole() {
    isAnalystPerspective = !isAnalystPerspective;
    playClickSound();

    const roleVal = suiteRoleSwitcher.querySelector(".role-val");
    if (isAnalystPerspective) {
      suiteRoleSwitcher.className = "role-perspective-badge analyst";
      roleVal.textContent = "Analyst / Self";
    } else {
      suiteRoleSwitcher.className = "role-perspective-badge suspect";
      roleVal.textContent = "Target / Suspect";
    }
  }

  suiteRoleSwitcher.addEventListener("click", toggleRole);

  // ----------------------------------------------------------------------------
  // 4. Telegram UI: Chat List Rendering
  // ----------------------------------------------------------------------------
  function renderTelegramChatList(filterType = "all", searchQuery = "") {
    tgChatList.innerHTML = "";

    const query = searchQuery.trim().toLowerCase();
    const filtered = telegramChats.filter(chat => {
      if (filterType === "channels" && chat.type !== "channel") return false;
      if (filterType === "groups" && chat.type !== "group") return false;
      if (filterType === "direct" && chat.type !== "private") return false;

      if (query) {
        return chat.title.toLowerCase().includes(query) || chat.username.toLowerCase().includes(query);
      }
      return true;
    });

    filtered.forEach(chat => {
      const item = document.createElement("div");
      item.className = `tg-chat-item ${currentTgChat && currentTgChat.id === chat.id ? "active" : ""}`;

      const lastMsg = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1] : null;
      const previewText = lastMsg ? (lastMsg.text || "[Media attachment]") : "No messages yet";

      item.innerHTML = `
        <div class="tg-avatar-wrap" style="background: ${chat.avatarColor || '#2AABEE'};">
          ${chat.avatarText || chat.title.slice(0, 2).toUpperCase()}
        </div>
        <div class="tg-chat-content">
          <div class="tg-chat-top">
            <div class="tg-chat-title-row">
              <span class="tg-chat-title">${escapeHtml(chat.title)}</span>
              ${chat.verified ? '<span class="tg-badge-verified" title="Verified Channel">★</span>' : ''}
              <span class="tg-badge-type">${chat.type}</span>
            </div>
            <span class="tg-chat-time">${chat.lastTime || ""}</span>
          </div>
          <div class="tg-chat-bottom">
            <span class="tg-chat-preview">${escapeHtml(previewText)}</span>
            ${chat.unreadCount > 0 ? `<span class="tg-chat-unread-badge">${chat.unreadCount}</span>` : ""}
          </div>
        </div>
      `;

      item.addEventListener("click", () => {
        currentTgChat = chat;
        chat.unreadCount = 0;
        playClickSound();
        renderTelegramChatList(filterType, searchQuery);
        renderTelegramMessages();
      });

      tgChatList.appendChild(item);
    });
  }

  // Telegram Folder Tabs
  tgFolderTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tgFolderTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      renderTelegramChatList(tab.dataset.tab, tgSearchInput.value);
    });
  });

  tgSearchInput.addEventListener("input", (e) => {
    const activeTab = document.querySelector(".tg-tab-btn.active");
    renderTelegramChatList(activeTab ? activeTab.dataset.tab : "all", e.target.value);
  });

  // ----------------------------------------------------------------------------
  // 5. Telegram UI: Message Thread Rendering
  // ----------------------------------------------------------------------------
  function renderTelegramMessages() {
    if (!currentTgChat) return;

    tgChatHeaderName.textContent = currentTgChat.title;
    tgChatHeaderStatus.textContent = currentTgChat.subscribers || currentTgChat.status || "channel";
    tgChatHeaderAvatar.textContent = currentTgChat.avatarText || currentTgChat.title.slice(0, 2).toUpperCase();
    tgChatHeaderAvatar.style.background = currentTgChat.avatarColor || "#2AABEE";

    tgMessagesScroll.innerHTML = `
      <div class="tg-day-divider">Today</div>
    `;

    currentTgChat.messages.forEach(msg => {
      const isOutgoing = msg.is_analyst; // If analyst sent it, treat as outgoing from analyst workstation
      const row = document.createElement("div");
      row.className = `tg-msg-row ${isOutgoing ? "outgoing" : "incoming"}`;

      let mediaHtml = "";
      if (msg.local_media_url) {
        mediaHtml = `
          <div class="tg-bubble-media">
            <img src="${msg.local_media_url}" alt="Evidence Media" onclick="window.open('${msg.local_media_url}', '_blank')">
          </div>
        `;
      }

      // Threat entity badges
      let entityBadgesHtml = "";
      if (msg.extracted_entities) {
        const tags = [];
        if (msg.extracted_entities.narcotics_detected) {
          msg.extracted_entities.narcotics_detected.forEach(d => tags.push(`<span class="tg-entity-tag narcotics">🚨 ${escapeHtml(d)}</span>`));
        }
        if (msg.extracted_entities.upi_ids) {
          msg.extracted_entities.upi_ids.forEach(u => tags.push(`<span class="tg-entity-tag upi">💳 ${escapeHtml(u)}</span>`));
        }
        if (msg.extracted_entities.bank_accounts) {
          msg.extracted_entities.bank_accounts.forEach(b => tags.push(`<span class="tg-entity-tag bank">🏦 Acc: ${escapeHtml(b)}</span>`));
        }
        if (msg.extracted_entities.gps_coordinates) {
          msg.extracted_entities.gps_coordinates.forEach(g => tags.push(`<span class="tg-entity-tag gps">📍 ${escapeHtml(g)}</span>`));
        }
        if (tags.length > 0) {
          entityBadgesHtml = `<div class="tg-threat-entities">${tags.join("")}</div>`;
        }
      }

      const senderDisplay = !isOutgoing && currentTgChat.type !== "private"
        ? `<span class="tg-bubble-sender">${escapeHtml(msg.sender_username || currentTgChat.username)}</span>`
        : "";

      const viewsDisplay = currentTgChat.type === "channel"
        ? `<span class="tg-channel-views">👁️ ${msg.views || "1.2K"}</span>`
        : "";

      row.innerHTML = `
        <div class="tg-bubble">
          ${senderDisplay}
          ${mediaHtml}
          <div class="tg-bubble-text">${escapeHtml(msg.text)}</div>
          ${entityBadgesHtml}
          <div class="tg-bubble-meta">
            ${viewsDisplay}
            <span class="tg-msg-time">${msg.timestamp || getFormattedTime()}</span>
            <span class="checks">✓✓</span>
          </div>
        </div>
      `;

      tgMessagesScroll.appendChild(row);
    });

    tgMessagesScroll.scrollTop = tgMessagesScroll.scrollHeight;
  }

  // ----------------------------------------------------------------------------
  // 6. Telegram UI: Message Sending & Ingestion Trigger
  // ----------------------------------------------------------------------------
  async function sendTelegramMessage() {
    const text = tgMessageInput.value.trim();
    if (!text && !attachedTgFile) return;

    playClickSound();

    const timestamp = new Date().toISOString();
    const formattedTime = getFormattedTime();

    const payload = {
      platform: "telegram",
      chat_type: currentTgChat.type,
      chat_title: currentTgChat.title,
      chat_id: currentTgChat.id,
      sender_username: isAnalystPerspective ? "@cyber_analyst_01" : currentTgChat.username,
      sender_phone: currentTgChat.phone,
      sender_id: currentTgChat.phone,
      message_body: text,
      is_analyst: isAnalystPerspective,
      file: attachedTgFile
    };

    // Optimistically add to UI
    const tempMsg = {
      id: `tg_msg_${Date.now()}`,
      sender_username: payload.sender_username,
      sender_phone: payload.sender_phone,
      is_analyst: isAnalystPerspective,
      text: text,
      timestamp: formattedTime,
      has_media: Boolean(attachedTgFile),
      local_media_url: attachedTgFile ? URL.createObjectURL(attachedTgFile) : null,
      views: "1"
    };

    currentTgChat.messages.push(tempMsg);
    currentTgChat.lastTime = formattedTime;
    renderTelegramMessages();

    // Clear inputs
    tgMessageInput.value = "";
    removeTelegramAttachment();

    try {
      const response = await SimulatorAPI.ingestMessage(payload, "telegram");
      if (response && response.record) {
        // Enrich message with parsed extracted entities
        tempMsg.extracted_entities = response.record.extracted_entities;
        if (response.record.local_media_url) {
          tempMsg.local_media_url = response.record.local_media_url;
        }
        renderTelegramMessages();
        updateTelemetry();
      }
    } catch (err) {
      console.error("[Suite] Ingestion failed:", err);
    }
  }

  tgBtnSend.addEventListener("click", sendTelegramMessage);
  tgMessageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendTelegramMessage();
    }
  });

  // Telegram Media Attachment
  tgBtnAttach.addEventListener("click", () => {
    tgFileInput.click();
  });

  tgFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      attachedTgFile = e.target.files[0];
      tgPreviewThumb.src = URL.createObjectURL(attachedTgFile);
      tgPreviewTitle.textContent = attachedTgFile.name;
      tgAttachPreview.classList.add("active");
    }
  });

  function removeTelegramAttachment() {
    attachedTgFile = null;
    tgFileInput.value = "";
    tgAttachPreview.classList.remove("active");
  }

  tgBtnRemoveAttach.addEventListener("click", removeTelegramAttachment);

  // ----------------------------------------------------------------------------
  // 7. Dynamic Target Chat Creation Modal
  // ----------------------------------------------------------------------------
  btnOpenCreateChat.addEventListener("click", () => {
    modalCreateChat.classList.add("active");
  });

  function closeCreateChatModal() {
    modalCreateChat.classList.remove("active");
  }

  btnCloseCreateChat.addEventListener("click", closeCreateChatModal);
  btnCancelCreateChat.addEventListener("click", closeCreateChatModal);

  btnSubmitCreateChat.addEventListener("click", async () => {
    const platform = createChatPlatform.value;
    const type = createChatType.value;
    const title = createChatTitle.value.trim() || "Target Suspect Thread";
    const username = createChatUsername.value.trim() || "@target_plug";
    const phone = createChatPhone.value.trim() || "+91 99999 88888";
    const avatarColor = createChatAvatarColor.value || "#2AABEE";

    playClickSound();

    const chatData = {
      platform,
      type,
      title,
      username,
      phone,
      avatarColor
    };

    try {
      const res = await SimulatorAPI.createChat(chatData);
      const newChat = {
        id: (res && res.chat && res.chat.id) || `chat_${Date.now()}`,
        type,
        title,
        username,
        phone,
        avatarText: title.slice(0, 2).toUpperCase(),
        avatarColor,
        verified: type === "channel",
        subscribers: type === "channel" ? "New Channel" : "online",
        status: type,
        lastTime: "Just now",
        unreadCount: 0,
        messages: []
      };

      if (platform === "telegram") {
        telegramChats.unshift(newChat);
        currentTgChat = newChat;
        setPlatform("telegram");
        renderTelegramChatList();
        renderTelegramMessages();
      } else {
        // If WhatsApp, inject into ContactsData if present
        if (window.ContactsData && window.ContactsData.CONTACTS) {
          window.ContactsData.CONTACTS.unshift({
            id: newChat.id,
            name: title,
            isGroup: type === "group",
            sender_id: phone,
            sender_name: title,
            phone: phone,
            avatar: "assets/avatars/suspect1.svg",
            status: "Hey there! I am using WhatsApp.",
            unread: 0,
            defaultMessages: []
          });
        }
        setPlatform("whatsapp");
      }

      closeCreateChatModal();
      createChatTitle.value = "";
    } catch (e) {
      alert("Failed to create target chat: " + e.message);
    }
  });

  // ----------------------------------------------------------------------------
  // 8. OSINT Narcotics Scenario Presets Injector
  // ----------------------------------------------------------------------------
  const SCENARIOS = [
    {
      title: "💊 MDMA & LSD Blotter Batch",
      platform: "telegram",
      text: "⚡ FRESH DROP: Crystal MDMA 1g @ 3.2k | 250ug LSD Blotters (Hoffman Bicycle stamps). Stealth delivery in BLR. UPI to lock order: dealer_blr@okhdfcbank",
      mediaPreset: "sample_menu.jpg",
      tags: ["MDMA", "LSD", "UPI"]
    },
    {
      title: "📍 Mephedrone Dead Drop with GPS",
      platform: "telegram",
      text: "Meow Meow (Mephedrone) score verified. Stash dropped at GPS: 28.4595, 77.0266 under brick behind electrical pole. Collect within 45 mins. Paytm token: dark_supply@paytm",
      mediaPreset: null,
      tags: ["Mephedrone", "GPS Pin", "Paytm"]
    },
    {
      title: "🧾 Payment QR Code Mule Transfer",
      platform: "whatsapp",
      text: "Scan this official dealer UPI QR code to transfer advance payment. Mention 'dinner' in remarks. Send screenshot here.",
      mediaPreset: "upi_qr_dealer.png",
      tags: ["QR Code", "UPI Ingestion", "Mule Account"]
    },
    {
      title: "📦 Hydroponic Weed & Malana Cream",
      platform: "telegram",
      text: "Premium A++ OG Kush Hydro & Malana Cream charas score ready. Vacuum sealed packages. Transfer ₹4,500 on A/C: 981234567890 IFSC: HDFC0001234",
      mediaPreset: "sample_image.jpg",
      tags: ["Cannabis", "Bank Account", "IFSC"]
    }
  ];

  function renderScenarios() {
    scenariosContainer.innerHTML = "";
    SCENARIOS.forEach(sc => {
      const card = document.createElement("div");
      card.className = "scenario-card";
      card.innerHTML = `
        <div class="scenario-title">${sc.title}</div>
        <div class="scenario-desc">${escapeHtml(sc.text)}</div>
        <div class="scenario-tags">
          <span class="scenario-tag" style="background:#2AABEE; color:#fff;">${sc.platform.toUpperCase()}</span>
          ${sc.tags.map(t => `<span class="scenario-tag">${t}</span>`).join("")}
        </div>
      `;

      card.addEventListener("click", async () => {
        playClickSound();
        modalScenarios.classList.remove("active");

        setPlatform(sc.platform);

        if (sc.platform === "telegram") {
          tgMessageInput.value = sc.text;
          if (sc.mediaPreset) {
            // Trigger with preset media
            const payload = {
              platform: "telegram",
              chat_type: currentTgChat.type,
              chat_title: currentTgChat.title,
              chat_id: currentTgChat.id,
              sender_username: currentTgChat.username,
              sender_phone: currentTgChat.phone,
              message_body: sc.text,
              preset_media_path: sc.mediaPreset,
              is_analyst: false
            };

            const tempMsg = {
              id: `tg_msg_${Date.now()}`,
              sender_username: currentTgChat.username,
              sender_phone: currentTgChat.phone,
              is_analyst: false,
              text: sc.text,
              timestamp: getFormattedTime(),
              local_media_url: `/presets/${sc.mediaPreset}`,
              views: "2.1K"
            };
            currentTgChat.messages.push(tempMsg);
            renderTelegramMessages();

            try {
              const res = await SimulatorAPI.ingestMessage(payload, "telegram");
              if (res && res.record) {
                tempMsg.extracted_entities = res.record.extracted_entities;
                renderTelegramMessages();
                updateTelemetry();
              }
            } catch (err) {}
          } else {
            sendTelegramMessage();
          }
        } else {
          // If WhatsApp, inject into WhatsApp input and send
          const waInput = document.getElementById("chatInput");
          if (waInput) {
            waInput.value = sc.text;
            const waSendBtn = document.getElementById("btnSend");
            if (waSendBtn) waSendBtn.click();
          }
        }
      });

      scenariosContainer.appendChild(card);
    });
  }

  btnOpenScenarios.addEventListener("click", () => {
    renderScenarios();
    modalScenarios.classList.add("active");
  });

  btnCloseScenarios.addEventListener("click", () => {
    modalScenarios.classList.remove("active");
  });

  // ----------------------------------------------------------------------------
  // 9. Telemetry Polling
  // ----------------------------------------------------------------------------
  async function updateTelemetry() {
    try {
      const status = await SimulatorAPI.getEngineStatus();
      if (status && status.stats && status.stats.total_raw_logs !== undefined) {
        headerLogsCount.textContent = `${status.stats.total_raw_logs} logs`;
      }
    } catch (e) {}
  }

  setInterval(updateTelemetry, 15000);

  // Initialize
  await bootstrapSuite();
});
