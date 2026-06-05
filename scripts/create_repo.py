#!/usr/bin/env python3
"""
Create a pristine repository on GitHub or GitLab.

Disables every non-essential feature by default, preserving a pure Git
repository structure unless explicitly enabled via command-line options.
"""

import argparse
from dataclasses import dataclass
import json
import os
import subprocess
import sys
from typing import Any, Dict, Final, List, NoReturn, Optional, Tuple
import urllib.error
import urllib.request

# --- Magic Values Extracted to Constants ---
GITHUB_API_URL: Final[str] = "https://api.github.com/user/repos"
GITHUB_API_VERSION: Final[str] = "2022-11-28"
GITHUB_ACCEPT_HEADER: Final[str] = "application/vnd.github+json"

GITLAB_DEFAULT_BASE_URL: Final[str] = "https://gitlab.com"
GITLAB_PROJECTS_API_PATH: Final[str] = "/api/v4/projects"

HTTP_POST_METHOD: Final[str] = "POST"
TEXT_ENCODING: Final[str] = "utf-8"
CONTENT_TYPE_JSON: Final[str] = "application/json"

GITLAB_FEATURE_ENABLED: Final[str] = "enabled"
GITLAB_FEATURE_DISABLED: Final[str] = "disabled"

STATUS_ENABLED_ICON: Final[str] = "🟩 Enabled"
STATUS_DISABLED_ICON: Final[str] = "🟥 Disabled"


def exit_with_fatal_error(message: str) -> NoReturn:
    print(f"❌ Error: {message}", file=sys.stderr)
    sys.exit(1)


def retrieve_secret_token(token_name: str) -> Optional[str]:
    """Retrieve a credential token from environment variables or secure keyrings."""
    env_token = os.getenv(token_name)
    if env_token:
        return env_token

    if sys.platform == "darwin":
        try:
            darwin_result = subprocess.run(
                ["security", "find-generic-password", "-s", token_name, "-w"],
                capture_output=True,
                text=True,
                check=True,
            )
            return darwin_result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    if sys.platform.startswith("linux"):
        try:
            linux_result = subprocess.run(
                ["secret-tool", "lookup", "service", token_name],
                capture_output=True,
                text=True,
                check=True,
            )
            return linux_result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    return None


def execute_http_post_request(
    target_url: str,
    payload: Dict[str, Any],
    request_headers: Dict[str, str],
) -> Dict[str, Any]:
    serialized_data = json.dumps(payload).encode(TEXT_ENCODING)
    http_request = urllib.request.Request(
        target_url,
        data=serialized_data,
        headers=request_headers,
        method=HTTP_POST_METHOD,
    )

    try:
        with urllib.request.urlopen(http_request) as response:
            raw_response_bytes = response.read()
            return json.loads(raw_response_bytes.decode(TEXT_ENCODING))
    except urllib.error.HTTPError as http_error:
        error_body = http_error.read().decode(TEXT_ENCODING)
        exit_with_fatal_error(
            f"API request failed with {http_error.code} {http_error.reason}\n"
            f"Details: {error_body}"
        )
    except urllib.error.URLError as url_error:
        exit_with_fatal_error(f"Network error occurred: {url_error.reason}")


@dataclass(frozen=True)
class GitHubConfiguration:
    repository_name: str
    repository_description: str
    is_public: bool
    enable_issues: bool
    enable_projects: bool
    enable_wiki: bool
    enable_discussions: bool
    enable_downloads: bool


@dataclass(frozen=True)
class GitLabConfiguration:
    project_name: str
    project_description: str
    is_public: bool
    enable_issues: bool
    enable_wiki: bool
    enable_snippets: bool
    enable_merge_requests: bool
    enable_pipelines: bool


def resolve_gitlab_access_level(is_feature_enabled: bool) -> str:
    if is_feature_enabled:
        return GITLAB_FEATURE_ENABLED
    return GITLAB_FEATURE_DISABLED


def create_github_repository(configuration: GitHubConfiguration) -> None:
    api_token = retrieve_secret_token("GITHUB_TOKEN")
    if not api_token:
        exit_with_fatal_error(
            "GITHUB_TOKEN environment variable or Keychain entry is missing."
        )

    # Ensure the Git repository is created without default initial commits
    request_payload: Dict[str, Any] = {
        "name": configuration.repository_name,
        "description": configuration.repository_description,
        "private": not configuration.is_public,
        "auto_init": False,
        "has_issues": configuration.enable_issues,
        "has_projects": configuration.enable_projects,
        "has_wiki": configuration.enable_wiki,
        "has_discussions": configuration.enable_discussions,
        "has_downloads": configuration.enable_downloads,
    }

    request_headers: Dict[str, str] = {
        "Authorization": f"Bearer {api_token}",
        "Accept": GITHUB_ACCEPT_HEADER,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "Content-Type": CONTENT_TYPE_JSON,
    }

    print(f"🚀 Creating pristine GitHub repository '{configuration.repository_name}'...")
    response_data = execute_http_post_request(
        GITHUB_API_URL, request_payload, request_headers
    )

    repository_url = response_data.get("html_url")
    print(f"\n✅ Success! Repository created at: {repository_url}")
    print("\nFeature Status:")

    github_features: List[Tuple[str, str]] = [
        ("has_issues", "Issues"),
        ("has_projects", "Projects"),
        ("has_wiki", "Wiki"),
        ("has_discussions", "Discussions"),
        ("has_downloads", "Downloads"),
    ]

    for api_field, display_name in github_features:
        is_feature_enabled = bool(response_data.get(api_field))
        status_label = (
            STATUS_ENABLED_ICON if is_feature_enabled else STATUS_DISABLED_ICON
        )
        print(f"  {display_name:<12} -> {status_label}")


def create_gitlab_project(configuration: GitLabConfiguration) -> None:
    api_token = retrieve_secret_token("GITLAB_TOKEN")
    if not api_token:
        exit_with_fatal_error(
            "GITLAB_TOKEN environment variable or Keychain entry is missing."
        )

    configured_base_url = os.getenv("GITLAB_URL", GITLAB_DEFAULT_BASE_URL).rstrip("/")
    target_endpoint = f"{configured_base_url}{GITLAB_PROJECTS_API_PATH}"

    # Lock down all built-in GitLab modules by default to maintain pristine state
    request_payload: Dict[str, Any] = {
        "name": configuration.project_name,
        "description": configuration.project_description,
        "visibility": "public" if configuration.is_public else "private",
        "repository_access_level": GITLAB_FEATURE_ENABLED,
        "issues_access_level": resolve_gitlab_access_level(
            configuration.enable_issues
        ),
        "wiki_access_level": resolve_gitlab_access_level(
            configuration.enable_wiki
        ),
        "snippets_access_level": resolve_gitlab_access_level(
            configuration.enable_snippets
        ),
        "merge_requests_access_level": resolve_gitlab_access_level(
            configuration.enable_merge_requests
        ),
        "builds_access_level": resolve_gitlab_access_level(
            configuration.enable_pipelines
        ),
        "analytics_access_level": GITLAB_FEATURE_DISABLED,
        "container_registry_access_level": GITLAB_FEATURE_DISABLED,
        "environments_access_level": GITLAB_FEATURE_DISABLED,
        "feature_flags_access_level": GITLAB_FEATURE_DISABLED,
        "forking_access_level": GITLAB_FEATURE_DISABLED,
        "infrastructure_access_level": GITLAB_FEATURE_DISABLED,
        "model_experiments_access_level": GITLAB_FEATURE_DISABLED,
        "model_registry_access_level": GITLAB_FEATURE_DISABLED,
        "monitor_access_level": GITLAB_FEATURE_DISABLED,
        "package_registry_access_level": GITLAB_FEATURE_DISABLED,
        "pages_access_level": GITLAB_FEATURE_DISABLED,
        "releases_access_level": GITLAB_FEATURE_DISABLED,
        "requirements_access_level": GITLAB_FEATURE_DISABLED,
        "security_and_compliance_access_level": GITLAB_FEATURE_DISABLED,
    }

    request_headers: Dict[str, str] = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": CONTENT_TYPE_JSON,
    }

    print(f"🚀 Creating pristine GitLab project '{configuration.project_name}'...")
    response_data = execute_http_post_request(
        target_endpoint, request_payload, request_headers
    )

    project_url = response_data.get("web_url")
    print(f"\n✅ Success! Project created at: {project_url}")
    print("\nFeature Status:")

    gitlab_features: List[Tuple[str, str]] = [
        ("Issues", "issues_access_level"),
        ("Wiki", "wiki_access_level"),
        ("Snippets", "snippets_access_level"),
        ("Merge Requests", "merge_requests_access_level"),
        ("Pipelines", "builds_access_level"),
    ]

    for display_name, api_key in gitlab_features:
        is_feature_enabled = response_data.get(api_key) == GITLAB_FEATURE_ENABLED
        status_label = (
            STATUS_ENABLED_ICON if is_feature_enabled else STATUS_DISABLED_ICON
        )
        print(f"  {display_name:<15} -> {status_label}")


def main() -> None:
    main_parser = argparse.ArgumentParser(
        description=(
            "Create a pristine repository on GitHub or GitLab.\n"
            "Disables EVERY feature by default, keeping it a pure Git\n"
            "repository unless explicitly opted-in via command line flags."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = main_parser.add_subparsers(
        dest="platform", required=True, help="Target hosting platform"
    )

    # --- GitHub Subparser ---
    github_parser = subparsers.add_parser(
        "github", help="Create a pure GitHub repository"
    )
    github_parser.add_argument("name", help="Repository name")
    github_parser.add_argument(
        "-d", "--description", default="", help="Repository description"
    )
    github_parser.add_argument(
        "--public",
        action="store_true",
        help="Make repository public (default: private)",
    )

    github_opt_in_group = github_parser.add_argument_group("Opt-in Features")
    github_opt_in_group.add_argument(
        "--issues", action="store_true", help="Enable Issues"
    )
    github_opt_in_group.add_argument(
        "--projects", action="store_true", help="Enable Projects"
    )
    github_opt_in_group.add_argument(
        "--wiki", action="store_true", help="Enable Wiki"
    )
    github_opt_in_group.add_argument(
        "--discussions", action="store_true", help="Enable Discussions"
    )
    github_opt_in_group.add_argument(
        "--downloads", action="store_true", help="Enable Downloads"
    )

    # --- GitLab Subparser ---
    gitlab_parser = subparsers.add_parser(
        "gitlab", help="Create a pure GitLab project"
    )
    gitlab_parser.add_argument("name", help="Project name")
    gitlab_parser.add_argument(
        "-d", "--description", default="", help="Project description"
    )
    gitlab_parser.add_argument(
        "--public",
        action="store_true",
        help="Make project public (default: private)",
    )

    gitlab_opt_in_group = gitlab_parser.add_argument_group("Opt-in Features")
    gitlab_opt_in_group.add_argument(
        "--issues", action="store_true", help="Enable Issues"
    )
    gitlab_opt_in_group.add_argument(
        "--wiki", action="store_true", help="Enable Wiki"
    )
    gitlab_opt_in_group.add_argument(
        "--snippets", action="store_true", help="Enable Snippets"
    )
    gitlab_opt_in_group.add_argument(
        "--merge-requests", action="store_true", help="Enable Merge Requests"
    )
    gitlab_opt_in_group.add_argument(
        "--pipelines", action="store_true", help="Enable CI/CD Pipelines"
    )

    parsed_arguments = main_parser.parse_args()

    match parsed_arguments.platform:
        case "github":
            github_config = GitHubConfiguration(
                repository_name=parsed_arguments.name,
                repository_description=parsed_arguments.description,
                is_public=parsed_arguments.public,
                enable_issues=parsed_arguments.issues,
                enable_projects=parsed_arguments.projects,
                enable_wiki=parsed_arguments.wiki,
                enable_discussions=parsed_arguments.discussions,
                enable_downloads=parsed_arguments.downloads,
            )
            create_github_repository(github_config)
        case "gitlab":
            gitlab_config = GitLabConfiguration(
                project_name=parsed_arguments.name,
                project_description=parsed_arguments.description,
                is_public=parsed_arguments.public,
                enable_issues=parsed_arguments.issues,
                enable_wiki=parsed_arguments.wiki,
                enable_snippets=parsed_arguments.snippets,
                enable_merge_requests=parsed_arguments.merge_requests,
                enable_pipelines=parsed_arguments.pipelines,
            )
            create_gitlab_project(gitlab_config)
        case _:
            exit_with_fatal_error(f"Unsupported platform: {parsed_arguments.platform}")


if __name__ == "__main__":
    main()
