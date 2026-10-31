/**
 * DrugShield AI - WhatsApp Simulation Service & Real-Time Event Publisher
 * =======================================================================
 * Local simulation UI service bound to loopback on port 8090 by default.
 * Decoupled from Telegram (Port 8000).
 * 
 * Capabilities:
 * 1. Real-time Live Message Ingestion & Streaming (SSE /api/stream)
 * 2. Automated Raw Log Archiving: data/raw/whatsapp_live_<timestamp>.json
 * 3. Media Asset Archiving: data/raw/images/
 * 4. Model Training Dataset Builder: data/raw/training_dataset.jsonl
 * 5. Local-only same-origin UI API
 * 6. Interactive Command Center Dashboard endpoint (/dashboard)
 */

const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const os = require('os');

const app = express();
const SERVER_BOOT_TIME = Date.now();

// ------------------------------------------------------------------------------
// 1. Resolve Data Paths Robustly
// ------------------------------------------------------------------------------
const candidateRoots = [
  path.resolve(__dirname, '..', '..'), // Workspace root when stored under simulations/<channel>
  path.resolve(__dirname, '..'), // Workspace root
  process.cwd(),
  __dirname
];

let projectRoot = candidateRoots.find(p => fs.existsSync(path.join(p, 'data', 'raw'))) || candidateRoots[0];

// Load environment configuration: prioritize local .env then root .env
const localEnvPath = path.join(__dirname, '.env');
const rootEnvPath = path.join(projectRoot, '.env');
const dotenvPath = fs.existsSync(localEnvPath) ? localEnvPath : rootEnvPath;

if (fs.existsSync(dotenvPath)) {
  const envContent = fs.readFileSync(dotenvPath, 'utf-8');
  for (const line of envContent.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#')) {
      const idx = trimmed.indexOf('=');
      if (idx !== -1) {
        const key = trimmed.slice(0, idx).trim();
        const value = trimmed.slice(idx + 1).trim().replace(/^['"](.*)['"]$/, '$1');
        if (!process.env[key]) {
          process.env[key] = value;
        }
      }
    }
  }
}

// Strictly Port 8090 for WhatsApp Simulation
const PORT = parseInt(process.env.WHATSAPP_PORT || process.env.PORT, 10) || 8090;
const HOST = '127.0.0.1';

const RAW_DIR = path.join(projectRoot, 'data', 'raw');
const IMAGES_DIR = path.join(RAW_DIR, 'images');
const TRAINING_DATASET_FILE = path.join(RAW_DIR, 'training_dataset.jsonl');
const MASTER_RAW_DATA_FILE = path.join(RAW_DIR, 'ingested_raw_data.json');
const SRC_DATA_FILE = path.join(projectRoot, 'src', 'data.json');

// Ensure target directories exist
fs.mkdirSync(RAW_DIR, { recursive: true });
fs.mkdirSync(IMAGES_DIR, { recursive: true });

console.log(`[WhatsApp Simulation Service] Project Root : ${projectRoot}`);
console.log(`[WhatsApp Simulation Service] Raw Storage  : ${RAW_DIR}`);
console.log(`[WhatsApp Simulation Service] Media Target : ${IMAGES_DIR}`);
console.log(`[WhatsApp Simulation Service] Training Set : ${TRAINING_DATASET_FILE}`);

// ------------------------------------------------------------------------------
// 2. Local-only middleware; cross-origin access is not enabled on the UI service.
// ------------------------------------------------------------------------------
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// ------------------------------------------------------------------------------
// 3. Multer File Upload Configuration
// ------------------------------------------------------------------------------
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    cb(null, IMAGES_DIR);
  },
  filename: function (req, file, cb) {
    const ext = path.extname(file.originalname) || '.png';
    const cleanBase = path.basename(file.originalname, ext).replace(/[^a-zA-Z0-9_-]/g, '_');
    const uniqueFilename = `wa_img_${Date.now()}_${cleanBase}${ext}`;
    cb(null, uniqueFilename);
  }
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 30 * 1024 * 1024 }
});

// ------------------------------------------------------------------------------
// 4. Live Threat Taxonomy & Classifier (Synchronous Pre-evaluation)
// ------------------------------------------------------------------------------
const NARCOTICS_TERMS = new Set([
  // Cannabis
  "weed", "marijuana", "ganja", "cannabis", "charas", "hash", "hashish", "pot",
  "bhang", "mary jane", "joint", "blunt", "bud", "buds", "thc", "cbd", "shatter",
  "wax", "skunk", "og kush", "hydro", "malana cream", "indica", "sativa", "dabs",
  "greens", "maal", "stuff",
  // Opioids
  "heroin", "chitta", "smack", "brown sugar", "morphine", "fentanyl", "tramadol",
  "codeine", "oxycodone", "oxycontin", "methadone", "buprenorphine", "opium", "afeem", "doda",
  // Stimulants
  "cocaine", "coke", "blow", "snow", "crack", "mephedrone", "m-cat", "meow meow",
  "mdma", "molly", "ecstasy", "xtc", "meth", "methamphetamine", "crystal meth",
  "ice", "speed", "amphetamine", "m-kat", "white sugar",
  // Psychedelics
  "lsd", "acid", "blotter", "blotters", "stamp", "stamps", "magic mushroom", "shrooms",
  "psilocybin", "dmt", "ayahuasca", "mescaline", "2c-b", "nbome", "ketamine", "special k", "k-hole",
  // Sedatives
  "alprazolam", "xanax", "valium", "diazepam", "clonazepam", "ativan", "lorazepam",
  "zolpidem", "nitrazepam", "rohypnol", "roofies", "lean", "purple drank", "cough syrup"
]);

const SOLICITATION_TERMS = new Set([
  "score", "stash", "plug", "dealer", "vendor", "supplies", "stuff", "delivery",
  "direct delivery", "drop", "dead drop", "drop pin", "drop point", "gps pin",
  "pin drop", "token", "token amount", "advance", "stock", "fresh stock", "pure",
  "pure stuff", "hq", "pure quality", "rates", "rate list", "price list", "menu",
  "stealth", "vacuum sealed", "1g", "2g", "3g", "5g", "10g", "gram", "grams",
  "pills", "tabs", "capsules", "sheet", "packet", "pouch", "upi accepted",
  "crypto only", "cash on drop", "dm to buy", "dm for order", "contact plug"
]);

const BENIGN_EXCLUSIONS = [
  "ice cream", "green tea", "ice water", "dry ice", "amino acid", "citric acid",
  "folic acid", "tea pot", "flower pot", "cooking pot", "jackpot"
];

const REGEX_UPI = /[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{3,64}/g;
const REGEX_IFSC = /\b[A-Z]{4}0[A-Z0-9]{6}\b/g;
const REGEX_BANK_ACC = /\b(?:acc(?:ount)?|a\/c|acct)?[:\s-]*(\d{9,18})\b/gi;
const REGEX_GEO = /[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|[1-9]?\d)(?:\.\d+)?)/g;
const REGEX_PHONE = /(?:\+?91[\-\s]?)?[6-9]\d{9}/g;

function analyzeThreatEntities(text, hasMedia, mediaFilename) {
  if (!text && !hasMedia) {
    return {
      isFlagged: false,
      threatScore: 0.05,
      reasons: [],
      entities: { upi_ids: [], bank_accounts: [], ifsc_codes: [], phone_numbers: [], narcotics_detected: [] }
    };
  }

  const clean = (text || "").toLowerCase();

  // Check benign exclusions
  for (const benign of BENIGN_EXCLUSIONS) {
    if (clean.includes(benign)) {
      return {
        isFlagged: false,
        threatScore: 0.05,
        reasons: [],
        entities: { upi_ids: [], bank_accounts: [], ifsc_codes: [], phone_numbers: [], narcotics_detected: [] }
      };
    }
  }

  const detectedDrugs = [];
  const detectedSol = [];

  for (const drug of NARCOTICS_TERMS) {
    const pattern = new RegExp(`\\b${drug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
    if (pattern.test(clean)) detectedDrugs.push(drug);
  }

  for (const sol of SOLICITATION_TERMS) {
    const pattern = new RegExp(`\\b${sol.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
    if (pattern.test(clean)) detectedSol.push(sol);
  }

  const upis = [...new Set(clean.match(REGEX_UPI) || [])];
  const ifscs = [...new Set((text || "").match(REGEX_IFSC) || [])];
  const geos = [...new Set(clean.match(REGEX_GEO) || [])];
  const phones = [...new Set((text || "").match(REGEX_PHONE) || [])];

  const banks = [];
  let bm;
  const bankRe = new RegExp(REGEX_BANK_ACC.source, 'gi');
  while ((bm = bankRe.exec(text || "")) !== null) {
    if (bm[1] && !upis.some(u => u.includes(bm[1]))) banks.push(bm[1]);
  }

  let mediaThreat = false;
  if (hasMedia && mediaFilename) {
    const fn = mediaFilename.toLowerCase();
    if (fn.includes("qr") || fn.includes("menu") || fn.includes("price") || fn.includes("stamp") || fn.includes("upi")) {
      mediaThreat = true;
    }
  }

  // Calculate dynamic threat score
  let score = 0.05;
  if (detectedDrugs.length > 0) score += 0.45 + Math.min(0.25, (detectedDrugs.length - 1) * 0.1);
  if (detectedSol.length > 0) score += 0.20 + Math.min(0.15, (detectedSol.length - 1) * 0.05);
  if (upis.length > 0 || banks.length > 0) score += 0.15;
  if (geos.length > 0) score += 0.10;
  if (mediaThreat) score += 0.15;

  score = Math.min(0.99, parseFloat(score.toFixed(2)));
  const isFlagged = score >= 0.60 || detectedDrugs.length > 0;

  const reasons = [];
  if (detectedDrugs.length) reasons.push(`Narcotics: [${detectedDrugs.join(', ')}]`);
  if (detectedSol.length) reasons.push(`Solicitation: [${detectedSol.join(', ')}]`);
  if (upis.length) reasons.push(`UPI: [${upis.join(', ')}]`);
  if (banks.length) reasons.push(`Bank: [${banks.join(', ')}]`);
  if (geos.length) reasons.push(`GPS: [${geos.join(', ')}]`);
  if (mediaThreat) reasons.push(`Suspicious Attachment: [${mediaFilename}]`);

  return {
    isFlagged,
    threatScore: score,
    reasons,
    entities: {
      upi_ids: upis,
      bank_accounts: [...new Set(banks)],
      ifsc_codes: ifscs,
      phone_numbers: phones,
      gps_coordinates: geos,
      narcotics_detected: detectedDrugs
    }
  };
}

// ------------------------------------------------------------------------------
// 5. In-Memory Session & Live SSE Broadcaster
// ------------------------------------------------------------------------------
let sessionMessages = [];
const sseClients = new Set();

function broadcastLiveEvent(eventData) {
  const payload = `data: ${JSON.stringify(eventData)}\n\n`;
  for (const client of sseClients) {
    try {
      client.write(payload);
    } catch (e) {
      sseClients.delete(client);
    }
  }
}

/**
 * Appends a record to the centralized fine-tuning dataset:
 * data/raw/training_dataset.jsonl
 */
function appendToTrainingDataset(record) {
  try {
    const entry = {
      id: record.id || `live_msg_${Date.now()}`,
      platform: "whatsapp_simulation",
      timestamp: record.timestamp || new Date().toISOString(),
      message_text: record.message_text || record.message_body || "",
      flagged_status: Boolean(record.flagged_status !== undefined ? record.flagged_status : record.isFlagged),
      threat_score: record.threat_score || 0.05,
      extracted_entities: {
        upi_ids: record.extracted_entities?.upi_ids || [],
        bank_accounts: record.extracted_entities?.bank_accounts || []
      },
      media_path: record.media_path || null
    };

    const line = JSON.stringify(entry) + '\n';
    fs.appendFileSync(TRAINING_DATASET_FILE, line, 'utf-8');
  } catch (err) {
    console.error("[-] Failed appending to training_dataset.jsonl:", err.message);
  }
}

// ------------------------------------------------------------------------------
// 6. Routes: Ingestion, Streaming, and Archiving
// ------------------------------------------------------------------------------

/**
 * Primary Ingestion Route: /api/ingest
 * Processes live messages, saves raw JSON, updates training dataset, and streams via SSE
 */
function handleIngestion(req, res) {
  try {
    const body = req.body || {};
    const timestamp = body.timestamp || new Date().toISOString();
    const sender_id = body.sender_id || '+91 98765 43210';
    const chat_id = body.chat_id || 'chat_aryan';
    const message_body = body.message_body || body.message_text || body.text || '';
    const is_analyst = body.is_analyst === 'true' || body.is_analyst === true;
    const has_media = Boolean(req.file || body.has_media === 'true' || body.has_media === true || body.preset_media_path);

    const uploadedFilename = req.file ? req.file.filename : (body.preset_media_path ? path.basename(body.preset_media_path) : null);

    // Run active threat analysis
    const analysis = analyzeThreatEntities(message_body, has_media, uploadedFilename);

    let media_path = null;
    let local_media_url = null;

    if (req.file) {
      media_path = `data/raw/images/${req.file.filename}`;
      local_media_url = `/api/images/${req.file.filename}`;
    } else if (body.preset_media_path) {
      const presetFilename = path.basename(body.preset_media_path);
      const targetPath = path.join(IMAGES_DIR, presetFilename);
      const candidates = [
        path.join(__dirname, 'public', body.preset_media_path),
        path.join(__dirname, 'public', 'presets', presetFilename),
        path.join(IMAGES_DIR, presetFilename)
      ];
      const found = candidates.find(c => fs.existsSync(c));
      if (found && !fs.existsSync(targetPath)) {
        fs.copyFileSync(found, targetPath);
      }
      media_path = `data/raw/images/${presetFilename}`;
      local_media_url = `/api/images/${presetFilename}`;
    }

    const uniqueMsgId = `live_msg_${Date.now()}_${Math.floor(Math.random() * 9000 + 1000)}`;

    const payload = {
      id: uniqueMsgId,
      platform: "whatsapp_simulation",
      timestamp: timestamp,
      sender_id: sender_id,
      chat_id: chat_id,
      message_body: message_body,
      message_text: message_body,
      text_content: message_body,
      has_media: has_media,
      media_path: media_path,
      flagged_status: analysis.isFlagged,
      isFlagged: analysis.isFlagged,
      threat_score: analysis.threatScore,
      extracted_entities: analysis.entities,
      extracted_upi_or_bank: analysis.entities.upi_ids.length ? analysis.entities.upi_ids.join(', ') : "None detected",
      is_analyst: is_analyst,
      is_fallback_mock: false,
      flag_reasons: analysis.reasons
    };

    const sessionRecord = {
      ...payload,
      local_media_url: local_media_url
    };
    sessionMessages.push(sessionRecord);

    // 1. Raw JSON Log Archive: data/raw/whatsapp_live_<timestamp>.json
    const timestampSlug = Date.now();
    const logFileName = `whatsapp_live_${timestampSlug}.json`;
    const logFilePath = path.join(RAW_DIR, logFileName);
    fs.writeFileSync(logFilePath, JSON.stringify(payload, null, 4), 'utf-8');

    // 2. Centralized Model Training Dataset Builder
    appendToTrainingDataset(payload);

    // 3. Append to master ingested_raw_data.json
    let masterRecords = [];
    if (fs.existsSync(MASTER_RAW_DATA_FILE)) {
      try {
        masterRecords = JSON.parse(fs.readFileSync(MASTER_RAW_DATA_FILE, 'utf-8'));
        if (!Array.isArray(masterRecords)) masterRecords = [];
      } catch (e) { masterRecords = []; }
    }
    masterRecords.push(payload);
    fs.writeFileSync(MASTER_RAW_DATA_FILE, JSON.stringify(masterRecords, null, 4), 'utf-8');

    // 4. Real-time Live Event Streaming via SSE
    broadcastLiveEvent({
      event: "new_message",
      platform: "whatsapp_simulation",
      logFileName: logFileName,
      data: sessionRecord
    });

    console.log(`\n[WhatsApp Ingestion] 💬 Live Message Ingested:`);
    console.log(`    Chat ID      : ${chat_id}`);
    console.log(`    Sender       : ${sender_id} [${is_analyst ? 'ANALYST' : 'TARGET'}]`);
    console.log(`    Content      : "${message_body.slice(0, 70)}"`);
    console.log(`    Threat Score : ${analysis.threatScore} | Flagged: ${analysis.isFlagged}`);
    console.log(`    Archived     : data/raw/${logFileName}`);
    if (media_path) console.log(`    Media Asset  : ${media_path}`);

    return res.status(200).json({
      success: true,
      logFileName: logFileName,
      media_path: media_path,
      record: sessionRecord,
      flagged: analysis.isFlagged,
      threat_score: analysis.threatScore
    });

  } catch (error) {
    console.error("[-] WhatsApp Ingestion Error:", error);
    return res.status(500).json({ success: false, error: error.message });
  }
}

app.post('/api/ingest', upload.single('media_file'), handleIngestion);
app.post('/api/ingest/whatsapp', upload.single('media_file'), handleIngestion);

// ------------------------------------------------------------------------------
// 7. Live SSE Stream Route: /api/stream
// ------------------------------------------------------------------------------
app.get('/api/stream', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  // Send initial handshake
  res.write(`data: ${JSON.stringify({ event: "connected", platform: "whatsapp_simulation", port: PORT })}\n\n`);
  sseClients.add(res);

  req.on('close', () => {
    sseClients.delete(res);
  });
});

// ------------------------------------------------------------------------------
// 8. Telemetry, Status & Live Messages Routes
// ------------------------------------------------------------------------------
app.get('/api/status', (req, res) => {
  try {
    const rawFiles = fs.existsSync(RAW_DIR) ? fs.readdirSync(RAW_DIR) : [];
    const liveFiles = rawFiles.filter(f => f.startsWith('whatsapp_live_') && f.endsWith('.json'));
    const imgFiles = fs.existsSync(IMAGES_DIR) ? fs.readdirSync(IMAGES_DIR).filter(f => !f.startsWith('.')) : [];

    let datasetLines = 0;
    if (fs.existsSync(TRAINING_DATASET_FILE)) {
      try {
        datasetLines = fs.readFileSync(TRAINING_DATASET_FILE, 'utf-8').trim().split('\n').filter(Boolean).length;
      } catch (e) {}
    }

    return res.json({
      ok: true,
      service: "WhatsApp Simulation Service",
      server_boot_time: SERVER_BOOT_TIME,
      port: PORT,
      host: HOST,
      stats: {
        raw_storage_dir: "data/raw/",
        images_dir: "data/raw/images/",
        whatsapp_live_logs_count: liveFiles.length,
        evidence_images_count: imgFiles.length,
        training_dataset_lines: datasetLines,
        session_total_messages: sessionMessages.length,
        connected_sse_clients: sseClients.size
      }
    });
  } catch (error) {
    return res.status(500).json({ ok: false, error: error.message });
  }
});

app.get('/api/live-messages', (req, res) => {
  const limit = parseInt(req.query.limit, 10) || 50;
  return res.json({
    success: true,
    platform: "whatsapp_simulation",
    total: sessionMessages.length,
    messages: sessionMessages.slice(-limit)
  });
});

app.get('/api/history', (req, res) => {
  return res.json({ success: true, messages: sessionMessages });
});

app.post('/api/clear', (req, res) => {
  sessionMessages = [];
  return res.json({ success: true, server_boot_time: SERVER_BOOT_TIME, message: "WhatsApp session history reset." });
});

// Flush batch endpoint for backwards compatibility
app.post('/api/flush', (req, res) => {
  try {
    const allFiles = fs.readdirSync(RAW_DIR);
    const liveFiles = allFiles.filter(f => f.startsWith('whatsapp_live_') && f.endsWith('.json'));
    
    const records = [];
    for (const file of liveFiles) {
      try {
        const content = JSON.parse(fs.readFileSync(path.join(RAW_DIR, file), 'utf-8'));
        if (content && typeof content === 'object') records.push(content);
      } catch (e) {}
    }

    const batchFile = path.join(RAW_DIR, 'whatsapp_live_batch.json');
    fs.writeFileSync(batchFile, JSON.stringify(records, null, 4), 'utf-8');

    return res.status(200).json({
      success: true,
      total_logs: records.length,
      destination: "data/raw/whatsapp_live_batch.json"
    });
  } catch (error) {
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ------------------------------------------------------------------------------
// 9. Static Assets & Command Center Dashboard
// ------------------------------------------------------------------------------
app.use('/api/images', express.static(IMAGES_DIR));
app.use('/data/raw/images', express.static(IMAGES_DIR));
const commandCenterUrl = process.env.DRUGSHIELD_DASHBOARD_URL || process.env.DRUGSHIELD_API_URL || 'http://127.0.0.1:8000/';
app.get(['/dashboard', '/dashboard.html', '/command-center'], (req, res) => res.redirect(302, commandCenterUrl));
app.use(express.static(path.join(__dirname, 'public')));

// Fallback to index.html for SPA
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ------------------------------------------------------------------------------
// 10. Start local WhatsApp simulation UI
// ------------------------------------------------------------------------------
app.listen(PORT, HOST, () => {
  const lanIps = [];
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      if (iface.family === 'IPv4' && !iface.internal) {
        lanIps.push(iface.address);
      }
    }
  }

  console.log(`\n=============================================================`);
  console.log(` 💬 WHATSAPP WEB SIMULATION SERVICE (DECOUPLED - PORT 8090)`);
  console.log(`=============================================================`);
  console.log(` 🌐 Network Host     : ${HOST} (loopback only)`);
  console.log(` 🔌 Dedicated Port   : ${PORT} (Strictly WhatsApp, NOT 3000 or 8000)`);
  console.log(` 💻 Local UI URL     : http://localhost:${PORT}`);
  console.log(` 🛡️ Command Center   : http://localhost:${PORT}/dashboard`);
  console.log(` 📡 Real-time Stream : http://localhost:${PORT}/api/stream`);
  console.log(`=============================================================\n`);
});
