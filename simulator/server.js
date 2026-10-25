/**
 * DrugShield AI - WhatsApp Web Simulation Server & Passive Ingestion Crawler
 * =========================================================================
 * Background listener that passively monitors simulated chat streams in real-time,
 * analyzes content against narcotics/threat indicators, and implements DATA ISOLATION:
 * 
 * - FLAGGED MESSAGES (Narcotics slang, solicitation intent, UPI/Bank details, GPS):
 *     -> Persisted to `data/raw/whatsapp_simulated_<timestamp>.json`
 *     -> Media saved to `data/raw/images/`
 *     -> Appended to master `data/raw/ingested_raw_data.json`
 * 
 * - BENIGN MESSAGES (Standard everyday conversation, non-threat chatter):
 *     -> DISCARDED from raw threat storage
 *     -> Kept only in local UI session for authentic realism
 */

const express = require('express');
const cors = require('cors');
const multer = require('multer');
const path = require('path');
const fs = require('fs');

const app = express();

// Resolve Paths Robustly
const projectRoot = fs.existsSync(path.join(process.cwd(), 'data', 'raw'))
  ? process.cwd()
  : path.resolve(__dirname, '..');

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

const PORT = parseInt(process.env.WHATSAPP_PORT || process.env.PORT, 10) || 8090;
const HOST = process.env.HOST || '0.0.0.0';

const RAW_DIR = path.join(projectRoot, 'data', 'raw');
const IMAGES_DIR = path.join(RAW_DIR, 'images');
const MASTER_RAW_DATA_FILE = path.join(RAW_DIR, 'ingested_raw_data.json');
const SRC_DATA_FILE = path.join(projectRoot, 'src', 'data.json');

// Ensure target directories exist
fs.mkdirSync(RAW_DIR, { recursive: true });
fs.mkdirSync(IMAGES_DIR, { recursive: true });

console.log(`[Passive Ingestion Engine] Raw Landing Zone : ${RAW_DIR}`);
console.log(`[Passive Ingestion Engine] Media Landing Zone : ${IMAGES_DIR}`);
console.log(`[Data Isolation Policy]   Active: Only FLAGGED threats are persisted to raw logs.`);

// Middleware
app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Configure Multer for File Uploads
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
  limits: { fileSize: 25 * 1024 * 1024 }
});

// ==============================================================================
// PASSIVE CRAWLER & THREAT CLASSIFIER (TAXONOMY & REGEX ENGINE)
// ==============================================================================

// Narcotics terms matching config/constants.py
const NARCOTICS_TERMS = new Set([
  // Cannabis
  "weed", "marijuana", "ganja", "cannabis", "charas", "hash", "hashish", "pot",
  "bhang", "mary jane", "joint", "blunt", "bud", "buds", "thc", "cbd", "shatter",
  "wax", "skunk", "og kush", "hydro", "malana cream", "indica", "sativa", "dabs",
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

// Dealing & Solicitation Slang
const SOLICITATION_TERMS = new Set([
  "score", "stash", "plug", "dealer", "vendor", "supplies", "stuff", "delivery",
  "direct delivery", "drop", "dead drop", "drop pin", "drop point", "gps pin",
  "pin drop", "token", "token amount", "advance", "stock", "fresh stock", "pure",
  "pure stuff", "hq", "pure quality", "rates", "rate list", "price list", "menu",
  "stealth", "vacuum sealed", "1g", "2g", "3g", "5g", "10g", "gram", "grams",
  "pills", "tabs", "capsules", "sheet", "packet", "pouch", "upi accepted",
  "crypto only", "cash on drop", "dm to buy", "dm for order", "contact plug"
]);

// False positive exclusions (e.g., "ice cream", "green tea", "amino acid")
const BENIGN_EXCLUSIONS = [
  "ice cream", "green tea", "ice water", "dry ice", "amino acid", "citric acid",
  "folic acid", "tea pot", "flower pot", "cooking pot", "jackpot"
];

// Regex Patterns
const REGEX_UPI = /[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{3,64}/g;
const REGEX_IFSC = /\b[A-Z]{4}0[A-Z0-9]{6}\b/g;
const REGEX_BANK_ACC = /\b(?:acc(?:ount)?|a\/c|acct)?[:\s-]*(\d{9,18})\b/gi;
const REGEX_GEO = /[-+]?(?:[1-8]?\d(?:\.\d+)?|90(?:\.0+)?),\s*[-+]?(?:180(?:\.0+)?|(?:1[0-7]\d|[1-9]?\d)(?:\.\d+)?)/g;
const REGEX_PHONE = /(?:\+?91[\-\s]?)?[6-9]\d{9}/g;

/**
 * Passive Threat Classifier:
 * Analyzes incoming message text and attachments to determine if the message
 * should be flagged and preserved in raw OSINT logs or discarded as benign.
 */
function inspectAndClassifyMessage(text, hasMedia, mediaFilename) {
  if (!text && !hasMedia) {
    return { isFlagged: false, reasons: [], extractedFinancial: null };
  }

  const cleanText = (text || "").toLowerCase();
  
  // Check benign exclusions
  for (const benign of BENIGN_EXCLUSIONS) {
    if (cleanText.includes(benign)) {
      return { isFlagged: false, reasons: [], extractedFinancial: null };
    }
  }

  const detectedDrugs = [];
  const detectedSolicitation = [];
  const detectedFinancial = [];

  // 1. Scan for Narcotics terms (word boundary check)
  for (const drug of NARCOTICS_TERMS) {
    const pattern = new RegExp(`\\b${drug.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
    if (pattern.test(cleanText)) {
      detectedDrugs.push(drug);
    }
  }

  // 2. Scan for Solicitation terms
  for (const sol of SOLICITATION_TERMS) {
    const pattern = new RegExp(`\\b${sol.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
    if (pattern.test(cleanText)) {
      detectedSolicitation.push(sol);
    }
  }

  // 3. Scan for Financial Identifiers (UPI / Bank / IFSC / GPS)
  const upiMatches = cleanText.match(REGEX_UPI) || [];
  const ifscMatches = (text || "").match(REGEX_IFSC) || [];
  const geoMatches = cleanText.match(REGEX_GEO) || [];

  if (upiMatches.length > 0) {
    detectedFinancial.push(`UPI: ${[...new Set(upiMatches)].join(', ')}`);
  }
  if (ifscMatches.length > 0) {
    detectedFinancial.push(`IFSC: ${[...new Set(ifscMatches)].join(', ')}`);
  }
  if (geoMatches.length > 0) {
    detectedFinancial.push(`GPS: ${[...new Set(geoMatches)].join(', ')}`);
  }

  // 4. Media inspection hints (QR codes, menu files)
  let mediaThreat = false;
  if (hasMedia && mediaFilename) {
    const lowerFn = mediaFilename.toLowerCase();
    if (lowerFn.includes("qr") || lowerFn.includes("menu") || lowerFn.includes("price") || lowerFn.includes("stamp")) {
      mediaThreat = true;
    }
  }

  // Classification Decision Rules:
  // FLAGGED IF:
  // - Contains any narcotics substance term
  // - Contains solicitation slang + financial identifier
  // - Contains dead drop GPS coordinates
  // - Media contains suspected payment QR or narcotics rate list
  const isFlagged = (
    detectedDrugs.length > 0 ||
    (detectedSolicitation.length > 0 && detectedFinancial.length > 0) ||
    geoMatches.length > 0 ||
    mediaThreat
  );

  const reasons = [];
  if (detectedDrugs.length) reasons.push(`Narcotics: [${detectedDrugs.join(', ')}]`);
  if (detectedSolicitation.length) reasons.push(`Solicitation: [${detectedSolicitation.join(', ')}]`);
  if (detectedFinancial.length) reasons.push(`Financial/Location: [${detectedFinancial.join(', ')}]`);
  if (mediaThreat) reasons.push(`Suspicious Media: [${mediaFilename}]`);

  const extractedFinancial = detectedFinancial.length > 0 
    ? detectedFinancial.join(' | ') 
    : (detectedDrugs.length > 0 ? `Substance: ${detectedDrugs.join(', ')}` : null);

  return {
    isFlagged,
    reasons,
    detectedDrugs,
    detectedSolicitation,
    extractedFinancial: extractedFinancial || "None detected"
  };
}

// In-memory chat history for the current browser session
let sessionMessages = [];

// ==============================================================================
// 1. INGESTION ROUTE: /api/ingest (WITH PASSIVE CRAWLER & SELECTIVE LOGGING)
// ==============================================================================
app.post('/api/ingest', upload.single('media_file'), (req, res) => {
  try {
    const body = req.body || {};
    const timestamp = body.timestamp || new Date().toISOString();
    const sender_id = body.sender_id || '+91 98765 43210';
    const chat_id = body.chat_id || 'chat_aryan';
    const message_body = body.message_body || '';
    const has_media = Boolean(req.file || body.has_media === 'true' || body.has_media === true);

    const uploadedFilename = req.file ? req.file.filename : (body.preset_media_path ? path.basename(body.preset_media_path) : null);

    // 1. Run Passive Crawler Analysis on Message
    const analysis = inspectAndClassifyMessage(message_body, has_media, uploadedFilename);

    let media_path = null;
    let local_media_url = null;

    if (req.file) {
      if (analysis.isFlagged) {
        media_path = `data/raw/images/${req.file.filename}`;
      } else {
        // Data Isolation: If benign, remove from raw threat images directory to prevent pollution
        try {
          fs.unlinkSync(path.join(IMAGES_DIR, req.file.filename));
        } catch (e) {}
      }
      local_media_url = `/api/images/${req.file.filename}`;
    } else if (body.preset_media_path) {
      const presetFilename = path.basename(body.preset_media_path);
      const targetPath = path.join(IMAGES_DIR, presetFilename);
      const sourcePath = path.join(__dirname, 'public', body.preset_media_path);

      if (analysis.isFlagged) {
        if (fs.existsSync(sourcePath) && !fs.existsSync(targetPath)) {
          fs.copyFileSync(sourcePath, targetPath);
        }
        media_path = `data/raw/images/${presetFilename}`;
      }
      local_media_url = `/api/images/${presetFilename}`;
    }

    const payload = {
      platform: "whatsapp_simulation",
      timestamp: timestamp,
      sender_id: sender_id,
      chat_id: chat_id,
      message_body: message_body,
      has_media: has_media,
      media_path: media_path,
      extracted_upi_or_bank: analysis.extractedFinancial,
      text_content: message_body,
      message_text: message_body,
      is_fallback_mock: false,
      is_analyst: body.is_analyst === 'true' || body.is_analyst === true,
      flag_reasons: analysis.reasons
    };

    // Always keep session message so WhatsApp UI updates naturally
    const sessionRecord = {
      ...payload,
      id: `msg_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      local_media_url: local_media_url,
      isFlagged: analysis.isFlagged
    };
    sessionMessages.push(sessionRecord);

    // ==============================================================================
    // 2. DATA ISOLATION LOGIC:
    // Only persist to data/raw/ IF FLAGGED AS SUSPICIOUS!
    // Discard benign messages from raw threat logs.
    // ==============================================================================
    if (analysis.isFlagged) {
      const timestampSlug = Date.now();
      const logFileName = `whatsapp_simulated_${timestampSlug}.json`;
      const logFilePath = path.join(RAW_DIR, logFileName);

      fs.writeFileSync(logFilePath, JSON.stringify(payload, null, 4), 'utf-8');

      // Also append to master ingested_raw_data.json
      let masterRecords = [];
      if (fs.existsSync(MASTER_RAW_DATA_FILE)) {
        try {
          masterRecords = JSON.parse(fs.readFileSync(MASTER_RAW_DATA_FILE, 'utf-8'));
          if (!Array.isArray(masterRecords)) masterRecords = [];
        } catch (e) { masterRecords = []; }
      }
      masterRecords.push(payload);
      fs.writeFileSync(MASTER_RAW_DATA_FILE, JSON.stringify(masterRecords, null, 4), 'utf-8');

      console.log(`\n[Passive Crawler] 🚨 FLAGGED SUSPICIOUS MESSAGE:`);
      console.log(`    Chat ID   : ${chat_id}`);
      console.log(`    Sender    : ${sender_id}`);
      console.log(`    Message   : "${message_body}"`);
      console.log(`    Triggers  : ${analysis.reasons.join(' | ')}`);
      console.log(`    Raw Log   : data/raw/${logFileName}`);
      if (media_path) console.log(`    Media     : ${media_path}`);

      return res.status(200).json({
        success: true,
        flagged: true,
        status: "flagged_and_persisted",
        record: sessionRecord,
        logFileName: logFileName,
        media_path: media_path
      });
    } else {
      // Benign message: DISCARDED from raw storage
      console.log(`[Passive Crawler] 🟢 Benign message analyzed: "${message_body.slice(0, 45)}..." -> Discarded (Data Isolation Active)`);

      return res.status(200).json({
        success: true,
        flagged: false,
        status: "benign_discarded",
        record: sessionRecord
      });
    }

  } catch (error) {
    console.error("[-] Ingestion Error:", error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

// ==============================================================================
// 2. STATUS & TELEMETRY ROUTE: /api/status
// ==============================================================================
app.get('/api/status', (req, res) => {
  try {
    const rawFiles = fs.readdirSync(RAW_DIR);
    const simFiles = rawFiles.filter(f => f.startsWith('whatsapp_simulated_') && f.endsWith('.json'));
    const imgFiles = fs.existsSync(IMAGES_DIR) ? fs.readdirSync(IMAGES_DIR).filter(f => !f.startsWith('.')) : [];

    let masterCount = 0;
    if (fs.existsSync(MASTER_RAW_DATA_FILE)) {
      try {
        const m = JSON.parse(fs.readFileSync(MASTER_RAW_DATA_FILE, 'utf-8'));
        masterCount = Array.isArray(m) ? m.length : 0;
      } catch (e) {}
    }

    return res.json({
      ok: true,
      stats: {
        raw_storage_dir: "data/raw/",
        images_dir: "data/raw/images/",
        flagged_raw_logs_count: simFiles.length,
        evidence_images_count: imgFiles.length,
        master_flagged_records_count: masterCount,
        session_total_messages: sessionMessages.length,
        data_isolation_policy: "selective_threat_logging"
      }
    });
  } catch (error) {
    return res.status(500).json({ ok: false, error: error.message });
  }
});

// ==============================================================================
// 3. FLUSH ROUTE: /api/flush
// ==============================================================================
app.post('/api/flush', (req, res) => {
  try {
    const allFiles = fs.readdirSync(RAW_DIR);
    const simFiles = allFiles.filter(f => f.startsWith('whatsapp_simulated_') && f.endsWith('.json') && f !== 'whatsapp_simulated_batch.json');
    
    const records = [];
    for (const file of simFiles) {
      try {
        const content = JSON.parse(fs.readFileSync(path.join(RAW_DIR, file), 'utf-8'));
        if (Array.isArray(content)) records.push(...content);
        else if (content && typeof content === 'object') records.push(content);
      } catch (e) {}
    }

    const batchFile = path.join(RAW_DIR, 'whatsapp_simulated_batch.json');
    fs.writeFileSync(batchFile, JSON.stringify(records, null, 4), 'utf-8');

    return res.status(200).json({
      success: true,
      total_flagged_logs: records.length,
      destination: "data/raw/whatsapp_simulated_batch.json"
    });
  } catch (error) {
    return res.status(500).json({ success: false, error: error.message });
  }
});

// Chat History & Clear
app.get('/api/history', (req, res) => {
  return res.json({ success: true, messages: sessionMessages });
});

app.post('/api/clear', (req, res) => {
  sessionMessages = [];
  return res.json({ success: true, message: "Session memory cleared." });
});

// Static File & Image Serving
app.use('/api/images', express.static(IMAGES_DIR));
app.use('/data/raw/images', express.static(IMAGES_DIR));
app.use(express.static(path.join(__dirname, 'public')));

// Fallback to index.html for SPA
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start Server
app.listen(PORT, () => {
  console.log(`\n=============================================================`);
  console.log(` 💬 WhatsApp Web Simulator & Passive Ingestion Crawler Active`);
  console.log(` 🌐 URL: http://localhost:${PORT}`);
  console.log(` 🛡️ Data Isolation Policy: Selective Raw Logging ON`);
  console.log(` 📁 Raw Target: data/raw/ (Only flagged threats saved)`);
  console.log(`=============================================================\n`);
});
