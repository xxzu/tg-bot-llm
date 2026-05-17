#!/usr/bin/env bash
# Gemini Telegram Bot 进程管理：启动 / 停止 / 重启 / 状态 / 日志
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PID_FILE="${PID_FILE:-$ROOT_DIR/data/bot.pid}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/bot.log}"
MAIN_PY="main.py"
VENV_DIR="$ROOT_DIR/.venv"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
    cat <<'EOF'
用法: ./manage.sh <命令> [选项]

命令:
  start       后台启动机器人（uv sync 同步依赖后启动）
  stop        停止机器人（发送 SIGTERM，必要时 SIGKILL）
  restart     先 stop 再 start
  sync-openrouter  用 OPENROUTER_API_KEY 拉取免费模型写入 models/openrouter_free_models.yaml
  pause       同 stop（别名）
  status      查看是否在运行
  logs, tail    查看日志（默认 tail -f 实时跟踪）
  follow        同 logs（仅实时跟踪）

logs / tail 选项:
  -f, --follow     持续跟踪（默认开启，等同 tail -f）
  -n, --lines N    先显示最后 N 行；单独使用时只查看不跟踪
                   与 -f 合用: tail -n N -f

环境变量:
  PID_FILE   PID 文件路径（默认 data/bot.pid）
  LOG_FILE   日志文件路径（默认 logs/bot.log）

示例:
  ./manage.sh start
  ./manage.sh logs              # tail -f 实时看最新日志
  ./manage.sh tail              # 同上
  ./manage.sh logs -n 200       # 只看最近 200 行
  ./manage.sh logs -n 50 -f     # 先看 50 行再继续跟踪
  ./manage.sh restart
EOF
}

log_info()  { echo -e "${BLUE}>>>${NC} $*"; }
log_ok()    { echo -e "${GREEN}>>>${NC} $*"; }
log_warn()  { echo -e "${YELLOW}>>>${NC} $*"; }
log_error() { echo -e "${RED}>>>${NC} $*" >&2; }

resolve_uv() {
    if command -v uv &>/dev/null; then
        UV_CMD="uv"
        return 0
    fi
    if [ -f "$HOME/.cargo/bin/uv" ]; then
        UV_CMD="$HOME/.cargo/bin/uv"
        return 0
    fi
    if [ -f "$HOME/.local/bin/uv" ]; then
        UV_CMD="$HOME/.local/bin/uv"
        return 0
    fi
    log_error "未找到 uv。请安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
    return 1
}

ensure_venv_and_deps() {
    resolve_uv || exit 1
    log_ok "使用 uv: $($UV_CMD --version)"

    if [ ! -f "$ROOT_DIR/pyproject.toml" ]; then
        log_error "未找到 pyproject.toml，无法 uv sync"
        exit 1
    fi

    log_info "同步依赖 (uv sync)..."
    $UV_CMD sync --python 3.12
}

mkdir -p "$LOG_DIR" "$(dirname "$PID_FILE")"

is_running() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -z "$pid" ]; then
        return 1
    fi
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

read_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    fi
}

cmd_start() {
    if is_running; then
        log_warn "已在运行 (PID $(read_pid))。如需重启: ./manage.sh restart"
        exit 0
    fi

    if [ ! -f "$ROOT_DIR/.env" ]; then
        log_warn "未找到 .env，请确认已配置 TG_BOT_TOKEN 等变量"
    fi

    ensure_venv_and_deps

    log_info "后台启动 $MAIN_PY ..."
    log_info "日志: $LOG_FILE"

  (
    cd "$ROOT_DIR"
    export LOG_LEVEL="${LOG_LEVEL:-INFO}"
    nohup "$UV_CMD" run "$MAIN_PY" >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
  )

    sleep 1
    if is_running; then
        log_ok "启动成功 PID=$(read_pid)"
    else
        log_error "启动失败，请查看日志: ./manage.sh logs -n 80"
        rm -f "$PID_FILE"
        exit 1
    fi
}

cmd_stop() {
    if ! is_running; then
        log_warn "未在运行"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid
    pid="$(read_pid)"
    log_info "停止 PID=$pid ..."

    kill -TERM "$pid" 2>/dev/null || true

    local i
    for i in $(seq 1 15); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            log_ok "已停止"
            return 0
        fi
        sleep 1
    done

    log_warn "未在 15s 内退出，强制结束..."
    kill -KILL "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    log_ok "已强制停止"
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_sync_openrouter() {
    ensure_venv_and_deps
    log_info "同步 OpenRouter 免费模型..."
    $UV_CMD run python scripts/sync_openrouter_free_models.py --reload
    log_ok "完成。重启机器人后菜单生效: ./manage.sh restart"
}

cmd_status() {
    echo -e "${BLUE}=== Gemini Telegram Bot 状态 ===${NC}"
    echo "工作目录: $ROOT_DIR"
    echo "PID 文件: $PID_FILE"
    echo "日志文件: $LOG_FILE"
    if is_running; then
        local pid
        pid="$(read_pid)"
        echo -e "状态: ${GREEN}运行中${NC} (PID $pid)"
        if command -v ps &>/dev/null; then
            ps -p "$pid" -o pid,etime,cmd --no-headers 2>/dev/null || true
        fi
    else
        echo -e "状态: ${YELLOW}未运行${NC}"
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    fi
    if [ -f "$LOG_FILE" ]; then
        echo "日志大小: $(du -h "$LOG_FILE" 2>/dev/null | cut -f1 || echo '?')"
    fi
}

cmd_logs() {
    local follow=1
    local lines=0
    local explicit_follow=0

    while [ $# -gt 0 ]; do
        case "$1" in
            -f|--follow)
                follow=1
                explicit_follow=1
                shift
                ;;
            -n|--lines)
                lines="${2:-100}"
                if [ "$explicit_follow" -eq 0 ]; then
                    follow=0
                fi
                shift 2
                ;;
            *)
                if [[ "$1" =~ ^[0-9]+$ ]]; then
                    lines="$1"
                    if [ "$explicit_follow" -eq 0 ]; then
                        follow=0
                    fi
                fi
                shift
                ;;
        esac
    done

    mkdir -p "$(dirname "$LOG_FILE")"

    if [ "$follow" -eq 1 ]; then
        if [ ! -f "$LOG_FILE" ]; then
            log_warn "日志文件尚未生成，等待写入: $LOG_FILE"
        fi
        log_info "实时日志 $LOG_FILE (tail -f, Ctrl+C 退出)"
        if [ "$lines" -gt 0 ]; then
            exec tail -n "$lines" -F "$LOG_FILE"
        else
            exec tail -F "$LOG_FILE"
        fi
    fi

    if [ ! -f "$LOG_FILE" ]; then
        log_warn "日志文件不存在: $LOG_FILE（请先 ./manage.sh start）"
        exit 1
    fi

    tail -n "${lines:-100}" "$LOG_FILE"
}

main() {
    local cmd="${1:-}"
    shift || true

    case "$cmd" in
        start)   cmd_start "$@" ;;
        stop)    cmd_stop "$@" ;;
        pause)   cmd_stop "$@" ;;
        restart) cmd_restart "$@" ;;
        sync-openrouter) cmd_sync_openrouter "$@" ;;
        status)  cmd_status "$@" ;;
        logs|tail|follow) cmd_logs "$@" ;;
        help|-h|--help|"") usage ;;
        *)
            log_error "未知命令: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
