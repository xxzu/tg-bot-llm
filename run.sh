#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Gemini Telegram Bot 一键启动脚本 ===${NC}"

# 检查 uv 是否安装
if ! command -v uv &> /dev/null; then
    echo -e "${BLUE}>>> 检测到未安装 uv，正在安装...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # 尝试将 uv 添加到当前 shell 环境
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    elif [ -f "$HOME/.local/bin/env" ]; then
         source "$HOME/.local/bin/env"
    else
        # Fallback: add standard uv install paths to PATH for this script execution
        export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    fi
else
    echo -e "${GREEN}>>> uv 已安装${NC}"
fi

# 再次检查 uv 是否可以直接运行
if ! command -v uv &> /dev/null; then
    echo "警告: 无法自动在当前PATH中找到 uv，尝试使用绝对路径..."
    if [ -f "$HOME/.cargo/bin/uv" ]; then
        UV_CMD="$HOME/.cargo/bin/uv"
    elif [ -f "$HOME/.local/bin/uv" ]; then
        UV_CMD="$HOME/.local/bin/uv"
    else
        echo "错误: 无法找到 uv 可执行文件。请尝试重新运行脚本或手动安装 uv。"
        exit 1
    fi
else
    UV_CMD="uv"
fi

echo -e "${GREEN}>>> 使用 uv: $($UV_CMD --version)${NC}"

# 创建虚拟环境 (如果不存在)
# 强制使用 Python 3.12 以确保兼容性 (如 audioop)
if [ ! -d ".venv" ]; then
    echo -e "${BLUE}>>> 正在创建虚拟环境 (Python 3.12)...${NC}"
    $UV_CMD venv --python 3.12
else
    echo -e "${GREEN}>>> 虚拟环境已存在${NC}"
fi

# 安装依赖
echo -e "${BLUE}>>> 正在同步依赖...${NC}"
$UV_CMD pip install -r requirements.txt

# 启动机器人
echo -e "${BLUE}>>> 正在启动机器人...${NC}"
$UV_CMD run main.py
