#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const GITHUB_API_URL = "https://api.github.com/user/repos";
const GITHUB_API_VERSION = "2022-11-28";
const GITHUB_ACCEPT_HEADER = "application/vnd.github+json";

const GITLAB_DEFAULT_BASE_URL = "https://gitlab.com";
const GITLAB_PROJECTS_API_PATH = "/api/v4/projects";

const STATUS_ENABLED_ICON = "🟩 Enabled";
const STATUS_DISABLED_ICON = "🟥 Disabled";

function printHelp() {
  console.log(`
Usage: create-repo <platform> <name> [options]

Platforms:
  github    Create a pristine GitHub repository.
  gitlab    Create a pristine GitLab project.

Arguments:
  name                  Repository / project name.

Options:
  -d, --description <text> Repository description.
      --public          Make repository public (default: private).
      --json            Output API response payload in JSON format.
  -h, --help            Show this help message.

GitHub Opt-in Flags:
      --issues          Enable Issues
      --projects        Enable Projects
      --wiki            Enable Wiki
      --discussions     Enable Discussions
      --downloads       Enable Downloads

GitLab Opt-in Flags:
      --issues          Enable Issues
      --wiki            Enable Wiki
      --snippets        Enable Snippets
      --merge-requests  Enable Merge Requests
      --pipelines       Enable CI/CD Pipelines
      --packages        Enable Package Registry
      --lfs             Enable Git Large File Storage (LFS)

Environment Variables / Keyring Credentials:
  GITHUB_TOKEN          GitHub API Token (or macOS Keychain / Linux secret-tool).
  GITLAB_TOKEN          GitLab API Token (or macOS Keychain / Linux secret-tool).
  GITLAB_URL            GitLab instance base URL (default: https://gitlab.com).

Examples:
  node scripts/create-repo.js github my-repo
  node scripts/create-repo.js github my-app -d "My private repo" --issues
  node scripts/create-repo.js gitlab my-service --public --pipelines
`);
}

function retrieveSecretToken(tokenName) {
  if (process.env[tokenName]) {
    return process.env[tokenName].trim();
  }

  if (process.platform === "darwin") {
    try {
      const output = execFileSync(
        "security",
        ["find-generic-password", "-s", tokenName, "-w"],
        { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
      );
      return output.trim();
    } catch {
      return null;
    }
  }

  if (process.platform === "linux") {
    try {
      const output = execFileSync(
        "secret-tool",
        ["lookup", "service", tokenName],
        {
          encoding: "utf8",
          stdio: ["ignore", "pipe", "ignore"],
        },
      );
      return output.trim();
    } catch {
      return null;
    }
  }

  return null;
}

function resolveGitLabAccessLevel(isEnabled) {
  return isEnabled ? "enabled" : "disabled";
}

function buildGitHubPayload(options) {
  const isPublic = Boolean(options.public);

  return {
    name: options.name,
    description: options.description || "",
    private: !isPublic,
    auto_init: false,
    has_issues: Boolean(options.issues),
    has_projects: Boolean(options.projects),
    has_wiki: Boolean(options.wiki),
    has_discussions: Boolean(options.discussions),
    has_downloads: Boolean(options.downloads),
    is_template: false,
    allow_squash_merge: false,
    allow_rebase_merge: false,
    allow_auto_merge: false,
    delete_branch_on_merge: true,
    allow_forking: false,
    web_commit_signoff_required: true,
    security_and_analysis: {
      advanced_security: { status: "disabled" },
      secret_scanning: { status: "disabled" },
      secret_scanning_push_protection: { status: "disabled" },
      secret_scanning_validity_checks: { status: "disabled" },
      dependabot_security_updates: { status: "disabled" },
    },
  };
}

function buildGitLabPayload(options) {
  const isPublic = Boolean(options.public);
  const repoLevel = isPublic ? "enabled" : "private";

  return {
    name: options.name,
    path: options.name,
    description: options.description || "",
    visibility: isPublic ? "public" : "private",
    repository_access_level: repoLevel,
    issues_access_level: resolveGitLabAccessLevel(options.issues),
    wiki_access_level: resolveGitLabAccessLevel(options.wiki),
    snippets_access_level: resolveGitLabAccessLevel(options.snippets),
    merge_requests_access_level: resolveGitLabAccessLevel(
      options["merge-requests"],
    ),
    builds_access_level: resolveGitLabAccessLevel(options.pipelines),
    forking_access_level: "disabled",
    pages_access_level: "disabled",
    analytics_access_level: "disabled",
    container_registry_access_level: "disabled",
    security_and_compliance_access_level: "disabled",
    releases_access_level: "disabled",
    environments_access_level: "disabled",
    feature_flags_access_level: "disabled",
    infrastructure_access_level: "disabled",
    monitor_access_level: "disabled",
    requirements_access_level: "disabled",
    model_experiments_access_level: "disabled",
    model_registry_access_level: "disabled",
    auto_devops_enabled: false,
    packages_enabled: Boolean(options.packages),
    service_desk_enabled: false,
    lfs_enabled: Boolean(options.lfs),
    shared_runners_enabled: false,
    public_jobs: false,
    emails_disabled: true,
    printing_merge_request_link_enabled: false,
    enforce_auth_checks_on_uploads: true,
    ci_forward_deployment_enabled: false,
    ci_allow_fork_pipelines_to_run_in_parent_project: false,
    container_expiration_policy_attributes: {
      enabled: false,
    },
  };
}

async function executeHttpPost(targetUrl, payload, headers) {
  const response = await fetch(targetUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify(payload),
  });

  const responseText = await response.text();
  let responseData;
  try {
    responseData = JSON.parse(responseText);
  } catch {
    responseData = { raw: responseText };
  }

  if (!response.ok) {
    const details = responseData.message
      ? JSON.stringify(responseData.message)
      : responseText;
    throw new Error(
      `API Request Failed (HTTP ${response.status} ${response.statusText}): ${details}`,
    );
  }

  return responseData;
}

async function createGitHubRepo(options) {
  const token = retrieveSecretToken("GITHUB_TOKEN");
  if (!token) {
    throw new Error(
      "GITHUB_TOKEN environment variable or Keychain entry is missing.",
    );
  }

  const payload = buildGitHubPayload(options);
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: GITHUB_ACCEPT_HEADER,
    "X-GitHub-Api-Version": GITHUB_API_VERSION,
  };

  console.log(`🚀 Creating pristine GitHub repository '${options.name}'...`);
  const response = await executeHttpPost(GITHUB_API_URL, payload, headers);

  if (options.json) {
    console.log(JSON.stringify(response, null, 2));
    return;
  }

  console.log(`\n✅ Success! Repository created at: ${response.html_url}`);
  console.log("\nFeature Status:");

  const features = [
    ["has_issues", "Issues"],
    ["has_projects", "Projects"],
    ["has_wiki", "Wiki"],
    ["has_discussions", "Discussions"],
    ["has_downloads", "Downloads"],
  ];

  for (const [key, label] of features) {
    const isEnabled = Boolean(response[key]);
    const icon = isEnabled ? STATUS_ENABLED_ICON : STATUS_DISABLED_ICON;
    console.log(`  ${label.padEnd(15)} -> ${icon}`);
  }
}

async function createGitLabRepo(options) {
  const token = retrieveSecretToken("GITLAB_TOKEN");
  if (!token) {
    throw new Error(
      "GITLAB_TOKEN environment variable or Keychain entry is missing.",
    );
  }

  const baseUrl = (process.env.GITLAB_URL || GITLAB_DEFAULT_BASE_URL).replace(
    /\/+$/,
    "",
  );
  const targetUrl = `${baseUrl}${GITLAB_PROJECTS_API_PATH}`;

  const payload = buildGitLabPayload(options);
  const headers = {
    Authorization: `Bearer ${token}`,
  };

  console.log(`🚀 Creating pristine GitLab project '${options.name}'...`);
  const response = await executeHttpPost(targetUrl, payload, headers);

  if (options.json) {
    console.log(JSON.stringify(response, null, 2));
    return;
  }

  console.log(`\n✅ Success! Project created at: ${response.web_url}`);
  console.log("\nFeature Status:");

  const features = [
    ["Issues", "issues_access_level"],
    ["Wiki", "wiki_access_level"],
    ["Snippets", "snippets_access_level"],
    ["Merge Requests", "merge_requests_access_level"],
    ["Pipelines", "builds_access_level"],
    ["Packages", "packages_enabled"],
    ["LFS", "lfs_enabled"],
  ];

  for (const [label, key] of features) {
    const isEnabled = response[key] === "enabled" || response[key] === true;
    const icon = isEnabled ? STATUS_ENABLED_ICON : STATUS_DISABLED_ICON;
    console.log(`  ${label.padEnd(15)} -> ${icon}`);
  }
}

async function main() {
  let args;
  try {
    args = parseArgs({
      options: {
        description: { type: "string", short: "d" },
        public: { type: "boolean", default: false },
        issues: { type: "boolean", default: false },
        projects: { type: "boolean", default: false },
        wiki: { type: "boolean", default: false },
        discussions: { type: "boolean", default: false },
        downloads: { type: "boolean", default: false },
        snippets: { type: "boolean", default: false },
        "merge-requests": { type: "boolean", default: false },
        pipelines: { type: "boolean", default: false },
        packages: { type: "boolean", default: false },
        lfs: { type: "boolean", default: false },
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

  const platform = positionals[0]?.toLowerCase();
  const repoName = positionals[1];

  if (!platform || !["github", "gitlab"].includes(platform)) {
    console.error(
      "Error: Platform argument ('github' or 'gitlab') is required.",
    );
    printHelp();
    process.exit(1);
  }

  if (!repoName) {
    console.error("Error: Repository / project name argument is required.");
    printHelp();
    process.exit(1);
  }

  const options = {
    ...values,
    name: repoName,
  };

  try {
    if (platform === "github") {
      await createGitHubRepo(options);
    } else {
      await createGitLabRepo(options);
    }
  } catch (err) {
    console.error(`\n❌ Error: ${err.message}`);
    process.exit(1);
  }
}

export {
  buildGitHubPayload,
  buildGitLabPayload,
  resolveGitLabAccessLevel,
  retrieveSecretToken,
};

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main();
}
