/**
 * Telegram Web K/Z Simulation - Authentic Master Controller
 * ========================================================
 * Authentic Telegram Web interface with drawer menu, native emoji picker,
 * interactive message reactions, and emoji-based threat indicators.
 */

document.addEventListener("DOMContentLoaded", async () => {
  let isAnalystMode = false;
  let attachedFile = null;

  // Channels state
  let channels = [
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
      unreadCount: 2,
      messages: [
        {
          id: "tg_m1",
          sender_username: "@blr_supplies_bot",
          sender_phone: "+91 98765 43210",
          is_analyst: false,
          text: "🚀 WEEKEND SPECIAL: Fresh MDMA 1g 3k / Pure Hydro Cannabis buds in stock! Fast dead drop delivery across Indiranagar, Koramangala & Whitefield. DM @blr_supplies_bot for menu.",
          timestamp: "10:30 AM",
          has_media: false,
          views: "1.4K",
          extracted_entities: {
            narcotics_detected: ["mdma", "cannabis", "hydro"]
          },
          reactions: [{ emoji: "💊", count: 1, tooltip: "Narcotics: mdma, cannabis" }]
        },
        {
          id: "tg_m2",
          sender_username: "@blr_supplies_bot",
          sender_phone: "+91 98765 43210",
          is_analyst: false,
          text: "Pay token advance to confirm slot via UPI: dealer_blr@okhdfcbank or dark_supply@paytm. GPS drop coordinates sent 10 mins post payment.",
          timestamp: "11:20 AM",
          has_media: false,
          views: "1.8K",
          extracted_entities: {
            upi_ids: ["dealer_blr@okhdfcbank", "dark_supply@paytm"]
          },
          reactions: [{ emoji: "💳", count: 1, tooltip: "UPI: dealer_blr@okhdfcbank" }]
        }
      ]
    },
    {
      id: "tg_ncr_drops",
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
      unreadCount: 0,
      messages: [
        {
          id: "tg_m3",
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
          },
          reactions: [
            { emoji: "💊", count: 1, tooltip: "Narcotics: meow meow" },
            { emoji: "📍", count: 1, tooltip: "Pin: 28.4595, 77.0266" },
            { emoji: "🚨", count: 1, tooltip: "Threat Score: 0.99" }
          ]
        }
      ]
    },
    {
      id: "tg_dealer_direct",
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
          id: "tg_m4",
          sender_username: "@aryan_plug",
          sender_phone: "+91 98765 43210",
          is_analyst: false,
          text: "Yo, setting ho gayi hai. 2g packet pack ho gaya. GPay pe token daal do.",
          timestamp: "12:05 PM",
          has_media: false,
          extracted_entities: {
            narcotics_detected: ["packet", "token"]
          },
          reactions: [{ emoji: "💊", count: 1, tooltip: "Hinglish Solicitation" }]
        }
      ]
    }
  ];

  let currentChat = channels[0];
  const savedState = window.TelegramLocalStore.load();
  if (savedState && Array.isArray(savedState.channels) && savedState.channels.length) {
    channels = savedState.channels;
    currentChat = channels.find(chat => chat.id === savedState.activeChatId) || channels[0];
  }

  function persistLocalState() {
    window.TelegramLocalStore.save({ channels, activeChatId: currentChat && currentChat.id });
  }

  async function restoreLocalAttachments() {
    for (const chat of channels) {
      for (const msg of chat.messages || []) {
        if (!msg.local_media_id) continue;
        const blob = await window.TelegramLocalStore.getAttachment(msg.local_media_id);
        if (blob) msg.local_media_url = URL.createObjectURL(blob);
      }
    }
  }

  // DOM Elements
  const chatListEl = document.getElementById("tgChatList");
  const messagesScrollEl = document.getElementById("tgMessagesScroll");
  const messageInput = document.getElementById("tgMessageInput");
  const btnSend = document.getElementById("tgBtnSend");
  const btnAttach = document.getElementById("tgBtnAttach");
  const fileInput = document.getElementById("tgFileInput");
  const attachPreview = document.getElementById("tgAttachPreview");
  const previewThumb = document.getElementById("tgPreviewThumb");
  const previewTitle = document.getElementById("tgPreviewTitle");
  const btnRemoveAttach = document.getElementById("tgBtnRemoveAttach");
  const searchInput = document.getElementById("tgSearchInput");
  const folderTabs = document.querySelectorAll(".tg-tab-btn");

  // Header Elements
  const headerNameEl = document.getElementById("tgChatHeaderName");
  const headerStatusEl = document.getElementById("tgChatHeaderStatus");
  const headerAvatarEl = document.getElementById("tgChatHeaderAvatar");
  const btnHeaderMore = document.getElementById("tgHeaderMore");
  const tgMoreDropdown = document.getElementById("tgMoreDropdown");
  const menuTogglePersona = document.getElementById("menuTogglePersona");
  const menuClearChat = document.getElementById("menuClearChat");

  // Drawer Elements
  const btnBurger = document.getElementById("btnBurger");
  const tgDrawer = document.getElementById("tgDrawer");
  const tgDrawerBackdrop = document.getElementById("tgDrawerBackdrop");
  const drawerNewChannel = document.getElementById("drawerNewChannel");
  const drawerNewGroup = document.getElementById("drawerNewGroup");
  const drawerTogglePersona = document.getElementById("drawerTogglePersona");
  const drawerPersonaText = document.getElementById("drawerPersonaText");
  const drawerUserName = document.getElementById("drawerUserName");

  // Emoji Elements
  const btnEmoji = document.getElementById("tgBtnEmoji");
  const emojiPicker = document.getElementById("tgEmojiPicker");
  const emojiGrid = document.getElementById("tgEmojiGrid");
  const emojiTabs = document.querySelectorAll(".tg-emoji-tab");

  // Modal Elements
  const modalCreateChat = document.getElementById("modalCreateChat");
  const modalCreateChatBackdrop = document.getElementById("modalCreateChatBackdrop");
  const btnCloseCreateChat = document.getElementById("btnCloseCreateChat");
  const btnCancelCreateChat = document.getElementById("btnCancelCreateChat");
  const btnSubmitCreateChat = document.getElementById("btnSubmitCreateChat");
  const createChatTitle = document.getElementById("createChatTitle");
  const createChatUsername = document.getElementById("createChatUsername");
  const createChatPhone = document.getElementById("createChatPhone");
  const createChatType = document.getElementById("createChatType");

  // ==============================================================================
  // EMOJI DATASET & INTERACTIVE PICKER
  // ==============================================================================
  const EMOJI_SETS = {
    smileys: [
      "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇",
      "🙂", "🙃", "😉", "😌", "😍", "🥰", "😘", "😗", "😙", "😚",
      "😋", "😛", "😜", "🤪", "🤨", "🧐", "🤓", "😎", "🥳", "😏",
      "😒", "😞", "😔", "😟", "😕", "🙁", "😣", "😖", "😫", "😩",
      "🥺", "😢", "😭", "😤", "😠", "😡", "🤬", "🤯", "😳", "🥵",
      "🥶", "😱", "😨", "😰", "😥", "😓", "🤗", "🤔", "🤭", "🤫",
      "🤥", "😶", "😐", "😑", "😬", "🙄", "😯", "😦", "😧", "😮",
      "😲", "🥱", "😴", "🤤", "😪", "😵", "🤐", "🥴", "🤢", "🤮"
    ],
    threat: [
      "💊", "💉", "🌿", "🍄", "📦", "📍", "💳", "🏦", "💵", "⚠️",
      "🚨", "🕵️", "🔒", "🤐", "🤫", "💀", "🔥", "⚡", "💣", "💨",
      "💎", "🧪", "🚬", "🍫", "🍁", "🍪", "🧂", "💰", "🧾", "🪙",
      "🎯", "🔑", "🛡️", "👀", "👁️", "🕶️", "💼", "📱", "📞", "🤝"
    ],
    objects: [
      "💳", "🏦", "📱", "💻", "📞", "💵", "💰", "💸", "🪙", "📦",
      "📮", "📍", "🗺️", "🔑", "🗝️", "🧾", "📄", "🏷️", "🛒", "🛍️",
      "🎁", "🎈", "🎉", "✈️", "🚀", "🚗", "🛵", "🚲", "🏠", "🏢"
    ],
    symbols: [
      "⚡", "🔥", "💯", "✨", "⭐", "🌟", "💥", "⚠️", "🚨", "🛑",
      "⛔", "✅", "❌", "❓", "❗", "🎯", "🏆", "💎", "👑", "🕊️",
      "👁️", "🗨️", "💬", "💭", "🔴", "🟢", "🟡", "🔵", "🟣", "⚫"
    ]
  };

  let activeEmojiTab = "smileys";

  function renderEmojiGrid(tabKey) {
    emojiGrid.innerHTML = "";
    const list = EMOJI_SETS[tabKey] || EMOJI_SETS.smileys;
    list.forEach(emoji => {
      const el = document.createElement("div");
      el.className = "tg-emoji-item";
      el.textContent = emoji;
      el.addEventListener("click", () => {
        insertEmoji(emoji);
      });
      emojiGrid.appendChild(el);
    });
  }

  function insertEmoji(emoji) {
    const start = messageInput.selectionStart || messageInput.value.length;
    const end = messageInput.selectionEnd || messageInput.value.length;
    const text = messageInput.value;
    messageInput.value = text.slice(0, start) + emoji + text.slice(end);
    messageInput.focus();
    messageInput.selectionStart = messageInput.selectionEnd = start + emoji.length;
  }

  btnEmoji.addEventListener("click", (e) => {
    e.stopPropagation();
    emojiPicker.classList.toggle("active");
    if (emojiPicker.classList.contains("active")) {
      renderEmojiGrid(activeEmojiTab);
    }
  });

  emojiTabs.forEach(tab => {
    tab.addEventListener("click", (e) => {
      e.stopPropagation();
      emojiTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      activeEmojiTab = tab.dataset.tab;
      renderEmojiGrid(activeEmojiTab);
    });
  });

  // Close emoji picker on click outside
  document.addEventListener("click", (e) => {
    if (!emojiPicker.contains(e.target) && e.target !== btnEmoji) {
      emojiPicker.classList.remove("active");
    }
    if (!tgMoreDropdown.contains(e.target) && e.target !== btnHeaderMore) {
      tgMoreDropdown.classList.remove("active");
    }
  });

  // ==============================================================================
  // DRAWER & HEADER MENU
  // ==============================================================================
  btnBurger.addEventListener("click", () => {
    tgDrawer.classList.add("active");
    tgDrawerBackdrop.classList.add("active");
  });

  tgDrawerBackdrop.addEventListener("click", () => {
    tgDrawer.classList.remove("active");
    tgDrawerBackdrop.classList.remove("active");
  });

  btnHeaderMore.addEventListener("click", (e) => {
    e.stopPropagation();
    tgMoreDropdown.classList.toggle("active");
  });

  function togglePersona() {
    isAnalystMode = !isAnalystMode;
    playClick();
    if (isAnalystMode) {
      drawerUserName.textContent = "Cyber OSINT Analyst (Self)";
      drawerPersonaText.textContent = "Switch to Suspect View";
      menuTogglePersona.innerHTML = `<span>🎭</span> Switch to Suspect View`;
    } else {
      drawerUserName.textContent = "Aryan (Target Suspect)";
      drawerPersonaText.textContent = "Switch to Analyst View";
      menuTogglePersona.innerHTML = `<span>🎭</span> Switch to Analyst View`;
    }
    tgDrawer.classList.remove("active");
    tgDrawerBackdrop.classList.remove("active");
    tgMoreDropdown.classList.remove("active");
  }

  drawerTogglePersona.addEventListener("click", togglePersona);
  menuTogglePersona.addEventListener("click", togglePersona);

  menuClearChat.addEventListener("click", () => {
    if (currentChat) {
      currentChat.messages = [];
      persistLocalState();
      renderMessages();
      tgMoreDropdown.classList.remove("active");
    }
  });

  // Modal open
  drawerNewChannel.addEventListener("click", () => {
    tgDrawer.classList.remove("active");
    tgDrawerBackdrop.classList.remove("active");
    createChatType.value = "channel";
    openChatModal();
  });

  drawerNewGroup.addEventListener("click", () => {
    tgDrawer.classList.remove("active");
    tgDrawerBackdrop.classList.remove("active");
    createChatType.value = "group";
    openChatModal();
  });

  function openChatModal() {
    modalCreateChat.classList.add("active");
    modalCreateChatBackdrop.classList.add("active");
  }

  function closeChatModal() {
    modalCreateChat.classList.remove("active");
    modalCreateChatBackdrop.classList.remove("active");
  }

  btnCloseCreateChat.addEventListener("click", closeChatModal);
  btnCancelCreateChat.addEventListener("click", closeChatModal);
  modalCreateChatBackdrop.addEventListener("click", closeChatModal);

  btnSubmitCreateChat.addEventListener("click", () => {
    const title = createChatTitle.value.trim();
    if (!title) return;

    const newChat = {
      id: `tg_chat_${Date.now()}`,
      type: createChatType.value,
      title: title,
      username: createChatUsername.value.trim() || "@custom_channel",
      phone: createChatPhone.value.trim() || "+91 99999 88888",
      avatarText: title.slice(0, 2).toUpperCase(),
      avatarColor: "#2AABEE",
      verified: createChatType.value === "channel",
      subscribers: createChatType.value === "channel" ? "1 subscriber" : "online",
      status: createChatType.value === "channel" ? "broadcast channel" : "group",
      lastTime: "Just now",
      unreadCount: 0,
      messages: []
    };

    channels.unshift(newChat);
    currentChat = newChat;
    persistLocalState();
    closeChatModal();
    renderChatList();
    renderMessages();

  });

  // ==============================================================================
  // RENDERING & AUDIO
  // ==============================================================================
  function playClick() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(800, ctx.currentTime);
      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.03);
    } catch (e) {}
  }

  function getFormattedTime() {
    const d = new Date();
    let h = d.getHours();
    const m = String(d.getMinutes()).padStart(2, "0");
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${m} ${ampm}`;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Render Sidebar
  function renderChatList(filterType = "all", query = "") {
    chatListEl.innerHTML = "";
    const cleanQuery = query.trim().toLowerCase();

    const filtered = channels.filter(c => {
      if (filterType === "channels" && c.type !== "channel") return false;
      if (filterType === "groups" && c.type !== "group") return false;
      if (filterType === "direct" && c.type !== "private") return false;
      if (cleanQuery) {
        return c.title.toLowerCase().includes(cleanQuery) || c.username.toLowerCase().includes(cleanQuery);
      }
      return true;
    });

    filtered.forEach(chat => {
      const item = document.createElement("div");
      item.className = `tg-chat-item ${currentChat && currentChat.id === chat.id ? "active" : ""}`;
      const lastMsg = chat.messages.length > 0 ? chat.messages[chat.messages.length - 1] : null;

      // Check for threat flagging
      let hasFlaggedMsg = chat.messages.some(m => m.reactions && m.reactions.some(r => r.emoji === "💊" || r.emoji === "🚨"));

      item.innerHTML = `
        <div class="tg-avatar-wrap" style="background: ${chat.avatarColor || '#2AABEE'};">
          ${chat.avatarText || chat.title.slice(0, 2).toUpperCase()}
        </div>
        <div class="tg-chat-content">
          <div class="tg-chat-top">
            <div class="tg-chat-title-row">
              <span class="tg-chat-title">${escapeHtml(chat.title)}</span>
              ${chat.verified ? '<span class="tg-badge-verified">★</span>' : ''}
              ${hasFlaggedMsg ? '<span class="tg-flag-indicator" title="Contraband Intelligence Detected">🚨</span>' : ''}
            </div>
            <span class="tg-chat-time">${chat.lastTime || ""}</span>
          </div>
          <div class="tg-chat-bottom">
            <span class="tg-chat-preview">${escapeHtml(lastMsg ? (lastMsg.text || "[Media]") : "No messages")}</span>
            ${chat.unreadCount > 0 ? `<span class="tg-chat-unread-badge">${chat.unreadCount}</span>` : ""}
          </div>
        </div>
      `;

      item.addEventListener("click", () => {
        currentChat = chat;
        chat.unreadCount = 0;
        persistLocalState();
        playClick();
        renderChatList(filterType, query);
        renderMessages();
      });

      chatListEl.appendChild(item);
    });
  }

  // Render Messages with Authentic Emoji Reactions
  function renderMessages() {
    if (!currentChat) return;

    headerNameEl.innerHTML = `${escapeHtml(currentChat.title)} ${currentChat.verified ? '<span class="tg-badge-verified">★</span>' : ''}`;
    headerStatusEl.textContent = currentChat.subscribers || currentChat.status;
    headerAvatarEl.textContent = currentChat.avatarText || currentChat.title.slice(0, 2).toUpperCase();
    headerAvatarEl.style.background = currentChat.avatarColor || "#2AABEE";

    messagesScrollEl.innerHTML = `<div class="tg-day-divider">Today</div>`;

    currentChat.messages.forEach((msg, mIdx) => {
      const isOutgoing = Boolean(msg.is_analyst || msg.is_honeypot);
      const row = document.createElement("div");
      row.className = `tg-msg-row ${isOutgoing ? "outgoing" : "incoming"}`;

      let mediaHtml = "";
      if (msg.local_media_url) {
        mediaHtml = `
          <div class="tg-bubble-media">
            <img src="${msg.local_media_url}" alt="Attachment" onclick="window.open('${msg.local_media_url}', '_blank')">
          </div>
        `;
      }

      // Build Authentic Telegram Reactions Pills
      let reactionsHtml = "";
      const reactionsList = msg.reactions || [];

      // Auto-generate reactions based on extracted entities if not populated
      if (reactionsList.length === 0 && msg.extracted_entities) {
        const ent = msg.extracted_entities;
        if (ent.narcotics_detected && ent.narcotics_detected.length) {
          reactionsList.push({
            emoji: "💊",
            count: 1,
            pillClass: "flagged-substance",
            tooltip: `Narcotics: ${ent.narcotics_detected.join(', ')}`
          });
        }
        if (ent.upi_ids && ent.upi_ids.length) {
          reactionsList.push({
            emoji: "💳",
            count: 1,
            pillClass: "flagged-upi",
            tooltip: `UPI: ${ent.upi_ids.join(', ')}`
          });
        }
        if (ent.gps_coordinates && ent.gps_coordinates.length) {
          reactionsList.push({
            emoji: "📍",
            count: 1,
            pillClass: "",
            tooltip: `Pin: ${ent.gps_coordinates.join(', ')}`
          });
        }
        if (ent.threat_score >= 0.60 || msg.threat_score >= 0.60) {
          reactionsList.push({
            emoji: "🚨",
            count: 1,
            pillClass: "flagged-threat",
            tooltip: `Threat Score: ${msg.threat_score || 0.99}`
          });
        }
        msg.reactions = reactionsList;
      }

      if (reactionsList.length > 0) {
        const pills = reactionsList.map((r, rIdx) => `
          <div class="tg-reaction-pill ${r.pillClass || ''}" data-tooltip="${escapeHtml(r.tooltip || 'Reaction')}" onclick="window.toggleReaction(${mIdx}, ${rIdx})">
            <span class="tg-reaction-emoji">${r.emoji}</span>
            <span class="tg-reaction-count">${r.count}</span>
          </div>
        `).join("");
        reactionsHtml = `<div class="tg-reactions-row">${pills}</div>`;
      }

      const senderDisplay = !isOutgoing && currentChat.type !== "private"
        ? `<span class="tg-bubble-sender">${escapeHtml(msg.sender_username || currentChat.username)}</span>`
        : "";

      const viewsDisplay = currentChat.type === "channel"
        ? `<span class="tg-channel-views">👁️ ${msg.views || "1.2K"}</span>`
        : "";

      row.innerHTML = `
        <div class="tg-bubble">
          <!-- Quick Reaction Hover Bar -->
          <div class="tg-hover-reactions">
            <span class="tg-quick-emoji" onclick="window.addReaction(${mIdx}, '👍')">👍</span>
            <span class="tg-quick-emoji" onclick="window.addReaction(${mIdx}, '🔥')">🔥</span>
            <span class="tg-quick-emoji" onclick="window.addReaction(${mIdx}, '💊')">💊</span>
            <span class="tg-quick-emoji" onclick="window.addReaction(${mIdx}, '🚨')">🚨</span>
          </div>

          ${senderDisplay}
          ${mediaHtml}
          <div class="tg-bubble-text">${(() => {
            let txt = escapeHtml(msg.text || "");
            return txt.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener" style="color: #53bdeb; text-decoration: underline; font-weight: 500; word-break: break-all;">$1</a>');
          })()}</div>
          ${reactionsHtml}
          <div class="tg-bubble-meta">
            ${viewsDisplay}
            <span class="tg-msg-time">${msg.timestamp || getFormattedTime()}</span>
            <span class="checks">✓✓</span>
          </div>
        </div>
      `;

      messagesScrollEl.appendChild(row);
    });

    messagesScrollEl.scrollTop = messagesScrollEl.scrollHeight;
  }

  // Reaction Handlers
  window.addReaction = function(msgIndex, emoji) {
    if (!currentChat || !currentChat.messages[msgIndex]) return;
    const msg = currentChat.messages[msgIndex];
    if (!msg.reactions) msg.reactions = [];

    const existing = msg.reactions.find(r => r.emoji === emoji);
    if (existing) {
      existing.count += 1;
    } else {
      msg.reactions.push({ emoji: emoji, count: 1, tooltip: `Reaction: ${emoji}` });
    }
    renderMessages();
    persistLocalState();
  };

  window.toggleReaction = function(msgIndex, reactionIndex) {
    if (!currentChat || !currentChat.messages[msgIndex]) return;
    const msg = currentChat.messages[msgIndex];
    if (msg.reactions && msg.reactions[reactionIndex]) {
      msg.reactions[reactionIndex].count += 1;
      renderMessages();
      persistLocalState();
    }
  };

  // Send Message
  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text && !attachedFile) return;

    playClick();
    const formattedTime = getFormattedTime();
    const messageId = crypto.randomUUID ? crypto.randomUUID() : `tg_${Date.now()}`;
    let analysisResult;
    try {
      analysisResult = await window.SimulatorAPI.ingestMessage({
        message_id: messageId,
        chat_id: currentChat.id,
        chat_title: currentChat.title,
        participant_id: currentChat.phone || currentChat.username || currentChat.id,
        sender_id: isAnalystMode ? `analyst:${currentChat.id}` : (currentChat.phone || currentChat.username || currentChat.id),
        sender_username: isAnalystMode ? "You" : (currentChat.username || currentChat.title),
        sender_display_name: isAnalystMode ? "You" : currentChat.title,
        recipient_name: currentChat.title,
        is_analyst: isAnalystMode,
        timestamp: new Date().toISOString(),
        message_body: text,
        file: attachedFile
      });
    } catch (error) {
      alert(`Message was not sent because backend analysis failed: ${error.message || "API unavailable"}`);
      return;
    }
    window.SimulatorAPI.showAnalysisResult(analysisResult);

    let attachmentId = null;
    if (attachedFile) attachmentId = await window.TelegramLocalStore.saveAttachment(attachedFile);
    const tempMsg = {
      id: messageId,
      sender_username: isAnalystMode ? "You" : (currentChat.username || currentChat.title),
      sender_phone: currentChat.phone,
      is_analyst: isAnalystMode,
      text: text,
      timestamp: formattedTime,
      has_media: Boolean(attachedFile),
      local_media_id: attachmentId,
      local_media_url: attachedFile ? URL.createObjectURL(attachedFile) : null,
      media_name: attachedFile ? attachedFile.name : null,
      media_type: attachedFile ? attachedFile.type : null,
      views: "1",
      reactions: [],
      analysis_case_id: analysisResult.case_id || null,
      analysis_review_required: Boolean(analysisResult.review_required)
    };

    currentChat.messages.push(tempMsg);
    currentChat.lastTime = formattedTime;

    // Check if Smart Bot honeypot was triggered on threshold reach
    const botText = (analysisResult && (analysisResult.bot_response || (analysisResult.smart_bot && analysisResult.smart_bot.dispatched_message))) || null;
    if (botText) {
      setTimeout(() => {
        const botMsg = {
          id: `msg_buyer_${Date.now()}`,
          sender_username: "You",
          sender_phone: "+91 99999 00000",
          is_analyst: true, // Right-aligned outgoing buyer persona
          text: botText,
          timestamp: getFormattedTime(),
          has_media: false,
          views: "1",
          reactions: [],
          is_honeypot: true
        };
        currentChat.messages.push(botMsg);
        persistLocalState();
        renderMessages();
      }, 700);
    }

    persistLocalState();
    renderMessages();

    messageInput.value = "";
    removeAttachment();
    emojiPicker.classList.remove("active");

  }

  btnSend.addEventListener("click", sendMessage);
  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Attachments
  btnAttach.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      attachedFile = e.target.files[0];
      previewThumb.src = URL.createObjectURL(attachedFile);
      previewTitle.textContent = attachedFile.name;
      attachPreview.classList.add("active");
    }
  });

  function removeAttachment() {
    if (previewThumb.src.startsWith("blob:")) URL.revokeObjectURL(previewThumb.src);
    attachedFile = null;
    fileInput.value = "";
    attachPreview.classList.remove("active");
  }
  btnRemoveAttach.addEventListener("click", removeAttachment);

  // Tabs
  folderTabs.forEach(t => {
    t.addEventListener("click", () => {
      folderTabs.forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      renderChatList(t.dataset.tab, searchInput.value);
    });
  });

  searchInput.addEventListener("input", (e) => {
    const act = document.querySelector(".tg-tab-btn.active");
    renderChatList(act ? act.dataset.tab : "all", e.target.value);
  });

  // Initial render
  await restoreLocalAttachments();
  persistLocalState();
  renderChatList();
  renderMessages();
  renderEmojiGrid("smileys");
});
