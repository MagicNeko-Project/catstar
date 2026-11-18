import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { createHash, randomBytes } from "node:crypto";
import http from "node:http";
import net from "node:net";
import { PassThrough, Writable } from "node:stream";
import { describe, it } from "node:test";
import {
  BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
  BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
  buildCloudflareAccessHeaders,
  buildProxyCommand,
  CONNECTION_TIMEOUT_MILLISECONDS,
  DRAIN_THROTTLE_DELAY_MILLISECONDS,
  extractWebSocketErrorMessage,
  FramedWebSocketStream,
  HALF_CLOSE_TIMEOUT_MILLISECONDS,
  isCleanWebSocketClose,
  MAX_WEBSOCKET_CLOSE_REASON_BYTES,
  MAXIMUM_FRAME_PAYLOAD_BYTES,
  parseWrapperArguments,
  resolveWebSocketUrl,
  runProxy,
  sanitizeClientCloseCode,
  truncateCloseReasonSafely,
  WEBSOCKET_CLOSE_TIMEOUT_MILLISECONDS,
  WEBSOCKET_READY_STATE_CLOSED,
  WEBSOCKET_READY_STATE_CLOSING,
  WEBSOCKET_READY_STATE_CONNECTING,
  WEBSOCKET_READY_STATE_OPEN,
} from "../../scripts/webssh.js";

const WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

class MemoryWebSocketDouble extends EventTarget {
  constructor(initialState = WEBSOCKET_READY_STATE_OPEN) {
    super();
    this.readyState = initialState;
    this.binaryType = "blob";
    this.bufferedAmount = 0;
    this.sentFrames = [];
    this.closeCalls = [];
    this.maxObservedBufferedAmount = 0;
    this.autoEchoClose = true;
    this.holdDrain = false;
  }

  send(data) {
    const chunk = Buffer.from(data);
    this.sentFrames.push(chunk);
    this.bufferedAmount += chunk.byteLength;
    if (this.bufferedAmount > this.maxObservedBufferedAmount) {
      this.maxObservedBufferedAmount = this.bufferedAmount;
    }
    if (!this.holdDrain) {
      queueMicrotask(() => {
        this.bufferedAmount = Math.max(
          0,
          this.bufferedAmount - chunk.byteLength,
        );
      });
    }
  }

  close(code = 1005, reason = "") {
    this.closeCalls.push({ code, reason });
    if (
      this.readyState === WEBSOCKET_READY_STATE_CLOSED ||
      this.readyState === WEBSOCKET_READY_STATE_CLOSING
    ) {
      return;
    }
    this.readyState = WEBSOCKET_READY_STATE_CLOSING;
    if (this.autoEchoClose) {
      queueMicrotask(() => {
        this.emitClose(code, reason, true);
      });
    }
  }

  emitOpen() {
    this.readyState = WEBSOCKET_READY_STATE_OPEN;
    this.dispatchEvent(new Event("open"));
  }

  emitMessage(data) {
    const messageEvent = new Event("message");
    messageEvent.data = data;
    this.dispatchEvent(messageEvent);
  }

  emitClose(code = 1000, reason = "", wasClean = true) {
    this.readyState = WEBSOCKET_READY_STATE_CLOSED;
    const closeEvent = new Event("close");
    closeEvent.code = code;
    closeEvent.reason = reason;
    closeEvent.wasClean = wasClean;
    this.dispatchEvent(closeEvent);
  }
}

function encodeServerFrame(opcode, payloadBuffer) {
  const length = payloadBuffer.length;
  let header;
  if (length <= 125) {
    header = Buffer.from([0x80 | opcode, length]);
  } else if (length <= 65535) {
    header = Buffer.alloc(4);
    header[0] = 0x80 | opcode;
    header[1] = 126;
    header.writeUInt16BE(length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x80 | opcode;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(length), 2);
  }
  return Buffer.concat([header, payloadBuffer]);
}

function encodeServerCloseFrame(code, reason = "") {
  const reasonBuffer = Buffer.from(reason, "utf-8");
  const payload = Buffer.alloc(2 + reasonBuffer.length);
  payload.writeUInt16BE(code, 0);
  reasonBuffer.copy(payload, 2);
  return encodeServerFrame(0x08, payload);
}

function decodeAvailableClientFrames(buffer) {
  const frames = [];
  let offset = 0;

  while (offset + 2 <= buffer.length) {
    const firstByte = buffer[offset];
    const secondByte = buffer[offset + 1];
    const fin = (firstByte & 0x80) !== 0;
    const rsv = (firstByte & 0x70) >> 4;
    const opcode = firstByte & 0x0f;
    const masked = (secondByte & 0x80) !== 0;
    let payloadLength = secondByte & 0x7f;
    let cursor = offset + 2;

    if (payloadLength === 126) {
      if (cursor + 2 > buffer.length) {
        break;
      }
      payloadLength = buffer.readUInt16BE(cursor);
      cursor += 2;
    } else if (payloadLength === 127) {
      if (cursor + 8 > buffer.length) {
        break;
      }
      payloadLength = Number(buffer.readBigUInt64BE(cursor));
      cursor += 8;
    }

    const maskLength = masked ? 4 : 0;
    if (cursor + maskLength + payloadLength > buffer.length) {
      break;
    }

    let payload;
    if (masked) {
      const maskKey = buffer.subarray(cursor, cursor + 4);
      const maskedPayload = buffer.subarray(
        cursor + 4,
        cursor + 4 + payloadLength,
      );
      payload = Buffer.allocUnsafe(payloadLength);
      for (let index = 0; index < payloadLength; index++) {
        payload[index] = maskedPayload[index] ^ maskKey[index % 4];
      }
    } else {
      payload = Buffer.from(buffer.subarray(cursor, cursor + payloadLength));
    }

    frames.push({ fin, rsv, opcode, masked, payload });
    offset = cursor + maskLength + payloadLength;
  }

  return {
    frames,
    remainder: buffer.subarray(offset),
  };
}

async function createLoopbackWebSocketServer(onConnection) {
  const activeSockets = new Set();

  const server = http.createServer((_request, response) => {
    response.writeHead(404);
    response.end();
  });

  server.on("upgrade", (request, socket, head) => {
    const webSocketKey = request.headers["sec-websocket-key"];
    if (typeof webSocketKey !== "string") {
      socket.destroy();
      return;
    }

    activeSockets.add(socket);
    socket.on("close", () => {
      activeSockets.delete(socket);
    });
    socket.on("error", () => {});

    const acceptKey = createHash("sha1")
      .update(`${webSocketKey}${WEBSOCKET_GUID}`)
      .digest("base64");

    socket.write(
      [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        `Sec-WebSocket-Accept: ${acceptKey}`,
        "\r\n",
      ].join("\r\n"),
    );

    const frameListeners = new Set();
    const closeListeners = new Set();
    let receiveBuffer = head.length > 0 ? Buffer.from(head) : Buffer.alloc(0);
    let closeSent = false;
    let serverCloseTimer = null;

    socket.on("close", () => {
      if (serverCloseTimer !== null) {
        clearTimeout(serverCloseTimer);
        serverCloseTimer = null;
      }
    });

    const sendBinary = (chunk) => {
      if (!socket.destroyed) {
        socket.write(encodeServerFrame(0x02, Buffer.from(chunk)));
      }
    };

    const replyCloseAndEnd = (code = 1000, reason = "") => {
      if (!closeSent && !socket.destroyed) {
        closeSent = true;
        socket.write(encodeServerCloseFrame(code, reason), () => {
          if (!socket.destroyed) {
            socket.end();
          }
        });
      }
    };

    const sendClose = (code = 1000, reason = "") => {
      if (!closeSent && !socket.destroyed) {
        closeSent = true;
        socket.write(encodeServerCloseFrame(code, reason), () => {
          serverCloseTimer = setTimeout(() => {
            serverCloseTimer = null;
            if (!socket.destroyed) {
              socket.end();
            }
          }, 50);
          serverCloseTimer.unref();
        });
      }
    };

    socket.on("data", (chunk) => {
      receiveBuffer =
        receiveBuffer.length === 0
          ? chunk
          : Buffer.concat([receiveBuffer, chunk]);
      const parsed = decodeAvailableClientFrames(receiveBuffer);
      receiveBuffer = parsed.remainder;

      for (const frame of parsed.frames) {
        if (frame.opcode === 0x09) {
          if (!socket.destroyed) {
            socket.write(encodeServerFrame(0x0a, frame.payload));
          }
          continue;
        }
        if (frame.opcode === 0x08) {
          const initiatedByClient = !closeSent;
          const closeCode =
            frame.payload.length >= 2 ? frame.payload.readUInt16BE(0) : 1005;
          const closeReason =
            frame.payload.length > 2
              ? frame.payload.subarray(2).toString("utf-8")
              : "";
          for (const listener of closeListeners) {
            listener({
              code: closeCode,
              reason: closeReason,
              initiatedByClient,
            });
          }
          if (initiatedByClient) {
            replyCloseAndEnd(
              closeCode === 1005 ? 1000 : closeCode,
              closeReason,
            );
          } else {
            if (serverCloseTimer !== null) {
              clearTimeout(serverCloseTimer);
              serverCloseTimer = null;
            }
            if (!socket.destroyed) {
              socket.end();
            }
          }
          continue;
        }
        for (const listener of frameListeners) {
          listener(frame);
        }
      }
    });

    onConnection({
      request,
      socket,
      sendBinary,
      sendClose,
      onFrame(listener) {
        frameListeners.add(listener);
      },
      onClientClose(listener) {
        closeListeners.add(listener);
      },
    });
  });

  await new Promise((resolve) => {
    server.listen(0, "127.0.0.1", resolve);
  });

  const address = server.address();
  return {
    url: `ws://127.0.0.1:${address.port}/ssh`,
    async close() {
      for (const socket of activeSockets) {
        socket.destroy();
      }
      await new Promise((resolve) => {
        server.close(() => resolve());
      });
    },
  };
}

function collectStreamOutput(stream) {
  const chunks = [];
  stream.on("data", (chunk) => {
    chunks.push(Buffer.from(chunk));
  });
  return () => Buffer.concat(chunks);
}

describe("webssh CLI & Framing Unit Tests (Offline)", {
  timeout: 5_000,
}, () => {
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
    assert.equal(WEBSOCKET_CLOSE_TIMEOUT_MILLISECONDS, 2_000);
    assert.equal(HALF_CLOSE_TIMEOUT_MILLISECONDS, 10_000);
    assert.equal(MAX_WEBSOCKET_CLOSE_REASON_BYTES, 123);
    assert.equal(WEBSOCKET_READY_STATE_CONNECTING, 0);
    assert.equal(WEBSOCKET_READY_STATE_OPEN, 1);
    assert.equal(WEBSOCKET_READY_STATE_CLOSING, 2);
    assert.equal(WEBSOCKET_READY_STATE_CLOSED, 3);
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

  it("parseWrapperArguments scopes --help to leading wrapper options only", () => {
    assert.equal(parseWrapperArguments(["--help"]).help, true);
    assert.deepEqual(parseWrapperArguments(["--insecure", "--help"]), {
      help: true,
      insecure: true,
      sshPath: "ssh",
      remainingArgs: [],
    });
    assert.deepEqual(parseWrapperArguments(["example.com", "ls", "--help"]), {
      help: false,
      insecure: false,
      sshPath: "ssh",
      remainingArgs: ["example.com", "ls", "--help"],
    });
  });

  it("resolveWebSocketUrl normalizes bare hosts and rejects invalid schemes", () => {
    assert.equal(resolveWebSocketUrl("example.com"), "wss://example.com");
    assert.equal(
      resolveWebSocketUrl("  example.com/tunnel?mode=ssh  "),
      "wss://example.com/tunnel?mode=ssh",
    );
    assert.equal(
      resolveWebSocketUrl("ws://127.0.0.1:8080/ssh"),
      "ws://127.0.0.1:8080/ssh",
    );
    assert.equal(
      resolveWebSocketUrl("wss://example.net:443/ws"),
      "wss://example.net:443/ws",
    );
    assert.equal(resolveWebSocketUrl("2001:db8::1"), "wss://[2001:db8::1]");
    assert.equal(
      resolveWebSocketUrl("2001:db8::1/ssh"),
      "wss://[2001:db8::1]/ssh",
    );

    assert.throws(() => resolveWebSocketUrl(""), /non-empty/);
    assert.throws(() => resolveWebSocketUrl("   "), /non-empty/);
    assert.throws(
      () => resolveWebSocketUrl("http://example.com"),
      /Unsupported WebSocket protocol/,
    );
    assert.throws(
      () => resolveWebSocketUrl("https://example.com"),
      /Unsupported WebSocket protocol/,
    );
    assert.throws(() => resolveWebSocketUrl("wss://"), /Invalid WebSocket/);
    assert.throws(
      () => resolveWebSocketUrl("example.com/ssh#frag"),
      /fragment identifier/,
    );
    assert.throws(
      () => resolveWebSocketUrl("wss://example.com#"),
      /fragment identifier/,
    );
  });

  it("buildCloudflareAccessHeaders extracts trimmed access token and paired client credentials", () => {
    assert.deepEqual(
      buildCloudflareAccessHeaders({
        CF_ACCESS_TOKEN: "  token-value  ",
      }),
      {
        "CF-Access-Token": "token-value",
      },
    );

    assert.deepEqual(
      buildCloudflareAccessHeaders({
        CF_CLIENT_ID: " client-id-value ",
        CF_CLIENT_SECRET: " client-secret-value ",
      }),
      {
        "CF-Access-Client-Id": "client-id-value",
        "CF-Access-Client-Secret": "client-secret-value",
      },
    );

    assert.deepEqual(
      buildCloudflareAccessHeaders({
        CF_ACCESS_TOKEN: "   ",
        CF_CLIENT_ID: "orphan-id",
      }),
      {},
    );
  });

  it("sanitizeClientCloseCode, truncateCloseReasonSafely, and isCleanWebSocketClose enforce protocol rules", () => {
    assert.equal(sanitizeClientCloseCode(1000), 1000);
    assert.equal(sanitizeClientCloseCode(3000), 3000);
    assert.equal(sanitizeClientCloseCode(4999), 4999);
    assert.equal(sanitizeClientCloseCode(1001), 1000);
    assert.equal(sanitizeClientCloseCode(1005), 1000);
    assert.equal(sanitizeClientCloseCode(1006), 1000);
    assert.equal(sanitizeClientCloseCode(1011), 1000);
    assert.equal(sanitizeClientCloseCode(2999), 1000);
    assert.equal(sanitizeClientCloseCode(5000), 1000);
    assert.equal(sanitizeClientCloseCode(undefined), 1000);

    const exactBoundary = "a".repeat(123);
    assert.equal(truncateCloseReasonSafely(exactBoundary), exactBoundary);

    const truncatedEmoji = truncateCloseReasonSafely("🔥".repeat(40));
    assert.equal(Buffer.byteLength(truncatedEmoji, "utf-8"), 120);
    assert.equal(truncatedEmoji.includes("\uFFFD"), false);

    const loneSurrogate = truncateCloseReasonSafely("close-\uD800");
    assert.equal(loneSurrogate, "close-\uFFFD");

    assert.equal(isCleanWebSocketClose({ code: 1000, wasClean: true }), true);
    assert.equal(isCleanWebSocketClose({ code: 1001, wasClean: true }), true);
    assert.equal(isCleanWebSocketClose({ code: 1005, wasClean: false }), true);
    assert.equal(isCleanWebSocketClose({ code: 1006, wasClean: false }), false);
    assert.equal(isCleanWebSocketClose({ code: 1011, wasClean: true }), false);
    assert.equal(isCleanWebSocketClose({ code: 1002, wasClean: true }), false);
    assert.equal(isCleanWebSocketClose({ code: 1008, wasClean: true }), false);
    assert.equal(isCleanWebSocketClose(null), false);

    assert.equal(
      extractWebSocketErrorMessage({
        error: new Error("outer", { cause: new Error("inner cause") }),
      }),
      "inner cause",
    );
    assert.equal(
      extractWebSocketErrorMessage({ message: "fallback event error" }),
      "fallback event error",
    );
  });

  it("FramedWebSocketStream slices 100,000-byte payload into 25 bounded frames", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    const stream = new FramedWebSocketStream(mockWebSocket, {
      drainPollIntervalMs: 1,
    });
    const payload = randomBytes(100_000);

    await new Promise((resolve, reject) => {
      stream.write(payload, (error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });

    assert.equal(mockWebSocket.sentFrames.length, 25);
    for (let index = 0; index < 24; index++) {
      assert.equal(mockWebSocket.sentFrames[index].length, 4096);
    }
    assert.equal(mockWebSocket.sentFrames[24].length, 1696);
    assert.deepEqual(Buffer.concat(mockWebSocket.sentFrames), payload);

    await new Promise((resolve) => {
      stream.once("close", resolve);
      stream.end();
    });
  });

  it("FramedWebSocketStream bounds in-flight bufferedAmount below highWaterMarkBytes", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    mockWebSocket.holdDrain = true;

    const highWaterMarkBytes = 16 * 1024;
    const lowWaterMarkBytes = 4 * 1024;
    const stream = new FramedWebSocketStream(mockWebSocket, {
      maxChunkBytes: 4096,
      highWaterMarkBytes,
      lowWaterMarkBytes,
      drainPollIntervalMs: 5,
    });

    const payload = randomBytes(48 * 1024);
    const drainTimer = setInterval(() => {
      if (mockWebSocket.bufferedAmount > 0) {
        mockWebSocket.bufferedAmount = Math.max(
          0,
          mockWebSocket.bufferedAmount - 8192,
        );
      }
    }, 8);
    drainTimer.unref();

    try {
      await new Promise((resolve, reject) => {
        stream.write(payload, (error) => {
          if (error) {
            reject(error);
            return;
          }
          resolve();
        });
      });

      assert.ok(
        mockWebSocket.maxObservedBufferedAmount <= highWaterMarkBytes,
        `expected max bufferedAmount <= ${highWaterMarkBytes}, got ${mockWebSocket.maxObservedBufferedAmount}`,
      );
      assert.deepEqual(Buffer.concat(mockWebSocket.sentFrames), payload);

      mockWebSocket.holdDrain = false;
      mockWebSocket.bufferedAmount = 0;
      await new Promise((resolve) => {
        stream.once("close", resolve);
        stream.end();
      });
    } finally {
      clearInterval(drainTimer);
    }
  });

  it("FramedWebSocketStream waits for bufferedAmount drain before closing in _final", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    mockWebSocket.holdDrain = true;
    const stream = new FramedWebSocketStream(mockWebSocket, {
      drainPollIntervalMs: 5,
    });

    let closeTriggeredWhileBuffered = false;
    const originalClose = mockWebSocket.close.bind(mockWebSocket);
    mockWebSocket.close = (code, reason) => {
      if (mockWebSocket.bufferedAmount > 0) {
        closeTriggeredWhileBuffered = true;
      }
      originalClose(code, reason);
    };

    const writeDone = new Promise((resolve, reject) => {
      stream.write(Buffer.alloc(4096, 0x41), (error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });

    await writeDone;
    assert.equal(mockWebSocket.bufferedAmount, 4096);

    const closedPromise = new Promise((resolve) => {
      stream.once("close", resolve);
    });
    stream.end();

    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(mockWebSocket.closeCalls.length, 0);

    mockWebSocket.bufferedAmount = 0;
    await closedPromise;

    assert.equal(closeTriggeredWhileBuffered, false);
    assert.equal(mockWebSocket.closeCalls.length, 1);
    assert.equal(mockWebSocket.closeCalls[0].code, 1000);
  });

  it("FramedWebSocketStream finishes unresponsive close handshake after closeTimeoutMs", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    mockWebSocket.autoEchoClose = false;
    const stream = new FramedWebSocketStream(mockWebSocket, {
      closeTimeoutMs: 40,
      drainPollIntervalMs: 5,
    });

    const closedPromise = new Promise((resolve) => {
      stream.once("close", resolve);
    });

    stream.closeGracefully(1000, "Idle shutdown");
    await closedPromise;

    assert.equal(mockWebSocket.closeCalls.length, 1);
    assert.equal(stream.destroyed, true);
  });

  it("FramedWebSocketStream delivers outgoing close cleanly when abortWithClose runs mid-write", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    mockWebSocket.holdDrain = true;
    const stream = new FramedWebSocketStream(mockWebSocket, {
      highWaterMarkBytes: 16 * 1024,
      lowWaterMarkBytes: 4 * 1024,
      drainPollIntervalMs: 5,
    });
    stream.on("error", () => {});

    const writeSettled = new Promise((resolve) => {
      stream.write(Buffer.alloc(128 * 1024, 0x7a), () => resolve());
    });
    const streamClosed = new Promise((resolve) => {
      stream.once("close", resolve);
    });

    await new Promise((resolve) => setTimeout(resolve, 15));
    stream.abortWithClose(1000, "Runner stopped");

    await streamClosed;
    await writeSettled;

    assert.equal(mockWebSocket.closeCalls.length, 1);
    assert.equal(mockWebSocket.closeCalls[0].code, 1000);
    assert.equal(mockWebSocket.closeCalls[0].reason, "Runner stopped");
  });

  it("FramedWebSocketStream preserves unread buffered inbound messages when write side ends while paused", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    const stream = new FramedWebSocketStream(mockWebSocket, {
      drainPollIntervalMs: 5,
    });

    const expectedInbound = Buffer.from("BUFFERED_BEFORE_CLOSE");
    mockWebSocket.emitMessage(expectedInbound);

    const finishedPromise = new Promise((resolve) => {
      stream.once("finish", resolve);
    });
    stream.end();
    await finishedPromise;

    assert.equal(stream.destroyed, false);
    assert.equal(stream.readableLength, expectedInbound.length);

    const receivedChunks = [];
    const closedPromise = new Promise((resolve) => {
      stream.once("close", resolve);
    });
    stream.on("data", (chunk) => {
      receivedChunks.push(Buffer.from(chunk));
    });

    await closedPromise;
    assert.deepEqual(Buffer.concat(receivedChunks), expectedInbound);
  });

  it("FramedWebSocketStream preserves unread inbound messages when closeTimeoutMs expires before reading", async () => {
    const mockWebSocket = new MemoryWebSocketDouble(WEBSOCKET_READY_STATE_OPEN);
    mockWebSocket.autoEchoClose = false;
    const stream = new FramedWebSocketStream(mockWebSocket, {
      closeTimeoutMs: 30,
      drainPollIntervalMs: 5,
    });

    const expectedInbound = Buffer.from("BUFFERED_BEFORE_CLOSE_TIMEOUT");
    mockWebSocket.emitMessage(expectedInbound);

    const finishedPromise = new Promise((resolve) => {
      stream.once("finish", resolve);
    });
    stream.closeGracefully(1000, "Idle shutdown");
    await finishedPromise;

    await new Promise((resolve) => setTimeout(resolve, 40));
    assert.equal(stream.destroyed, false);
    assert.equal(stream.readableLength, expectedInbound.length);

    const receivedChunks = [];
    const closedPromise = new Promise((resolve) => {
      stream.once("close", resolve);
    });
    stream.on("data", (chunk) => {
      receivedChunks.push(Buffer.from(chunk));
    });

    await closedPromise;
    assert.deepEqual(Buffer.concat(receivedChunks), expectedInbound);
  });

  it("FramedWebSocketStream completes zero-byte flush barrier on closed socket and defers aborting CONNECTING writes", async () => {
    const closedWebSocket = new MemoryWebSocketDouble(
      WEBSOCKET_READY_STATE_CLOSED,
    );
    const closedStream = new FramedWebSocketStream(closedWebSocket);

    await new Promise((resolve, reject) => {
      closedStream.write(Buffer.alloc(0), (error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
    assert.equal(closedStream.hasFlushedAllWrites(), true);
    closedStream.destroy();

    const connectingWebSocket = new MemoryWebSocketDouble(
      WEBSOCKET_READY_STATE_CONNECTING,
    );
    connectingWebSocket.autoEchoClose = false;
    const connectingStream = new FramedWebSocketStream(connectingWebSocket, {
      closeTimeoutMs: 250,
    });
    connectingStream.on("error", () => {});

    let writeSettled = false;
    let writeError = null;
    connectingStream.write(Buffer.from("DEFERRED_BEFORE_OPEN"), (error) => {
      writeSettled = true;
      writeError = error ?? null;
    });

    connectingWebSocket.readyState = WEBSOCKET_READY_STATE_OPEN;
    connectingStream.abortWithClose(1000, "Aborted during open");
    connectingWebSocket.dispatchEvent(new Event("open"));
    await new Promise((resolve) => setTimeout(resolve, 10));

    assert.equal(connectingStream.destroyed, false);
    assert.equal(writeSettled, false);

    const streamClosed = new Promise((resolve) => {
      connectingStream.once("close", resolve);
    });
    connectingWebSocket.emitClose(1000, "Aborted during open", true);
    await streamClosed;

    assert.equal(writeSettled, true);
    assert.ok(writeError instanceof Error);
  });
});

describe("webssh Loopback Proxy Integration Tests", { timeout: 5_000 }, () => {
  it("runProxy streams 128 KiB bidirectionally with bounded FIN=1 binary frames and Cloudflare headers", async () => {
    const clientPayload = randomBytes(128 * 1024);
    const serverPayload = randomBytes(128 * 1024);
    const receivedFrames = [];
    let upgradeHeaders = null;

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      upgradeHeaders = connection.request.headers;
      let totalReceived = 0;

      connection.onFrame((frame) => {
        receivedFrames.push(frame);
        totalReceived += frame.payload.length;
        if (totalReceived === clientPayload.length) {
          for (let offset = 0; offset < serverPayload.length; offset += 4096) {
            connection.sendBinary(
              serverPayload.subarray(offset, offset + 4096),
            );
          }
          connection.sendClose(1000, "Done");
        }
      });
    });

    const inputStream = new PassThrough();
    const outputChunks = [];
    const outputStream = new Writable({
      highWaterMark: 4096,
      write(chunk, _encoding, callback) {
        outputChunks.push(Buffer.from(chunk));
        callback();
      },
    });
    const errorStream = new PassThrough();
    const readErrors = collectStreamOutput(errorStream);

    try {
      const proxyPromise = runProxy(loopbackServer.url, false, {
        inputStream,
        outputStream,
        errorStream,
        drainPollIntervalMs: 2,
        env: {
          CF_ACCESS_TOKEN: " test-access-token ",
          CF_CLIENT_ID: " test-client-id ",
          CF_CLIENT_SECRET: " test-client-secret ",
        },
      });

      inputStream.end(clientPayload);
      const exitCode = await proxyPromise;

      assert.equal(exitCode, 0);
      assert.equal(readErrors().toString("utf-8"), "");

      assert.equal(upgradeHeaders["cf-access-token"], "test-access-token");
      assert.equal(upgradeHeaders["cf-access-client-id"], "test-client-id");
      assert.equal(
        upgradeHeaders["cf-access-client-secret"],
        "test-client-secret",
      );

      assert.ok(receivedFrames.length >= 32);
      for (const frame of receivedFrames) {
        assert.equal(frame.fin, true);
        assert.equal(frame.rsv, 0);
        assert.equal(frame.opcode, 0x02);
        assert.equal(frame.masked, true);
        assert.ok(frame.payload.length <= MAXIMUM_FRAME_PAYLOAD_BYTES);
      }

      const reassembledClient = Buffer.concat(
        receivedFrames.map((frame) => frame.payload),
      );
      assert.deepEqual(reassembledClient, clientPayload);
      assert.deepEqual(Buffer.concat(outputChunks), serverPayload);
    } finally {
      await loopbackServer.close();
    }
  });

  it("runProxy preserves WebSocket across stdin EOF until trailing server frames arrive", async () => {
    const requestPayload = Buffer.from("SSH_COMMAND_REQUEST");
    const trailingResponse = Buffer.from("TRAILING_STDOUT_PAYLOAD");
    let clientClosedPrematurely = false;

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onClientClose((closeInfo) => {
        if (closeInfo.initiatedByClient) {
          clientClosedPrematurely = true;
        }
      });
      connection.onFrame((frame) => {
        if (frame.payload.equals(requestPayload)) {
          const responseTimer = setTimeout(() => {
            connection.sendBinary(trailingResponse);
            connection.sendClose(1000, "Command complete");
          }, 40);
          responseTimer.unref();
        }
      });
    });

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();
    const readOutput = collectStreamOutput(outputStream);
    const readErrors = collectStreamOutput(errorStream);

    try {
      const proxyPromise = runProxy(loopbackServer.url, false, {
        inputStream,
        outputStream,
        errorStream,
        halfCloseTimeoutMs: 500,
        env: {},
      });

      inputStream.end(requestPayload);
      const exitCode = await proxyPromise;

      assert.equal(exitCode, 0);
      assert.equal(clientClosedPrematurely, false);
      assert.deepEqual(readOutput(), trailingResponse);
      assert.equal(readErrors().toString("utf-8"), "");
    } finally {
      await loopbackServer.close();
    }
  });

  it("runProxy initiates graceful Close when half-close idle timeout elapses", async () => {
    let receivedCloseFrame = null;

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onClientClose((closeInfo) => {
        receivedCloseFrame = closeInfo;
      });
    });

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();

    try {
      const proxyPromise = runProxy(loopbackServer.url, false, {
        inputStream,
        outputStream,
        errorStream,
        halfCloseTimeoutMs: 60,
        closeTimeoutMs: 250,
        env: {},
      });

      inputStream.end(Buffer.from("HALF_CLOSE_IDLE_TEST"));
      const exitCode = await proxyPromise;

      assert.equal(exitCode, 0);
      assert.deepEqual(receivedCloseFrame, {
        code: 1000,
        reason: "Half-close idle timeout",
        initiatedByClient: true,
      });
    } finally {
      await loopbackServer.close();
    }
  });

  it("runProxy exits with code 1 when peer sends RFC 6455 error close code 1011", async () => {
    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onFrame(() => {
        connection.sendClose(1011, "Upstream target failure");
      });
    });

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();

    try {
      const proxyPromise = runProxy(loopbackServer.url, false, {
        inputStream,
        outputStream,
        errorStream,
        env: {},
      });

      inputStream.write(Buffer.from("TRIGGER_REMOTE_ERROR"));
      const exitCode = await proxyPromise;

      assert.equal(exitCode, 1);
    } finally {
      await loopbackServer.close();
    }
  });

  it("runProxy exits with code 1 on abrupt TCP disconnect without close frame", async () => {
    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onFrame(() => {
        connection.socket.destroy();
      });
    });

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();

    try {
      const proxyPromise = runProxy(loopbackServer.url, false, {
        inputStream,
        outputStream,
        errorStream,
        env: {},
      });

      inputStream.write(Buffer.from("TRIGGER_ABRUPT_DROP"));
      const exitCode = await proxyPromise;

      assert.equal(exitCode, 1);
    } finally {
      await loopbackServer.close();
    }
  });

  it("runProxy sends graceful Close and exits with code 0 on downstream EPIPE", async () => {
    let clientClosePromiseResolve;
    const clientClosePromise = new Promise((resolve) => {
      clientClosePromiseResolve = resolve;
    });

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onClientClose((closeInfo) => {
        clientClosePromiseResolve(closeInfo);
      });
      connection.sendBinary(Buffer.from("INITIAL_OUTPUT"));
    });

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();

    const triggerEpipe = new Promise((resolve) => {
      outputStream.once("data", () => {
        queueMicrotask(resolve);
      });
    });

    try {
      const proxyPromise = runProxy(loopbackServer.url, false, {
        inputStream,
        outputStream,
        errorStream,
        closeTimeoutMs: 250,
        env: {},
      });

      await triggerEpipe;
      const epipeError = Object.assign(new Error("broken pipe"), {
        code: "EPIPE",
      });
      outputStream.emit("error", epipeError);

      const exitCode = await proxyPromise;
      const receivedClose = await clientClosePromise;

      assert.equal(exitCode, 0);
      assert.equal(receivedClose.code, 1000);
    } finally {
      await loopbackServer.close();
    }
  });

  it("runProxy aborts and exits with code 1 when HTTP upgrade stalls past connectionTimeoutMs", async () => {
    const openSockets = new Set();
    const stalledServer = net.createServer((socket) => {
      openSockets.add(socket);
      socket.on("close", () => {
        openSockets.delete(socket);
      });
      socket.on("error", () => {});
    });

    await new Promise((resolve) => {
      stalledServer.listen(0, "127.0.0.1", resolve);
    });
    const address = stalledServer.address();

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();
    const readErrors = collectStreamOutput(errorStream);

    try {
      const exitCode = await runProxy(
        `ws://127.0.0.1:${address.port}/stalled`,
        false,
        {
          inputStream,
          outputStream,
          errorStream,
          connectionTimeoutMs: 60,
          env: {},
        },
      );

      assert.equal(exitCode, 1);
      assert.match(readErrors().toString("utf-8"), /timed out/);
    } finally {
      for (const socket of openSockets) {
        socket.destroy();
      }
      await new Promise((resolve) => {
        stalledServer.close(() => resolve());
      });
    }
  });

  it("runProxy exits with code 0 and empty stderr when origin closes TCP without Close frame after stdin EOF", async (t) => {
    const requestPayload = Buffer.from("SSH_COMMAND_REQUEST");
    const trailingResponse = Buffer.from("TRAILING_STDOUT_PAYLOAD");

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onFrame((frame) => {
        if (frame.payload.equals(requestPayload)) {
          connection.sendBinary(trailingResponse);
          connection.socket.end();
        }
      });
    });
    t.after(() => loopbackServer.close());

    const inputStream = new PassThrough();
    const outputStream = new PassThrough();
    const errorStream = new PassThrough();
    const readOutput = collectStreamOutput(outputStream);
    const readErrors = collectStreamOutput(errorStream);

    const proxyPromise = runProxy(loopbackServer.url, false, {
      inputStream,
      outputStream,
      errorStream,
      halfCloseTimeoutMs: 500,
      env: {},
    });

    inputStream.end(requestPayload);
    const exitCode = await proxyPromise;

    assert.equal(exitCode, 0);
    assert.deepEqual(readOutput(), trailingResponse);
    assert.equal(readErrors().toString("utf-8"), "");
  });

  it("runProxy flushes trailing server output through backpressured stdout before exiting 1 on mid-session abrupt disconnect", async (t) => {
    const serverPayload = randomBytes(64 * 1024);

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onFrame(() => {
        for (let offset = 0; offset < serverPayload.length; offset += 4096) {
          connection.sendBinary(serverPayload.subarray(offset, offset + 4096));
        }
        connection.socket.end();
      });
    });
    t.after(() => loopbackServer.close());

    const inputStream = new PassThrough();
    const outputChunks = [];
    const outputStream = new Writable({
      highWaterMark: 4096,
      write(chunk, _encoding, callback) {
        outputChunks.push(Buffer.from(chunk));
        setTimeout(callback, 2);
      },
    });
    const errorStream = new PassThrough();

    const proxyPromise = runProxy(loopbackServer.url, false, {
      inputStream,
      outputStream,
      errorStream,
      env: {},
    });

    inputStream.write(Buffer.from("START_SESSION"));
    const exitCode = await proxyPromise;

    assert.equal(exitCode, 1);
    const actualOutput = Buffer.concat(outputChunks);
    assert.equal(actualOutput.length, serverPayload.length);
    assert.equal(actualOutput.equals(serverPayload), true);
  });

  it("runProxy flushes async sub-highWaterMark stdout writes before resolving", {
    timeout: 500,
  }, async (t) => {
    const trailingPayload = Buffer.from("ASYNC_SUB_HWM_TRAILING");

    const loopbackServer = await createLoopbackWebSocketServer((connection) => {
      connection.onFrame(() => {
        connection.sendBinary(trailingPayload);
        connection.sendClose(1000, "Done");
      });
    });
    t.after(() => loopbackServer.close());

    const inputStream = new PassThrough();
    const outputChunks = [];
    const outputStream = new Writable({
      highWaterMark: 16 * 1024,
      write(chunk, _encoding, callback) {
        outputChunks.push(Buffer.from(chunk));
        setTimeout(callback, 15);
      },
    });
    const errorStream = new PassThrough();

    const proxyPromise = runProxy(loopbackServer.url, false, {
      inputStream,
      outputStream,
      errorStream,
      env: {},
    });

    inputStream.end(Buffer.from("REQ"));
    const exitCode = await proxyPromise;

    assert.equal(exitCode, 0);
    assert.deepEqual(Buffer.concat(outputChunks), trailingPayload);
  });

  it("runProxy logs explicit WebSocket error and exits 1 after draining backpressured stdout even after stdin EOF", async () => {
    const serverPayload = randomBytes(64 * 1024);

    class ScriptedErrorWebSocket extends MemoryWebSocketDouble {
      constructor() {
        super(WEBSOCKET_READY_STATE_CONNECTING);
        queueMicrotask(() => this.emitOpen());
      }

      send(data) {
        super.send(data);
        for (let offset = 0; offset < serverPayload.length; offset += 4096) {
          this.emitMessage(serverPayload.subarray(offset, offset + 4096));
        }
        this.readyState = WEBSOCKET_READY_STATE_CLOSED;
        const errorEvent = new Event("error");
        errorEvent.error = new Error("ECONNRESET");
        this.dispatchEvent(errorEvent);
        this.emitClose(1006, "", false);
      }
    }

    const inputStream = new PassThrough();
    const outputChunks = [];
    const outputStream = new Writable({
      highWaterMark: 4096,
      write(chunk, _encoding, callback) {
        outputChunks.push(Buffer.from(chunk));
        setTimeout(callback, 2);
      },
    });
    const errorStream = new PassThrough();
    const readErrors = collectStreamOutput(errorStream);

    const proxyPromise = runProxy("wss://example.com/ssh", false, {
      WebSocketConstructor: ScriptedErrorWebSocket,
      inputStream,
      outputStream,
      errorStream,
      halfCloseTimeoutMs: 500,
      env: {},
    });

    inputStream.end(Buffer.from("REQ"));
    const exitCode = await proxyPromise;

    assert.equal(exitCode, 1);
    assert.match(
      readErrors().toString("utf-8"),
      /Connection error: ECONNRESET/,
    );
    const actualOutput = Buffer.concat(outputChunks);
    assert.equal(actualOutput.length, serverPayload.length);
    assert.equal(actualOutput.equals(serverPayload), true);
  });
});
