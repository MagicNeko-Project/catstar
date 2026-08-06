import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildGitHubPayload,
  buildGitLabPayload,
  resolveGitLabAccessLevel,
  retrieveSecretToken,
} from "../../scripts/create-repo.js";

describe("create-repo CLI Unit Tests (Offline)", () => {
  it("resolveGitLabAccessLevel maps booleans to GitLab access level strings", () => {
    assert.equal(resolveGitLabAccessLevel(true), "enabled");
    assert.equal(resolveGitLabAccessLevel(false), "disabled");
  });

  it("buildGitHubPayload constructs private pristine repository payload by default", () => {
    const payload = buildGitHubPayload({ name: "my-test-repo" });

    assert.equal(payload.name, "my-test-repo");
    assert.equal(payload.private, true);
    assert.equal(payload.auto_init, false);
    assert.equal(payload.has_issues, false);
    assert.equal(payload.has_projects, false);
    assert.equal(payload.has_wiki, false);
    assert.equal(payload.has_discussions, false);
    assert.equal(payload.has_downloads, false);
    assert.equal(payload.allow_forking, false);
    assert.equal(payload.web_commit_signoff_required, true);

    assert.deepEqual(payload.security_and_analysis, {
      advanced_security: { status: "disabled" },
      secret_scanning: { status: "disabled" },
      secret_scanning_push_protection: { status: "disabled" },
      secret_scanning_validity_checks: { status: "disabled" },
      dependabot_security_updates: { status: "disabled" },
    });
  });

  it("buildGitHubPayload respects public visibility and opt-in flags", () => {
    const payload = buildGitHubPayload({
      name: "public-repo",
      description: "Public project",
      public: true,
      issues: true,
      wiki: true,
    });

    assert.equal(payload.private, false);
    assert.equal(payload.description, "Public project");
    assert.equal(payload.has_issues, true);
    assert.equal(payload.has_wiki, true);
    assert.equal(payload.has_projects, false);
  });

  it("buildGitLabPayload locks down all auxiliary modules and AI features by default", () => {
    const payload = buildGitLabPayload({ name: "gitlab-pristine" });

    assert.equal(payload.name, "gitlab-pristine");
    assert.equal(payload.path, "gitlab-pristine");
    assert.equal(payload.visibility, "private");
    assert.equal(payload.repository_access_level, "private");
    assert.equal(payload.issues_access_level, "disabled");
    assert.equal(payload.wiki_access_level, "disabled");
    assert.equal(payload.snippets_access_level, "disabled");
    assert.equal(payload.merge_requests_access_level, "disabled");
    assert.equal(payload.builds_access_level, "disabled");

    // Lockdowns on auxiliary, analytics, infrastructure, and AI modules
    assert.equal(payload.analytics_access_level, "disabled");
    assert.equal(payload.container_registry_access_level, "disabled");
    assert.equal(payload.security_and_compliance_access_level, "disabled");
    assert.equal(payload.environments_access_level, "disabled");
    assert.equal(payload.feature_flags_access_level, "disabled");
    assert.equal(payload.infrastructure_access_level, "disabled");
    assert.equal(payload.monitor_access_level, "disabled");
    assert.equal(payload.requirements_access_level, "disabled");
    assert.equal(payload.model_experiments_access_level, "disabled");
    assert.equal(payload.model_registry_access_level, "disabled");
    assert.equal(payload.auto_devops_enabled, false);
    assert.equal(payload.packages_enabled, false);
    assert.equal(payload.lfs_enabled, false);
  });

  it("buildGitLabPayload sets public repository level and enables opted-in features", () => {
    const payload = buildGitLabPayload({
      name: "gitlab-pub",
      public: true,
      issues: true,
      pipelines: true,
      packages: true,
    });

    assert.equal(payload.visibility, "public");
    assert.equal(payload.repository_access_level, "enabled");
    assert.equal(payload.issues_access_level, "enabled");
    assert.equal(payload.builds_access_level, "enabled");
    assert.equal(payload.packages_enabled, true);
    assert.equal(payload.wiki_access_level, "disabled");
  });

  it("retrieveSecretToken fetches environment variables", () => {
    process.env.TEST_DUMMY_TOKEN = "secret123";
    const token = retrieveSecretToken("TEST_DUMMY_TOKEN");
    assert.equal(token, "secret123");
    delete process.env.TEST_DUMMY_TOKEN;
  });
});
