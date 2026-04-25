#!/bin/bash

# 切换到脚本所在的绝对路径
cd "$(dirname "$0")"

echo "=========================================="
echo "      AutoSRT WebUI 一键启动脚本"
echo "=========================================="
echo ""

# 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "[警告] 未找到 venv 虚拟环境，尝试使用系统全局 Python 运行"
fi

echo "[*] 正在启动后端 API 服务 (端口 8000)..."
python app.py &
BACKEND_PID=$!

echo "[*] 正在启动前端 Web 服务 (端口 8080)..."
# 兼容前端文件夹可能被命名为 fronted 的情况
if [ -d "frontend" ]; then
    cd frontend
elif [ -d "fronted" ]; then
    cd fronted
fi
python -m http.server 8080 &
FRONTEND_PID=$!

echo ""
echo "[*] 服务已启动！"
echo "[!] 请保持此终端窗口开启。按 Ctrl+C 可一键退出所有服务。"

# 延迟 2 秒，确保服务完全跑起来
sleep 2

# 尝试自动打开浏览器 (兼容 macOS 的 open 和 Linux 的 xdg-open)
if command -v open > /dev/null; then
    open http://127.0.0.1:8080
elif command -v xdg-open > /dev/null; then
    xdg-open http://127.0.0.1:8080
fi

# 捕获 Ctrl+C (SIGINT) 和终止信号，确保退出时杀死前后端后台进程
trap "echo -e '\n[*] 接收到停止信号，正在关闭服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

# 挂起脚本，等待用户中止
wait