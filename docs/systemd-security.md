# systemd Security & Sandboxing Cheatsheet

This cheatsheet provides a hardened baseline configuration for systemd service units, along with explanations and critical compatibility caveats. It is designed for standard, non-system/user-facing service units that do not need to perform administrative or OS-level tasks.

---

## 1. Hardened Baseline Template

Copy and paste this snippet into the `[Service]` section of your systemd system unit file (e.g., `/etc/systemd/system/my-service.service`):

```ini
[Service]
# --- User & Privilege Isolation ---
# Dynamically allocates a transient UID/GID (implies RemoveIPC=, NoNewPrivileges=, ProtectSystem=strict, ProtectHome=read-only)
DynamicUser=yes
# Ensures the process and its children cannot elevate privileges (via SUID/SGID/capabilities)
NoNewPrivileges=yes
# Denies creation of new SUID/SGID files or directories
RestrictSUIDSGID=yes

# --- File System Protection ---
# Mounts /usr, /boot, and /etc read-only
ProtectSystem=full
# Prevents access to /home, /root, and /run/user (set to "no" if the service needs home dir access)
ProtectHome=yes
# Provides isolated /tmp and /var/tmp directories in a private mount namespace
PrivateTmp=yes
# Hides processes owned by other users from /proc
ProtectProc=invisible
# Restricts /proc to only PID-related files and directories (hides system information)
ProcSubset=pid

# --- Hardware & Kernel Protection ---
# Blocks low-level access to hardware /dev nodes (provides minimal API /dev)
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
# Blocks the process from changing the hostname or domainname
ProtectHostname=yes
# Prevents acquiring real-time CPU scheduling privileges (mitigates DoS)
RestrictRealtime=yes
# Prevents the process itself from creating new Linux namespaces
RestrictNamespaces=yes
# Prevents creating writable/executable memory mappings (W^X) (see JIT caveat below)
MemoryDenyWriteExecute=yes
# Prevents the process from changing its execution domain (personality) via personality(2)
LockPersonality=yes

# --- Control Groups, Keyrings & Sockets ---
# Runs the unit in a cgroup namespace with a private read-only cgroup mount
ProtectControlGroups=strict
# Allocates an isolated kernel session keyring, preventing credential sharing across services sharing a UID
KeyringMode=private
# Restricts network socket creation to Unix domain and standard IP sockets
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
# Allow-lists standard system calls while blocking dangerous administrative calls
SystemCallFilter=@system-service
```

---

## 2. Meticulous Directive Explanations & Reference

| Directive | Recommended Value | Detailed Functionality | Compatibility / Caveats |
| :--- | :--- | :--- | :--- |
| **`DynamicUser=`** | `yes` | Allocates a transient UID/GID (in the range 61184–65519) on-the-fly. The UID is freed when the service stops. | Automatically implies `NoNewPrivileges=yes`, `RestrictSUIDSGID=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, and `RemoveIPC=yes`. |
| **`NoNewPrivileges=`** | `yes` | Prevents the process and its children from gaining new privileges (such as via SUID/SGID bits or file capabilities). | Strongly recommended for all unprivileged units. Cannot be disabled if `DynamicUser=yes` is set. |
| **`ProtectSystem=`** | `full` | Mounts `/usr/`, `/boot` read-only. Setting `full` also mounts `/etc/` read-only. | Essential for blocking system configuration changes. Use `strict` to make the entire filesystem read-only (except API VFS). |
| **`ProtectHome=`** | `yes` | Makes `/home/`, `/root`, and `/run/user/` invisible and inaccessible. | **Critical Warning:** Must be set to `no` (or `read-only`) for services that need to read/write to user home directories (e.g., code editors, user document processors). |
| **`PrivateTmp=`** | `yes` | Mounts a private `/tmp` and `/var/tmp` directory using file system namespaces. Files are deleted when the service stops. | Not supported for services run in user manager instances (`systemd --user`). |
| **`ProtectProc=`** | `invisible` | Restricts access to other users' processes in `/proc`. | Set to `invisible` to hide processes completely. Requires Linux kernel 5.8+ or systemd to emulate via hidepid mount. |
| **`ProcSubset=`** | `pid` | Restricts the `/proc` filesystem to show only PID information, hiding system information like `/proc/cpuinfo`, `/proc/meminfo`, etc. | May break applications that rely on system performance auditing or hardware querying. |
| **`PrivateDevices=`** | `yes` | Sets up a private `/dev` mount with only basic loopback and pseudo API devices (`/dev/null`, `/dev/zero`, etc.), hiding physical disk nodes. | Breaks services requiring raw GPU access, physical storage devices, or raw sound card access. |
| **`ProtectClock=`** | `yes` | Blocks write access to the hardware/system clock and disables related time-setting system calls (`adjtimex`, `settimeofday`, etc.). | Must be disabled for NTP clients or time-synchronization services. |
| **`ProtectKernelTunables=`** | `yes` | Mounts `/proc/sys`, `/sys`, `/sys/fs/selinux`, etc., as read-only. | Blocks the service from adjusting system-wide sysctl and kernel configurations at runtime. |
| **`ProtectKernelModules=`** | `yes` | Denies explicit kernel module loading/unloading. | Explicitly blocks the `init_module` and `finit_module` system calls. |
| **`ProtectKernelLogs=`** | `yes` | Blocks access to the kernel log ring buffer (`/dev/kmsg` or `syslog(2)`). | Prevent daemons from sniffing kernel messages or details about other processes. |
| **`ProtectControlGroups=`** | `strict` | Runs the unit in a cgroup namespace with a private read-only cgroup mount (`/sys/fs/cgroup`). | Standard system services should never need write access to cgroups. |
| **`KeyringMode=`** | `private` | Allocates an isolated kernel session keyring, preventing credential sharing across services sharing a UID. | Recommended to isolate processes that share the same user context. |
| **`MemoryDenyWriteExecute=`** | `yes` | Enforces W^X (Write XOR Execute) memory mappings, blocking dynamic execution of modified memory segments. | **Critical Warning:** Incompatible with JIT compilation engines (such as V8 in Node.js/Electron, Java JVM, PyPy, or python packages using ctypes). |
| **`RestrictNamespaces=`** | `yes` | Prohibits the unit's processes from creating or switching Linux namespaces (`unshare`, `clone`, `setns`). | Still allows systemd itself to configure unit namespacing (like `PrivateTmp` and `ProtectSystem`). |
| **`LockPersonality=`** | `yes` | Locks down the personality(2) system call, preventing the execution of non-native binaries (e.g. running 32-bit binaries on a 64-bit kernel). | Prevents kernel exploit vectors targeting compatibility layers. |
| **`RestrictAddressFamilies=`** | `AF_UNIX AF_INET AF_INET6` | Restricts socket families to local Unix sockets and standard IPv4/IPv6 networks. | Blocks access to raw sockets (`AF_PACKET`) or netlink (`AF_NETLINK`) unless specifically required. |
| **`SystemCallFilter=`** | `@system-service` | Restricts system calls to a pre-defined safe whitelist of system calls suitable for services. | Can be customized to include specific calls or exclude groups using the `~` prefix (e.g., `~@mount`). |

---

## 3. Auditing Service Security

You can audit the security/exposure score of any active systemd service unit using the built-in auditing tool:

```bash
systemd-analyze security your-service-name.service
```

This commands lists the active sandboxing options, evaluates the security posture, and offers specific recommendations to lower the service's overall exposure score.
