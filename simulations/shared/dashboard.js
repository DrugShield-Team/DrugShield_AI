(() => {
  const API_BASE = window.DRUGSHIELD_API_URL || "http://127.0.0.1:8000";
  const streamContainer = document.getElementById("streamContainer");
  const emptyState = document.getElementById("emptyState");
  let cases = [];
  let activeFilter = "all";
  let graphData = { nodes: [], edges: [] };
  const detailCache = new Map();

  const byId = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "");
  const reportOf = (item) => item.report || {};
  const summaryOf = (item) => reportOf(item).summary || item.summary || {};
  const channelOf = (item) => String(summaryOf(item).channel || "unknown").toLowerCase();
  const statusLabel = (status) => ({
    pending_review: "Pending review",
    further_review: "Further review",
    accepted: "Accepted",
    dismissed: "Dismissed",
  }[status] || status || "Unknown");

  async function getJson(path, options) {
    const response = await fetch(`${API_BASE}${path}`, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : body.detail?.error;
      throw new Error(detail || `Backend returned HTTP ${response.status}`);
    }
    return body;
  }

  function setConnection(connected, message) {
    const pill = byId("backendStatus");
    if (pill) {
      const dot = pill.querySelector(".pulse-dot");
      pill.replaceChildren(dot, document.createTextNode(connected ? "ANALYSIS API CONNECTED" : "ANALYSIS API OFFLINE"));
      pill.classList.toggle("offline", !connected);
      pill.title = message || "";
    }
    const apiInfo = byId("apiNodeInfo");
    if (apiInfo) apiInfo.textContent = connected ? "http://127.0.0.1:8000 | Healthy" : (message || "Backend API unavailable");
  }

  async function loadDashboard() {
    try {
      await getJson("/api/v1/health");
      setConnection(true, "Backend API is reachable");
      const [list, graph] = await Promise.all([
        getJson("/api/v1/cases?limit=100"),
        getJson("/api/v1/graph?limit=500"),
      ]);
      graphData = graph;
      const details = await Promise.all((list.cases || []).map(async (item) => {
        const cached = detailCache.get(item.case_id);
        if (cached) return { ...cached, status: item.status, created_at: item.created_at, summary: item.summary };
        try {
          const full = await getJson(`/api/v1/cases/${encodeURIComponent(item.case_id)}`);
          detailCache.set(item.case_id, full);
          return full;
        } catch (error) { return { ...item, detail_error: error.message }; }
      }));
      cases = details;
      renderMetrics();
      renderGraph();
      renderCases();
    } catch (error) {
      setConnection(false, error.message);
      cases = [];
      graphData = { nodes: [], edges: [] };
      renderMetrics();
      renderGraph();
      streamContainer.innerHTML = "";
      const state = document.createElement("div");
      state.className = "empty-state";
      const heading = document.createElement("h3");
      heading.textContent = "Backend API unavailable";
      const detail = document.createElement("p");
      detail.textContent = `${error.message}. Start the DrugShield backend, then refresh this dashboard.`;
      state.append(heading, detail);
      streamContainer.appendChild(state);
    }
  }

  function renderMetrics() {
    const pending = cases.filter((item) => item.status === "pending_review").length;
    const identifiers = new Set();
    for (const item of cases) {
      for (const candidate of reportOf(item).analysis?.vpa_candidates || []) {
        if (candidate.candidate) identifiers.add(String(candidate.candidate).toLowerCase());
      }
    }
    byId("kpiTotalMsgs").textContent = String(cases.length);
    byId("kpiFlaggedThreats").textContent = String(pending);
    byId("kpiEntitiesCount").textContent = String(identifiers.size);
    byId("kpiDatasetSize").textContent = String((graphData.nodes || []).length);
    const queue = byId("reviewQueueInfo");
    if (queue) queue.textContent = `${pending} case${pending === 1 ? "" : "s"} awaiting a human decision`;
  }

  function renderGraph() {
    const host = byId("evidenceGraph");
    if (!host) return;
    host.replaceChildren();
    const nodes = (graphData.nodes || []).slice(0, 36);
    const edges = (graphData.edges || []).filter((edge) => nodes.some((n) => n.id === edge.source) && nodes.some((n) => n.id === edge.target)).slice(0, 60);
    if (!nodes.length) {
      const message = document.createElement("p");
      message.className = "graph-empty";
      message.textContent = "No evidence network is available yet. A graph appears when a message reaches a human-review case.";
      host.appendChild(message);
      return;
    }
    const width = 1000;
    const height = 260;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Evidence graph of fictional participants, messages, attachments and candidate payment identifiers");
    const positions = new Map();
    const cols = Math.min(6, Math.max(1, Math.ceil(Math.sqrt(nodes.length * 1.7))));
    nodes.forEach((node, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);
      const rows = Math.ceil(nodes.length / cols);
      positions.set(node.id, {
        x: 80 + col * (width - 160) / Math.max(1, cols - 1),
        y: 45 + row * (height - 90) / Math.max(1, rows - 1),
      });
    });
    edges.forEach((edge) => {
      const start = positions.get(edge.source);
      const end = positions.get(edge.target);
      const line = document.createElementNS(svg.namespaceURI, "line");
      line.setAttribute("x1", start.x); line.setAttribute("y1", start.y);
      line.setAttribute("x2", end.x); line.setAttribute("y2", end.y);
      line.setAttribute("class", "graph-edge");
      svg.appendChild(line);
    });
    nodes.forEach((node) => {
      const point = positions.get(node.id);
      const group = document.createElementNS(svg.namespaceURI, "g");
      const circle = document.createElementNS(svg.namespaceURI, "circle");
      circle.setAttribute("cx", point.x); circle.setAttribute("cy", point.y); circle.setAttribute("r", "17");
      circle.setAttribute("class", `graph-node ${String(node.type || "").replace(/[^a-z_]/gi, "")}`);
      const title = document.createElementNS(svg.namespaceURI, "title");
      title.textContent = `${node.type || "evidence"}: ${node.label || node.id}`;
      circle.appendChild(title);
      const label = document.createElementNS(svg.namespaceURI, "text");
      label.setAttribute("x", point.x); label.setAttribute("y", point.y + 34);
      label.setAttribute("text-anchor", "middle");
      label.textContent = esc(node.label || node.type || node.id).slice(0, 22);
      group.append(circle, label);
      svg.appendChild(group);
    });
    host.appendChild(svg);
    const caption = document.createElement("p");
    caption.className = "graph-caption";
    caption.textContent = `${nodes.length} nodes · ${edges.length} links shown · graph is evidence linkage, not a real-world identity claim.`;
    host.appendChild(caption);
  }

  function addText(parent, tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = esc(value);
    parent.appendChild(element);
    return element;
  }

  function addChip(parent, value, className = "") {
    const chip = document.createElement("span");
    chip.className = `entity-tag ${className}`.trim();
    chip.textContent = esc(value);
    parent.appendChild(chip);
  }

  function renderCases() {
    const filtered = cases.filter((item) => {
      const channel = channelOf(item);
      if (activeFilter === "review") return ["pending_review", "further_review"].includes(item.status);
      if (["instagram", "whatsapp", "telegram"].includes(activeFilter)) return channel === activeFilter;
      return true;
    });
    streamContainer.replaceChildren();
    if (!filtered.length) {
      const state = emptyState.cloneNode(true);
      state.querySelector("h3").textContent = cases.length ? "No cases match this filter" : "No evidence cases yet";
      state.querySelector("p").textContent = cases.length
        ? "Choose another channel or review filter."
        : "Newly composed simulation messages that meet a review trigger will appear here with their evidence report.";
      streamContainer.appendChild(state);
      return;
    }
    filtered.forEach((item) => streamContainer.appendChild(createCaseCard(item)));
  }

  function createCaseCard(item) {
    const report = reportOf(item);
    const summary = summaryOf(item);
    const analysis = report.analysis || {};
    const card = document.createElement("article");
    card.className = "feed-card flagged-threat";
    const header = document.createElement("div");
    header.className = "feed-card-header";
    const left = document.createElement("div");
    left.className = "feed-platform-tag";
    addChip(left, String(summary.channel || "unknown").toUpperCase(), `channel-${channelOf(item)}`);
    addText(left, "span", "sender-handle", `${summary.sender_display_name || summary.sender_id || "Unknown sender"} → ${summary.recipient_display_name || summary.recipient_id || "Unknown recipient"}`);
    addText(left, "span", "msg-timestamp", new Date(item.created_at || summary.timestamp || Date.now()).toLocaleString());
    const badge = addText(header, "span", "threat-score-pill threat-critical", statusLabel(item.status));
    header.appendChild(left);
    header.appendChild(badge);
    card.appendChild(header);
    addText(card, "div", "feed-card-body", summary.message_text || "[Attachment-only message]");

    const reasons = report.review_policy?.reasons || [];
    if (reasons.length) {
      const signalRow = document.createElement("div");
      signalRow.className = "extracted-entities-tags";
      reasons.forEach((reason) => addChip(signalRow, `${reason.signal} · ${reason.source}${typeof reason.value === "number" ? ` (${reason.value.toFixed(2)})` : ""}`, "drug"));
      card.appendChild(signalRow);
    }

    const evidence = document.createElement("div");
    evidence.className = "extracted-entities-tags";
    (analysis.vpa_candidates || []).forEach((item) => addChip(evidence, `Candidate VPA: ${item.candidate}`, "upi"));
    (analysis.qr_scans || []).forEach((item) => {
      const count = (item.all_decoded_codes || []).length + (item.payload_raw ? 1 : 0);
      if (count) addChip(evidence, `QR payload decoded (${count})`, "upi");
    });
    (analysis.image_classification || []).forEach((item) => {
      const label = item.predicted_class || item.label || item.status || "Image analyzed";
      addChip(evidence, `Image: ${label}`, "bank");
    });
    if (evidence.childElementCount) card.appendChild(evidence);

    const attachments = report.attachments || [];
    if (attachments.length) {
      const attachmentRow = document.createElement("div");
      attachmentRow.className = "attachment-links";
      attachments.forEach((attachment) => {
        const url = `${API_BASE}/api/v1/cases/${encodeURIComponent(item.case_id)}/attachments/${encodeURIComponent(attachment.attachment_id)}`;
        const link = document.createElement("a");
        link.className = "media-preview-btn";
        link.href = url;
        link.textContent = `View ${attachment.filename || attachment.content_type || "attachment"}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        attachmentRow.appendChild(link);
      });
      card.appendChild(attachmentRow);
    }

    const footer = document.createElement("div");
    footer.className = "case-actions";
    const detail = document.createElement("details");
    const summaryToggle = document.createElement("summary");
    summaryToggle.textContent = "Open evidence report";
    detail.appendChild(summaryToggle);
    const reportBlock = document.createElement("pre");
    reportBlock.className = "report-json";
    reportBlock.textContent = JSON.stringify({
      analysis: report.analysis,
      review_policy: report.review_policy,
      graph: report.graph,
      integrity: report.integrity,
    }, null, 2);
    detail.appendChild(reportBlock);
    footer.appendChild(detail);
    if (!["accepted", "dismissed"].includes(item.status)) {
      [["accept", "Accept"], ["further_review", "Further review"], ["dismiss", "Dismiss"]].forEach(([action, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = action === "dismiss" ? "btn-secondary review-button" : "btn-action review-button";
        button.textContent = label;
        button.addEventListener("click", () => reviewCase(item.case_id, action));
        footer.appendChild(button);
      });
    }
    card.appendChild(footer);
    return card;
  }

  async function reviewCase(caseId, action) {
    const savedReviewer = localStorage.getItem("drugshield-dashboard-reviewer") || "";
    const reviewerId = window.prompt("Reviewer name or ID:", savedReviewer);
    if (!reviewerId?.trim()) return;
    localStorage.setItem("drugshield-dashboard-reviewer", reviewerId.trim());
    const note = window.prompt("Optional review note:", "") || "";
    try {
      await getJson(`/api/v1/cases/${encodeURIComponent(caseId)}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewer_id: reviewerId.trim(), action, note }),
      });
      detailCache.delete(caseId);
      await loadDashboard();
    } catch (error) {
      window.alert(`Review update failed: ${error.message}`);
    }
  }

  window.setFilter = (filter) => {
    activeFilter = filter;
    document.querySelectorAll(".tab-btn").forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === filter);
    });
    renderCases();
  };
  window.fetchRecentMessages = loadDashboard;

  window.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".tab-btn").forEach((button) => {
      button.addEventListener("click", () => window.setFilter(button.dataset.filter));
    });
    loadDashboard();
    window.setInterval(loadDashboard, 5000);
    connectDispatchWS();
  });

  function connectDispatchWS() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const nodeParam = urlParams.get("node") || urlParams.get("precinct_id") || "ALL";
      const wsUrl = `${API_BASE.replace(/^http/, "ws")}/api/v1/ws/dispatch?node=${encodeURIComponent(nodeParam)}`;
      const ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event === "POLICE_DISPATCH_ALERT" && payload.is_primary && payload.data) {
            showDispatchToast(payload.data);
          }
        } catch (e) {}
      };
      ws.onclose = () => { setTimeout(connectDispatchWS, 5000); };
    } catch (e) {}
  }

  function showDispatchToast(data) {
    const assigned = data.assigned_precinct || {};
    const coords = data.target_coordinates || {};
    const msg = `🚨 POLICE DISPATCH: ${assigned.name || 'Precinct'}\n` +
      `Target Coords: ${coords.latitude?.toFixed(4)}, ${coords.longitude?.toFixed(4)}\n` +
      `Distance: ${assigned.distance_km} km | ETA: ~${assigned.estimated_eta_minutes} mins`;
    console.warn("[DRUGSHIELD DISPATCH ALERT]", msg);
    
    let toast = document.getElementById("drugshield-dispatch-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "drugshield-dispatch-toast";
      toast.style.cssText = "position:fixed;bottom:20px;right:20px;background:#7f1d1d;color:#fff;padding:16px 20px;border-radius:10px;border:2px solid #ef4444;box-shadow:0 8px 30px rgba(0,0,0,0.5);z-index:99999;font-family:sans-serif;max-width:400px;font-size:13px;line-height:1.4;";
      document.body.appendChild(toast);
    }
    toast.innerHTML = `<strong style="font-size:14px;color:#fca5a5;">🚨 POLICE DISPATCH ALERT</strong><br>` +
      `<strong>Precinct:</strong> ${assigned.name || 'Precinct North'}<br>` +
      `<strong>Target:</strong> ${coords.latitude?.toFixed(4)}, ${coords.longitude?.toFixed(4)} (${data.city || 'NCR'})<br>` +
      `<strong>Distance:</strong> <span style="color:#86efac;font-weight:700;">${assigned.distance_km} km</span> • ` +
      `<strong>ETA:</strong> <span style="color:#fde047;font-weight:700;">~${assigned.estimated_eta_minutes}m</span>`;
    toast.style.display = "block";
    setTimeout(() => { if (toast) toast.style.display = "none"; }, 10000);
  }
})();
