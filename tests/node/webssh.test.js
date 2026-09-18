import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
  BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
  buildProxyCommand,
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
});
