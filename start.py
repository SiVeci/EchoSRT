import subprocess
import time
import webbrowser
import sys
import os

def main():
    print("==========================================")
    print("     EchoSRT WebUI 启动脚本 (全平台兼容版)")
    print("==========================================")
    print()

    # 检测当前操作系统是否为 Windows
    is_windows = sys.platform == "win32"
    
    # 根据操作系统选择默认全局 python 命令 (Linux/macOS 通常是 python3)
    python_cmd = "python" if is_windows else "python3"
    

    print(f"[*] 正在启动后端 API 服务 (端口 8000)...")
    if is_windows:
        # Windows 逻辑：弹出独立的新 CMD 窗口，强行设置 UTF-8 编码(chcp 65001)防止乱码
        CREATE_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE
        subprocess.Popen(
            f'cmd /k "chcp 65001 >nul && title EchoSRT 后端 (FastAPI) && {python_cmd} app.py"',
            creationflags=CREATE_NEW_CONSOLE
        )
    else:
        # Linux/Mac 逻辑：作为当前脚本的子进程运行
        backend_process = subprocess.Popen([python_cmd, "app.py"])

    print(f"[*] 正在启动前端 Web 服务 (端口 8080)...")
    if is_windows:
        subprocess.Popen(
            f'cmd /k "chcp 65001 >nul && title EchoSRT 前端 (WebUI) && cd frontend && {python_cmd} -m http.server 8080"',
            creationflags=CREATE_NEW_CONSOLE
        )
    else:
        # 使用 cwd 参数优雅地指定前端工作目录
        frontend_process = subprocess.Popen([python_cmd, "-m", "http.server", "8080"], cwd="frontend")

    print("\n[*] 服务已启动，正在为你打开浏览器...")
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8080")

    # ----- 针对 Linux/macOS 的特殊处理 -----
    if not is_windows:
        print("\n[*] 服务正在运行中。前后端日志将在此处输出。")
        print("[*] 请不要关闭此终端，按 Ctrl+C 即可同时停止所有服务。")
        try:
            # 阻塞主线程，不让脚本退出，从而保持服务存活
            backend_process.wait()
            frontend_process.wait()
        except KeyboardInterrupt:
            # 捕获 Ctrl+C 信号，优雅地杀掉子进程，防止产生孤儿进程
            print("\n[*] 收到退出信号，正在关闭服务...")
            backend_process.terminate()
            frontend_process.terminate()
            print("[*] 服务已安全关闭。")

if __name__ == "__main__":
    main()