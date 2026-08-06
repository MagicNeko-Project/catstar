#!/usr/bin/env node

import { execSync } from "node:child_process";
import {
  createWriteStream,
  existsSync,
  mkdirSync,
  statSync,
  unlinkSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const REPO_API =
  "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest";

function printHelp() {
  console.log(`
Usage: pydl <version> [options]

Arguments:
  version               Required. Python version to download (e.g. 3.12, 3.11.8).

Options:
  -o, --output <path>   Destination output file path or directory.
  -a, --arch <arch>     Target architecture (e.g. x86_64, aarch64, armv7, i686).
  -p, --platform <plat> Target platform (e.g. unknown-linux-gnu, apple-darwin, pc-windows-msvc).
  -f, --flavor <flavor> Target build flavor (stripped, install, full).
      --freethreaded    Download free-threaded (GIL-disabled) Python build.
  -x, --extract         Extract archive automatically after download.
  -l, --list            List available matching Python builds without downloading.
  -q, --quiet           Suppress progress bar and non-essential output.
      --json            Output asset metadata in JSON format.
  -h, --help            Show this help message.

Environment Variables:
  GITHUB_TOKEN          Optional GitHub Personal Access Token to avoid API rate limits.

Examples:
  node scripts/pydl.js 3.12
  node scripts/pydl.js 3.11.8 -o ./dist/
  node scripts/pydl.js 3.12 --extract -o ./python-bin/
  node scripts/pydl.js --list
`);
}

function detectArch() {
  const arch = os.arch();
  switch (arch) {
    case "x64":
      return "x86_64";
    case "arm64":
      return "aarch64";
    case "arm":
      return "armv7";
    case "ia32":
      return "i686";
    case "ppc64":
      return "powerpc64le";
    case "s390x":
      return "s390x";
    case "riscv64":
      return "riscv64";
    default:
      return arch;
  }
}

function detectPlatform() {
  const platform = os.platform();
  switch (platform) {
    case "linux":
      return "unknown-linux-gnu";
    case "darwin":
      return "apple-darwin";
    case "win32":
      return "pc-windows-msvc";
    default:
      return platform;
  }
}

function parseVersion(vStr) {
  if (!vStr || vStr === "latest") return null;
  const parts = vStr.replace(/^cpython-/, "").split(".");
  const major = Number.parseInt(parts[0], 10);
  const minor = parts[1] !== undefined ? Number.parseInt(parts[1], 10) : null;
  const patch = parts[2] !== undefined ? Number.parseInt(parts[2], 10) : null;

  if (Number.isNaN(major)) return null;
  return { major, minor, patch };
}

function versionMatches(requested, assetVersion) {
  if (!requested) return true;
  if (requested.major !== assetVersion.major) return false;
  if (requested.minor !== null && requested.minor !== assetVersion.minor) {
    return false;
  }
  if (requested.patch !== null && requested.patch !== assetVersion.patch) {
    return false;
  }
  return true;
}

function compareVersions(v1, v2) {
  if (v1.major !== v2.major) return v1.major - v2.major;
  if (v1.minor !== v2.minor) return v1.minor - v2.minor;
  return v1.patch - v2.patch;
}

function parseAssetInfo(name) {
  const match = name.match(/^cpython-(\d+)\.(\d+)\.(\d+)(?:\+\d+)?-(.+)$/);
  if (!match) return null;

  const version = {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3], 10),
    string: `${match[1]}.${match[2]}.${match[3]}`,
  };

  return { version, details: match[4] };
}

function scoreAsset(
  name,
  targetArch,
  targetPlatform,
  targetFlavor,
  freethreaded = false,
) {
  if (!name.includes(targetArch)) return -1;
  if (!name.includes(targetPlatform)) return -1;

  if (name.includes("debug")) return -1;

  if (freethreaded) {
    if (!name.includes("freethreaded")) return -1;
  } else {
    if (name.includes("freethreaded")) return -1;
  }

  let score = 0;

  if (name.includes(`-${targetArch}-`)) score += 200;
  if (name.includes(`-${targetArch}_v`) && !targetArch.includes("_v")) {
    score -= 100;
  }

  if (targetFlavor) {
    const flav = targetFlavor.toLowerCase();
    if (flav === "stripped" || flav === "install_only_stripped") {
      if (name.includes("install_only_stripped")) score += 1000;
      else return -1;
    } else if (flav === "install" || flav === "install_only") {
      if (name.includes("install_only") && !name.includes("stripped")) {
        score += 1000;
      } else return -1;
    } else if (flav === "full") {
      if (name.includes("full")) score += 1000;
      else return -1;
    }
  } else {
    if (name.includes("install_only_stripped")) score += 500;
    else if (name.includes("install_only")) score += 400;
    else if (name.includes("pgo+lto-full")) score += 200;
    else score += 100;
  }

  if (name.endsWith(".tar.gz")) score += 50;
  else if (name.endsWith(".zip")) score += 40;
  else if (name.endsWith(".tar.zst")) score += 30;

  return score;
}

async function fetchReleaseData() {
  const headers = {
    "User-Agent": "pydl-python-downloader",
    Accept: "application/vnd.github.v3+json",
  };

  if (process.env.GITHUB_TOKEN) {
    headers.Authorization = `token ${process.env.GITHUB_TOKEN}`;
  }

  const response = await fetch(REPO_API, { headers });

  if (!response.ok) {
    if (response.status === 403) {
      throw new Error(
        "GitHub API rate limit exceeded. Set GITHUB_TOKEN environment variable to bypass rate limits.",
      );
    }
    throw new Error(
      `GitHub API HTTP ${response.status}: ${response.statusText}`,
    );
  }

  return await response.json();
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function renderProgressBar(ratio, downloaded, total, bytesPerSec) {
  const width = 24;
  const filled = Math.min(width, Math.max(0, Math.round(width * ratio)));
  const bar = "█".repeat(filled) + "░".repeat(width - filled);
  const percent = (ratio * 100).toFixed(1).padStart(5);
  const totalStr = total ? formatBytes(total) : "Unknown";
  const speedStr = `${formatBytes(bytesPerSec)}/s`;

  return `\r[${bar}] ${percent}% (${formatBytes(downloaded)} / ${totalStr}) ${speedStr}`;
}

async function downloadFileWithProgress(url, destPath, quiet) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(
      `Download failed with HTTP ${response.status}: ${response.statusText}`,
    );
  }

  const contentLength = response.headers.get("content-length");
  const totalBytes = contentLength ? Number.parseInt(contentLength, 10) : 0;

  const fileStream = createWriteStream(destPath);
  const bodyStream = Readable.fromWeb(response.body);

  let downloadedBytes = 0;
  let lastLoggedTime = Date.now();
  let lastLoggedBytes = 0;
  let currentSpeed = 0;

  const isInteractive = process.stdout.isTTY && !quiet;

  bodyStream.on("data", (chunk) => {
    downloadedBytes += chunk.length;
    const now = Date.now();
    const elapsed = now - lastLoggedTime;

    if (elapsed >= 200) {
      currentSpeed = ((downloadedBytes - lastLoggedBytes) / elapsed) * 1000;
      lastLoggedTime = now;
      lastLoggedBytes = downloadedBytes;

      if (isInteractive) {
        const ratio = totalBytes ? downloadedBytes / totalBytes : 0;
        process.stdout.write(
          renderProgressBar(ratio, downloadedBytes, totalBytes, currentSpeed),
        );
      }
    }
  });

  try {
    await pipeline(bodyStream, fileStream);
    if (isInteractive) {
      process.stdout.write(
        renderProgressBar(1, downloadedBytes, totalBytes, currentSpeed),
      );
      process.stdout.write("\n");
    }
  } catch (err) {
    fileStream.close();
    if (existsSync(destPath)) {
      unlinkSync(destPath);
    }
    throw err;
  }
}

function extractArchive(archivePath, targetDir, quiet) {
  if (!existsSync(targetDir)) {
    mkdirSync(targetDir, { recursive: true });
  }

  if (!quiet) {
    console.log(`Extracting to: ${targetDir}`);
  }

  const isTarGz = archivePath.endsWith(".tar.gz");
  const isTarZst = archivePath.endsWith(".tar.zst");
  const isZip = archivePath.endsWith(".zip");

  if (isTarGz) {
    execSync(`tar -xzf "${archivePath}" -C "${targetDir}"`, {
      stdio: "inherit",
    });
  } else if (isTarZst) {
    execSync(`tar --zstd -xf "${archivePath}" -C "${targetDir}"`, {
      stdio: "inherit",
    });
  } else if (isZip) {
    if (os.platform() === "win32") {
      execSync(
        `powershell -Command "Expand-Archive -Path '${archivePath}' -DestinationPath '${targetDir}' -Force"`,
        { stdio: "inherit" },
      );
    } else {
      execSync(`unzip -q "${archivePath}" -d "${targetDir}"`, {
        stdio: "inherit",
      });
    }
  } else {
    throw new Error(
      `Unsupported archive format for extraction: ${archivePath}`,
    );
  }
}

function filterAndRankAssets(
  assets,
  requestedVersion,
  targetArch,
  targetPlatform,
  targetFlavor,
  freethreaded = false,
) {
  const candidates = [];

  for (const asset of assets) {
    const parsed = parseAssetInfo(asset.name);
    if (!parsed) continue;

    if (!versionMatches(requestedVersion, parsed.version)) continue;

    const score = scoreAsset(
      asset.name,
      targetArch,
      targetPlatform,
      targetFlavor,
      freethreaded,
    );
    if (score < 0) continue;

    candidates.push({
      asset,
      version: parsed.version,
      score,
    });
  }

  candidates.sort((a, b) => {
    const vComp = compareVersions(b.version, a.version);
    if (vComp !== 0) return vComp;
    return b.score - a.score;
  });

  return candidates;
}

async function main() {
  let args;
  try {
    args = parseArgs({
      options: {
        output: { type: "string", short: "o" },
        arch: { type: "string", short: "a" },
        platform: { type: "string", short: "p" },
        flavor: { type: "string", short: "f" },
        freethreaded: { type: "boolean", default: false },
        extract: { type: "boolean", short: "x", default: false },
        list: { type: "boolean", short: "l", default: false },
        quiet: { type: "boolean", short: "q", default: false },
        json: { type: "boolean", default: false },
        help: { type: "boolean", short: "h", default: false },
      },
      allowPositionals: true,
    });
  } catch (err) {
    console.error(`CLI Error: ${err.message}`);
    console.error("Run with --help for usage details.");
    process.exit(1);
  }

  const { values, positionals } = args;

  if (values.help) {
    printHelp();
    process.exit(0);
  }

  const requestedVersionRaw = positionals[0];

  if (!requestedVersionRaw && !values.list) {
    console.error(
      "Error: Python version argument is required (e.g. pydl 3.12 or pydl 3.11.8).",
    );
    printHelp();
    process.exit(1);
  }

  const requestedVersion = parseVersion(requestedVersionRaw);
  const targetArch = values.arch || detectArch();
  const targetPlatform = values.platform || detectPlatform();
  const targetFlavor = values.flavor;
  const freethreaded = values.freethreaded;
  const quiet = values.quiet || values.json;

  if (!quiet && !values.json) {
    console.log(`Target Platform : ${targetArch} (${targetPlatform})`);
    console.log(
      `Python Version  : ${requestedVersionRaw || "Latest available"}`,
    );
    console.log("Fetching release metadata from GitHub...");
  }

  let releaseData;
  try {
    releaseData = await fetchReleaseData();
  } catch (err) {
    console.error(`Error: ${err.message}`);
    process.exit(1);
  }

  const candidates = filterAndRankAssets(
    releaseData.assets,
    requestedVersion,
    targetArch,
    targetPlatform,
    targetFlavor,
    freethreaded,
  );

  if (candidates.length === 0) {
    console.error(
      `Error: No matching Python build found for version '${requestedVersionRaw || "latest"}' on ${targetArch}-${targetPlatform}.`,
    );
    process.exit(1);
  }

  if (values.list) {
    if (values.json) {
      console.log(
        JSON.stringify(
          candidates.map((c) => ({
            name: c.asset.name,
            version: c.version.string,
            size: c.asset.size,
            url: c.asset.browser_download_url,
          })),
          null,
          2,
        ),
      );
    } else {
      console.log("\nMatching Python Releases:");
      for (const c of candidates) {
        console.log(
          `  - ${c.asset.name} (${formatBytes(c.asset.size)}) -> ${c.asset.browser_download_url}`,
        );
      }
    }
    process.exit(0);
  }

  const bestMatch = candidates[0];
  const asset = bestMatch.asset;

  if (values.json) {
    console.log(
      JSON.stringify(
        {
          name: asset.name,
          version: bestMatch.version.string,
          size: asset.size,
          downloadUrl: asset.browser_download_url,
          arch: targetArch,
          platform: targetPlatform,
        },
        null,
        2,
      ),
    );
    process.exit(0);
  }

  if (!quiet) {
    console.log(`\nFound Release  : ${asset.name}`);
    console.log(`Version        : ${bestMatch.version.string}`);
    console.log(`File Size      : ${formatBytes(asset.size)}`);
  }

  let destPath;
  let outputDir;
  let extractTargetDir;

  const isArchiveFilename = (p) => {
    const l = p.toLowerCase();
    return (
      l.endsWith(".tar.gz") ||
      l.endsWith(".tar.zst") ||
      l.endsWith(".tgz") ||
      l.endsWith(".zip")
    );
  };

  if (values.output) {
    const specifiedPath = path.resolve(process.cwd(), values.output);
    const isDir =
      (existsSync(specifiedPath) && statSync(specifiedPath).isDirectory()) ||
      values.output.endsWith("/") ||
      values.output.endsWith("\\") ||
      !isArchiveFilename(values.output);

    if (isDir) {
      outputDir = specifiedPath;
      destPath = path.join(specifiedPath, asset.name);
      extractTargetDir = specifiedPath;
    } else {
      outputDir = path.dirname(specifiedPath);
      destPath = specifiedPath;
      extractTargetDir = outputDir;
    }
  } else {
    outputDir = process.cwd();
    destPath = path.join(outputDir, asset.name);
    extractTargetDir = outputDir;
  }

  if (!existsSync(outputDir)) {
    mkdirSync(outputDir, { recursive: true });
  }

  if (!quiet) {
    console.log(`Downloading to : ${destPath}\n`);
  }

  try {
    await downloadFileWithProgress(asset.browser_download_url, destPath, quiet);
    if (!quiet) {
      console.log(`Download complete: ${destPath}`);
    }

    if (values.extract) {
      extractArchive(destPath, extractTargetDir, quiet);
      if (!quiet) {
        console.log("Extraction complete!");
      }
    }
  } catch (err) {
    console.error(`\nOperation failed: ${err.message}`);
    process.exit(1);
  }
}

export {
  detectArch,
  detectPlatform,
  parseVersion,
  versionMatches,
  compareVersions,
  parseAssetInfo,
  scoreAsset,
  filterAndRankAssets,
  formatBytes,
  renderProgressBar,
};

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main();
}
