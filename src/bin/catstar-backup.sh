#!/bin/bash

# 定义提醒函数
telegram_send() {
  if [[ -v TELEGRAM_BOT_TOKEN ]]; then
    TELEGRAM_URL="https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
    curl -sSo /dev/null "$TELEGRAM_URL" \
      -F chat_id="$TELEGRAM_BOT_SendMsg_User" \
      -F text="$1"
  fi
}

discord_send() {
  if [[ -v DISCORD_WEBHOOK_URL ]]; then
    curl -sSo /dev/null "$DISCORD_WEBHOOK_URL" \
      -F username="$DISCORD_USERNAME" \
      -F content="$1"
  fi
}

debug_send() {
  if [[ -v NOTIFY_DEBUG ]]; then
    echo "发送通知：$1"
  fi
}

notify_send() {
  local text; printf -v text '%s\n' "$@"
  telegram_send "$text"
  discord_send "$text"
  debug_send "$text"
}

notify_summary() {
  local text; printf -v text '%s\n' "$@"
  if ! [[ -v TELEGRAM_SKIP_SUMMARY ]]; then
    telegram_send "$text"
  fi

  if ! [[ -v DISCORD_SKIP_SUMMARY ]]; then
    discord_send "$text"
  fi

  if ! [[ -v DEBUG_SKIP_SUMMARY ]]; then
    debug_send "$text"
  fi
}

notify_send_verbose() {
  append_log "$1"
  local msg="$MACHINE_NAME $1"
  echo "*** $msg ***"
  if [[ -v NOTIFY_SEND_VERBOSE ]]; then
    notify_send "$msg"
  fi
}

append_log() {
  local timestamp
  printf -v timestamp '%(%F %T)T'
  BACKUP_VERBOSE_LOGS+=("$timestamp $*")
}

http_ping() {
  if [[ -v HTTP_PING_URL ]]; then
    curl -sSo /dev/null "$HTTP_PING_URL$1" --data-raw "$2"
  fi
}

http_ping_start() {
  if [[ -v HTTP_PING_START_URL ]]; then
    curl -sSo /dev/null "$HTTP_PING_START_URL" --data-raw "$1"
  fi
}

# 定义备份函数
backup_btrfs_restic() {
  notify_send_verbose "开始备份：btrfs 子卷快照 + restic"
  btrfs subvolume delete "$BTRFS_SNAPSHOTS_ROOT/"* || true

  # 遍历 BTRFS_SNAPSHOT_* 变量，创建快照
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
  notify_send_verbose "开始备份：tar.zst"

  printf -v TAR_SAVE_FILE '%s' "$TAR_FILE_NAME"
  tar -I zstd -cp --one-file-system --exclude="$HOME/.cache" / | openssl "$TAR_OPENSSL_TYPE" -salt -k "$TAR_OPENSSL_PASSWORD" | dd bs=64K | ssh "$TAR_SSH_SERVER" "cat > '$TAR_SAVE_FILE'"
}

backup_root_restic() {
  notify_send_verbose "开始备份：restic"

  restic backup --one-file-system --exclude="**/.cache" --exclude="**/*.db" "$RESTIC_ROOT"
}

backup_test() {
  notify_send_verbose "开始备份：测试，只输出消息"

  local i
  for i in {1..2}; do
    echo "测试备份消息：123*$i"
  done
  return "$BACKUP_TEST"  # 测试返回值
}


backup_main() {
  notify_send_verbose "开始备份时间: $(printf '%(%F %T)T')"
  http_ping_start "开始备份时间: $(printf '%(%F %T)T')"

  if [[ -v BACKUP_TEST ]]; then
    backup_test
  fi

  if [[ -v TAR_SSH_SERVER ]]; then
    backup_root_tar
  fi

  if [[ -v RESTIC_ROOT ]]; then
    backup_root_restic
  fi

  if [[ -v BTRFS_SNAPSHOTS_ROOT ]]; then
    backup_btrfs_restic
  fi

  notify_send_verbose "结束备份时间: $(printf '%(%F %T)T')"
}

print_journal() {
  echo "Catstar - 喵星备份日志"
  printf '%s\n' "${BACKUP_VERBOSE_LOGS[@]}"
  echo "================================="
  if [ -n "$INVOCATION_ID" ]; then
    journalctl -o cat _SYSTEMD_INVOCATION_ID="$INVOCATION_ID"
  fi
}

upload_journal() {
  # journald 日志
  if [ -n "$INVOCATION_ID" ]; then
    # 上传日志，指定一个可以上传文件的接口（参考 ix.io），接口上传完毕需要返回链接
    if [[ -v JOURNAL_UPLOAD_URL ]]; then
      JOURNAL="日志：$(echo "$JOURNAL_TEXT" | curl -sS -F "logs=@-" "$JOURNAL_UPLOAD_URL")"
    fi

    # 日志上传失败或没有配置链接
    if [ -z "$JOURNAL" ]; then
      JOURNAL="$JOURNAL_TEXT"
    fi
  fi
}

printf -v BACKUP_BEGIN "%(%F %T)T"
( set -eu; backup_main ) # 报错立即退出
BACKUP_STAT=$?
printf -v BACKUP_END "%(%F %T)T"
JOURNAL_TEXT="$(print_journal)"
if [[ -v HTTP_PING_APPEND_STATUS ]]; then
  http_ping "/$BACKUP_STAT" "$JOURNAL_TEXT"
else
  http_ping "" "$JOURNAL_TEXT"
fi


if [[ "$BACKUP_STAT" -ne 0 ]]; then
  upload_journal
  notify_send "$MACHINE_NAME 备份失败❌！" \
              "错误码：$BACKUP_STAT" \
              "开始：$BACKUP_BEGIN" \
              "结束：$BACKUP_END" \
              "$JOURNAL"
elif [[ -v NOTIFY_SEND_SUMMARY ]]; then
  if [[ ! -v NOTIFY_SEND_SUMMARY_HOURS ]] || [[ " $NOTIFY_SEND_SUMMARY_HOURS " =~ " $(printf '%(%H)T') " ]]; then
    upload_journal
    notify_summary "$MACHINE_NAME 备份完成✅" \
                   "开始：$BACKUP_BEGIN" \
                   "结束：$BACKUP_END" \
                   "$JOURNAL"
  fi
fi
