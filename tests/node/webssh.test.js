import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
  BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
  buildProxyCommand,
  CHUNK_SIZE,
  CONNECTION_TIMEOUT_MILLISECONDS,
  DRAIN_THROTTLE_DELAY_MILLISECONDS,
  MAXIMUM_FRAME_PAYLOAD_BYTES,
  parseWrapperArguments,
  runProxy,
  WEBSOCKET_READY_STATE_CONNECTING,
  WEBSOCKET_READY_STATE_OPEN,
} from "../../scripts/webssh.js";

describe("webssh CLI & Configuration Unit Tests", () => {
  it("constants enforce safe buffer thresholds and state invariants", () => {
    assert.equal(MAXIMUM_FRAME_PAYLOAD_BYTES, 4096);
    assert.equal(CHUNK_SIZE, 4096);
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

  it("runProxy sets rejectUnauthorized: false in options and does not mutate process.env.NODE_TLS_REJECT_UNAUTHORIZED", async (t) => {
    const originalWebSocket = globalThis.WebSocket;
    t.mock.method(process, "exit", () => {});
    const originalEnvVal = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
    delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;

    let capturedUrl = null;
    let capturedOptions = null;

    class MockWebSocket {
      constructor(url, options) {
        capturedUrl = url;
        capturedOptions = options;
        this.readyState = 0;
        this.listeners = {};
      }
      addEventListener(event, fn) {
        this.listeners[event] = fn;
        if (event === "close") {
          queueMicrotask(() => fn());
        }
      }
      close() {}
    }

    globalThis.WebSocket = MockWebSocket;

    try {
      await runProxy("example.com", true);

      assert.equal(process.env.NODE_TLS_REJECT_UNAUTHORIZED, undefined);
      assert.equal(capturedUrl, "wss://example.com");
      assert.deepEqual(capturedOptions, { rejectUnauthorized: false });
    } finally {
      globalThis.WebSocket = originalWebSocket;
      if (originalEnvVal !== undefined) {
        process.env.NODE_TLS_REJECT_UNAUTHORIZED = originalEnvVal;
      } else {
        delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
      }
    }
  });

  it("runProxy sets rejectUnauthorized: true in options when insecure mode is disabled", async (t) => {
    const originalWebSocket = globalThis.WebSocket;
    t.mock.method(process, "exit", () => {});
    const originalEnvVal = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
    delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;

    let capturedUrl = null;
    let capturedOptions = null;

    class MockWebSocket {
      constructor(url, options) {
        capturedUrl = url;
        capturedOptions = options;
        this.readyState = 0;
        this.listeners = {};
      }
      addEventListener(event, fn) {
        this.listeners[event] = fn;
        if (event === "close") {
          queueMicrotask(() => fn());
        }
      }
      close() {}
    }

    globalThis.WebSocket = MockWebSocket;

    try {
      await runProxy("example.com", false);

      assert.equal(process.env.NODE_TLS_REJECT_UNAUTHORIZED, undefined);
      assert.equal(capturedUrl, "wss://example.com");
      assert.deepEqual(capturedOptions, { rejectUnauthorized: true });
    } finally {
      globalThis.WebSocket = originalWebSocket;
      if (originalEnvVal !== undefined) {
        process.env.NODE_TLS_REJECT_UNAUTHORIZED = originalEnvVal;
      } else {
        delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
      }
    }
  });

  it("runProxy passes Cloudflare credentials headers alongside scoped TLS options", async (t) => {
    const originalWebSocket = globalThis.WebSocket;
    t.mock.method(process, "exit", () => {});
    const originalToken = process.env.CF_ACCESS_TOKEN;
    const originalId = process.env.CF_CLIENT_ID;
    const originalSecret = process.env.CF_CLIENT_SECRET;

    process.env.CF_ACCESS_TOKEN = "cf-token-123";
    process.env.CF_CLIENT_ID = "cf-client-id-456";
    process.env.CF_CLIENT_SECRET = "cf-client-secret-789";

    let capturedUrl = null;
    let capturedOptions = null;

    class MockWebSocket {
      constructor(url, options) {
        capturedUrl = url;
        capturedOptions = options;
        this.readyState = 0;
        this.listeners = {};
      }
      addEventListener(event, fn) {
        this.listeners[event] = fn;
        if (event === "close") {
          queueMicrotask(() => fn());
        }
      }
      close() {}
    }

    globalThis.WebSocket = MockWebSocket;

    try {
      await runProxy("example.com", true);

      assert.equal(capturedUrl, "wss://example.com");
      assert.deepEqual(capturedOptions, {
        rejectUnauthorized: false,
        headers: {
          "cf-access-token": "cf-token-123",
          "cf-access-client-id": "cf-client-id-456",
          "cf-access-client-secret": "cf-client-secret-789",
        },
      });
    } finally {
      globalThis.WebSocket = originalWebSocket;
      if (originalToken !== undefined) {
        process.env.CF_ACCESS_TOKEN = originalToken;
      } else {
        delete process.env.CF_ACCESS_TOKEN;
      }
      if (originalId !== undefined) {
        process.env.CF_CLIENT_ID = originalId;
      } else {
        delete process.env.CF_CLIENT_ID;
      }
      if (originalSecret !== undefined) {
        process.env.CF_CLIENT_SECRET = originalSecret;
      } else {
        delete process.env.CF_CLIENT_SECRET;
      }
    }
  });

  it("integration: runProxy completes WebSocket connection under --insecure mode with self-signed TLS options", async (t) => {
    const originalWebSocket = globalThis.WebSocket;
    t.mock.method(process, "exit", () => {});
    delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;

    let connectionEstablished = false;

    class SelfSignedTLSWebSocket {
      constructor(url, options) {
        this.url = url;
        this.options = options;
        this.readyState = 0;
        this.listeners = {};

        if (options.rejectUnauthorized === false) {
          connectionEstablished = true;
        }

        queueMicrotask(() => {
          this.readyState = 1;
          if (this.listeners.open) {
            this.listeners.open();
          }
          queueMicrotask(() => {
            this.readyState = 2;
            if (this.listeners.close) {
              this.listeners.close();
            }
          });
        });
      }
      addEventListener(event, fn) {
        this.listeners[event] = fn;
      }
      close() {}
    }

    globalThis.WebSocket = SelfSignedTLSWebSocket;

    try {
      await runProxy("wss://self-signed.internal:8443", true);

      assert.equal(connectionEstablished, true);
      assert.equal(process.env.NODE_TLS_REJECT_UNAUTHORIZED, undefined);
    } finally {
      globalThis.WebSocket = originalWebSocket;
    }
  });
});
