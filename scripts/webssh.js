#!/usr/bin/env node

import { Buffer } from "node:buffer";
import { spawn } from "node:child_process";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const MAXIMUM_FRAME_PAYLOAD_BYTES = 4096;
const CONNECTION_TIMEOUT_MILLISECONDS = 10_000;
const BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES = 64 * 1024;
const BUFFERED_AMOUNT_LOW_WATERMARK_BYTES = 16 * 1024;
const DRAIN_THROTTLE_DELAY_MILLISECONDS = 10;
const WEBSOCKET_READY_STATE_CONNECTING = 0;
const WEBSOCKET_READY_STATE_OPEN = 1;

// Aliases preserved for backwards compatibility with tests and callers
const CHUNK_SIZE = MAXIMUM_FRAME_PAYLOAD_BYTES;
const CONNECT_TIMEOUT_MS = CONNECTION_TIMEOUT_MILLISECONDS;

function parseWrapperArguments(sshArguments) {
  let allowInsecureCertificate = false;
  let sshBinaryPath = process.env.SSH_PATH || "ssh";
  let argumentIndex = 0;

  while (argumentIndex < sshArguments.length) {
    const currentArgument = sshArguments[argumentIndex];
    if (currentArgument === "--insecure") {
      allowInsecureCertificate = true;
      argumentIndex++;
      continue;
    }

    if (currentArgument === "--ssh") {
      const specifiedSshBinaryPath = sshArguments[argumentIndex + 1];
      if (!specifiedSshBinaryPath) {
        throw new Error("Error: --ssh requires an argument.");
      }
      sshBinaryPath = specifiedSshBinaryPath;
      argumentIndex += 2;
      continue;
    }

    break;
  }

  return {
    insecure: allowInsecureCertificate,
    sshPath: sshBinaryPath,
    remainingArgs: sshArguments.slice(argumentIndex),
  };
}

function sliceBufferIntoFrames(
  dataBuffer,
  maximumFrameBytes = MAXIMUM_FRAME_PAYLOAD_BYTES,
) {
  const frames = [];
  for (
    let bufferOffset = 0;
    bufferOffset < dataBuffer.length;
    bufferOffset += maximumFrameBytes
  ) {
    frames.push(
      dataBuffer.subarray(bufferOffset, bufferOffset + maximumFrameBytes),
    );
  }
  return frames;
}

function runWrapper(sshArguments) {
  let parsedConfiguration;
  try {
    parsedConfiguration = parseWrapperArguments(sshArguments);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }

  const { insecure, sshPath, remainingArgs } = parsedConfiguration;
  const scriptPath = import.meta.filename;
  const nodeBinaryPath = process.execPath;
  const insecureFlag = insecure ? " --insecure" : "";
  const proxyCommand = `"${nodeBinaryPath}" "${scriptPath}" --ws-proxy "%h"${insecureFlag}`;

  const sshChildProcess = spawn(
    sshPath,
    ["-o", `ProxyCommand=${proxyCommand}`, ...remainingArgs],
    {
      stdio: "inherit",
    },
  );

  sshChildProcess.on("error", (spawnError) => {
    console.error(`Failed to start SSH process: ${spawnError.message}`);
    process.exit(1);
  });

  sshChildProcess.on("exit", (exitCode) => {
    process.exit(exitCode ?? 0);
  });
}

async function runProxy(targetHost, allowInsecureCertificate) {
  if (allowInsecureCertificate) {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  }

  if (typeof globalThis.WebSocket === "undefined") {
    console.error(
      "Error: Native globalThis.WebSocket is not available in this Node.js version.",
    );
    process.exit(1);
  }

  const websocketUrl = targetHost.includes("://")
    ? targetHost
    : `wss://${targetHost}`;
  const requestHeaders = {};

  if (process.env.CF_ACCESS_TOKEN) {
    requestHeaders["cf-access-token"] = process.env.CF_ACCESS_TOKEN;
  }
  if (process.env.CF_CLIENT_ID && process.env.CF_CLIENT_SECRET) {
    requestHeaders["cf-access-client-id"] = process.env.CF_CLIENT_ID;
    requestHeaders["cf-access-client-secret"] = process.env.CF_CLIENT_SECRET;
  }

  const websocket = new globalThis.WebSocket(
    websocketUrl,
    Object.keys(requestHeaders).length > 0 ? { headers: requestHeaders } : {},
  );
  websocket.binaryType = "arraybuffer";

  const connectionTimeout = setTimeout(() => {
    if (websocket.readyState === WEBSOCKET_READY_STATE_CONNECTING) {
      console.error(
        `Connection to ${websocketUrl} timed out after ${CONNECTION_TIMEOUT_MILLISECONDS / 1000}s`,
      );
      websocket.close();
      process.exit(1);
    }
  }, CONNECTION_TIMEOUT_MILLISECONDS);

  websocket.addEventListener("open", async () => {
    clearTimeout(connectionTimeout);
    try {
      for await (const inputChunk of process.stdin) {
        if (websocket.readyState !== WEBSOCKET_READY_STATE_OPEN) {
          break;
        }

        for (
          let bufferOffset = 0;
          bufferOffset < inputChunk.length;
          bufferOffset += MAXIMUM_FRAME_PAYLOAD_BYTES
        ) {
          if (websocket.readyState !== WEBSOCKET_READY_STATE_OPEN) {
            break;
          }

          websocket.send(
            inputChunk.subarray(
              bufferOffset,
              bufferOffset + MAXIMUM_FRAME_PAYLOAD_BYTES,
            ),
          );

          if (
            websocket.bufferedAmount > BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES
          ) {
            while (
              websocket.bufferedAmount > BUFFERED_AMOUNT_LOW_WATERMARK_BYTES &&
              websocket.readyState === WEBSOCKET_READY_STATE_OPEN
            ) {
              await new Promise((resolve) =>
                setTimeout(resolve, DRAIN_THROTTLE_DELAY_MILLISECONDS).unref(),
              );
            }
          }
        }
      }
    } catch {
      // Catch stream cancellation or broken stdin pipe without unhandled rejection
    } finally {
      if (websocket.readyState === WEBSOCKET_READY_STATE_OPEN) {
        websocket.close();
      }
    }
  });

  websocket.addEventListener("message", (messageEvent) => {
    process.stdout.write(Buffer.from(messageEvent.data));
  });

  websocket.addEventListener("close", () => {
    clearTimeout(connectionTimeout);
    process.stdout.write("", () => process.exit(0));
  });

  websocket.addEventListener("error", (errorEvent) => {
    clearTimeout(connectionTimeout);
    const underlyingError = errorEvent.error || errorEvent;
    const errorMessage =
      underlyingError.message ||
      underlyingError.code ||
      "Connection error";
    console.error(`Connection error: ${errorMessage}`);
    process.exit(1);
  });

  process.stdout.on("error", (outputError) => {
    clearTimeout(connectionTimeout);
    if (websocket.readyState === WEBSOCKET_READY_STATE_OPEN) {
      websocket.close();
    }
    if (outputError.code === "EPIPE") {
      process.exit(0);
    }
    console.error(`stdout error: ${outputError.message}`);
    process.exit(1);
  });
}

function isExecutingAsMain() {
  if (!process.argv[1]) {
    return false;
  }
  try {
    const executedScriptPath = fs.realpathSync(process.argv[1]);
    const moduleScriptPath = fileURLToPath(import.meta.url);
    return executedScriptPath === moduleScriptPath;
  } catch {
    return false;
  }
}

if (isExecutingAsMain()) {
  const commandLineArguments = process.argv.slice(2);

  if (commandLineArguments[0] === "--ws-proxy") {
    const targetHost = commandLineArguments[1];
    if (!targetHost) {
      console.error("Error: --ws-proxy requires a target host.");
      process.exit(1);
    }
    const allowInsecureCertificate = commandLineArguments.includes("--insecure");
    await runProxy(targetHost, allowInsecureCertificate);
  } else if (
    commandLineArguments.length === 0 ||
    commandLineArguments.includes("--help")
  ) {
    console.log(
      "Usage: webssh [wrapper-options] [ssh-options] [host] [command]",
    );
    console.log("Wrapper Options:");
    console.log("  --insecure        Bypass TLS/SSL certificate verification");
    console.log("  --ssh <path>      Overwrite the path to the ssh binary");
    console.log("  --help            Show this help message");
    process.exit(0);
  } else {
    runWrapper(commandLineArguments);
  }
}

export {
  BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
  BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
  CHUNK_SIZE,
  CONNECT_TIMEOUT_MS,
  CONNECTION_TIMEOUT_MILLISECONDS,
  DRAIN_THROTTLE_DELAY_MILLISECONDS,
  MAXIMUM_FRAME_PAYLOAD_BYTES,
  WEBSOCKET_READY_STATE_CONNECTING,
  WEBSOCKET_READY_STATE_OPEN,
  parseWrapperArguments,
  sliceBufferIntoFrames,
  runProxy,
  runWrapper,
};
