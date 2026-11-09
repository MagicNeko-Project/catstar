# KeePassXC Key File with Paper Backup

The database uses a **composite key**: master password plus key file. The key file lives locally on every device that opens the database, with a handwritten paper copy as the authoritative backup. The `.kdbx` may sync through untrusted storage; the key file never does.

## Security Model

| Attacker holds | Remaining protection |
|---|---|
| `.kdbx` from cloud storage or its version history | Password **and** 256-bit key file — brute force infeasible |
| A device (key file on disk) | Password + KDF only — keep the password strong, disks encrypted |
| The paper backup | Password and the `.kdbx` |
| Malware on an unlocked device | None |

## Format

XML key file, version 2.0 — natively generated and read by KeePass-family clients, and designed for printing and retyping:

```xml
<KeyFile><Meta><Version>2.0</Version></Meta><Key><Data Hash="XXXXXXXX">…64 hex characters…</Data></Key></KeyFile>
```

- `Data` is the 32-byte key; `Hash` is the first 4 bytes of its SHA-256, a transcription check.
- Whitespace and letter case are ignored. A typo fails at key file load, distinct from a wrong-credentials error.
- A few illegible characters are recoverable by enumerating candidates against `Hash` (16 per unknown character), then confirming by opening the database.

Hex over BIP39 words: clients restore hex natively, while words would make recovery depend on a converter existing on every platform years later.

## Generation

Use KeePassXC's own generator on a trusted device, preferably offline — the key never passes through a chat, AI agent, or any networked tool.

- Existing database: Database Security → add Key File protection → Generate.
- New database: `keepassxc-cli db-create -p --set-key-file vault.keyx vault.kdbx` creates the key file when the path does not yet exist.

Verify before transcribing to paper:

- Opens with password + key file; is rejected with the password alone.
- `keepassxc-cli db-info` reports KDF Argon2id — `db-create` defaults to AES-KDF, which leaves the password weaker against device theft. Change it under Database Security → Encryption Settings.

## Invariants

- The key file never crosses a network: no cloud sync, chat or AI agents, synced clipboards, cloud-learning keyboards, or device backups that include app data. Install it offline (USB, cable, retyping).
- The key file never changes. A different `Data` is a different key; never regenerate on a working setup.
- The paper is self-describing — label it with format, target database, the fact that the password is also required, and creation date.
- At least two paper copies in separate locations. The password's sealed backup lives apart from the key file paper — the password is the likelier lockout cause.
- Local `.kdbx` backups exist independently of cloud sync.

## Rotation

No scheduled rotation — a random 256-bit key does not age. Rotate when a device holding it is lost or compromised, the paper may have been seen, or a device is retired unwiped.

- Rotation does not protect existing ciphertext: old `.kdbx` copies still open with the old factors. If both factors may be exposed, rotate the credentials stored inside the database.
- Lock the database on all other devices first — an instance unlocked with the old key can save over the rotated file.
- Keep the old paper, labeled retired, until every backup encrypted with it has aged out.

## Lockout Checklist

- [ ] Password recoverable independently of memory, stored apart from the key file paper
- [ ] Two or more labeled paper copies in separate locations
- [ ] Restore from paper drilled on every client type in use, repeated periodically
- [ ] Key file absent from cloud sync, device backups, and keyboard learning
- [ ] Local `.kdbx` backups outside cloud sync
- [ ] Retired key files kept while their backups remain
