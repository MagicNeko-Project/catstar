#!/usr/bin/env node

import { Buffer } from "node:buffer";
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { Duplex } from "node:stream";
import { StringDecoder } from "node:string_decoder";

const MAXIMUM_FRAME_PAYLOAD_BYTES = 4096;
const CONNECTION_TIMEOUT_MILLISECONDS = 10_000;
const BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES = 64 * 1024;
const BUFFERED_AMOUNT_LOW_WATERMARK_BYTES = 16 * 1024;
const DRAIN_THROTTLE_DELAY_MILLISECONDS = 10;
const WEBSOCKET_READY_STATE_CONNECTING = 0;
const WEBSOCKET_READY_STATE_OPEN = 1;
const WEBSOCKET_READY_STATE_CLOSING = 2;
const WEBSOCKET_READY_STATE_CLOSED = 3;
const WEBSOCKET_CLOSE_TIMEOUT_MILLISECONDS = 2_000;
const HALF_CLOSE_TIMEOUT_MILLISECONDS = 10_000;
// RFC 6455 section 5.5 caps control payloads at 125 bytes minus 2 bytes for the close status code.
const MAX_WEBSOCKET_CLOSE_REASON_BYTES = 123;

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

function buildProxyCommand(
  nodeBinaryPath,
  scriptPath,
  allowInsecureCertificate,
) {
  const insecureFlag = allowInsecureCertificate ? " --insecure" : "";
  return `"${nodeBinaryPath}" "${scriptPath}" --ws-proxy "%h"${insecureFlag}`;
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
  const proxyCommand = buildProxyCommand(nodeBinaryPath, scriptPath, insecure);

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

  sshChildProcess.on("exit", (exitCode, signal) => {
    if (exitCode !== null) {
      process.exit(exitCode);
    }
    const signalNumber = signal ? os.constants.signals[signal] : undefined;
    process.exit(signalNumber ? 128 + signalNumber : 1);
  });
}

function resolveWebSocketUrl(targetHost) {
  const trimmedTarget = typeof targetHost === "string" ? targetHost.trim() : "";
  if (!trimmedTarget) {
    throw new Error("Target host must be a non-empty string.");
  }

  let candidateUrl;
  if (trimmedTarget.includes("://")) {
    candidateUrl = trimmedTarget;
  } else {
    const slashIndex = trimmedTarget.indexOf("/");
    const hostSegment =
      slashIndex === -1 ? trimmedTarget : trimmedTarget.slice(0, slashIndex);
    const pathSuffix = slashIndex === -1 ? "" : trimmedTarget.slice(slashIndex);
    const isUnbracketedIpv6 =
      !hostSegment.startsWith("[") &&
      hostSegment.indexOf(":") !== hostSegment.lastIndexOf(":");
    candidateUrl = isUnbracketedIpv6
      ? `wss://[${hostSegment}]${pathSuffix}`
      : `wss://${trimmedTarget}`;
  }

  let parsedUrl;
  try {
    parsedUrl = new URL(candidateUrl);
  } catch {
    throw new Error(`Invalid WebSocket target URL: "${trimmedTarget}".`);
  }

  if (
    (parsedUrl.protocol !== "ws:" && parsedUrl.protocol !== "wss:") ||
    !parsedUrl.hostname
  ) {
    throw new Error(
      `Unsupported WebSocket protocol in target URL: "${candidateUrl}".`,
    );
  }

  return candidateUrl;
}

function buildCloudflareAccessHeaders(environment = process.env) {
  const requestHeaders = {};

  const accessToken =
    typeof environment.CF_ACCESS_TOKEN === "string"
      ? environment.CF_ACCESS_TOKEN.trim()
      : "";
  if (accessToken) {
    requestHeaders["CF-Access-Token"] = accessToken;
  }

  const clientId =
    typeof environment.CF_CLIENT_ID === "string"
      ? environment.CF_CLIENT_ID.trim()
      : "";
  const clientSecret =
    typeof environment.CF_CLIENT_SECRET === "string"
      ? environment.CF_CLIENT_SECRET.trim()
      : "";
  if (clientId && clientSecret) {
    requestHeaders["CF-Access-Client-Id"] = clientId;
    requestHeaders["CF-Access-Client-Secret"] = clientSecret;
  }

  return requestHeaders;
}

function sanitizeClientCloseCode(code) {
  // WHATWG WebSocket.close() rejects codes outside {1000} and 3000..4999 with InvalidAccessError.
  if (
    typeof code === "number" &&
    Number.isInteger(code) &&
    (code === 1000 || (code >= 3000 && code <= 4999))
  ) {
    return code;
  }
  return 1000;
}

function truncateCloseReasonSafely(
  reason,
  maximumBytes = MAX_WEBSOCKET_CLOSE_REASON_BYTES,
) {
  if (typeof reason !== "string" || reason.length === 0 || maximumBytes <= 0) {
    return "";
  }
  const wellFormedReason = reason.toWellFormed();
  if (Buffer.byteLength(wellFormedReason, "utf-8") <= maximumBytes) {
    return wellFormedReason;
  }
  // StringDecoder omits incomplete trailing multi-byte UTF-8 sequences so close reasons remain valid UTF-8.
  const decoder = new StringDecoder("utf-8");
  return decoder.write(
    Buffer.from(wellFormedReason, "utf-8").subarray(0, maximumBytes),
  );
}

function isCleanWebSocketClose(closeEvent) {
  if (!closeEvent) {
    return false;
  }
  // Error codes like 1002, 1008, and 1011 complete a valid handshake (wasClean=true) yet indicate remote failure.
  return (
    closeEvent.code === 1000 ||
    closeEvent.code === 1001 ||
    closeEvent.code === 1005
  );
}

function extractWebSocketErrorMessage(errorEvent) {
  const underlyingError = errorEvent?.error ?? errorEvent;
  const causeMessage = underlyingError?.cause?.message;
  if (typeof causeMessage === "string" && causeMessage.length > 0) {
    return causeMessage;
  }
  const causeCode = underlyingError?.cause?.code;
  if (typeof causeCode === "string" && causeCode.length > 0) {
    return causeCode;
  }
  if (
    typeof underlyingError?.message === "string" &&
    underlyingError.message.length > 0
  ) {
    return underlyingError.message;
  }
  if (
    typeof underlyingError?.code === "string" &&
    underlyingError.code.length > 0
  ) {
    return underlyingError.code;
  }
  if (
    typeof errorEvent?.message === "string" &&
    errorEvent.message.length > 0
  ) {
    return errorEvent.message;
  }
  return "Connection error";
}

function toDuplexBuffer(chunk, encoding) {
  if (Buffer.isBuffer(chunk)) {
    return chunk;
  }
  if (ArrayBuffer.isView(chunk)) {
    return Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength);
  }
  if (typeof chunk === "string") {
    return Buffer.from(chunk, encoding);
  }
  if (chunk instanceof ArrayBuffer) {
    return Buffer.from(chunk);
  }
  throw new TypeError(
    "Unsupported chunk type written to FramedWebSocketStream.",
  );
}

function messageDataToBuffer(messageData) {
  if (Buffer.isBuffer(messageData)) {
    return messageData;
  }
  if (ArrayBuffer.isView(messageData)) {
    return Buffer.from(
      messageData.buffer,
      messageData.byteOffset,
      messageData.byteLength,
    );
  }
  if (typeof messageData === "string") {
    return Buffer.from(messageData, "utf-8");
  }
  if (messageData instanceof ArrayBuffer) {
    return Buffer.from(messageData);
  }
  return Buffer.from(messageData);
}

function normalizeError(error) {
  return error instanceof Error ? error : new Error(String(error));
}

class FramedWebSocketStream extends Duplex {
  constructor(webSocket, options = {}) {
    const maxChunkBytes = options.maxChunkBytes ?? MAXIMUM_FRAME_PAYLOAD_BYTES;
    if (!Number.isInteger(maxChunkBytes) || maxChunkBytes < 1) {
      throw new RangeError(
        `maxChunkBytes must be a positive integer, received ${maxChunkBytes}.`,
      );
    }

    const highWaterMarkBytes =
      options.highWaterMarkBytes ?? BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES;
    if (!Number.isInteger(highWaterMarkBytes) || highWaterMarkBytes < 1) {
      throw new RangeError(
        `highWaterMarkBytes must be a positive integer, received ${highWaterMarkBytes}.`,
      );
    }

    const lowWaterMarkBytes =
      options.lowWaterMarkBytes ?? BUFFERED_AMOUNT_LOW_WATERMARK_BYTES;
    if (
      !Number.isInteger(lowWaterMarkBytes) ||
      lowWaterMarkBytes < 0 ||
      lowWaterMarkBytes >= highWaterMarkBytes
    ) {
      throw new RangeError(
        `lowWaterMarkBytes must be a non-negative integer less than highWaterMarkBytes (${highWaterMarkBytes}), received ${lowWaterMarkBytes}.`,
      );
    }

    const closeTimeoutMs =
      options.closeTimeoutMs ?? WEBSOCKET_CLOSE_TIMEOUT_MILLISECONDS;
    if (!Number.isFinite(closeTimeoutMs) || closeTimeoutMs < 0) {
      throw new RangeError(
        `closeTimeoutMs must be non-negative, received ${closeTimeoutMs}.`,
      );
    }

    const drainPollIntervalMs =
      options.drainPollIntervalMs ?? DRAIN_THROTTLE_DELAY_MILLISECONDS;
    if (!Number.isFinite(drainPollIntervalMs) || drainPollIntervalMs <= 0) {
      throw new RangeError(
        `drainPollIntervalMs must be positive, received ${drainPollIntervalMs}.`,
      );
    }

    super({
      allowHalfOpen: true,
      autoDestroy: true,
      emitClose: true,
      objectMode: false,
      readableHighWaterMark: highWaterMarkBytes,
      writableHighWaterMark: highWaterMarkBytes,
    });

    this.webSocket = webSocket;
    this.maxChunkBytes = maxChunkBytes;
    this.highWaterMarkBytes = highWaterMarkBytes;
    this.lowWaterMarkBytes = lowWaterMarkBytes;
    this.closeTimeoutMs = closeTimeoutMs;
    this.drainPollIntervalMs = drainPollIntervalMs;
    this.pendingConnectingAborts = new Set();
    this.pendingWriteAborts = new Set();
    this.pendingDrainWaiters = new Set();
    this.activeWriteWaiters = new Set();
    this.activeWriteCount = 0;
    this.closeTimer = null;
    this.abortCloseListener = null;
    this.finalCloseListener = null;
    this.pendingFinalCallback = null;
    this.peerCloseEvent = null;
    this.closeCode = 1000;
    this.closeReason = undefined;
    this.initiatedGracefulClose = false;
    this.isAborting = false;
    this.isCleanedUp = false;

    this.webSocket.binaryType = "arraybuffer";

    this.once("finish", () => {
      this.completeReadableEofIfIdle();
    });

    this.handleWebSocketMessage = (messageEvent) => {
      if (this.destroyed || this.readableEnded || this.isAborting) {
        return;
      }
      const payload = messageDataToBuffer(messageEvent.data);
      if (payload.length === 0) {
        return;
      }
      this.push(payload);
    };

    this.handleWebSocketError = (errorEvent) => {
      const connectionError = new Error(
        extractWebSocketErrorMessage(errorEvent),
      );
      this.wakeDrainWaiters();
      if (!this.destroyed && !this.isAborting) {
        this.destroy(connectionError);
      }
    };

    this.handleWebSocketClose = (closeEvent) => {
      this.peerCloseEvent = {
        code: closeEvent?.code ?? 1005,
        reason: typeof closeEvent?.reason === "string" ? closeEvent.reason : "",
        wasClean: Boolean(closeEvent?.wasClean),
      };
      this.wakeDrainWaiters();
      if (!this.destroyed && !this.readableEnded) {
        this.push(null);
      }
      this.completeReadableEofIfIdle();
    };

    if (this.webSocket.readyState === WEBSOCKET_READY_STATE_CLOSED) {
      this.peerCloseEvent = { code: 1005, reason: "", wasClean: false };
      this.push(null);
    } else {
      this.webSocket.addEventListener("message", this.handleWebSocketMessage);
      this.webSocket.addEventListener("error", this.handleWebSocketError);
      this.webSocket.addEventListener("close", this.handleWebSocketClose);
    }
  }

  getPeerCloseEvent() {
    return this.peerCloseEvent;
  }

  didInitiateGracefulClose() {
    return this.initiatedGracefulClose;
  }

  closeGracefully(code = 1000, reason) {
    this.initiatedGracefulClose = true;
    this.closeCode = sanitizeClientCloseCode(code);
    this.closeReason =
      reason !== undefined ? truncateCloseReasonSafely(reason) : undefined;

    if (this.destroyed || this.isAborting) {
      return;
    }
    if (!this.writableEnded) {
      this.end();
      return;
    }
    this.ensureBoundedCloseHandshake();
  }

  abortWithClose(code = 1000, reason) {
    this.closeCode = sanitizeClientCloseCode(code);
    this.closeReason =
      reason !== undefined ? truncateCloseReasonSafely(reason) : undefined;

    if (this.destroyed || this.isAborting) {
      return;
    }
    this.isAborting = true;
    this.wakeDrainWaiters();

    if (
      this.webSocket.readyState === WEBSOCKET_READY_STATE_OPEN ||
      this.webSocket.readyState === WEBSOCKET_READY_STATE_CLOSING
    ) {
      const onCloseComplete = () => {
        this.clearCloseTimer();
        if (this.abortCloseListener !== null) {
          this.webSocket.removeEventListener("close", this.abortCloseListener);
          this.abortCloseListener = null;
        }
        if (!this.destroyed) {
          this.destroy();
        }
      };
      this.abortCloseListener = onCloseComplete;
      this.webSocket.addEventListener("close", onCloseComplete);
      this.ensureBoundedCloseHandshake();
      return;
    }

    this.destroy();
  }

  async flushOutbound() {
    if (this.destroyed || this.isAborting) {
      return;
    }

    while (
      !this.destroyed &&
      !this.isAborting &&
      (this.activeWriteCount > 0 ||
        this.writableLength > 0 ||
        this.writableNeedDrain)
    ) {
      await new Promise((resolve) => {
        let settled = false;
        const done = () => {
          if (settled) {
            return;
          }
          settled = true;
          this.activeWriteWaiters.delete(done);
          this.removeListener("drain", done);
          this.removeListener("close", done);
          this.removeListener("error", done);
          this.removeListener("finish", done);
          resolve();
        };

        this.activeWriteWaiters.add(done);
        this.once("drain", done);
        this.once("close", done);
        this.once("error", done);
        this.once("finish", done);
      });
    }

    if (
      !this.destroyed &&
      !this.isAborting &&
      this.webSocket.readyState === WEBSOCKET_READY_STATE_OPEN &&
      this.webSocket.bufferedAmount > 0
    ) {
      await this.waitForBufferedAmountDrain(0);
    }
  }

  _read() {
    // Incoming WebSocket messages are pushed as they arrive from the EventTarget listener.
  }

  _write(chunk, encoding, callback) {
    if (this.destroyed) {
      callback(new Error("WebSocket stream destroyed."));
      return;
    }
    if (this.isAborting) {
      // Defer failing writes until abortWithClose finishes the Close handshake in _destroy(),
      // so autoDestroy does not close the socket before the Close frame is flushed.
      this.pendingWriteAborts.add(callback);
      return;
    }

    let buffer;
    try {
      buffer = toDuplexBuffer(chunk, encoding);
    } catch (error) {
      callback(normalizeError(error));
      return;
    }

    if (this.webSocket.readyState === WEBSOCKET_READY_STATE_CONNECTING) {
      this.waitForOpen(
        () => {
          if (this.destroyed || this.isAborting) {
            callback(new Error("WebSocket stream destroyed before open."));
            return;
          }
          void this.sendBufferSlices(buffer, callback);
        },
        () => callback(new Error("WebSocket closed before opening.")),
        callback,
      );
      return;
    }

    if (this.webSocket.readyState !== WEBSOCKET_READY_STATE_OPEN) {
      callback(
        new Error(
          `Cannot write to WebSocket in readyState ${this.webSocket.readyState}.`,
        ),
      );
      return;
    }

    void this.sendBufferSlices(buffer, callback);
  }

  _final(callback) {
    this.initiatedGracefulClose = true;
    if (
      this.destroyed ||
      this.isAborting ||
      this.webSocket.readyState === WEBSOCKET_READY_STATE_CLOSED
    ) {
      callback(null);
      return;
    }

    if (this.webSocket.readyState === WEBSOCKET_READY_STATE_CONNECTING) {
      this.waitForOpen(
        () => this._final(callback),
        () => callback(null),
        callback,
      );
      return;
    }

    void this.finalizeAfterDrain(callback);
  }

  _destroy(error, callback) {
    if (this.isCleanedUp) {
      callback(error);
      return;
    }
    this.isCleanedUp = true;

    this.clearCloseTimer();
    this.detachWebSocketListeners();
    this.wakeDrainWaiters();

    if (this.pendingFinalCallback !== null) {
      const pendingCallback = this.pendingFinalCallback;
      this.pendingFinalCallback = null;
      pendingCallback(
        error ??
          new Error("WebSocket stream destroyed before close completed."),
      );
    }

    const destroyError = error ?? new Error("WebSocket stream destroyed.");
    for (const abortConnecting of Array.from(this.pendingConnectingAborts)) {
      abortConnecting(destroyError);
    }
    this.pendingConnectingAborts.clear();

    for (const abortWrite of Array.from(this.pendingWriteAborts)) {
      abortWrite(destroyError);
    }
    this.pendingWriteAborts.clear();

    this.closeWebSocketSafely(this.closeCode, this.closeReason);
    callback(error);
  }

  wakeDrainWaiters() {
    for (const notifyDrain of Array.from(this.pendingDrainWaiters)) {
      notifyDrain();
    }
    this.pendingDrainWaiters.clear();
  }

  notifyWriteWaiters() {
    for (const notifyWrite of Array.from(this.activeWriteWaiters)) {
      notifyWrite();
    }
  }

  completeReadableEofIfIdle() {
    if (
      !this.destroyed &&
      this.peerCloseEvent !== null &&
      this.writableFinished &&
      this.readableLength === 0 &&
      this.readableFlowing === null
    ) {
      // Drain buffered EOF when no readable consumer is attached so autoDestroy completes cleanup.
      this.resume();
    }
  }

  clearCloseTimer() {
    if (this.closeTimer !== null) {
      clearTimeout(this.closeTimer);
      this.closeTimer = null;
    }
  }

  detachWebSocketListeners() {
    if (this.abortCloseListener !== null) {
      this.webSocket.removeEventListener("close", this.abortCloseListener);
      this.abortCloseListener = null;
    }
    if (this.finalCloseListener !== null) {
      this.webSocket.removeEventListener("close", this.finalCloseListener);
      this.finalCloseListener = null;
    }
    this.webSocket.removeEventListener("message", this.handleWebSocketMessage);
    this.webSocket.removeEventListener("error", this.handleWebSocketError);
    this.webSocket.removeEventListener("close", this.handleWebSocketClose);
  }

  closeWebSocketSafely(code = 1000, reason) {
    const state = this.webSocket.readyState;
    if (
      state === WEBSOCKET_READY_STATE_CLOSED ||
      state === WEBSOCKET_READY_STATE_CLOSING
    ) {
      return;
    }
    const sanitizedCode = sanitizeClientCloseCode(code);
    try {
      if (reason !== undefined) {
        this.webSocket.close(sanitizedCode, truncateCloseReasonSafely(reason));
      } else {
        this.webSocket.close(sanitizedCode);
      }
    } catch {
      // Ignore close errors if the underlying socket has already transitioned.
    }
  }

  forceLocalCloseAfterTimeout() {
    this.clearCloseTimer();
    this.detachWebSocketListeners();
    this.wakeDrainWaiters();

    if (this.pendingFinalCallback !== null) {
      const pendingCallback = this.pendingFinalCallback;
      this.pendingFinalCallback = null;
      pendingCallback(null);
    }

    if (this.isAborting) {
      if (!this.destroyed) {
        this.destroy();
      }
      return;
    }

    if (!this.destroyed && !this.readableEnded) {
      this.push(null);
    }
    this.completeReadableEofIfIdle();

    process.nextTick(() => {
      if (!this.destroyed && this.readableLength === 0) {
        this.destroy();
      }
    });
  }

  ensureBoundedCloseHandshake() {
    const currentState = this.webSocket.readyState;
    if (currentState === WEBSOCKET_READY_STATE_CLOSED) {
      return;
    }
    if (currentState === WEBSOCKET_READY_STATE_CONNECTING) {
      this.closeWebSocketSafely(this.closeCode, this.closeReason);
    } else if (currentState === WEBSOCKET_READY_STATE_OPEN) {
      try {
        if (this.closeReason !== undefined) {
          this.webSocket.close(this.closeCode, this.closeReason);
        } else {
          this.webSocket.close(this.closeCode);
        }
      } catch {
        this.forceLocalCloseAfterTimeout();
        return;
      }
    }

    if (
      this.closeTimer === null &&
      this.webSocket.readyState !== WEBSOCKET_READY_STATE_CLOSED
    ) {
      this.closeTimer = setTimeout(() => {
        this.closeTimer = null;
        this.forceLocalCloseAfterTimeout();
      }, this.closeTimeoutMs);
      this.closeTimer.unref();
    }
  }

  async finalizeAfterDrain(callback) {
    // Wait for queued frames in bufferedAmount to drain before calling webSocket.close(),
    // because WHATWG WebSocket sends Close after queued data or may abort pending sends on close.
    await this.waitForBufferedAmountDrain(0);

    if (
      this.destroyed ||
      this.isAborting ||
      this.webSocket.readyState === WEBSOCKET_READY_STATE_CLOSED
    ) {
      callback(null);
      return;
    }

    this.pendingFinalCallback = callback;
    const onClosed = () => {
      this.clearCloseTimer();
      if (this.finalCloseListener !== null) {
        this.webSocket.removeEventListener("close", this.finalCloseListener);
        this.finalCloseListener = null;
      }
      const pendingCallback = this.pendingFinalCallback;
      this.pendingFinalCallback = null;
      if (pendingCallback !== null) {
        pendingCallback(null);
      }
    };

    this.finalCloseListener = onClosed;
    this.webSocket.addEventListener("close", onClosed);
    this.ensureBoundedCloseHandshake();
  }

  waitForBufferedAmountDrain(targetBytes) {
    if (
      this.destroyed ||
      this.isAborting ||
      this.webSocket.readyState !== WEBSOCKET_READY_STATE_OPEN ||
      this.webSocket.bufferedAmount <= targetBytes
    ) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      let settled = false;
      let pollTimer = null;

      const finish = () => {
        if (settled) {
          return;
        }
        settled = true;
        if (pollTimer !== null) {
          clearTimeout(pollTimer);
          pollTimer = null;
        }
        this.pendingDrainWaiters.delete(finish);
        resolve();
      };

      this.pendingDrainWaiters.add(finish);

      const pollDrainState = () => {
        if (
          settled ||
          this.destroyed ||
          this.isAborting ||
          this.webSocket.readyState !== WEBSOCKET_READY_STATE_OPEN ||
          this.webSocket.bufferedAmount <= targetBytes
        ) {
          finish();
          return;
        }
        pollTimer = setTimeout(pollDrainState, this.drainPollIntervalMs);
      };

      pollTimer = setTimeout(pollDrainState, this.drainPollIntervalMs);
    });
  }

  waitForOpen(onOpenReady, onClosedBeforeOpen, onFailed) {
    const webSocket = this.webSocket;
    let settled = false;
    let cleanup = () => {};

    const abortConnecting = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      onFailed(error);
    };

    const onOpen = () => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      onOpenReady();
    };

    const onError = (errorEvent) =>
      abortConnecting(new Error(extractWebSocketErrorMessage(errorEvent)));
    const onClose = () => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      onClosedBeforeOpen();
    };

    cleanup = () => {
      this.pendingConnectingAborts.delete(abortConnecting);
      webSocket.removeEventListener("open", onOpen);
      webSocket.removeEventListener("error", onError);
      webSocket.removeEventListener("close", onClose);
    };

    this.pendingConnectingAborts.add(abortConnecting);
    webSocket.addEventListener("open", onOpen);
    webSocket.addEventListener("error", onError);
    webSocket.addEventListener("close", onClose);
  }

  async drainBufferedAmountWhileOpen() {
    await this.waitForBufferedAmountDrain(this.lowWaterMarkBytes);
    if (this.isAborting) {
      return "aborted";
    }
    if (
      this.destroyed ||
      this.webSocket.readyState !== WEBSOCKET_READY_STATE_OPEN
    ) {
      return "closed";
    }
    return "ok";
  }

  async sendBufferSlices(buffer, callback) {
    if (buffer.length === 0) {
      callback(null);
      return;
    }

    this.activeWriteCount++;
    let settled = false;
    let unregisterWriteAbort = () => {};

    const finish = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      unregisterWriteAbort();
      this.activeWriteCount--;
      this.notifyWriteWaiters();
      callback(error);
    };

    const abortWrite = (error) => {
      finish(error);
    };

    unregisterWriteAbort = () => {
      this.pendingWriteAborts.delete(abortWrite);
    };
    this.pendingWriteAborts.add(abortWrite);

    // 4 KiB standalone frames prevent multi-second RFC 6455 control-frame head-of-line stalls
    // and avoid Cloudflare Tunnel burst-window failures while bounding in-flight bufferedAmount.
    for (
      let bufferOffset = 0;
      bufferOffset < buffer.length;
      bufferOffset += this.maxChunkBytes
    ) {
      if (settled || this.isAborting) {
        return;
      }
      if (
        this.destroyed ||
        this.webSocket.readyState !== WEBSOCKET_READY_STATE_OPEN
      ) {
        finish(new Error("WebSocket closed during frame transmission."));
        return;
      }

      const sliceEnd = Math.min(
        bufferOffset + this.maxChunkBytes,
        buffer.length,
      );
      const slice = buffer.subarray(bufferOffset, sliceEnd);

      if (
        this.webSocket.bufferedAmount > 0 &&
        this.webSocket.bufferedAmount + slice.byteLength >
          this.highWaterMarkBytes
      ) {
        const drainState = await this.drainBufferedAmountWhileOpen();
        if (settled || drainState === "aborted") {
          return;
        }
        if (drainState === "closed") {
          finish(new Error("WebSocket closed during frame transmission."));
          return;
        }
      }

      try {
        this.webSocket.send(slice);
      } catch (sendError) {
        if (settled || this.isAborting) {
          return;
        }
        finish(normalizeError(sendError));
        return;
      }

      if (this.webSocket.bufferedAmount > this.highWaterMarkBytes) {
        const drainState = await this.drainBufferedAmountWhileOpen();
        if (settled || drainState === "aborted") {
          return;
        }
        if (drainState === "closed") {
          finish(new Error("WebSocket closed during frame transmission."));
          return;
        }
      }
    }

    finish(null);
  }
}

async function flushWritableStream(writableStream) {
  if (writableStream.destroyed || writableStream.writableFinished) {
    return;
  }

  if (
    !writableStream.writableNeedDrain &&
    writableStream.writableLength === 0
  ) {
    if (
      writableStream === process.stdout &&
      writableStream.writable &&
      !writableStream.writableEnded
    ) {
      await new Promise((resolve) => {
        try {
          writableStream.write("", () => resolve());
        } catch {
          resolve();
        }
      });
    }
    return;
  }

  await new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      writableStream.removeListener("drain", finish);
      writableStream.removeListener("finish", finish);
      writableStream.removeListener("close", finish);
      writableStream.removeListener("error", finish);
      resolve();
    };

    writableStream.once("drain", finish);
    writableStream.once("finish", finish);
    writableStream.once("close", finish);
    writableStream.once("error", finish);
  });
}

function waitForStreamClose(stream) {
  if (stream.destroyed || stream.closed) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const finish = () => {
      stream.removeListener("close", finish);
      stream.removeListener("error", finish);
      resolve();
    };
    stream.once("close", finish);
    stream.once("error", finish);
  });
}

function closeHandshakeSocketSafely(webSocket) {
  const state = webSocket.readyState;
  if (
    state === WEBSOCKET_READY_STATE_CLOSED ||
    state === WEBSOCKET_READY_STATE_CLOSING
  ) {
    return;
  }
  try {
    webSocket.close(1000);
  } catch {
    // Ignore close errors while aborting an incomplete handshake.
  }
}

function awaitWebSocketHandshake(
  webSocket,
  websocketUrl,
  inputStream,
  outputStream,
  errorStream,
  connectionTimeoutMs,
) {
  if (webSocket.readyState === WEBSOCKET_READY_STATE_OPEN) {
    return Promise.resolve({ connected: true, exitCode: 0 });
  }

  return new Promise((resolve) => {
    let settled = false;
    let connectionTimer = null;

    const cleanup = () => {
      if (connectionTimer !== null) {
        clearTimeout(connectionTimer);
        connectionTimer = null;
      }
      webSocket.removeEventListener("open", onOpen);
      webSocket.removeEventListener("error", onHandshakeError);
      webSocket.removeEventListener("close", onHandshakeClose);
      outputStream.removeListener("error", onOutputError);
      inputStream.removeListener("error", onInputError);
    };

    const finish = (result) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(result);
    };

    const onOpen = () => {
      finish({ connected: true, exitCode: 0 });
    };

    const onHandshakeError = (errorEvent) => {
      closeHandshakeSocketSafely(webSocket);
      errorStream.write(
        `Connection error: ${extractWebSocketErrorMessage(errorEvent)}\n`,
      );
      finish({ connected: false, exitCode: 1 });
    };

    const onHandshakeClose = (closeEvent) => {
      errorStream.write(
        `Connection error: closed before open (${closeEvent?.code ?? 1006})\n`,
      );
      finish({ connected: false, exitCode: 1 });
    };

    const onOutputError = (outputError) => {
      closeHandshakeSocketSafely(webSocket);
      if (outputError?.code === "EPIPE") {
        finish({ connected: false, exitCode: 0 });
        return;
      }
      errorStream.write(
        `stdout error: ${outputError?.message ?? String(outputError)}\n`,
      );
      finish({ connected: false, exitCode: 1 });
    };

    const onInputError = (inputError) => {
      closeHandshakeSocketSafely(webSocket);
      errorStream.write(
        `stdin error: ${inputError?.message ?? String(inputError)}\n`,
      );
      finish({ connected: false, exitCode: 1 });
    };

    connectionTimer = setTimeout(() => {
      connectionTimer = null;
      closeHandshakeSocketSafely(webSocket);
      errorStream.write(
        `Connection to ${websocketUrl} timed out after ${connectionTimeoutMs / 1000}s\n`,
      );
      finish({ connected: false, exitCode: 1 });
    }, connectionTimeoutMs);
    connectionTimer.unref();

    webSocket.addEventListener("open", onOpen);
    webSocket.addEventListener("error", onHandshakeError);
    webSocket.addEventListener("close", onHandshakeClose);
    outputStream.once("error", onOutputError);
    inputStream.once("error", onInputError);
  });
}

function coordinateProxySession(
  webSocketStream,
  inputStream,
  outputStream,
  errorStream,
  halfCloseTimeoutMs,
) {
  return new Promise((resolve) => {
    let settled = false;
    let inputEnded = false;
    let webSocketReadEnded = false;
    let halfCloseTimer = null;

    const clearHalfCloseTimer = () => {
      if (halfCloseTimer !== null) {
        clearTimeout(halfCloseTimer);
        halfCloseTimer = null;
      }
    };

    const armHalfCloseTimer = () => {
      if (settled || webSocketReadEnded) {
        return;
      }
      clearHalfCloseTimer();
      halfCloseTimer = setTimeout(() => {
        halfCloseTimer = null;
        if (!settled && !webSocketReadEnded) {
          webSocketStream.closeGracefully(1000, "Half-close idle timeout");
        }
      }, halfCloseTimeoutMs);
      halfCloseTimer.unref();
    };

    let detachSessionListeners = () => {};

    const completeFromRemote = async () => {
      if (settled) {
        return;
      }
      settled = true;
      clearHalfCloseTimer();
      detachSessionListeners();

      inputStream.unpipe(webSocketStream);
      inputStream.pause();
      webSocketStream.unpipe(outputStream);
      // Swallow late transport errors after teardown has begun.
      webSocketStream.on("error", () => {});

      await flushWritableStream(outputStream);

      const peerCloseEvent = webSocketStream.getPeerCloseEvent();
      const isCleanClose =
        peerCloseEvent !== null
          ? isCleanWebSocketClose(peerCloseEvent)
          : webSocketStream.didInitiateGracefulClose();

      if (!webSocketStream.destroyed) {
        webSocketStream.destroy();
      }

      resolve(isCleanClose ? 0 : 1);
    };

    const onInputEnd = () => {
      if (settled || inputEnded) {
        return;
      }
      inputEnded = true;
      inputStream.unpipe(webSocketStream);

      // Keep the outbound WebSocket open after local stdin EOF so trailing server responses
      // can finish arriving before an idle half-close timeout triggers a graceful Close frame.
      void (async () => {
        await webSocketStream.flushOutbound();
        if (!settled && !webSocketReadEnded) {
          armHalfCloseTimer();
        }
      })();
    };

    const onInputError = async (inputError) => {
      if (settled) {
        return;
      }
      settled = true;
      clearHalfCloseTimer();
      detachSessionListeners();

      inputStream.unpipe(webSocketStream);
      webSocketStream.unpipe(outputStream);
      webSocketStream.on("error", () => {});

      errorStream.write(
        `stdin error: ${inputError?.message ?? String(inputError)}\n`,
      );
      const closePromise = waitForStreamClose(webSocketStream);
      webSocketStream.abortWithClose(1000, "Input stream error");
      await closePromise;
      await flushWritableStream(outputStream);
      resolve(1);
    };

    const onOutputError = async (outputError) => {
      if (settled) {
        return;
      }
      settled = true;
      clearHalfCloseTimer();
      detachSessionListeners();

      inputStream.unpipe(webSocketStream);
      inputStream.pause();
      webSocketStream.unpipe(outputStream);
      webSocketStream.on("error", () => {});

      const closePromise = waitForStreamClose(webSocketStream);
      if (outputError?.code === "EPIPE") {
        webSocketStream.abortWithClose(1000, "Output pipe closed");
        await closePromise;
        resolve(0);
        return;
      }

      errorStream.write(
        `stdout error: ${outputError?.message ?? String(outputError)}\n`,
      );
      webSocketStream.abortWithClose(1000, "Output stream error");
      await closePromise;
      resolve(1);
    };

    const onWebSocketData = () => {
      if (halfCloseTimer !== null) {
        armHalfCloseTimer();
      }
    };

    const onWebSocketEnd = () => {
      webSocketReadEnded = true;
      void completeFromRemote();
    };

    const onWebSocketClose = () => {
      if (!settled) {
        void completeFromRemote();
      }
    };

    const onWebSocketError = async (error) => {
      if (settled) {
        return;
      }
      settled = true;
      clearHalfCloseTimer();
      detachSessionListeners();

      inputStream.unpipe(webSocketStream);
      inputStream.pause();
      webSocketStream.unpipe(outputStream);

      errorStream.write(`Connection error: ${error.message}\n`);
      await flushWritableStream(outputStream);
      resolve(1);
    };

    detachSessionListeners = () => {
      inputStream.removeListener("end", onInputEnd);
      inputStream.removeListener("error", onInputError);
      outputStream.removeListener("error", onOutputError);
      webSocketStream.removeListener("data", onWebSocketData);
      webSocketStream.removeListener("end", onWebSocketEnd);
      webSocketStream.removeListener("close", onWebSocketClose);
      webSocketStream.removeListener("error", onWebSocketError);
    };

    inputStream.once("end", onInputEnd);
    inputStream.once("error", onInputError);
    outputStream.once("error", onOutputError);
    webSocketStream.on("data", onWebSocketData);
    webSocketStream.once("end", onWebSocketEnd);
    webSocketStream.once("close", onWebSocketClose);
    webSocketStream.once("error", onWebSocketError);

    inputStream.pipe(webSocketStream, { end: false });
    webSocketStream.pipe(outputStream, { end: false });
    inputStream.resume();

    if (inputStream.readableEnded) {
      onInputEnd();
    }
  });
}

async function runProxy(targetHost, allowInsecureCertificate, options = {}) {
  const {
    inputStream = process.stdin,
    outputStream = process.stdout,
    errorStream = process.stderr,
    env = process.env,
    WebSocketConstructor = globalThis.WebSocket,
    connectionTimeoutMs = CONNECTION_TIMEOUT_MILLISECONDS,
    halfCloseTimeoutMs = HALF_CLOSE_TIMEOUT_MILLISECONDS,
    closeTimeoutMs = WEBSOCKET_CLOSE_TIMEOUT_MILLISECONDS,
    maxFramePayloadBytes = MAXIMUM_FRAME_PAYLOAD_BYTES,
    highWaterMarkBytes = BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
    lowWaterMarkBytes = BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
    drainPollIntervalMs = DRAIN_THROTTLE_DELAY_MILLISECONDS,
  } = options;

  if (allowInsecureCertificate) {
    // Native globalThis.WebSocket lacks direct TLS options, and custom dispatchers require external npm dependencies.
    // Disabling verification here is isolated to this ephemeral ProxyCommand subprocess.
    env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  }

  if (typeof WebSocketConstructor !== "function") {
    errorStream.write(
      "Error: Native globalThis.WebSocket is not available in this Node.js version.\n",
    );
    return 1;
  }

  let websocketUrl;
  try {
    websocketUrl = resolveWebSocketUrl(targetHost);
  } catch (error) {
    errorStream.write(`${normalizeError(error).message}\n`);
    return 1;
  }

  const requestHeaders = buildCloudflareAccessHeaders(env);

  // Pause stdin before the handshake so initial SSH banner bytes stay buffered until open.
  inputStream.pause();

  let websocket;
  try {
    websocket =
      Object.keys(requestHeaders).length > 0
        ? new WebSocketConstructor(websocketUrl, { headers: requestHeaders })
        : new WebSocketConstructor(websocketUrl);
  } catch (error) {
    errorStream.write(
      `Connection error: ${extractWebSocketErrorMessage(error)}\n`,
    );
    return 1;
  }
  websocket.binaryType = "arraybuffer";

  const handshakeResult = await awaitWebSocketHandshake(
    websocket,
    websocketUrl,
    inputStream,
    outputStream,
    errorStream,
    connectionTimeoutMs,
  );
  if (!handshakeResult.connected) {
    return handshakeResult.exitCode;
  }

  const webSocketStream = new FramedWebSocketStream(websocket, {
    maxChunkBytes: maxFramePayloadBytes,
    highWaterMarkBytes,
    lowWaterMarkBytes,
    closeTimeoutMs,
    drainPollIntervalMs,
  });

  return coordinateProxySession(
    webSocketStream,
    inputStream,
    outputStream,
    errorStream,
    halfCloseTimeoutMs,
  );
}

function isExecutingAsMain() {
  if (!process.argv[1]) {
    return false;
  }
  try {
    return fs.realpathSync(process.argv[1]) === import.meta.filename;
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
    const allowInsecureCertificate =
      commandLineArguments.includes("--insecure");
    const exitCode = await runProxy(targetHost, allowInsecureCertificate);
    process.exit(exitCode);
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
  runWrapper,
  sanitizeClientCloseCode,
  truncateCloseReasonSafely,
  WEBSOCKET_CLOSE_TIMEOUT_MILLISECONDS,
  WEBSOCKET_READY_STATE_CLOSED,
  WEBSOCKET_READY_STATE_CLOSING,
  WEBSOCKET_READY_STATE_CONNECTING,
  WEBSOCKET_READY_STATE_OPEN,
};
