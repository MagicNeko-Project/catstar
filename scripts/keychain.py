#!/usr/bin/env python3
"""
keychain.py - A Modern Python Implementation of the Keychain Agent Manager

This script provides a native Python alternative to the traditional shell-based 'keychain'
utility. It manages OpenSSH ssh-agent instances, ensuring that only one agent is running
per user session and that keys are loaded only once.

Main features:
- Automatically discovers existing agents via environment variables or pidfiles.
- Spawns a new agent if none are found or if the existing one is unresponsive.
- Generates shell-compatible export scripts for bash/zsh, csh, and fish.
- Prevents redundant key loading by checking fingerprints of already loaded identities.
- Provides a clean, object-oriented interface for agent management.

Usage:
    eval $(keychain.py --eval id_rsa)
"""

import os
import sys
import argparse
import subprocess
import socket
import signal
import logging
import re
from pathlib import Path
from typing import Optional, Set, Tuple, List, Dict

# --- Logging Configuration ---
# We route all user-facing messages to stderr so that stdout remains reserved
# for shell 'eval' strings. This prevents logs from being interpreted as commands.
logger = logging.getLogger("keychain")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("* %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class AgentError(Exception):
    """Base exception for keychain agent operations."""
    pass


class SSHAgent:
    """
    Encapsulates the state and operations of an OpenSSH agent.

    Attributes:
        auth_sock (Path): Path to the UNIX domain socket for agent communication.
        pid (Optional[int]): The process ID of the ssh-agent.
        source (str): A description of how this agent was discovered (e.g., 'env', 'pidfile').
    """

    def __init__(self, auth_sock: Path, pid: Optional[int] = None, source: str = "unknown"):
        self.auth_sock = auth_sock
        self.pid = pid
        self.source = source

    @property
    def env(self) -> Dict[str, str]:
        """
        Constructs the environment variables needed for subprocesses to talk to this agent.

        Returns:
            Dict[str, str]: A dictionary containing SSH_AUTH_SOCK and SSH_AGENT_PID.
        """
        env = os.environ.copy()
        env["SSH_AUTH_SOCK"] = str(self.auth_sock)
        if self.pid:
            env["SSH_AGENT_PID"] = str(self.pid)
        return env

    def is_valid(self) -> bool:
        """
        Checks if the agent is responsive and reachable.

        This pings the agent using 'ssh-add -l'.
        - Return code 0: Agent is alive and has identities.
        - Return code 1: Agent is alive but has no identities.
        - Other codes: Agent is unreachable or errored.

        Returns:
            bool: True if the agent responds correctly, False otherwise.
        """
        if not self.auth_sock.exists():
            return False
        try:
            # We use ssh-add -l as a "ping".
            res = subprocess.run(
                ["ssh-add", "-l"],
                env=self.env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2  # Don't hang if the socket is stale
            )
            return res.returncode in (0, 1)
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def stop(self) -> None:
        """
        Terminates the ssh-agent process.

        This sends a SIGTERM to the PID associated with this agent instance.
        """
        if not self.pid:
            logger.info("No PID known for current agent; cannot stop.")
            return

        try:
            os.kill(self.pid, signal.SIGTERM)
            logger.info(f"Stopped ssh-agent (PID: {self.pid})")
        except ProcessLookupError:
            logger.info(f"ssh-agent (PID: {self.pid}) is already dead.")
        except PermissionError:
            logger.error(f"Permission denied when trying to stop PID {self.pid}.")

    def clear_keys(self) -> None:
        """
        Removes all identities from the agent.

        Equivalent to running 'ssh-add -D'.
        """
        try:
            subprocess.run(
                ["ssh-add", "-D"],
                env=self.env,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info("All identities removed from agent.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clear identities: {e.stderr.strip()}")

    def get_loaded_fingerprints(self) -> Set[str]:
        """
        Retrieves the fingerprints of all keys currently loaded in the agent.

        Returns:
            Set[str]: A set of SHA256 fingerprints.
        """
        try:
            res = subprocess.run(
                ["ssh-add", "-l"],
                env=self.env,
                capture_output=True,
                text=True
            )
            # 1 means the agent is alive but empty
            if res.returncode == 1:
                return set()

            # Typical output: "2048 SHA256:abc... user@host (RSA)"
            # We want the second column (the fingerprint).
            fingerprints = set()
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    fingerprints.add(parts[1])
            return fingerprints
        except subprocess.SubprocessError:
            return set()

    def add_keys(self, key_paths: List[Path]) -> None:
        """
        Adds multiple private keys to the agent.

        Args:
            key_paths (List[Path]): List of absolute paths to private key files.
        """
        if not key_paths:
            return

        logger.info(f"Adding {len(key_paths)} ssh key(s)...")
        try:
            # We convert Paths to strings for the subprocess call.
            cmd = ["ssh-add"] + [str(p) for p in key_paths]
            subprocess.run(cmd, env=self.env, check=True)
        except subprocess.CalledProcessError:
            logger.error("Failed to add one or more keys. You might need to enter a passphrase.")

    @classmethod
    def spawn_new(cls, agent_bin: str = "ssh-agent") -> "SSHAgent":
        """
        Starts a fresh ssh-agent process.

        Args:
            agent_bin (str): Path or name of the ssh-agent executable.

        Returns:
            SSHAgent: A new instance representing the spawned process.

        Raises:
            RuntimeError: If the agent fails to start or output is unparseable.
            SystemExit: If the ssh-agent executable is missing.
        """
        try:
            # -s forces Bourne shell syntax which is easiest to parse.
            res = subprocess.run([agent_bin, "-s"], capture_output=True, text=True, check=True)

            # We expect output like:
            # SSH_AUTH_SOCK=/tmp/ssh-XXXXXX/agent.123; export SSH_AUTH_SOCK;
            # SSH_AGENT_PID=124; export SSH_AGENT_PID;
            sock_match = re.search(r'SSH_AUTH_SOCK=([^;]+);', res.stdout)
            pid_match = re.search(r'SSH_AGENT_PID=(\d+);', res.stdout)

            if not sock_match or not pid_match:
                raise RuntimeError(f"Could not parse ssh-agent output: {res.stdout}")

            return cls(
                auth_sock=Path(sock_match.group(1)),
                pid=int(pid_match.group(1)),
                source="spawned"
            )
        except FileNotFoundError:
            logger.error(f"Executable '{agent_bin}' not found in PATH.")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"'{agent_bin}' failed to start: {e.stderr}")



class KeychainEnvironment:
    """
    Manages the persistent state of keychain on the filesystem.

    This class handles the creation and reading of shell-specific script files
    in ~/.keychain/ that allow shell sessions to 'inherit' the ssh-agent.
    """

    def __init__(self):
        """Initializes the environment manager with host-specific file paths."""
        self.hostname = socket.gethostname()
        self.keydir = Path.home() / ".keychain"

        # We generate different files for different shell families.
        self.sh_file = self.keydir / f"{self.hostname}-sh"      # Bourne: bash, zsh, dash
        self.csh_file = self.keydir / f"{self.hostname}-csh"    # C-Shell: csh, tcsh
        self.fish_file = self.keydir / f"{self.hostname}-fish"  # Fish

    def get_agent_from_pidfile(self) -> Optional[SSHAgent]:
        """
        Attempts to reconstruct an agent instance from the existing Bourne sh pidfile.

        Returns:
            Optional[SSHAgent]: An agent instance if found and parseable, else None.
        """
        if not self.sh_file.exists():
            return None

        try:
            content = self.sh_file.read_text()
            # We look for the export lines we wrote previously.
            sock_match = re.search(r'SSH_AUTH_SOCK="([^"]+)"', content)
            pid_match = re.search(r'SSH_AGENT_PID=(\d+)', content)

            if sock_match:
                pid = int(pid_match.group(1)) if pid_match else None
                return SSHAgent(Path(sock_match.group(1)), pid, source="pidfile")
        except (IOError, ValueError):
            pass
        return None

    def get_agent_from_env(self) -> Optional[SSHAgent]:
        """
        Detects if an ssh-agent is already provided by the current environment variables.

        Returns:
            Optional[SSHAgent]: An agent instance if SSH_AUTH_SOCK is set, else None.
        """
        sock = os.environ.get("SSH_AUTH_SOCK")
        if sock:
            pid_str = os.environ.get("SSH_AGENT_PID")
            pid = int(pid_str) if pid_str and pid_str.isdigit() else None
            return SSHAgent(Path(sock), pid, source="environment")
        return None

    def persist_agent(self, agent: SSHAgent) -> None:
        """
        Writes export scripts for all supported shells to ~/.keychain/.

        Args:
            agent (SSHAgent): The agent instance to persist.
        """
        self.keydir.mkdir(parents=True, exist_ok=True)
        self.keydir.chmod(0o700) # Strict directory permissions

        sock_str = str(agent.auth_sock)
        pid = agent.pid

        # 1. Bourne Shell (sh, bash, zsh)
        sh_content = f'SSH_AUTH_SOCK="{sock_str}"; export SSH_AUTH_SOCK;\n'
        if pid:
            sh_content += f'SSH_AGENT_PID={pid}; export SSH_AGENT_PID;\n'

        # 2. C-Shell (csh, tcsh)
        csh_content = f'setenv SSH_AUTH_SOCK "{sock_str}";\n'
        if pid:
            csh_content += f'setenv SSH_AGENT_PID {pid};\n'

        # 3. Fish Shell
        # We use Universal variables (-U) and export (-x) so they persist across sessions.
        fish_content = f'set -e SSH_AUTH_SOCK; set -x -U SSH_AUTH_SOCK "{sock_str}";\n'
        if pid:
            fish_content += f'set -e SSH_AGENT_PID; set -x -U SSH_AGENT_PID {pid};\n'

        # Write all files with strict permissions
        targets = [
            (self.sh_file, sh_content),
            (self.csh_file, csh_content),
            (self.fish_file, fish_content)
        ]
        for path, content in targets:
            path.write_text(content)
            path.chmod(0o600)

    def clean_pidfiles(self) -> None:
        """Deletes all shell export scripts from ~/.keychain/."""
        for f in [self.sh_file, self.csh_file, self.fish_file]:
            f.unlink(missing_ok=True)

    def get_eval_string(self) -> str:
        """
        Determines the appropriate eval string for the user's current shell.

        Returns:
            str: The content of the shell-specific export script.
        """
        shell_path = os.environ.get("SHELL", "")
        shell_name = Path(shell_path).name

        if "fish" in shell_name:
            target = self.fish_file
        elif "csh" in shell_name or "tcsh" in shell_name:
            target = self.csh_file
        else:
            # Default to Bourne shell family
            target = self.sh_file

        return target.read_text() if target.exists() else ""


def resolve_key_path(key_name: str) -> Optional[Path]:
    """
    Attempts to find a private key file based on a name or path.

    Resolution order:
    1. If it's an absolute path that exists.
    2. If it's a relative path that exists.
    3. If it exists inside ~/.ssh/.

    Args:
        key_name (str): The name or path of the key.

    Returns:
        Optional[Path]: The resolved absolute path to the key, or None if not found.
    """
    p = Path(key_name).expanduser()

    # Check if direct path works
    if p.exists():
        return p.resolve()

    # Check ~/.ssh/ fallback
    ssh_p = Path.home() / ".ssh" / key_name
    if ssh_p.exists():
        return ssh_p.resolve()

    return None

def get_key_fingerprint(key_path: Path) -> Optional[str]:
    """
    Computes the SHA256 fingerprint of a private key.

    Args:
        key_path (Path): Path to the private key file.

    Returns:
        Optional[str]: The fingerprint string (e.g., 'SHA256:...'), or None on failure.
    """
    try:
        # ssh-keygen -l -f <key> prints the fingerprint of the key.
        res = subprocess.run(
            ["ssh-keygen", "-l", "-f", str(key_path)],
            capture_output=True,
            text=True,
            check=True
        )
        # Output format: "4096 SHA256:xyz... comment (RSA)"
        return res.stdout.split()[1]
    except (subprocess.CalledProcessError, IndexError, IOError):
        return None


def main() -> None:
    """
    Main entry point for the keychain utility.

    This function orchestrates the agent discovery, lifecycle management,
    key loading, and shell integration.
    """
    parser = argparse.ArgumentParser(
        description="Modern Python Keychain: Manage your OpenSSH agent and keys with ease."
    )
    parser.add_argument(
        "keys", nargs="*",
        help="Names or paths of SSH keys to load (e.g., 'id_rsa' or '~/.ssh/my_key')"
    )
    parser.add_argument(
        "--eval", action="store_true",
        help="Output the shell commands to set environment variables (intended for 'eval')"
    )
    parser.add_argument(
        "--stop", action="store_true",
        help="Stop the currently managed ssh-agent and clean up pidfiles"
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Remove all identities currently loaded in the agent"
    )
    parser.add_argument(
        "--agent", type=str, default="ssh-agent",
        help="Path to the ssh-agent binary to use (default: ssh-agent)"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress all informational logs (errors will still be shown)"
    )

    args = parser.parse_args()

    # Configure verbosity based on -q flag
    if args.quiet:
        logger.setLevel(logging.WARNING)

    env_mgr = KeychainEnvironment()

    # --- 1. Handle Stop Request ---
    # If the user wants to stop the agent, we do it first and exit.
    if args.stop:
        agent = env_mgr.get_agent_from_pidfile()
        if agent:
            agent.stop()
        else:
            logger.info("No ssh-agent currently tracked in ~/.keychain/")
        env_mgr.clean_pidfiles()
        return

    # --- 2. Agent Discovery & Lifecycle ---
    # We try to find a valid agent in this order:
    # 1. Previously tracked agent (from ~/.keychain/ pidfile)
    # 2. Inherited agent (from current SSH_AUTH_SOCK environment variable)
    # 3. New agent (spawned if no valid agent found)

    agent = env_mgr.get_agent_from_pidfile()

    if not agent or not agent.is_valid():
        agent = env_mgr.get_agent_from_env()

    if not agent or not agent.is_valid():
        agent = SSHAgent.spawn_new(agent_bin=args.agent)
        logger.info(f"Started new ssh-agent using '{args.agent}' (PID: {agent.pid})")
    else:
        logger.info(f"Found existing ssh-agent ({agent.source})")

    # Ensure the current agent's details are persisted for future sessions.
    env_mgr.persist_agent(agent)

    # --- 3. Key Management ---
    # Optional: Clear existing keys if requested.
    if args.clear:
        agent.clear_keys()

    # Load requested keys if they aren't already in the agent.
    if args.keys:
        loaded_fps = agent.get_loaded_fingerprints()
        keys_to_add: List[Path] = []

        for key_name in args.keys:
            key_path = resolve_key_path(key_name)
            if not key_path:
                logger.error(f"Cannot find key file: {key_name}")
                continue

            fp = get_key_fingerprint(key_path)
            if not fp:
                logger.error(f"Could not extract fingerprint for: {key_name}")
                continue

            # Check if this key's fingerprint is already known by the agent.
            if fp in loaded_fps:
                logger.info(f"Known ssh key: {key_name}")
            else:
                keys_to_add.append(key_path)

        # Add all new keys in a single batch call.
        agent.add_keys(keys_to_add)

    # --- 4. Shell Integration ---
    # If --eval was passed, we print the export script to stdout.
    # Note: sys.stdout.write is used to avoid trailing newlines if not needed,
    # though here we just dump the file content.
    if args.eval:
        eval_str = env_mgr.get_eval_string()
        if eval_str:
            sys.stdout.write(eval_str)
        else:
            logger.error("No eval string available. Was the agent started correctly?")



if __name__ == "__main__":
    main()
