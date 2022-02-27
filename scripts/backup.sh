#!/bin/bash

set -x

export RESTIC_REPOSITORY=
export RESTIC_PASSWORD=

TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_SendMsg_User=
DISCORD_WEBHOOK_URL=

export TZ=Asia/Shanghai

# 定义提醒函数
telegram_send() {
  TELEGRAM_URL="https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
  curl "$TELEGRAM_URL" \
    -F chat_id="$TELEGRAM_BOT_SendMsg_User" \
    -F text="$1"
}

discord_send() {
  curl "$DISCORD_WEBHOOK_URL" \
    -F username="Catstar 备份通知" \
    -F content="$1"
}

notify_send() {
  telegram_send "$1"
  discord_send "$1"
}

BEGIN="$(date '+%F %T')"
btrfs subvolume delete /snapshots/root
btrfs subvolume snapshot -r / /snapshots/root
restic backup --exclude '**/.cache' --exclude '**/*.db' /snapshots/root
btrfs subvolume delete /snapshots/root
END="$(date '+%F %T')"

MSG="CyanMC (Cato-6) 备份完成
结束时间：$END
$(journalctl -u catstar-backup.service -o cat -n 15 | head -n -4)"

if [ "$(date +'%H')" -eq 21 ]; then
  notify_send "$MSG"
fi
