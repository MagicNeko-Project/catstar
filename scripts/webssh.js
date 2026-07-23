#!/usr/bin/env node

import { spawn } from 'node:child_process';
import fs from 'node:fs';

const args = process.argv.slice(2);

if (args[0] === '--ws-proxy') {
  const hostIdx = args.indexOf('--ws-proxy') + 1;
  const host = args[hostIdx];
  if (!host) {
    console.error("Error: --ws-proxy requires a target host.");
    process.exit(1);
  }
  const insecure = args.includes('--insecure');
  await runProxy(host, insecure);
} else if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
  console.log("Usage: webssh [options] [user@]hostname[/path] [command]");
  console.log("Options:");
  console.log("  -k, --insecure      Bypass TLS/SSL certificate verification");
  console.log("  -h, --help          Show this help message");
  process.exit(0);
} else {
  runWrapper(args);
}

function runWrapper(sshArgs) {
  let insecure = false;
  const cleanedArgs = [];
  
  let hostFound = false;
  let prevWasFlag = false;

  for (const arg of sshArgs) {
    if (hostFound) {
      cleanedArgs.push(arg);
      continue;
    }

    if (arg.startsWith('-')) {
      if (arg === '-k' || arg === '--insecure') {
        insecure = true;
        continue;
      }
      cleanedArgs.push(arg);
      prevWasFlag = true;
    } else {
      cleanedArgs.push(arg);
      if (!prevWasFlag) {
        hostFound = true;
      }
      prevWasFlag = false;
    }
  }

  const scriptPath = fs.realpathSync(import.meta.filename).replace(/\\/g, '/').replace(/"/g, '\\"');
  const nodePath = process.execPath.replace(/\\/g, '/').replace(/"/g, '\\"');
  const insecureFlag = insecure ? ' --insecure' : '';
  // Secure %h against shell injection by double-quoting it
  const proxyCmd = `"${nodePath}" "${scriptPath}" --ws-proxy "%h"${insecureFlag}`;

  const sshProc = spawn('ssh', ['-o', `ProxyCommand=${proxyCmd}`, ...cleanedArgs], {
    stdio: 'inherit'
  });

  sshProc.on('error', (err) => {
    console.error(`Failed to start SSH process: ${err.message}`);
    process.exit(1);
  });

  sshProc.on('exit', (code) => {
    process.exit(code ?? 0);
  });
}

async function runProxy(host, insecure) {
  if (insecure) {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
  }

  let WsClient;
  try {
    const wsModule = await import('ws');
    WsClient = globalThis.WebSocket || wsModule.WebSocket || wsModule.default;
  } catch {
    console.error("Error: Built-in WebSocket not found and 'ws' package is not installed.");
    process.exit(1);
  }

  const wsUrl = host.includes('://') ? host : `wss://${host}`;
  const options = {};

  // Custom headers injection (works for both built-in WebSocket and fallback 'ws' package)
  const headers = {};
  if (process.env.CF_ACCESS_TOKEN) {
    headers['cf-access-token'] = process.env.CF_ACCESS_TOKEN;
  }
  if (process.env.CF_CLIENT_ID && process.env.CF_CLIENT_SECRET) {
    headers['cf-access-client-id'] = process.env.CF_CLIENT_ID;
    headers['cf-access-client-secret'] = process.env.CF_CLIENT_SECRET;
  }
  if (Object.keys(headers).length > 0) {
    options.headers = headers;
  }

  const ws = new WsClient(wsUrl, options);
  ws.binaryType = 'arraybuffer';

  const connectionTimeout = setTimeout(() => {
    if (ws.readyState === 0) {
      console.error(`\r\nwebssh error: Connection to ${wsUrl} timed out after 10s`);
      try {
        ws.close();
      } catch {
        // Ignore
      }
      process.exit(1);
    }
  }, 10_000);

  // Queue to buffer stdin until the handshake completes
  const queue = [];
  let opened = false;

  ws.addEventListener('open', () => {
    clearTimeout(connectionTimeout);
    opened = true;
    for (const chunk of queue) {
      try {
        ws.send(chunk);
      } catch (err) {
        console.error(`\r\nwebssh send error: ${err.message}`);
        process.exit(1);
      }
    }
    queue.length = 0;
  });

  process.stdin.on('data', (chunk) => {
    if (opened) {
      try {
        ws.send(chunk);
      } catch (err) {
        console.error(`\r\nwebssh send error: ${err.message}`);
        process.exit(1);
      }
    } else {
      queue.push(chunk);
    }
  });

  ws.addEventListener('message', (event) => {
    // Zero-copy wrapping of ArrayBuffer to Buffer for faster stdout writes
    process.stdout.write(Buffer.from(event.data));
  });

  ws.addEventListener('close', () => {
    process.stdout.write('', () => {
      process.exit(0);
    });
  });

  ws.addEventListener('error', (event) => {
    clearTimeout(connectionTimeout);
    const errorObj = event.error || event;
    const msg = errorObj.message || errorObj.code || "Unknown error";
    console.error(`\r\nwebssh error connecting to ${wsUrl}: ${msg}`);
    process.exit(1);
  });

  process.stdin.on('end', () => {
    if (ws.readyState === 1) {
      ws.close();
    } else if (ws.readyState === 0) {
      try {
        ws.close();
      } catch {
        // Ignore TypeError on connecting sockets
      }
      process.exit(0);
    } else {
      process.exit(0);
    }
  });
}
