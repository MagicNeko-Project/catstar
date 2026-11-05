# ⚠️ DEMONSTRATION KEYS ONLY

## Intentional Inclusion
The presence of private keys in this directory is **intentional** and purely for **demonstration and testing purposes**. These keys are part of a mock setup and do not grant access to any production environments or sensitive data.

## 🚨 Security Warning
- **PUBLICLY EXPOSED**: These keys are committed to a public or shared repository and are therefore **compromised**.
- **DO NOT USE**: Never use these keys for any real-world authentication or encryption.
- **RISK**: Using these keys in a real environment creates a severe security vulnerability.

---

## Key Catalog & References

### 1. `age-key.txt` (Age Secret Key)
- **Tool**: [age](https://github.com/FiloSottile/age)
- **Purpose**: Repository-level secret management.
- **Reference**: Intended for encrypting and decrypting sensitive configuration files or Ansible variable blocks that are stored in the repository.
- **Usage Guide**:
  ```bash
  # Decrypt a file using this secret key
  age --decrypt -i keys/age-key.txt secret.age > secret.txt
  ```

### 2. `id_ed25519` / `id_ed25519.pub` (SSH Key Pair)
- **Tool**: OpenSSH
- **Purpose**: System identity and remote authentication.
- **Reference**:
    - **Backups**: Specifically used by `src/bin/catstar-backup.sh` to authenticate with the remote backup server (`TAR_SSH_SERVER`) during data streaming.
    - **Automation**: Used by the `catstar` system to identify itself to other nodes in the cluster.
- **Usage Guide**:
  ```bash
  # Connect to a remote host using this identity
  ssh -i keys/id_ed25519 user@remote-backup-server

  # Deploy the public key to a new remote host
  ssh-copy-id -i keys/id_ed25519.pub user@remote-backup-server
  ```
