FROM python:3.10-slim

# 设置非交互式安装，避免构建过程卡住
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 1. 安装 FFmpeg 和用于权限控制的 gosu
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg gosu && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 2. 设置工作目录
WORKDIR /app

# 3. 首先拷贝 requirements 以利用 Docker 构建缓存
COPY requirements.txt .

# 4. 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 5. 拷贝整个项目代码到容器中
COPY . .

# [新增] 备份默认配置文件到不受挂载影响的根目录，防止被用户的空 volume 覆盖
RUN cp config/config.example.json /app/config.example.json

# 6. 转换换行符为 Unix 格式并赋予 entrypoint 脚本执行权限
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# 暴露 FastAPI 端口
EXPOSE 8000

# 7. 定义启动入口 (接管 PUID/PGID 的处理)
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# 8. 默认启动命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
