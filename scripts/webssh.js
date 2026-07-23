#!/usr/bin/env node

import { spawn } from "node:child_process";

const args = process.argv.slice(2);

if (args[0] === "--ws-proxy") {
  const host = args[1];
  if (!host) {
    console.error("Error: --ws-proxy requires a target host.");
    process.exit(1);
  }
  const insecure = args.includes("--insecure");
  await runProxy(host, insecure);
} else if (args.length === 0 || args.includes("--help")) {
  console.log("Usage: webssh [wrapper-options] [ssh-options] [host] [command]");
  console.log("Wrapper Options:");
  console.log("  --insecure      Bypass TLS/SSL certificate verification");
  console.log("  --help          Show this help message");
  process.exit(0);
} else {
  runWrapper(args);
}

function runWrapper(sshArgs) {
  let insecure = false;
  let i = 0;

  // Consume leading wrapper-specific options
  while (i < sshArgs.length) {
    const arg = sshArgs[i];
    if (arg === "--insecure") {
      insecure = true;
      i++;
    } else {
      break;
    }
  }

  const cleanedArgs = sshArgs.slice(i);
  const scriptPath = import.meta.filename;
  const nodePath = process.execPath;
  const insecureFlag = insecure ? " --insecure" : "";
  const proxyCmd = `"${nodePath}" "${scriptPath}" --ws-proxy "%h"${insecureFlag}`;

  const sshProc = spawn(
    "ssh",
    ["-o", `ProxyCommand=${proxyCmd}`, ...cleanedArgs],
    {
      stdio: "inherit",
    },
  );

  sshProc.on("error", (err) => {
    console.error(`Failed to start SSH process: ${err.message}`);
    process.exit(1);
  });

  sshProc.on("exit", (code) => {
    process.exit(code ?? 0);
  });
}

async function runProxy(host, insecure) {
  if (insecure) {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  }

  if (typeof globalThis.WebSocket === "undefined") {
    console.error(
      "Error: Native globalThis.WebSocket is not available in this Node.js version.",
    );
    process.exit(1);
  }

  const wsUrl = host.includes("://") ? host : `wss://${host}`;
  const options = {};
  const headers = {};

  if (process.env.CF_ACCESS_TOKEN) {
    headers["cf-access-token"] = process.env.CF_ACCESS_TOKEN;
  }
  if (process.env.CF_CLIENT_ID && process.env.CF_CLIENT_SECRET) {
    headers["cf-access-client-id"] = process.env.CF_CLIENT_ID;
    headers["cf-access-client-secret"] = process.env.CF_CLIENT_SECRET;
  }
  if (Object.keys(headers).length > 0) {
    options.headers = headers;
  }

  const ws = new globalThis.WebSocket(wsUrl, options);
  ws.binaryType = "arraybuffer";

  const timeout = setTimeout(() => {
    if (ws.readyState === 0) {
      console.error(`Connection to ${wsUrl} timed out after 10s`);
      ws.close();
      process.exit(1);
    }
  }, 10_000);

  const queue = [];
  let opened = false;

  ws.addEventListener("open", () => {
    clearTimeout(timeout);
    opened = true;
    for (const chunk of queue) {
      try {
        ws.send(chunk);
      } catch (err) {
        console.error(`Write error: ${err.message}`);
        process.exit(1);
      }
    }
    queue.length = 0;
  });

  process.stdin.on("data", (chunk) => {
    if (opened) {
      try {
        ws.send(chunk);
      } catch (err) {
        console.error(`Write error: ${err.message}`);
        process.exit(1);
      }
    } else {
      queue.push(chunk);
    }
  });

  ws.addEventListener("message", (event) => {
    process.stdout.write(Buffer.from(event.data));
  });

  ws.addEventListener("close", () => {
    process.stdout.write("", () => process.exit(0));
  });

  ws.addEventListener("error", (event) => {
    clearTimeout(timeout);
    const errorObj = event.error || event;
    const msg = errorObj.message || errorObj.code || "Connection error";
    console.error(`Connection error: ${msg}`);
    process.exit(1);
  });

  process.stdin.on("end", () => {
    if (ws.readyState === 1) {
      ws.close();
    } else {
      process.exit(0);
    }
  });
}
