/**
 * DrugShield AI - WhatsApp Web Simulation Public Tunnel & Live Sharer
 * =================================================================
 * Starts the local simulation server and creates a secure public tunnel
 * so evaluators or remote testers can open and interact with the simulation
 * directly over the public internet (mobile, tablet, or external PC).
 */

const localtunnel = require('localtunnel');
const http = require('http');
const https = require('https');
const { spawn } = require('child_process');
const path = require('path');

const PORT = process.env.PORT || 3000;

// Helper: Query Public IP (Tunnel Password for loca.lt)
function fetchPublicIP() {
  return new Promise((resolve) => {
    https.get('https://api.ipify.org', (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data.trim()));
    }).on('error', () => {
      // Fallback
      https.get('https://ipv4.icanhazip.com', (res2) => {
        let data2 = '';
        res2.on('data', chunk => data2 += chunk);
        res2.on('end', () => resolve(data2.trim()));
      }).on('error', () => resolve('Check your public IP'));
    });
  });
}

// Helper: Check if local server is already running on port
function isPortOpen(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${port}/api/status`, (res) => {
      resolve(true);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function startTunneling() {
  console.log('\n[1/3] Checking local simulation server on port ' + PORT + '...');
  const serverRunning = await isPortOpen(PORT);

  let serverProcess = null;
  if (!serverRunning) {
    console.log('[+] Launching local simulation server (node server.js)...');
    serverProcess = spawn('node', [path.join(__dirname, 'server.js')], {
      stdio: 'inherit',
      cwd: __dirname
    });
    // Wait 1.5 seconds for server boot
    await new Promise(r => setTimeout(r, 1500));
  } else {
    console.log('[+] Local simulation server is already active on http://localhost:' + PORT);
  }

  console.log('[2/3] Fetching tunnel authentication credentials...');
  const publicIP = await fetchPublicIP();

  console.log('[3/3] Establishing secure public tunnel to localhost:' + PORT + '...');
  try {
    const tunnel = await localtunnel({ port: PORT });

    console.log('\n' + '='.repeat(68));
    console.log(' 🌐  WHATSAPP SIMULATION IS NOW LIVE ON THE PUBLIC INTERNET!');
    console.log('='.repeat(68));
    console.log(' 🔗  Public Shareable URL : ' + tunnel.url);
    console.log(' 🔑  Tunnel Password       : ' + publicIP);
    console.log(' 📱  Mobile & External PC : Anyone can open this link to test!');
    console.log(' 📁  Ingestion Landing    : data/raw/ (Selective threat logging active)');
    console.log('='.repeat(68));
    console.log(' (*) Note: If loca.lt asks for "Tunnel Password", enter: ' + publicIP);
    console.log(' (*) Press Ctrl + C to stop sharing\n');

    tunnel.on('close', () => {
      console.log('[-] Tunnel closed.');
    });

    // Handle cleanup
    const cleanExit = () => {
      console.log('\n[*] Shutting down tunnel...');
      tunnel.close();
      if (serverProcess) serverProcess.kill();
      process.exit(0);
    };

    process.on('SIGINT', cleanExit);
    process.on('SIGTERM', cleanExit);

  } catch (err) {
    console.error('[-] Failed to create tunnel:', err.message);
  }
}

startTunneling();
