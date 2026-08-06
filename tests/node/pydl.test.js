import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  compareVersions,
  detectArch,
  detectPlatform,
  filterAndRankAssets,
  formatBytes,
  parseAssetInfo,
  parseVersion,
  renderProgressBar,
  scoreAsset,
  versionMatches,
} from "../../scripts/pydl.js";

describe("pydl CLI Unit Tests (Offline)", () => {
  it("detectArch returns non-empty string", () => {
    const arch = detectArch();
    assert.equal(typeof arch, "string");
    assert.ok(arch.length > 0);
  });

  it("detectPlatform returns non-empty string", () => {
    const platform = detectPlatform();
    assert.equal(typeof platform, "string");
    assert.ok(platform.length > 0);
  });

  it("parseVersion handles major, minor, patch and invalid inputs", () => {
    assert.deepEqual(parseVersion("3.12"), {
      major: 3,
      minor: 12,
      patch: null,
    });
    assert.deepEqual(parseVersion("3.11.8"), { major: 3, minor: 11, patch: 8 });
    assert.deepEqual(parseVersion("cpython-3.10.5"), {
      major: 3,
      minor: 10,
      patch: 5,
    });
    assert.equal(parseVersion("latest"), null);
    assert.equal(parseVersion("invalid"), null);
    assert.equal(parseVersion(null), null);
  });

  it("versionMatches matches major, minor, patch accurately", () => {
    const reqPrefix = { major: 3, minor: 12, patch: null };
    const reqExact = { major: 3, minor: 12, patch: 3 };
    const asset1 = { major: 3, minor: 12, patch: 13 };
    const asset2 = { major: 3, minor: 12, patch: 3 };
    const asset3 = { major: 3, minor: 11, patch: 8 };

    assert.equal(versionMatches(reqPrefix, asset1), true);
    assert.equal(versionMatches(reqExact, asset1), false);
    assert.equal(versionMatches(reqExact, asset2), true);
    assert.equal(versionMatches(reqPrefix, asset3), false);
    assert.equal(versionMatches(null, asset1), true);
  });

  it("compareVersions orders semver correctly", () => {
    const v3123 = { major: 3, minor: 12, patch: 3 };
    const v31213 = { major: 3, minor: 12, patch: 13 };
    const v3118 = { major: 3, minor: 11, patch: 8 };

    assert.ok(compareVersions(v31213, v3123) > 0);
    assert.ok(compareVersions(v3118, v3123) < 0);
    assert.equal(compareVersions(v3123, v3123), 0);
  });

  it("parseAssetInfo extracts version and details from asset filenames", () => {
    const info = parseAssetInfo(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    );
    assert.ok(info);
    assert.deepEqual(info.version, {
      major: 3,
      minor: 12,
      patch: 13,
      string: "3.12.13",
    });
    assert.equal(
      info.details,
      "x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    );

    assert.equal(parseAssetInfo("random-file.txt"), null);
  });

  it("scoreAsset scores matching platforms and preferred variants higher", () => {
    const genericMatch = scoreAsset(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
      "x86_64",
      "unknown-linux-gnu",
    );
    const fullMatch = scoreAsset(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-full.tar.zst",
      "x86_64",
      "unknown-linux-gnu",
    );
    const debugMatch = scoreAsset(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-debug-full.tar.zst",
      "x86_64",
      "unknown-linux-gnu",
    );
    const wrongArch = scoreAsset(
      "cpython-3.12.13+20260805-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
      "x86_64",
      "unknown-linux-gnu",
    );

    assert.ok(genericMatch > fullMatch);
    assert.equal(debugMatch, -1);
    assert.equal(wrongArch, -1);
  });

  it("scoreAsset and filterAndRankAssets filter by targetFlavor correctly", () => {
    const strippedScore = scoreAsset(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
      "x86_64",
      "unknown-linux-gnu",
      "stripped",
    );
    const fullScoreWithStrippedFlav = scoreAsset(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst",
      "x86_64",
      "unknown-linux-gnu",
      "stripped",
    );
    const fullScoreWithFullFlav = scoreAsset(
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-pgo+lto-full.tar.zst",
      "x86_64",
      "unknown-linux-gnu",
      "full",
    );

    assert.ok(strippedScore > 0);
    assert.equal(fullScoreWithStrippedFlav, -1);
    assert.ok(fullScoreWithFullFlav > 0);
  });

  it("scoreAsset filters free-threaded builds correctly", () => {
    const normalAsset =
      "cpython-3.13.0+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz";
    const freeThreadedAsset =
      "cpython-3.13.0+20260805-x86_64-unknown-linux-gnu-freethreaded-install_only_stripped.tar.gz";

    const normalDefault = scoreAsset(
      normalAsset,
      "x86_64",
      "unknown-linux-gnu",
      null,
      false,
    );
    const freeThreadedDefault = scoreAsset(
      freeThreadedAsset,
      "x86_64",
      "unknown-linux-gnu",
      null,
      false,
    );
    const freeThreadedRequested = scoreAsset(
      freeThreadedAsset,
      "x86_64",
      "unknown-linux-gnu",
      null,
      true,
    );

    assert.ok(normalDefault > 0);
    assert.equal(freeThreadedDefault, -1);
    assert.ok(freeThreadedRequested > 0);
  });

  it("filterAndRankAssets ranks best candidate first without network calls", () => {
    const mockAssets = [
      {
        name: "cpython-3.11.8+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        size: 30000000,
        browser_download_url: "http://example.com/3.11",
      },
      {
        name: "cpython-3.12.5+20260805-x86_64-unknown-linux-gnu-install_only.tar.gz",
        size: 100000000,
        browser_download_url: "http://example.com/3.12.5",
      },
      {
        name: "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        size: 32000000,
        browser_download_url: "http://example.com/3.12.13",
      },
      {
        name: "cpython-3.12.13+20260805-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
        size: 32000000,
        browser_download_url: "http://example.com/aarch64",
      },
    ];

    const candidates = filterAndRankAssets(
      mockAssets,
      { major: 3, minor: 12, patch: null },
      "x86_64",
      "unknown-linux-gnu",
    );

    assert.equal(candidates.length, 2);
    assert.equal(candidates[0].version.string, "3.12.13");
    assert.equal(
      candidates[0].asset.name,
      "cpython-3.12.13+20260805-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
    );
  });

  it("formatBytes formats KB and MB values correctly", () => {
    assert.equal(formatBytes(512 * 1024), "512.0 KB");
    assert.equal(formatBytes(10.5 * 1024 * 1024), "10.50 MB");
  });

  it("renderProgressBar produces progress output", () => {
    const bar = renderProgressBar(
      0.5,
      5 * 1024 * 1024,
      10 * 1024 * 1024,
      1024 * 1024,
    );
    assert.ok(bar.includes("50.0%"));
    assert.ok(bar.includes("1.00 MB/s"));
  });
});
