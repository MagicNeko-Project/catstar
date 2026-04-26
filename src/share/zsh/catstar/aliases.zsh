# Catstar General Aliases
# -----------------------------------------------------------------------------
# This file defines general-purpose aliases and smart wrappers for system tools.
# It prioritizes modern, color-enabled, and human-readable output.
# -----------------------------------------------------------------------------

# --- Navigation & File Listing ---
alias ls='ls --color=auto'
alias ll='ls -lAh --color=auto --time-style=long-iso'
alias llt='ls -lAhtr --color=auto --time-style=long-iso'

# --- Network Utilities ---
alias wgetr='wget -r -np -R "index.html*"'

# --- Media Download (yt-dlp) ---
# Common presets for high-quality downloads and audio extraction
alias ydla='yt-dlp -o "%(title)s.%(ext)s" -f mp4 --extract-audio --write-thumbnail --write-description'
alias ydl4='yt-dlp -o "%(title)s.%(ext)s" -f mp4'
alias ydl='yt-dlp -o "%(title)s.%(ext)s"'
alias ydlbest='yt-dlp -o "%(title)s.%(ext)s" -f "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best" --merge-output-format mp4'
alias ydlbest4='yt-dlp -o "%(title)s.%(ext)s" -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best" --merge-output-format mp4'

# --- Media Player ---
alias m='mpv'

# --- Service Management (Smart Detection) ---
# Automatically detects the best available service manager (systemd, launchd, or supervisord)
() {
  if (($+commands[systemctl])); then
    alias ct='systemctl'
    alias sct='sudo systemctl'
    alias ctu='systemctl --user'
    alias jt='journalctl -u'
    alias sjt='sudo journalctl -u'
    alias jtf='journalctl -fu'
    alias sjtf='sudo journalctl -fu'
    alias jtu='journalctl --user -u'
    alias jtfu='journalctl --user -fu'
  elif (($+commands[launchctl])); then
    alias ct='launchctl'
    alias lct='launchctl'
  elif (($+commands[supervisorctl])); then
    alias ct='supervisorctl'
  fi
}

# --- System Maintenance ---
alias reload='sudo killall -SIGUSR1'
alias dns='sudo killall -SIGHUP mDNSResponder'

# --- Universal Package Manager Wrapper ---
# Support 'y' as the primary package manager, 'yy' for upgrade, 'yu' for update, and 'yi' for info.
# This abstraction allows using the same muscle memory across different OSs.
() {
  local -A pms
  pms=(
    paru    "paru;paru -Sy;paru -Syu;paru -Si"
    yay     "yay;yay -Sy;yay -Syu;yay -Si"
    pacman  "sudo pacman;sudo pacman -Sy;sudo pacman -Syu;pacman -Si"
    brew    "brew;brew update;brew update && brew upgrade;brew info"
    apt     "sudo apt;sudo apt update;sudo apt update && sudo apt upgrade;apt show"
    dnf     "sudo dnf;sudo dnf check-update;sudo dnf upgrade;dnf info"
    zypper  "sudo zypper;sudo zypper ref;sudo zypper dup;zypper info"
    apk     "sudo apk;sudo apk update;sudo apk update && sudo apk upgrade;apk info"
  )

  local pm
  # Priority list for detection
  for pm in paru yay pacman brew apt dnf zypper apk; do
    if (( $+commands[$pm] )); then
      local -a cmds
      cmds=(${(s:;:)pms[$pm]})
      alias y=$cmds[1]
      alias yy=$cmds[2]
      alias yu=$cmds[3]
      alias yi=$cmds[4]
      break
    fi
  done
}

# --- Utility Aliases ---
if (($+commands[uuid])); then
  alias u='uuid -v4'
elif (($+commands[uuidgen])); then
  alias u='uuidgen'
fi


