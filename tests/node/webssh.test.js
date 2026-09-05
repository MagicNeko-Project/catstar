import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { describe, it } from "node:test";
import {
  BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES,
  BUFFERED_AMOUNT_LOW_WATERMARK_BYTES,
  CHUNK_SIZE,
  CONNECTION_TIMEOUT_MILLISECONDS,
  DRAIN_THROTTLE_DELAY_MILLISECONDS,
  MAXIMUM_FRAME_PAYLOAD_BYTES,
  WEBSOCKET_READY_STATE_CONNECTING,
  WEBSOCKET_READY_STATE_OPEN,
  parseWrapperArguments,
  sliceBufferIntoFrames,
} from "../../scripts/webssh.js";

describe("webssh CLI & Frame Slicing Unit Tests", () => {
  it("constants enforce safe buffer thresholds and state invariants", () => {
    assert.equal(MAXIMUM_FRAME_PAYLOAD_BYTES, 4096);
    assert.equal(CHUNK_SIZE, 4096);
    assert.ok(MAXIMUM_FRAME_PAYLOAD_BYTES <= 8192);
    assert.ok(BUFFERED_AMOUNT_LOW_WATERMARK_BYTES < BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES);
    assert.equal(BUFFERED_AMOUNT_LOW_WATERMARK_BYTES, 16 * 1024);
    assert.equal(BUFFERED_AMOUNT_HIGH_WATERMARK_BYTES, 64 * 1024);
    assert.equal(DRAIN_THROTTLE_DELAY_MILLISECONDS, 10);
    assert.equal(CONNECTION_TIMEOUT_MILLISECONDS, 10_000);
    assert.equal(WEBSOCKET_READY_STATE_CONNECTING, 0);
    assert.equal(WEBSOCKET_READY_STATE_OPEN, 1);
  });

  it("sliceBufferIntoFrames returns empty array for empty buffer", () => {
    const emptyBuffer = Buffer.alloc(0);
    const frames = sliceBufferIntoFrames(emptyBuffer, CHUNK_SIZE);
    assert.deepEqual(frames, []);
  });

  it("sliceBufferIntoFrames preserves buffer smaller than chunk size", () => {
    const smallBuffer = Buffer.from("arbitrary test payload");
    const frames = sliceBufferIntoFrames(smallBuffer, CHUNK_SIZE);

    assert.equal(frames.length, 1);
    assert.equal(frames[0].toString(), "arbitrary test payload");
  });

  it("sliceBufferIntoFrames partitions oversized buffer into deterministic chunks without loss", () => {
    const totalPayloadBytes = 10_000;
    const testPattern = Buffer.alloc(totalPayloadBytes);
    for (let index = 0; index < totalPayloadBytes; index++) {
      testPattern[index] = index % 256;
    }

    const frames = sliceBufferIntoFrames(testPattern, CHUNK_SIZE);

    // 10,000 bytes sliced by 4,096 gives 4096, 4096, 1808 (3 frames)
    assert.equal(frames.length, 3);
    assert.equal(frames[0].length, 4096);
    assert.equal(frames[1].length, 4096);
    assert.equal(frames[2].length, 1808);

    const reassembledBuffer = Buffer.concat(frames);
    assert.equal(reassembledBuffer.length, totalPayloadBytes);
    assert.deepEqual(reassembledBuffer, testPattern);
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
