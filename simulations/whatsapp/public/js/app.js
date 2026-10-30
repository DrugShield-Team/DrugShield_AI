/**
 * WhatsApp Web Client Application - Master Interactive Controller
 * ==============================================================
 * Comprehensive functional logic for:
 * 1. Top Header Action Modals (New Group & New Chat)
 * 2. Attachment Menu & In-Input Preview Card
 * 3. Emoji Picker with live cursor insertion & category filter
 * 4. Voice Note Recording via browser MediaRecorder API
 * 5. Interactive Poll Voting & Document Rendering
 * 6. Browser-local message and attachment persistence
 */

document.addEventListener("DOMContentLoaded", async () => {
  // Application State
  let currentContact = ContactsData.CONTACTS[0];
  let isYouMode = false; // Toggle: typing as Contact (incoming) vs You (outgoing)
  let attachedFile = null;
  let attachedDoc = null;
  let presetMediaPath = null;
  let chatHistories = {};
  const simulatedLocalities = { chat_group: "Koramangala", chat_aryan: "Jayanagar", chat_priya: "Indiranagar", chat_vikram: "Whitefield", chat_rohan: "Rajajinagar", chat_sneha: "Banashankari" };
  const currentSimulatedLocality = () => currentContact?.simulated_locality || simulatedLocalities[currentContact?.id] || null;

  // Voice Note Recording State
  let mediaRecorder = null;
  let audioChunks = [];
  let recordTimerInterval = null;
  let recordSeconds = 0;
  const savedState = window.WhatsAppLocalStore.load();
  if (savedState && Array.isArray(savedState.contacts) && savedState.contacts.length) {
    ContactsData.CONTACTS.splice(0, ContactsData.CONTACTS.length, ...savedState.contacts);
  }
  ContactsData.CONTACTS.forEach(contact => {
    chatHistories[contact.id] = savedState?.chatHistories?.[contact.id] || [...(contact.defaultMessages || [])];
  });
  currentContact = ContactsData.CONTACTS.find(contact => contact.id === savedState?.activeContactId) || ContactsData.CONTACTS[0];

  function persistLocalState() {
    window.WhatsAppLocalStore.save({ contacts: ContactsData.CONTACTS, chatHistories, activeContactId: currentContact?.id });
  }

  async function restoreLocalAttachments() {
    for (const history of Object.values(chatHistories)) {
      for (const message of history) {
        if (!message.local_media_id) continue;
        const blob = await window.WhatsAppLocalStore.getAttachment(message.local_media_id);
        if (!blob) continue;
        const url = URL.createObjectURL(blob);
        message.local_media_url = url;
        if (message.is_voice) message.voice_url = url;
      }
    }
  }

  // DOM Elements - Main Layout
  const chatListEl = document.getElementById("chatList");
  const messagesContainer = document.getElementById("messagesContainer");
  const chatHeaderTitle = document.getElementById("chatHeaderTitle");
  const chatHeaderSubtitle = document.getElementById("chatHeaderSubtitle");
  const chatHeaderAvatar = document.getElementById("chatHeaderAvatar");
  const chatInput = document.getElementById("chatInput");
  const btnSend = document.getElementById("btnSend");
  const btnVoiceNote = document.getElementById("btnVoiceNote");
  const btnSenderSwitch = document.getElementById("btnSenderSwitch");
  const senderModeIndicator = document.getElementById("senderModeIndicator");
  const attachmentBtn = document.getElementById("attachmentBtn");
  const attachmentPopup = document.getElementById("attachmentPopup");
  const fileInputPhoto = document.getElementById("fileInputPhoto");
  const fileInputDoc = document.getElementById("fileInputDoc");
  const dragDropOverlay = document.getElementById("dragDropOverlay");
  const chatWindow = document.getElementById("chatWindow");

  // Attachment Preview Card Elements
  const attachmentPreviewCard = document.getElementById("attachmentPreviewCard");
  const previewMediaBox = document.getElementById("previewMediaBox");
  const previewFileName = document.getElementById("previewFileName");
  const previewFileSize = document.getElementById("previewFileSize");
  const btnRemoveAttachment = document.getElementById("btnRemoveAttachment");

  // Emoji Elements
  const btnEmoji = document.getElementById("btnEmoji");
  const emojiDrawer = document.getElementById("emojiDrawer");
  const emojiGrid = document.getElementById("emojiGrid");
  const emojiSearchInput = document.getElementById("emojiSearchInput");
  const emojiCategoryNav = document.getElementById("emojiCategoryNav");

  // Voice Recording Elements
  const footerNormalRow = document.getElementById("footerNormalRow");
  const recordingBar = document.getElementById("recordingBar");
  const recordingTimer = document.getElementById("recordingTimer");
  const btnCancelRecording = document.getElementById("btnCancelRecording");
  const btnSendRecording = document.getElementById("btnSendRecording");

  // Modals Elements
  const btnNewChat = document.getElementById("btnNewChat");
  const btnSidebarMenu = document.getElementById("btnSidebarMenu");
  const sidebarMenu = document.getElementById("sidebarMenu");
  const menuNewGroup = document.getElementById("menuNewGroup");
  const menuNewChatOption = document.getElementById("menuNewChatOption");
  const menuToggleTheme = document.getElementById("menuToggleTheme");
  const menuToggleSender = document.getElementById("menuToggleSender");

  // New Group Modal
  const modalNewGroup = document.getElementById("modalNewGroup");
  const btnCloseGroupModal = document.getElementById("btnCloseGroupModal");
  const selectedGroupChips = document.getElementById("selectedGroupChips");
  const groupSubjectInput = document.getElementById("groupSubjectInput");
  const groupCharCounter = document.getElementById("groupCharCounter");
  const groupContactsList = document.getElementById("groupContactsList");
  const btnCreateGroupSubmit = document.getElementById("btnCreateGroupSubmit");

  // New Chat Modal
  const modalNewChat = document.getElementById("modalNewChat");
  const btnCloseChatModal = document.getElementById("btnCloseChatModal");
  const newChatName = document.getElementById("newChatName");
  const newChatPhone = document.getElementById("newChatPhone");
  const btnCreateChatSubmit = document.getElementById("btnCreateChatSubmit");

  // Poll Modal
  const modalPoll = document.getElementById("modalPoll");
  const btnClosePollModal = document.getElementById("btnClosePollModal");
  const btnAttachPoll = document.getElementById("btnAttachPoll");
  const btnAddPollOption = document.getElementById("btnAddPollOption");
  const pollOptionsContainer = document.getElementById("pollOptionsContainer");
  const pollQuestion = document.getElementById("pollQuestion");
  const pollMultipleAnswers = document.getElementById("pollMultipleAnswers");
  const btnSubmitPoll = document.getElementById("btnSubmitPoll");

  // Audio Synthesizer (Realistic Click Feedback)
  function playAudioClick() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(800, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.035);
      gain.gain.setValueAtTime(0.06, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.035);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.04);
    } catch (e) {}
  }

  // Format Helper: Bytes to KB/MB
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  // Format Time Helper (e.g., "11:42 AM")
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
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ==============================================================================
  // 1. SIDEBAR CONTACTS LIST RENDERING & SELECTION
  // ==============================================================================
  function renderContacts() {
    chatListEl.innerHTML = "";
    ContactsData.CONTACTS.forEach(contact => {
      const history = chatHistories[contact.id] || [];
      const lastMsg = history[history.length - 1];
      let previewText = contact.status;
      if (lastMsg) {
        if (lastMsg.is_poll) previewText = "📊 Poll: " + lastMsg.question;
        else if (lastMsg.is_voice) previewText = "🎤 Voice message (" + (lastMsg.duration || "0:05") + ")";
        else if (lastMsg.has_media && lastMsg.is_doc) previewText = "📄 " + (lastMsg.doc_name || "Document");
        else if (lastMsg.has_media) previewText = "📷 Photo";
        else previewText = lastMsg.text || "";
      }
      const previewTime = lastMsg ? (lastMsg.timestamp || "Just now") : "10:15 AM";

      const item = document.createElement("div");
      item.className = `chat-item ${contact.id === currentContact.id ? "active" : ""}`;
      item.dataset.contactId = contact.id;

      item.innerHTML = `
        <div class="avatar-container">
          <img src="${contact.avatar}" alt="${contact.name}">
        </div>
        <div class="chat-item-content">
          <div class="chat-item-header">
            <span class="chat-item-name">${escapeHtml(contact.name)}</span>
            <span class="chat-item-time">${previewTime}</span>
          </div>
          <div class="chat-item-footer">
            <span class="chat-item-preview">
              ${lastMsg && lastMsg.is_analyst ? '<span class="tick-icon blue">✓✓</span>' : ''}
              ${escapeHtml(previewText)}
            </span>
            ${contact.unread > 0 ? `<span class="unread-badge">${contact.unread}</span>` : ""}
          </div>
        </div>
      `;

      item.addEventListener("click", () => {
        selectContact(contact);
      });

      chatListEl.appendChild(item);
    });
  }

  function selectContact(contact) {
    currentContact = contact;
    contact.unread = 0;
    renderContacts();

    chatHeaderTitle.textContent = contact.name;
    chatHeaderAvatar.src = contact.avatar;
    chatHeaderSubtitle.textContent = contact.lastSeen || "online";

    renderMessages();
    updateSenderModeUI();
    persistLocalState();
  }

  // ==============================================================================
  // 2. CHAT MESSAGES RENDERING (TEXT, IMAGES, DOCUMENTS, AUDIO, POLLS)
  // ==============================================================================
  function renderMessages() {
    messagesContainer.innerHTML = "";

    // Date Divider
    const datePill = document.createElement("div");
    datePill.className = "date-pill-container";
    datePill.innerHTML = `<div class="date-pill">TODAY</div>`;
    messagesContainer.appendChild(datePill);

    // Encryption Banner
    const encBanner = document.createElement("div");
    encBanner.className = "encryption-banner";
    encBanner.innerHTML = `
      🔒 Messages and calls are end-to-end encrypted. No one outside of this chat, not even WhatsApp, can read or listen to them. Click to learn more.
    `;
    messagesContainer.appendChild(encBanner);

    const messages = chatHistories[currentContact.id] || [];

    messages.forEach((msg, idx) => {
      const isRight = Boolean(msg.is_analyst || msg.is_honeypot);
      const row = document.createElement("div");
      row.className = `message-bubble-row ${isRight ? "outgoing" : "incoming"}`;

      let contentHtml = "";

      // Group sender label
      let senderTag = "";
      if (currentContact.isGroup && !msg.is_analyst && msg.sender_name) {
        senderTag = `<div class="bubble-sender-name">${escapeHtml(msg.sender_name)}</div>`;
      }

      // System message
      if (msg.is_system) {
        row.innerHTML = `
          <div class="date-pill-container" style="margin: 4px 0;">
            <div class="date-pill" style="text-transform: none; font-size: 11.5px;">${escapeHtml(msg.text)}</div>
          </div>
        `;
        messagesContainer.appendChild(row);
        return;
      }

      // Voice Note Bubble
      if (msg.is_voice) {
        contentHtml = `
          <div class="voice-bubble-card">
            <button type="button" class="btn-voice-play" onclick="window.playVoiceNote('${msg.id}', '${msg.voice_url || ''}')" id="playBtn_${msg.id}">▶</button>
            <div class="voice-waveform-track">
              <div class="voice-scrubber">
                <div class="voice-scrubber-progress" id="progress_${msg.id}"></div>
              </div>
              <span class="voice-time-text" id="duration_${msg.id}">${msg.duration || "0:05"}</span>
            </div>
          </div>
        `;
      }
      // Document Bubble
      else if (msg.has_media && msg.is_doc) {
        contentHtml = `
          <div class="doc-bubble-card">
            <span class="doc-bubble-icon">📄</span>
            <div class="doc-bubble-meta">
              <span class="doc-bubble-name">${escapeHtml(msg.doc_name || "Document.pdf")}</span>
              <span class="doc-bubble-size">${escapeHtml(msg.doc_size || "150 KB")} • PDF</span>
            </div>
          </div>
          ${msg.text ? `<div class="bubble-text">${escapeHtml(msg.text)}</div>` : ""}
        `;
      }
      // Photo / Video Bubble
      else if (msg.has_media && (msg.media_path || msg.local_media_url)) {
        const imgSrc = msg.local_media_url || (msg.media_path ? `/${msg.media_path}` : "");
        contentHtml = `
          <div class="bubble-media-wrapper" onclick="window.openImageModal('${imgSrc}', '${escapeHtml(msg.text)}')">
            <img src="${imgSrc}" alt="Photo" onerror="this.style.display='none'">
          </div>
          ${msg.text ? `<div class="bubble-text">${escapeHtml(msg.text)}</div>` : ""}
        `;
      }
      // Interactive Poll Bubble
      else if (msg.is_poll) {
        const totalVotes = msg.options.reduce((sum, opt) => sum + (opt.votes || 0), 0);
        let optionsHtml = msg.options.map((opt, optIdx) => {
          const pct = totalVotes > 0 ? Math.round((opt.votes / totalVotes) * 100) : 0;
          return `
            <div class="poll-option-row" onclick="window.votePoll('${currentContact.id}', ${idx}, ${optIdx})">
              <div class="poll-option-header">
                <span>${opt.selected ? '☑' : '☐'} ${escapeHtml(opt.text)}</span>
                <span class="poll-vote-count">${opt.votes || 0}</span>
              </div>
              <div class="poll-bar-track">
                <div class="poll-bar-fill" style="width: ${pct}%;"></div>
              </div>
            </div>
          `;
        }).join("");

        contentHtml = `
          <div class="poll-bubble-card">
            <div class="poll-bubble-question">📊 ${escapeHtml(msg.question)}</div>
            <div style="font-size: 11px; color: var(--bubble-meta);">Select one or more</div>
            ${optionsHtml}
            <div style="font-size: 11px; color: var(--bubble-meta); text-align: right; margin-top: 4px;">${totalVotes} vote(s)</div>
          </div>
        `;
      }
      // Standard Text Bubble
      else {
        let formatted = escapeHtml(msg.text);
        // Turn http(s) links into clean clickable hyperlinks
        formatted = formatted.replace(
          /(https?:\/\/[^\s<]+)/g,
          '<a href="$1" target="_blank" rel="noopener" style="color: #53bdeb; text-decoration: underline; font-weight: 500; word-break: break-all;">$1</a>'
        );
        contentHtml = `<div class="bubble-text">${formatted}</div>`;
      }

      row.innerHTML = `
        <div class="message-bubble ${isRight ? "outgoing" : "incoming"}">
          ${senderTag}
          ${contentHtml}
          <div class="bubble-meta-info">
            <span>${msg.timestamp || "11:20 AM"}</span>
            ${isRight ? '<span class="tick-icon blue">✓✓</span>' : ''}
          </div>
        </div>
      `;

      messagesContainer.appendChild(row);
    });

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Global Poll Voting Handler
  window.votePoll = function(contactId, msgIdx, optIdx) {
    const history = chatHistories[contactId];
    if (!history || !history[msgIdx]) return;
    const poll = history[msgIdx];
    if (!poll.is_poll) return;

    if (!poll.multiple) {
      poll.options.forEach((o, i) => {
        if (i !== optIdx && o.selected) {
          o.selected = false;
          o.votes = Math.max(0, o.votes - 1);
        }
      });
    }

    const targetOpt = poll.options[optIdx];
    targetOpt.selected = !targetOpt.selected;
    targetOpt.votes = targetOpt.selected ? (targetOpt.votes + 1) : Math.max(0, targetOpt.votes - 1);

    renderMessages();
    persistLocalState();
  };

  // Global Voice Note Playback Handler
  let activeAudio = null;
  window.playVoiceNote = function(msgId, audioUrl) {
    const btn = document.getElementById(`playBtn_${msgId}`);
    const progress = document.getElementById(`progress_${msgId}`);
    const durLabel = document.getElementById(`duration_${msgId}`);

    if (activeAudio && !activeAudio.paused) {
      activeAudio.pause();
      if (activeAudio.activeBtn) activeAudio.activeBtn.textContent = "▶";
      if (activeAudio.msgId === msgId) return;
    }

    if (!audioUrl) return;

    const audio = new Audio(audioUrl);
    activeAudio = audio;
    audio.msgId = msgId;
    audio.activeBtn = btn;
    btn.textContent = "⏸";

    audio.ontimeupdate = () => {
      if (audio.duration) {
        const pct = (audio.currentTime / audio.duration) * 100;
        progress.style.width = pct + "%";
        const mins = Math.floor(audio.currentTime / 60);
        const secs = String(Math.floor(audio.currentTime % 60)).padStart(2, "0");
        durLabel.textContent = `${mins}:${secs}`;
      }
    };

    audio.onended = () => {
      btn.textContent = "▶";
      progress.style.width = "0%";
    };

    audio.play();
  };

  // ==============================================================================
  // 3. SENDER SWITCHER LOGIC (CONTACT VS YOU)
  // ==============================================================================
  function toggleSenderMode() {
    isYouMode = !isYouMode;
    updateSenderModeUI();
  }

  function updateSenderModeUI() {
    if (isYouMode) {
      btnSenderSwitch.className = "icon-btn sender-mode-btn you-mode";
      senderModeIndicator.textContent = "💬";
      btnSenderSwitch.title = "Current: Outgoing from You [Press Alt+S to switch]";
      chatInput.placeholder = attachedFile || attachedDoc ? "Add a caption..." : "Type a message (Outgoing from You)";
    } else {
      btnSenderSwitch.className = "icon-btn sender-mode-btn contact-mode";
      senderModeIndicator.textContent = "👤";
      btnSenderSwitch.title = `Current: Incoming from ${currentContact.name} [Press Alt+S to switch]`;
      chatInput.placeholder = attachedFile || attachedDoc ? "Add a caption..." : `Type a message (Incoming from ${currentContact.name})`;
    }
  }

  btnSenderSwitch.addEventListener("click", toggleSenderMode);
  document.addEventListener("keydown", (e) => {
    if (e.altKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      toggleSenderMode();
    }
  });

  // Toggle Send button vs Mic button on typing
  chatInput.addEventListener("input", () => {
    const hasText = chatInput.value.trim().length > 0;
    const hasAttachment = Boolean(attachedFile || attachedDoc || presetMediaPath);
    if (hasText || hasAttachment) {
      btnSend.style.display = "flex";
      btnVoiceNote.style.display = "none";
    } else {
      btnSend.style.display = "none";
      btnVoiceNote.style.display = "flex";
    }
  });

  // ==============================================================================
  // 4. ATTACHMENT MENU & PREVIEW CARD LOGIC
  // ==============================================================================
  attachmentBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    attachmentPopup.classList.toggle("active");
  });

  document.addEventListener("click", () => {
    attachmentPopup.classList.remove("active");
    sidebarMenu.classList.remove("active");
  });

  // Photo & Video Selection
  document.getElementById("btnAttachPhoto").addEventListener("click", () => {
    fileInputPhoto.click();
  });

  fileInputPhoto.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0], "image");
    }
  });

  // Document Selection
  document.getElementById("btnAttachDoc").addEventListener("click", () => {
    fileInputDoc.click();
  });

  fileInputDoc.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0], "doc");
    }
  });

  // Payment QR Code Preset Selection
  document.getElementById("btnAttachPresetQR").addEventListener("click", () => {
    presetMediaPath = "presets/upi_qr_dealer.png";
    showAttachmentPreview({
      name: "upi_qr_dealer.png",
      sizeStr: "1.2 KB",
      thumbUrl: "presets/upi_qr_dealer.png",
      isImage: true
    });
    chatInput.focus();
  });

  // Common File Handler
  function handleFileSelected(file, type) {
    if (type === "image") {
      attachedFile = file;
      attachedDoc = null;
      presetMediaPath = null;
      showAttachmentPreview({
        name: file.name,
        sizeStr: formatBytes(file.size),
        thumbUrl: URL.createObjectURL(file),
        isImage: true
      });
    } else {
      attachedDoc = file;
      attachedFile = null;
      presetMediaPath = null;
      showAttachmentPreview({
        name: file.name,
        sizeStr: formatBytes(file.size),
        thumbUrl: null,
        isImage: false
      });
    }
    chatInput.focus();
  }

  function showAttachmentPreview({ name, sizeStr, thumbUrl, isImage }) {
    previewFileName.textContent = name;
    previewFileSize.textContent = sizeStr;

    if (isImage && thumbUrl) {
      previewMediaBox.innerHTML = `<img src="${thumbUrl}" alt="Preview">`;
    } else {
      previewMediaBox.innerHTML = `📄`;
    }

    attachmentPreviewCard.classList.add("active");
    chatInput.placeholder = "Add a caption...";
    btnSend.style.display = "flex";
    btnVoiceNote.style.display = "none";
  }

  // Remove Attachment
  btnRemoveAttachment.addEventListener("click", () => {
    clearAttachmentPreview();
  });

  function clearAttachmentPreview() {
    attachedFile = null;
    attachedDoc = null;
    presetMediaPath = null;
    attachmentPreviewCard.classList.remove("active");
    previewMediaBox.innerHTML = "";
    updateSenderModeUI();

    if (chatInput.value.trim().length === 0) {
      btnSend.style.display = "none";
      btnVoiceNote.style.display = "flex";
    }
  }

  // Drag and Drop Handling
  chatWindow.addEventListener("dragover", (e) => {
    e.preventDefault();
    dragDropOverlay.classList.add("active");
  });

  dragDropOverlay.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragDropOverlay.classList.remove("active");
  });

  dragDropOverlay.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDropOverlay.classList.remove("active");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const dropped = e.dataTransfer.files[0];
      if (dropped.type.startsWith("image/")) {
        handleFileSelected(dropped, "image");
      } else {
        handleFileSelected(dropped, "doc");
      }
    }
  });

  // ==============================================================================
  // 5. EMOJI PICKER DRAWER LOGIC
  // ==============================================================================
  const EMOJI_CATEGORIES = {
    smileys: ["😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇","🙂","🙃","😉","😌","😍","🥰","😘","😗","😙","😚","😋","😛","😜","🤪","😝","🤑","🤗","🤭","🤫","🤔","🤐","🤨","😐","😑","😶","😏","😒","🙄","😬","🤥","😌","😔","😪","🤤","😴","😷","🤒","🤕","🤢","🤮","🤧","🥵","🥶","🥴","😵","🤯","🤠","🥳","😎","🤓","🧐"],
    gestures: ["👋","🤚","🖐️","✋","🖖","👌","🤌","🤏","✌️","🤞","🤟","🤘","🤙","👈","👉","👆","🖕","👇","☝️","👍","👎","✊","👊","🤛","🤜","👏","🙌","👐","🤲","🤝","🙏","✍️","💪"],
    slang: ["💊","🌿","❄️","🍬","💉","📦","📍","💳","💸","💰","⚠️","🚨","🔒","🔑","📱","🚚","💨","🧊","🔥","✨","👀"],
    food: ["🍏","🍎","🍐","🍊","🍋","🍌","🍉","🍇","🍓","🫐","🍈","🍒","🍑","🥭","🍍","🥥","🥝","🍅","🥑","🍕","🍔","🍟","🌭","🍿","🧈","🥞","🧇","🥓","🥩"],
    activities: ["⚽","🏀","🏈","⚾","🥎","🎾","🏐","🏉","🎱","🏓","🏸","🥅","🥊","🥋","⛳","🎯","🎮","🎲","🧩"],
    symbols: ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❣️","💕","💞","💓","💗","💖","💘","💝","💟","☮️","✝️","☪️","🕉️","☸️","✡️","🔯","🕎","☯️","☦️"]
  };

  btnEmoji.addEventListener("click", (e) => {
    e.stopPropagation();
    emojiDrawer.classList.toggle("active");
    if (emojiDrawer.classList.contains("active")) {
      renderEmojis("smileys");
    }
  });

  document.addEventListener("click", (e) => {
    if (!emojiDrawer.contains(e.target) && e.target !== btnEmoji) {
      emojiDrawer.classList.remove("active");
    }
  });

  // Category switching
  document.querySelectorAll(".emoji-cat-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".emoji-cat-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderEmojis(btn.dataset.cat);
    });
  });

  // Render Emojis into Grid
  function renderEmojis(category, searchQuery = "") {
    emojiGrid.innerHTML = "";
    let emojis = [];

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      // Gather all categories
      Object.values(EMOJI_CATEGORIES).forEach(arr => {
        emojis.push(...arr);
      });
      emojis = [...new Set(emojis)];
    } else {
      emojis = EMOJI_CATEGORIES[category] || EMOJI_CATEGORIES.smileys;
    }

    emojis.forEach(emo => {
      const span = document.createElement("span");
      span.className = "emoji-item";
      span.textContent = emo;
      span.addEventListener("click", () => {
        insertEmojiAtCursor(emo);
      });
      emojiGrid.appendChild(span);
    });
  }

  // Live cursor insertion
  function insertEmojiAtCursor(emoji) {
    const input = chatInput;
    const start = input.selectionStart || input.value.length;
    const end = input.selectionEnd || input.value.length;
    const text = input.value;

    input.value = text.substring(0, start) + emoji + text.substring(end);
    const newPos = start + emoji.length;
    input.selectionStart = newPos;
    input.selectionEnd = newPos;
    input.focus();
    input.dispatchEvent(new Event("input"));
  }

  // Emoji Search Input
  emojiSearchInput.addEventListener("input", (e) => {
    renderEmojis("smileys", e.target.value.trim());
  });

  // ==============================================================================
  // 6. VOICE NOTE RECORDING (BROWSER MEDIARECORDER API)
  // ==============================================================================
  btnVoiceNote.addEventListener("click", async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error("Voice recording is unavailable in this browser.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      startMediaRecording(stream);
    } catch (err) {
      alert(err.message || "Microphone access was not granted.");
    }
  });

  function startMediaRecording(stream) {
    audioChunks = [];
    try {
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.start();
    } catch (e) {
      stream.getTracks().forEach(track => track.stop());
      alert("Voice recording could not be started in this browser.");
      return;
    }
    enterRecordingUI();
  }

  function enterRecordingUI() {
    footerNormalRow.style.display = "none";
    recordingBar.style.display = "flex";
    recordSeconds = 0;
    recordingTimer.textContent = "0:00";

    recordTimerInterval = setInterval(() => {
      recordSeconds++;
      const mins = Math.floor(recordSeconds / 60);
      const secs = String(recordSeconds % 60).padStart(2, "0");
      recordingTimer.textContent = `${mins}:${secs}`;
    }, 1000);
  }

  function exitRecordingUI() {
    clearInterval(recordTimerInterval);
    recordingBar.style.display = "none";
    footerNormalRow.style.display = "flex";
    btnSend.style.display = "none";
    btnVoiceNote.style.display = "flex";
  }

  // Cancel Recording
  btnCancelRecording.addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach(t => t.stop());
    }
    audioChunks = [];
    exitRecordingUI();
  });

  // Send Voice Note
  btnSendRecording.addEventListener("click", () => {
    const finalDuration = recordingTimer.textContent;

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        await dispatchVoiceNote(audioBlob, finalDuration);
        mediaRecorder.stream.getTracks().forEach(t => t.stop());
      };
      mediaRecorder.stop();
    } else {
      alert("There is no recorded audio to send.");
    }
    exitRecordingUI();
  });

  async function dispatchVoiceNote(audioBlob, durationStr) {
    if (!audioBlob || !audioBlob.size) return;
    playAudioClick();
    const timeStr = getFormattedTime();
    const messageId = crypto.randomUUID ? crypto.randomUUID() : `voice_${Date.now()}`;
    let analysisResult;
    try {
      analysisResult = await window.SimulatorAPI.ingestMessage({
        message_id: messageId,
        chat_id: currentContact.chat_id || currentContact.id,
        participant_id: currentContact.sender_id || currentContact.id,
        sender_id: isYouMode ? `analyst:${currentContact.id}` : currentContact.sender_id,
        sender_name: isYouMode ? "You" : currentContact.sender_name,
        recipient_name: currentContact.name,
        is_analyst: isYouMode,
        timestamp: new Date().toISOString(),
        message_body: "",
        simulated_locality: currentSimulatedLocality(),
        file: new File([audioBlob], `voice-note-${messageId}.webm`, { type: audioBlob.type || "audio/webm" })
      });
    } catch (error) {
      alert(`Voice note was not sent because backend analysis failed: ${error.message || "API unavailable"}`);
      return;
    }
    window.SimulatorAPI.showAnalysisResult(analysisResult);
    const localMediaId = await window.WhatsAppLocalStore.saveAttachment(audioBlob);
    const voiceUrl = URL.createObjectURL(audioBlob);

    const msgObj = {
      id: messageId,
      is_analyst: isYouMode,
      sender_id: isYouMode ? "+91 99999 00000" : currentContact.sender_id,
      sender_name: isYouMode ? "You" : currentContact.sender_name,
      is_voice: true,
      has_media: true,
      duration: durationStr || "0:04",
      voice_url: voiceUrl,
      local_media_url: voiceUrl,
      local_media_id: localMediaId,
      timestamp: timeStr,
      status: "sent",
      analysis_case_id: analysisResult.case_id || null,
      analysis_review_required: Boolean(analysisResult.review_required)
    };

    chatHistories[currentContact.id].push(msgObj);
    persistLocalState();
    renderMessages();
    renderContacts();
  }

  // ==============================================================================
  // 7. NEW GROUP MODAL LOGIC
  // ==============================================================================
  menuNewGroup.addEventListener("click", () => {
    openNewGroupModal();
  });

  function openNewGroupModal() {
    modalNewGroup.classList.add("active");
    groupSubjectInput.value = "";
    groupCharCounter.textContent = "25";
    selectedGroupChips.innerHTML = "";
    groupContactsList.innerHTML = "";

    // Populate contacts with checkboxes
    const individualContacts = ContactsData.CONTACTS.filter(c => !c.isGroup);
    individualContacts.forEach(contact => {
      const row = document.createElement("div");
      row.className = "modal-contact-row";
      row.innerHTML = `
        <div class="modal-contact-info">
          <div class="avatar-container" style="width: 36px; height: 36px;">
            <img src="${contact.avatar}" alt="${contact.name}">
          </div>
          <div>
            <div style="font-size: 14.5px; font-weight: 500;">${escapeHtml(contact.name)}</div>
            <div style="font-size: 12px; color: var(--text-secondary);">${contact.phone || contact.status}</div>
          </div>
        </div>
        <input type="checkbox" class="modal-contact-checkbox" value="${contact.id}" data-name="${escapeHtml(contact.name)}">
      `;

      row.addEventListener("click", (e) => {
        if (e.target.tagName !== "INPUT") {
          const cb = row.querySelector(".modal-contact-checkbox");
          cb.checked = !cb.checked;
          cb.dispatchEvent(new Event("change"));
        }
      });

      const cb = row.querySelector(".modal-contact-checkbox");
      cb.addEventListener("change", () => {
        updateGroupSelectedChips();
      });

      groupContactsList.appendChild(row);
    });
  }

  function updateGroupSelectedChips() {
    selectedGroupChips.innerHTML = "";
    const checked = groupContactsList.querySelectorAll(".modal-contact-checkbox:checked");
    checked.forEach(cb => {
      const chip = document.createElement("span");
      chip.className = "contact-chip";
      chip.innerHTML = `
        <span>${cb.dataset.name}</span>
        <span class="contact-chip-remove" data-id="${cb.value}">×</span>
      `;
      chip.querySelector(".contact-chip-remove").addEventListener("click", () => {
        cb.checked = false;
        updateGroupSelectedChips();
      });
      selectedGroupChips.appendChild(chip);
    });
  }

  groupSubjectInput.addEventListener("input", (e) => {
    groupCharCounter.textContent = 25 - e.target.value.length;
  });

  btnCloseGroupModal.addEventListener("click", () => {
    modalNewGroup.classList.remove("active");
  });

  // Create Group Submit
  btnCreateGroupSubmit.addEventListener("click", () => {
    const subject = groupSubjectInput.value.trim() || "New Discussion Group";
    const selectedBoxes = groupContactsList.querySelectorAll(".modal-contact-checkbox:checked");
    const memberNames = Array.from(selectedBoxes).map(cb => cb.dataset.name);

    if (memberNames.length === 0) {
      memberNames.push("Aryan Kapoor", "Priya Sharma");
    }

    const newGroupId = `group_${Date.now()}`;
    const newGroup = {
      id: newGroupId,
      chat_id: `${newGroupId}@g.us`,
      name: subject,
      simulated_locality: document.getElementById("groupSimulatedLocality").value,
      isGroup: true,
      sender_id: "+91 99999 00000",
      sender_name: "You",
      avatar: "assets/avatars/group.svg",
      status: memberNames.join(", "),
      unread: 0,
      lastSeen: `${memberNames.length + 1} participants`,
      defaultMessages: [
        {
          id: `sys_${Date.now()}`,
          is_system: true,
          text: `You created group "${subject}" with ${memberNames.join(", ")}`,
          timestamp: getFormattedTime()
        }
      ]
    };

    // Prepend to contacts and select
    ContactsData.CONTACTS.unshift(newGroup);
    chatHistories[newGroupId] = [...newGroup.defaultMessages];
    modalNewGroup.classList.remove("active");
    selectContact(newGroup);
  });

  // ==============================================================================
  // 8. NEW CHAT MODAL LOGIC
  // ==============================================================================
  btnNewChat.addEventListener("click", () => {
    openNewChatModal();
  });
  menuNewChatOption.addEventListener("click", () => {
    openNewChatModal();
  });

  function openNewChatModal() {
    modalNewChat.classList.add("active");
    newChatName.value = "";
    newChatPhone.value = "";
    newChatName.focus();
  }

  btnCloseChatModal.addEventListener("click", () => {
    modalNewChat.classList.remove("active");
  });

  btnCreateChatSubmit.addEventListener("click", () => {
    const name = newChatName.value.trim() || "New Contact";
    const phone = newChatPhone.value.trim() || "+91 98000 00000";

    const newChatId = `chat_${Date.now()}`;
    const newContact = {
      id: newChatId,
      chat_id: `${phone.replace(/[^0-9]/g, "")}@c.us`,
      name: name,
      isGroup: false,
      sender_id: phone,
      sender_name: name,
      phone: phone,
      avatar: "assets/avatars/user1.svg",
      status: "Hey there! I am using WhatsApp.",
      simulated_locality: document.getElementById("newChatLocality").value,
      unread: 0,
      lastSeen: "online",
      defaultMessages: []
    };

    ContactsData.CONTACTS.unshift(newContact);
    chatHistories[newChatId] = [];
    modalNewChat.classList.remove("active");
    selectContact(newContact);
  });

  // ==============================================================================
  // 9. INTERACTIVE POLL MODAL LOGIC
  // ==============================================================================
  btnAttachPoll.addEventListener("click", () => {
    attachmentPopup.classList.remove("active");
    modalPoll.classList.add("active");
    pollQuestion.value = "";
    pollQuestion.focus();
  });

  btnClosePollModal.addEventListener("click", () => {
    modalPoll.classList.remove("active");
  });

  btnAddPollOption.addEventListener("click", () => {
    const count = pollOptionsContainer.querySelectorAll(".poll-option-input").length + 1;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "poll-option-input";
    input.placeholder = `Option ${count}`;
    pollOptionsContainer.appendChild(input);
  });

  btnSubmitPoll.addEventListener("click", () => {
    const qText = pollQuestion.value.trim() || "Which meeting venue do you prefer?";
    const optionInputs = pollOptionsContainer.querySelectorAll(".poll-option-input");
    const options = [];

    optionInputs.forEach(inp => {
      const val = inp.value.trim();
      if (val) {
        options.push({ text: val, votes: 0, selected: false });
      }
    });

    if (options.length === 0) {
      options.push({ text: "Option A", votes: 0 }, { text: "Option B", votes: 0 });
    }

    const pollMsg = {
      id: `poll_${Date.now()}`,
      is_analyst: isYouMode,
      sender_id: isYouMode ? "+91 99999 00000" : currentContact.sender_id,
      sender_name: isYouMode ? "You" : currentContact.sender_name,
      is_poll: true,
      question: qText,
      options: options,
      multiple: pollMultipleAnswers.checked,
      timestamp: getFormattedTime(),
      status: "sent"
    };

    chatHistories[currentContact.id].push(pollMsg);
    persistLocalState();
    renderMessages();
    renderContacts();
    modalPoll.classList.remove("active");
    playAudioClick();

  });

  // ==============================================================================
  // 10. SEND MESSAGE CONTROLLER
  // ==============================================================================
  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text && !attachedFile && !attachedDoc && !presetMediaPath) return;

    playAudioClick();
    const timeStr = getFormattedTime();
    const isOutgoing = isYouMode;

    const fileToUpload = attachedFile || attachedDoc;
    const presetToUpload = presetMediaPath;

    const isDoc = Boolean(attachedDoc);
    const docName = attachedDoc ? attachedDoc.name : null;
    const docSize = attachedDoc ? formatBytes(attachedDoc.size) : null;
    const messageId = crypto.randomUUID ? crypto.randomUUID() : `msg_${Date.now()}`;
    let analysisResult;
    try {
      analysisResult = await window.SimulatorAPI.ingestMessage({
        message_id: messageId,
        chat_id: currentContact.chat_id || currentContact.id,
        participant_id: currentContact.sender_id || currentContact.id,
        sender_id: isOutgoing ? `analyst:${currentContact.id}` : currentContact.sender_id,
        sender_name: isOutgoing ? "You" : currentContact.sender_name,
        recipient_name: currentContact.name,
        is_analyst: isOutgoing,
        timestamp: new Date().toISOString(),
        message_body: text,
        simulated_locality: currentSimulatedLocality(),
        file: fileToUpload,
        preset_media_path: presetToUpload
      });
    } catch (error) {
      alert(`Message was not sent because backend analysis failed: ${error.message || "API unavailable"}`);
      return;
    }
    window.SimulatorAPI.showAnalysisResult(analysisResult);
    const localMediaId = fileToUpload ? await window.WhatsAppLocalStore.saveAttachment(fileToUpload) : null;
    const localMediaUrl = fileToUpload ? URL.createObjectURL(fileToUpload) : (presetToUpload ? `/${presetToUpload}` : null);

    const msgObj = {
      id: messageId,
      is_analyst: isOutgoing,
      sender_id: isOutgoing ? "+91 99999 00000" : currentContact.sender_id,
      sender_name: isOutgoing ? "You" : currentContact.sender_name,
      text: text,
      has_media: Boolean(fileToUpload || presetToUpload),
      is_doc: isDoc,
      doc_name: docName,
      doc_size: docSize,
      media_path: null,
      local_media_url: localMediaUrl,
      local_media_id: localMediaId,
      timestamp: timeStr,
      status: "sent",
      analysis_case_id: analysisResult.case_id || null,
      analysis_review_required: Boolean(analysisResult.review_required)
    };

    // Update Chat UI
    chatHistories[currentContact.id].push(msgObj);

    // Check if Smart Bot honeypot was triggered on threshold reach
    const botText = (analysisResult && (analysisResult.bot_response || (analysisResult.smart_bot && analysisResult.smart_bot.dispatched_message))) || null;
    if (botText) {
      setTimeout(() => {
        const botMsg = {
          id: `msg_buyer_${Date.now()}`,
          is_analyst: true, // Right-aligned outgoing buyer persona
          sender_id: "+91 99999 00000",
          sender_name: "You",
          text: botText,
          has_media: false,
          timestamp: getFormattedTime(),
          status: "read",
          is_honeypot: true
        };
        chatHistories[currentContact.id].push(botMsg);
        persistLocalState();
        renderMessages();
        renderContacts();
        playAudioClick();
      }, 700);
    }

    persistLocalState();
    renderMessages();
    renderContacts();

    // Reset input fields
    chatInput.value = "";
    clearAttachmentPreview();

  }

  btnSend.addEventListener("click", sendMessage);

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Sidebar 3-dots Menu
  btnSidebarMenu.addEventListener("click", (e) => {
    e.stopPropagation();
    sidebarMenu.classList.toggle("active");
  });

  menuToggleTheme.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const nextTheme = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", nextTheme);
    localStorage.setItem("wa_theme", nextTheme);
  });

  menuToggleSender.addEventListener("click", () => {
    toggleSenderMode();
  });

  // Load Saved Theme
  const savedTheme = localStorage.getItem("wa_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);

  // Lightbox Modal
  window.openImageModal = function (src, caption) {
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("modalImg");
    const modalCaption = document.getElementById("modalCaption");
    modalImg.src = src;
    modalCaption.textContent = caption || "";
    modal.classList.add("active");
  };

  document.getElementById("btnCloseModal").addEventListener("click", () => {
    document.getElementById("imageModal").classList.remove("active");
  });

  // Search in Chat List
  document.getElementById("searchChatInput").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll(".chat-item").forEach(item => {
      const name = item.querySelector(".chat-item-name").textContent.toLowerCase();
      item.style.display = name.includes(q) ? "flex" : "none";
    });
  });

  // Initialize First Contact
  selectContact(currentContact);
});
