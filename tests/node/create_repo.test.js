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

  it("buildGitHubPayload constructs private repository payload by default", () => {
    const payload = buildGitHubPayload({ name: "my-test-repo" });

    assert.equal(payload.name, "my-test-repo");
    assert.equal(payload.description, "");
    assert.equal(payload.private, true);
    assert.equal(payload.has_issues, false);
    assert.equal(payload.has_projects, false);
    assert.equal(payload.has_wiki, false);
    assert.equal(payload.has_discussions, false);
    assert.equal(payload.has_downloads, false);
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

  it("buildGitLabPayload constructs private repository payload by default", () => {
    const payload = buildGitLabPayload({ name: "gitlab-pristine" });

    assert.equal(payload.name, "gitlab-pristine");
    assert.equal(payload.path, "gitlab-pristine");
    assert.equal(payload.description, "");
    assert.equal(payload.visibility, "private");
    assert.equal(payload.issues_access_level, "disabled");
    assert.equal(payload.wiki_access_level, "disabled");
    assert.equal(payload.snippets_access_level, "disabled");
    assert.equal(payload.merge_requests_access_level, "disabled");
    assert.equal(payload.builds_access_level, "disabled");
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
