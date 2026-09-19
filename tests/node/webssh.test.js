import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import https from "node:https";
import os from "node:os";
import path from "node:path";
import { describe, it } from "node:test";
import {
  BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
  BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
  buildProxyCommand,
  buildWebSocketOptions,
  CONNECTION_TIMEOUT_MILLISECONDS,
  DRAIN_THROTTLE_DELAY_MILLISECONDS,
  MAXIMUM_FRAME_PAYLOAD_BYTES,
  parseWrapperArguments,
  WEBSOCKET_READY_STATE_CONNECTING,
  WEBSOCKET_READY_STATE_OPEN,
} from "../../scripts/webssh.js";

describe("webssh CLI & Configuration Unit Tests", () => {
  it("constants enforce safe buffer thresholds and state invariants", () => {
    assert.equal(MAXIMUM_FRAME_PAYLOAD_BYTES, 4096);
    assert.ok(MAXIMUM_FRAME_PAYLOAD_BYTES <= 8192);
    assert.ok(
      BUFFERED_AMOUNT_LOW_WATERMARK_BYTES <
        BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
    );
    assert.equal(BUFFERED_AMOUNT_LOW_WATERMARK_BYTES, 16 * 1024);
    assert.equal(BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES, 64 * 1024);
    assert.equal(DRAIN_THROTTLE_DELAY_MILLISECONDS, 10);
    assert.equal(CONNECTION_TIMEOUT_MILLISECONDS, 10_000);
    assert.equal(WEBSOCKET_READY_STATE_CONNECTING, 0);
    assert.equal(WEBSOCKET_READY_STATE_OPEN, 1);
  });

  it("buildProxyCommand formats secure ProxyCommand string with node path and script path", () => {
    const nodeBinaryPath = "/usr/local/bin/node";
    const scriptPath = "/usr/local/bin/webssh";
    const allowInsecure = false;

    const proxyCommand = buildProxyCommand(
      nodeBinaryPath,
      scriptPath,
      allowInsecure,
    );

    assert.equal(
      proxyCommand,
      '"/usr/local/bin/node" "/usr/local/bin/webssh" --ws-proxy "%h"',
    );
  });

  it("buildProxyCommand appends --insecure flag when insecure certificate verification is allowed", () => {
    const nodeBinaryPath = "/usr/local/bin/node";
    const scriptPath = "/usr/local/bin/webssh";
    const allowInsecure = true;

    const proxyCommand = buildProxyCommand(
      nodeBinaryPath,
      scriptPath,
      allowInsecure,
    );

    assert.equal(
      proxyCommand,
      '"/usr/local/bin/node" "/usr/local/bin/webssh" --ws-proxy "%h" --insecure',
    );
  });

  it("parseWrapperArguments sets default options and preserves remaining command arguments", () => {
    const inputArguments = ["example.com", "uptime"];
    const parsed = parseWrapperArguments(inputArguments);

    assert.equal(parsed.insecure, false);
    assert.equal(parsed.sshPath, "ssh");
    assert.deepEqual(parsed.remainingArgs, ["example.com", "uptime"]);
  });

  it("parseWrapperArguments parses insecure and custom ssh binary options", () => {
    const inputArguments = [
      "--insecure",
      "--ssh",
      "/usr/bin/custom-ssh",
      "example.net",
      "uname",
      "-a",
    ];
    const parsed = parseWrapperArguments(inputArguments);

    assert.equal(parsed.insecure, true);
    assert.equal(parsed.sshPath, "/usr/bin/custom-ssh");
    assert.deepEqual(parsed.remainingArgs, ["example.net", "uname", "-a"]);
  });

  it("parseWrapperArguments throws error when ssh option lacks target path", () => {
    const invalidArguments = ["--ssh"];
    assert.throws(
      () => parseWrapperArguments(invalidArguments),
      /--ssh requires an argument/,
    );
  });

  it("buildWebSocketOptions returns rejectUnauthorized: false when allowInsecureCertificate is true", () => {
    delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;

    const options = buildWebSocketOptions(true);

    assert.equal(
      process.env.NODE_TLS_REJECT_UNAUTHORIZED,
      undefined,
      "process.env.NODE_TLS_REJECT_UNAUTHORIZED must not be mutated",
    );
    assert.equal(options.rejectUnauthorized, false);
  });

  it("buildWebSocketOptions returns rejectUnauthorized: true when allowInsecureCertificate is false", () => {
    delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;

    const options = buildWebSocketOptions(false);

    assert.equal(process.env.NODE_TLS_REJECT_UNAUTHORIZED, undefined);
    assert.equal(options.rejectUnauthorized, true);
  });

  it("buildWebSocketOptions includes request headers alongside scoped TLS options", () => {
    const headers = {
      "cf-access-token": "test-token",
      "cf-access-client-id": "client-id",
      "cf-access-client-secret": "client-secret",
    };

    const options = buildWebSocketOptions(true, headers);

    assert.equal(options.rejectUnauthorized, false);
    assert.deepEqual(options.headers, headers);
  });

  it("integration: verifies process.env.NODE_TLS_REJECT_UNAUTHORIZED remains unmodified during --insecure proxy runs", async () => {
    delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "webssh-test-"));
    const keyPath = path.join(tempDir, "key.pem");
    const certPath = path.join(tempDir, "cert.pem");

    try {
      execSync(
        `openssl req -x509 -newkey rsa:2048 -keyout "${keyPath}" -out "${certPath}" -days 1 -nodes -subj "/CN=127.0.0.1"`,
        { stdio: "ignore" },
      );
    } catch {
      fs.rmSync(tempDir, { recursive: true, force: true });
      return;
    }

    const key = fs.readFileSync(keyPath);
    const cert = fs.readFileSync(certPath);

    const activeSockets = new Set();
    const server = https.createServer({ key, cert });
    let upgradeReceived = false;

    server.on("connection", (socket) => {
      activeSockets.add(socket);
      socket.on("close", () => activeSockets.delete(socket));
    });

    server.on("upgrade", (req, socket) => {
      upgradeReceived = true;
      activeSockets.add(socket);
      const keyHeader = req.headers["sec-websocket-key"];
      const acceptKey = crypto
        .createHash("sha1")
        .update(`${keyHeader}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
        .digest("base64");

      socket.write(
        "HTTP/1.1 101 Switching Protocols\r\n" +
          "Upgrade: websocket\r\n" +
          "Connection: Upgrade\r\n" +
          `Sec-WebSocket-Accept: ${acceptKey}\r\n` +
          "\r\n",
      );
      const destroyTimer = setTimeout(() => {
        socket.destroy();
      }, 50);
      destroyTimer.unref();
    });

    await new Promise((resolve, reject) => {
      server.listen(0, "127.0.0.1", resolve);
      server.on("error", reject);
    });

    const port = server.address().port;
    const wsOptions = buildWebSocketOptions(true);
    const ws = new globalThis.WebSocket(`wss://127.0.0.1:${port}`, wsOptions);

    await new Promise((resolve, reject) => {
      ws.onopen = () => {
        ws.close();
        resolve();
      };
      ws.onerror = (err) => {
        reject(err.error || err);
      };
    });

    try {
      assert.ok(
        upgradeReceived,
        "WebSocket connection must successfully reach upgrade handler on self-signed TLS server",
      );
      assert.equal(
        process.env.NODE_TLS_REJECT_UNAUTHORIZED,
        undefined,
        "NODE_TLS_REJECT_UNAUTHORIZED must not be mutated during insecure proxy execution",
      );
    } finally {
      process.stdin.pause();
      const wsControllerSymbol = Object.getOwnPropertySymbols(ws).find(
        (s) => s.description === "controller",
      );
      ws[wsControllerSymbol]?.terminate?.();
      ws[wsControllerSymbol]?.abort?.();
      for (const socket of activeSockets) {
        socket.destroy();
      }
      server.close();
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  });
});
