import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Dynamically import catstar-netheal from /app/src/bin
NETHEAL_PATH = Path("/app/src/bin/catstar-netheal")
if NETHEAL_PATH.exists():
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("catstar_netheal", str(NETHEAL_PATH))
    spec = importlib.util.spec_from_loader("catstar_netheal", loader)
    catstar_netheal = importlib.util.module_from_spec(spec)
    sys.modules["catstar_netheal"] = catstar_netheal
    loader.exec_module(catstar_netheal)
else:
    catstar_netheal = None


@pytest.fixture
def sandbox_dir():
    """
    Creates a physical temporary directory for test isolation and ensures
    it is completely deleted after the test execution completes.
    """
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    yield temp_path
    shutil.rmtree(temp_dir, ignore_errors=True)
    assert not temp_path.exists(), f"Sandbox directory {temp_path} was not cleaned up successfully."


def test_zipsync_safe_extraction_and_recursion(sandbox_dir):
    """
    Verifies that the zip synchronizer handles normal files, recursively extracts
    nested zips, and safely rejects malicious path traversal (Zip Slip).
    """
    from scripts.zipsync import ZipSyncer

    # 1. Setup physical source and destination directories
    src_dir = sandbox_dir / "src"
    dest_dir = sandbox_dir / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()

    # Create normal text files
    normal_file = src_dir / "normal.txt"
    normal_file.write_text("plain text", encoding="utf-8")

    # 2. Create nested zip file on the fly
    # We first create a small zip to be nested
    nested_zip_bytes_path = sandbox_dir / "temp_nested.zip"
    with zipfile.ZipFile(nested_zip_bytes_path, "w") as z_sub:
        z_sub.writestr("world.txt", "hello nested world")

    # Now create the outer nested zip
    nested_zips_path = src_dir / "nested_zips.zip"
    with zipfile.ZipFile(nested_zips_path, "w") as z_outer:
        z_outer.write(nested_zip_bytes_path, "sub.zip")

    # Clean up the temp nested zip
    nested_zip_bytes_path.unlink()

    # 3. Create a good zip with simple contents
    good_zip_path = src_dir / "good.zip"
    with zipfile.ZipFile(good_zip_path, "w") as z_good:
        z_good.writestr("file1.txt", "hello file1")
        z_good.writestr("nested/file2.txt", "hello file2")

    # 4. Create a bad zip with relative path traversal (Zip Slip)
    bad_zip_path = src_dir / "bad.zip"
    with zipfile.ZipFile(bad_zip_path, "w") as z_bad:
        z_bad.writestr("../escaped.txt", "escaped content")
        z_bad.writestr("good_member.txt", "safe content")

    # 5. Run the ZipSyncer sync operation
    syncer = ZipSyncer(verbose=True)
    syncer.sync(src_dir, dest_dir)

    # 6. Assert copy and extract outcomes
    # Normal file copy assert
    assert (dest_dir / "normal.txt").exists()
    assert (dest_dir / "normal.txt").read_text(encoding="utf-8") == "plain text"

    # Good zip extract assert
    assert (dest_dir / "good" / "file1.txt").exists()
    assert (dest_dir / "good" / "file1.txt").read_text(encoding="utf-8") == "hello file1"
    assert (dest_dir / "good" / "nested" / "file2.txt").exists()
    assert (dest_dir / "good" / "nested" / "file2.txt").read_text(encoding="utf-8") == "hello file2"

    # Recursive zip extract and cleanup assert
    assert (dest_dir / "nested_zips" / "sub" / "world.txt").exists()
    assert (dest_dir / "nested_zips" / "sub" / "world.txt").read_text(encoding="utf-8") == "hello nested world"
    # Ensure nested zip file itself is deleted
    assert not (dest_dir / "nested_zips" / "sub" / "sub.zip").exists()

    # Path traversal validation and rejection assert
    # Good member in the bad.zip must be extracted
    assert (dest_dir / "bad" / "good_member.txt").exists()
    assert (dest_dir / "bad" / "good_member.txt").read_text(encoding="utf-8") == "safe content"
    # Malicious member must be skipped, and no file must be created outside the sandbox or target folders
    assert not (dest_dir / "bad" / "../escaped.txt").exists()
    assert not (dest_dir / "escaped.txt").exists()
    assert not (sandbox_dir / "escaped.txt").exists()


def test_repo2txt_exclusions_and_formatting(sandbox_dir):
    """
    Verifies that repo2txt correctly identifies and handles nested ignore
    files and default pattern-matching exclusion rules.
    """
    # 1. Setup a nested target directory layout in the sandbox
    repo_dir = sandbox_dir / "repo"
    repo_dir.mkdir()

    # Normal included files
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    app_file = src_dir / "app.py"
    app_file.write_text("print('app')", encoding="utf-8")

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_app.py"
    test_file.write_text("def test_app(): pass", encoding="utf-8")

    # Ghosted by default (dependencies)
    node_modules_dir = repo_dir / "node_modules" / "library"
    node_modules_dir.mkdir(parents=True)
    dep_file = node_modules_dir / "index.js"
    dep_file.write_text("console.log('dependency')", encoding="utf-8")

    # Pruned by default (VCS systems)
    git_dir = repo_dir / ".git"
    git_dir.mkdir()
    git_config = git_dir / "config"
    git_config.write_text("vcs=true", encoding="utf-8")

    # Redacted by default (Secrets / security)
    env_file = repo_dir / ".env"
    env_file.write_text("API_SECRET=supersecuretoken\nPASSWORD=123", encoding="utf-8")

    # Custom ignored via .gitignore -> should be ghosted
    debug_log = repo_dir / "debug.log"
    debug_log.write_text("debug logging info", encoding="utf-8")
    gitignore = repo_dir / ".gitignore"
    gitignore.write_text("*.log", encoding="utf-8")

    # Custom ignored via .llmignore -> should be pruned
    temp_dir = repo_dir / "temp"
    temp_dir.mkdir()
    temp_file = temp_dir / "cache.txt"
    temp_file.write_text("temporary cache content", encoding="utf-8")
    llmignore = repo_dir / ".llmignore"
    llmignore.write_text("temp/", encoding="utf-8")

    # 2. Run repo2txt via subprocess on the sandbox directory
    output_xml = sandbox_dir / "output.xml"
    
    # We execute repo2txt using python interpreter to guarantee isolated execution without modification
    cmd = [
        sys.executable,
        "/app/scripts/repo2txt.py",
        ".",
        "-o",
        str(output_xml)
    ]
    
    subprocess.run(cmd, cwd=repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 3. Assert on the contents of the generated XML payload
    assert output_xml.exists()
    xml_content = output_xml.read_text(encoding="utf-8")

    # --- Directory Tree Asserts ---
    # Included and Ghosted files should be present in the tree
    assert "├── src/" in xml_content
    assert "│   └── app.py" in xml_content
    assert "├── tests/" in xml_content
    assert "│   └── test_app.py" in xml_content
    assert "├── node_modules/" in xml_content
    assert "├── .env" in xml_content
    assert "debug.log" in xml_content

    # Pruned files should NOT be present in the directory tree or files
    tree_part = xml_content.split("<files>")[0]
    assert "temp/" not in tree_part
    assert ".git/" not in tree_part
    assert "cache.txt" not in xml_content
    assert "temporary cache content" not in xml_content
    assert "vcs=true" not in xml_content

    # --- File Extract Content Asserts ---
    # Included files must have full content
    assert '<file path="src/app.py">' in xml_content
    assert "<language>python</language>" in xml_content
    assert "print('app')" in xml_content

    assert '<file path="tests/test_app.py">' in xml_content
    assert "def test_app(): pass" in xml_content

    # Ghosted files (dependencies or .gitignore matches) must NOT have content elements
    assert '<file path="node_modules/library/index.js">' not in xml_content
    assert '<file path="debug.log">' not in xml_content
    assert "console.log('dependency')" not in xml_content
    assert "debug logging info" not in xml_content

    # Redacted files (.env) must show REDACTED metadata but OMIT sensitive content
    assert '<file path=".env">' in xml_content
    assert "<status>REDACTED: SECURITY_RISK</status>" in xml_content
    assert "File content redacted to prevent credential exposure." in xml_content
    assert "API_SECRET" not in xml_content
    assert "supersecuretoken" not in xml_content


def test_netheal_state_transitions(sandbox_dir):
    """
    Verifies state transitions and health check monitoring of catstar-netheal
    using isolated configurations under a sandboxed directory.
    """
    if catstar_netheal is None:
        pytest.skip("catstar-netheal script not found at the expected location.")

    # 1. Setup isolated environment configuration
    config_path = sandbox_dir / "netheal_config.json"
    state_path = sandbox_dir / "netheal_state.json"

    config_data = {
        "requirement": "any",
        "failure_threshold": 3,
        "state_file_path": str(state_path),
        "methods": [
            {
                "type": "ping",
                "target": "1.1.1.1",
                "count": 3,
                "timeout_seconds": 2
            }
        ],
        "actions": [
            {
                "type": "restart_service",
                "service_name": "v2ray"
            }
        ],
        "ntfy": {
            "enabled": True,
            "topic": "test-topic",
            "server_url": "https://ntfy.sh"
        }
    }

    config_path.write_text(json.dumps(config_data, indent=2), encoding="utf-8")

    # Prepare mocked argv for main function
    mock_argv = ["catstar-netheal", "-c", str(config_path)]

    with patch("sys.argv", mock_argv), \
         patch("catstar_netheal.verify_internet_connectivity") as mock_connectivity, \
         patch("catstar_netheal.trigger_recovery_actions") as mock_trigger_actions, \
         patch("catstar_netheal.send_ntfy_notification") as mock_ntfy_notification:

        # --- Transition 1: Initially Healthy & Remains Online ---
        mock_connectivity.return_value = True
        catstar_netheal.main()

        # State file should not be created yet (since error count is 0 and not recovering)
        assert not state_path.exists()
        mock_trigger_actions.assert_not_called()
        mock_ntfy_notification.assert_not_called()

        # --- Transition 2: First Failure (Healthy -> Degraded Level 1) ---
        mock_connectivity.return_value = False
        catstar_netheal.main()

        assert state_path.exists()
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["consecutive_failure_count"] == 1
        assert state_data["recovering"] is False
        
        # Warnings sent, actions not triggered
        mock_ntfy_notification.assert_called_once()
        mock_trigger_actions.assert_not_called()
        
        # Reset mock call history
        mock_ntfy_notification.reset_mock()

        # --- Transition 3: Second Failure (Degraded Level 1 -> Degraded Level 2) ---
        mock_connectivity.return_value = False
        catstar_netheal.main()

        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["consecutive_failure_count"] == 2
        assert state_data["recovering"] is False
        mock_ntfy_notification.assert_called_once()
        mock_trigger_actions.assert_not_called()
        
        mock_ntfy_notification.reset_mock()

        # --- Transition 4: Third Failure (Threshold Reached -> Recovery Triggered) ---
        mock_connectivity.return_value = False
        catstar_netheal.main()

        # After reaching 3 failures, failure count is reset to 0, recovering is set to True,
        # and recovery actions are triggered.
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["consecutive_failure_count"] == 0
        assert state_data["recovering"] is True
        
        mock_trigger_actions.assert_called_once_with(config_data["actions"])
        # Critical alert sent
        assert mock_ntfy_notification.call_count >= 1
        
        mock_trigger_actions.reset_mock()
        mock_ntfy_notification.reset_mock()

        # --- Transition 5: Still Offline but recovering (Failure count should increment/be handled) ---
        mock_connectivity.return_value = False
        catstar_netheal.main()
        
        # State transitions to failure_count = 1, recovering remains True
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["consecutive_failure_count"] == 1
        assert state_data["recovering"] is True
        mock_trigger_actions.assert_not_called()
        
        mock_trigger_actions.reset_mock()
        mock_ntfy_notification.reset_mock()

        # --- Transition 6: Internet Restored (Recovering -> Healthy) ---
        mock_connectivity.return_value = True
        catstar_netheal.main()

        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["consecutive_failure_count"] == 0
        assert state_data["recovering"] is False
        
        # Successful recovery notification sent
        mock_ntfy_notification.assert_called_once()
        mock_trigger_actions.assert_not_called()
