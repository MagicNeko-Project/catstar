# Catstar General Aliases

alias ls='ls --color=auto'
alias ll='ls -lAh --color=auto --time-style=long-iso'
alias llt='ls -lAhtr --color=auto --time-style=long-iso'
alias wgetr='wget -r -np -R "index.html*"'
alias ydla='yt-dlp -o "%(title)s.%(ext)s" -f mp4 --extract-audio --write-thumbnail --write-description'
alias ydl4='yt-dlp -o "%(title)s.%(ext)s" -f mp4'
alias ydl='yt-dlp -o "%(title)s.%(ext)s"'
alias ydlbest='yt-dlp -o "%(title)s.%(ext)s" -f "bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best" --merge-output-format mp4'
alias ydlbest4='yt-dlp -o "%(title)s.%(ext)s" -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best" --merge-output-format mp4'
alias m='mpv'

if (($+commands[supervisorctl])); then
    alias ct='supervisorctl'
    alias lct='launchctl'
elif (($+commands[launchctl])); then
    alias ct='launchctl'
    alias lct='launchctl'
elif (($+commands[systemctl])); then
    alias ct='systemctl'
    alias sct='sudo systemctl'
    alias ctu='systemctl --user'
    alias jt='journalctl -u'
    alias sjt='sudo journalctl -u'
    alias jtf='journalctl -fu'
    alias sjtf='sudo journalctl -fu'
    alias jtu='journalctl --user -u'
    alias jtfu='journalctl --user -fu'
fi

alias reload='sudo killall -SIGUSR1'
alias dns='sudo killall -SIGHUP mDNSResponder'

if (($+commands[paru])); then
    alias y='paru'
elif (($+commands[yay])); then
    alias y='yay'
elif (($+commands[pacman])); then
    alias y='pacman'
elif (($+commands[brew])); then
    alias y='brew'
elif (($+commands[apt-get])); then
    alias y='apt-get'
fi

if (($+commands[uuid])); then
    alias u='uuid -v4'
elif (($+commands[uuidgen])); then
    alias u='uuidgen'
fi

alias tar0="tar --numeric-owner --owner=0 --group=0"
alias tarz="tar --zstd"
alias tarz0="tar --zstd --numeric-owner --owner=0 --group=0"
