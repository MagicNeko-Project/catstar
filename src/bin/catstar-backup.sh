#!/bin/bash

# 定义提醒函数
telegram_send() {
  TELEGRAM_URL="https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
  curl "$TELEGRAM_URL" \
    -F chat_id="$TELEGRAM_BOT_SendMsg_User" \
    -F text="$1"
}

discord_send() {
  curl "$DISCORD_WEBHOOK_URL" \
    -F username="$DISCORD_USERNAME" \
    -F content="$1"
}

debug_send() {
  echo "发送通知：$1"
}

notify_send() {
  if [[ -v TELEGRAM_BOT_TOKEN ]]; then
    telegram_send "$1"
  fi

  if [[ -v DISCORD_WEBHOOK_URL ]]; then
    discord_send "$1"
  fi

  if [[ -v NOTIFY_DEBUG ]]; then
    debug_send "$1"
  fi
}

notify_send_verbose() {
  # echo "通知：$1"
  if [[ -v NOTIFY_SEND_VERBOSE ]]; then
    notify_send "$1"
  fi
}

# 定义备份函数
backup_btrfs_restic() {
  notify_send_verbose "$MACHINE_NAME 开始备份：btrfs 子卷快照 + restic"
  btrfs subvolume delete "$BTRFS_SNAPSHOTS_ROOT/"* || true

  local subvol dest
  for subvol in "${!BTRFS_SNAPSHOT_@}"; do
    dest="${subvol#BTRFS_SNAPSHOT_}"
    btrfs subvolume snapshot -r "${!subvol}" "$BTRFS_SNAPSHOTS_ROOT/$dest"
  done

  pushd "$BTRFS_SNAPSHOTS_ROOT"
  restic backup --exclude="**/.cache" --exclude="**/*.db" .
  popd

  btrfs subvolume delete "$BTRFS_SNAPSHOTS_ROOT/"*
}

backup_root_tar() {
  notify_send_verbose "$MACHINE_NAME 开始备份：tar.zst"
  printf -v TAR_SAVE_FILE "$TAR_FILE_NAME"
  tar -I zstd -cp --one-file-system --exclude="$HOME/.cache" / | openssl "$TAR_OPENSSL_TYPE" -salt -k "$TAR_OPENSSL_PASSWORD" | dd bs=64K | ssh "$TAR_SSH_SERVER" "cat > '$TAR_SAVE_FILE'"
}

backup_root_restic() {
  notify_send_verbose "$MACHINE_NAME 开始备份：restic"
  restic backup --one-file-system --exclude="**/.cache" --exclude="**/*.db" /
}

backup_test() {
  notify_send_verbose "$MACHINE_NAME 开始备份：测试，只输出消息"
  local i
  for i in {1..5}; do
    echo "测试备份消息：123*$i"
  done
  return "$BACKUP_TEST"
}


backup_main() {
  set -eu  # 报错立即退出

  notify_send_verbose "开始备份时间: $(printf '%(%F %T)T')"

  if [[ -v BACKUP_TEST ]]; then
    backup_test
  fi

  if [[ -v TAR_SSH_SERVER ]]; then
    backup_root_tar
  fi

  if [[ -v RESTIC_REPOSITORY ]]; then
    backup_root_restic
  fi

  if [[ -v BTRFS_SNAPSHOTS_ROOT ]]; then
    backup_root_btrfs
  fi

  notify_send_verbose "结束备份时间: $(printf '%(%F %T)T')"
}

printf -v BACKUP_BEGIN "%(%F %T)T"
(backup_main) &
wait $!
BACKUP_STAT=$?
printf -v BACKUP_END "%(%F %T)T"

# journald 日志
JOURNAL="$(journalctl -o cat -n 15 _PID=$!)"

if [[ "$BACKUP_STAT" -ne 0 ]]; then
  notify_send "$MACHINE_NAME 备份失败！
错误码：$BACKUP_STAT
开始：$BACKUP_BEGIN
结束：$BACKUP_END
$JOURNAL"
elif [[ -v NOTIFY_SEND_SUMMARY ]]; then
  if [[ ! -v NOTIFY_SEND_SUMMARY_HOURS ]] || [[ " $NOTIFY_SEND_SUMMARY_HOURS " =~ " $(printf '%(%H)T') " ]]; then
    notify_send "$MACHINE_NAME 备份完成！
开始：$BACKUP_BEGIN
结束：$BACKUP_END
$JOURNAL"
  fi
fi
