# systemd Security & Sandboxing Cheatsheet

This cheatsheet provides a hardened baseline configuration for systemd service units, along with explanations and critical compatibility caveats. It is designed for standard, non-system/user-facing service units that do not need to perform administrative or OS-level tasks.

---

## 1. Hardened Baseline Templates

### 1.1 DynamicUser Baseline (Recommended for Unprivileged Daemons)

Use this baseline for standalone services, webhooks, bots, and background workers that do not require static system users or persistent OS-level identity:

```ini
[Service]
# --- User & Privilege Isolation ---
# Transient UID/GID (automatically enforces NoNewPrivileges=, RestrictSUIDSGID=, ProtectSystem=strict, RemoveIPC=)
DynamicUser=yes

# --- File System Protection ---
# Fully hides /home, /root, and /run/user (upgrades implied read-only to inaccessible)
ProtectHome=yes
# Allocates an isolated, private /tmp and /var/tmp namespace
PrivateTmp=yes
# Hides processes owned by other users from /proc
ProtectProc=invisible

# --- Hardware & Kernel Protection ---
# Blocks raw hardware access and exposes minimal pseudo /dev nodes
PrivateDevices=yes
# Prevents modification of system or hardware clock
ProtectClock=yes
# Makes kernel tunables (/proc/sys, /sys) read-only
ProtectKernelTunables=yes
# Prevents explicit kernel module loading/unloading
ProtectKernelModules=yes
# Blocks access to kernel log ring buffer (/dev/kmsg, syslog)
ProtectKernelLogs=yes

# --- Namespaces & Process Isolation ---
# Blocks modifying hostname or domainname
ProtectHostname=yes
# Prevents acquiring real-time CPU scheduling privileges
RestrictRealtime=yes
# Prevents the process from creating new Linux namespaces
RestrictNamespaces=yes
# Prevents changing execution domain via personality(2)
LockPersonality=yes

# --- Control Groups, Keyrings & Syscalls ---
# Isolates unit in a private cgroup namespace with read-only cgroup mount
ProtectControlGroups=strict
# Allocates an isolated kernel session keyring
KeyringMode=private
# Restricts network socket creation to Unix domain and standard IP sockets
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
# Restricts system calls to native architecture (blocks 32-bit transition on 64-bit kernels)
SystemCallArchitectures=native
# Whitelists standard system service system calls
SystemCallFilter=@system-service
```

### 1.2 Static User Baseline (For Units Requiring Dedicated UIDs)

Use this baseline when services require static ownership, specific user home directories, or D-Bus bus name ownership:

```ini
[Service]
User=my-service
Group=my-service

# --- User & Privilege Isolation ---
NoNewPrivileges=yes
RestrictSUIDSGID=yes

# --- File System Protection ---
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ProtectProc=invisible

# --- Hardware & Kernel Protection ---
PrivateDevices=yes
ProtectClock=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes

# --- Namespaces & Process Isolation ---
ProtectHostname=yes
RestrictRealtime=yes
RestrictNamespaces=yes
LockPersonality=yes

# --- Control Groups, Keyrings & Syscalls ---
ProtectControlGroups=strict
KeyringMode=private
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
SystemCallArchitectures=native
SystemCallFilter=@system-service
```

---

## 2. Meticulous Directive Explanations & Reference

| Directive | Recommended Value | Detailed Functionality | Compatibility / Caveats |
| :--- | :--- | :--- | :--- |
| **`DynamicUser=`** | `yes` | Allocates a transient UID/GID (61184–65519) on-the-fly via `nss-systemd`. Recycled on service termination. | Automatically implies `NoNewPrivileges=yes`, `RestrictSUIDSGID=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, `RemoveIPC=yes`, and `PrivateTmp=disconnected`. See Section 3. |
| **`NoNewPrivileges=`** | `yes` | Prevents the process and its children from gaining new privileges (such as via SUID/SGID bits or file capabilities). | Strongly recommended for all unprivileged units. Cannot be disabled if `DynamicUser=yes` is set. |
| **`RestrictSUIDSGID=`** | `yes` | Denies creating or setting SUID/SGID bits on files and directories, and prevents executing existing SUID/SGID binaries (blocking privilege elevation). | Implied by `DynamicUser=yes`. Recommended for all unprivileged static units. |
| **`ProtectSystem=`** | `full` | Mounts `/usr/`, `/boot` read-only. Setting `full` also mounts `/etc/` read-only. | Essential for blocking system configuration changes. `DynamicUser=yes` natively enforces `strict` (read-only `/`). |
| **`ProtectHome=`** | `yes` | Makes `/home/`, `/root`, and `/run/user/` invisible and inaccessible. | **Critical Warning:** Must be set to `no` (or `read-only`) for services that need to read/write to user home directories (e.g., code editors, user document processors). |
| **`PrivateTmp=`** | `yes` | Mounts a private `/tmp` and `/var/tmp` directory using file system namespaces. Files are deleted when the service stops. | Supported in `systemd --user` units out-of-the-box (systemd automatically enables `PrivateUsers=true`), provided unprivileged user namespaces are enabled on the host (`kernel.unprivileged_userns_clone=1`). |
| **`ProtectProc=`** | `invisible` | Restricts access to other users' processes in `/proc`. | Set to `invisible` to hide processes completely. Requires Linux kernel 5.8+ or systemd to emulate via hidepid mount. |
| **`ProcSubset=`** | `pid` | Restricts the `/proc` filesystem to show only PID information, hiding system information like `/proc/cpuinfo`, `/proc/meminfo`, etc. | May break applications that rely on system performance auditing or hardware querying. |
| **`PrivateDevices=`** | `yes` | Sets up a private `/dev` mount with only basic loopback and pseudo API devices (`/dev/null`, `/dev/zero`, etc.), hiding physical disk nodes. | Breaks services requiring raw GPU access, physical storage devices, or raw sound card access. |
| **`ProtectClock=`** | `yes` | Blocks write access to the hardware/system clock and disables related time-setting system calls (`adjtimex`, `settimeofday`, etc.). | Must be disabled for NTP clients or time-synchronization services. |
| **`ProtectKernelTunables=`** | `yes` | Mounts `/proc/sys`, `/sys`, `/sys/fs/selinux`, etc., as read-only. | Blocks the service from adjusting system-wide sysctl and kernel configurations at runtime. |
| **`ProtectKernelModules=`** | `yes` | Denies explicit kernel module loading/unloading. | Explicitly blocks the `init_module` and `finit_module` system calls. |
| **`ProtectKernelLogs=`** | `yes` | Blocks access to the kernel log ring buffer (`/dev/kmsg` or `syslog(2)`). | Prevent daemons from sniffing kernel messages or details about other processes. |
| **`ProtectControlGroups=`** | `strict` | Runs the unit in a private cgroup namespace with a private read-only cgroup mount (`/sys/fs/cgroup`). Falls back to `yes` if cgroup namespaces are unavailable. | Standard system services should never need write access to cgroups. |
| **`KeyringMode=`** | `private` | Allocates an isolated kernel session keyring, preventing credential sharing across services sharing a UID. | Recommended to isolate processes that share the same user context. |
| **`MemoryDenyWriteExecute=`** | `yes` | Enforces W^X (Write XOR Execute) memory mappings, blocking dynamic execution of modified memory segments. | **Critical Warning:** Incompatible with JIT compilation engines (such as V8 in Node.js/Electron, Java JVM, PyPy, or python packages using ctypes). |
| **`RestrictNamespaces=`** | `yes` | Prohibits the unit's processes from creating or switching Linux namespaces (`unshare`, `clone`, `setns`). | Still allows systemd itself to configure unit namespacing (like `PrivateTmp` and `ProtectSystem`). |
| **`LockPersonality=`** | `yes` | Locks down the personality(2) system call, preventing the execution of non-native binaries (e.g. running 32-bit binaries on a 64-bit kernel). | Prevents kernel exploit vectors targeting compatibility layers. |
| **`RestrictAddressFamilies=`** | `AF_UNIX AF_INET AF_INET6` | Restricts socket families to local Unix sockets and standard IPv4/IPv6 networks. | Blocks access to raw sockets (`AF_PACKET`) or netlink (`AF_NETLINK`) unless specifically required. |
| **`SystemCallFilter=`** | `@system-service` | Restricts system calls to a pre-defined safe whitelist of system calls suitable for services. | Can be customized to include specific calls or exclude groups using the `~` prefix (e.g., `~@mount`). |

---

## 3. DynamicUser Lifecycle & Sandboxing Mechanics

When `DynamicUser=yes` is enabled, systemd activates runtime sandboxing mechanisms designed for unprivileged, transient services.

### Transient UID Allocation
* Transient UIDs/GIDs are allocated from the reserved range `61184`–`65519` upon unit start and immediately released back to the pool upon unit termination.
* Identity resolution is synthesized at runtime via `nss-systemd(8)` rather than modifying static databases (`/etc/passwd`, `/etc/group`).

### Implied Directives (Invariable Enforcements)
Enabling `DynamicUser=yes` automatically implies and enforces the following security boundaries (which cannot be disabled):
* **`RemoveIPC=yes`**: Destroys all System V and POSIX IPC primitives (shared memory, semaphores, message queues) owned by the UID upon service shutdown.
* **`NoNewPrivileges=yes`**: Prevents privilege escalation through SUID/SGID bits or filesystem capabilities.
* **`RestrictSUIDSGID=yes`**: Bidirectionally restricts the process tree from creating or setting SUID/SGID bits on files, and blocks privilege elevation during execution of existing SUID/SGID binaries.
* **`ProtectSystem=strict`**: Mounts the entire host VFS read-only (`/`), excluding `/dev`, `/proc`, `/sys`, and explicitly declared writable directories.
* **`ProtectHome=read-only`**: Mounts `/home/`, `/root/`, and `/run/user/` read-only (explicitly declare `ProtectHome=yes` to make them completely invisible/inaccessible).
* **`PrivateTmp=disconnected`**: Unshares the `/tmp` and `/var/tmp` namespaces in a disconnected mode (overridden to a private temporary directory with `PrivateTmp=yes`).

### Directory Isolation & UID Reuse Mitigation
To prevent privilege crossover and UID reuse attacks across service restarts, persistent directories are managed via private host stores:
* **Persistent Stores (`StateDirectory=`, `CacheDirectory=`, `LogsDirectory=`)**:
  * Files are stored on the host under `/var/lib/private/`, `/var/cache/private/`, and `/var/log/private/` with restrictive permissions (`0700`).
  * On modern kernels supporting ID-mapped mounts (Linux 5.12+), systemd directly maps UID/GID ranges at the VFS mount layer without recursive on-disk metadata modifications. On filesystems or kernels lacking ID-mapped mount support, systemd safely falls back to checking and recursively re-chowning the directory tree when the top-level directory UID changes on startup.
* **Runtime Data (`RuntimeDirectory=`)**:
  * Places transient runtime data under `/run/` (or `/run/private/` when `RuntimeDirectoryPreserve=` is set) and purges the directory upon service termination.

### Defaults & Constraints
* **Environment Provisioning**: `SetLoginEnvironment=true` is the default behavior, auto-populating `$HOME`, `$LOGNAME`, `$USER`, and `$SHELL`.
* **D-Bus Bus Ownership**: Incompatible with registering or acquiring well-known system D-Bus bus names, as D-Bus daemon security policies require static UIDs.

---

## 4. Auditing Service Security

You can audit the security/exposure score of any active systemd service unit using the built-in auditing tool:

```bash
systemd-analyze security your-service-name.service
```

This commands lists the active sandboxing options, evaluates the security posture, and offers specific recommendations to lower the service's overall exposure score.
