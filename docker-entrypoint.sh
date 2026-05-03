#!/bin/bash

# 设置默认的用户 UID 和 GID（0 代表 root）
PUID=${PUID:-0}
PGID=${PGID:-0}

# 确保工作区和模型目录存在
mkdir -p /app/workspace /app/models /app/config

# [兜底策略] 如果用户挂载了空的 config 目录，导致配置和模板双双丢失，则从安全备份中恢复
if [ ! -f "/app/config/config.json" ]; then
    if [ -f "/app/config.example.json" ]; then
        cp /app/config.example.json /app/config/config.json
        echo "[*] Docker entrypoint: initialized default config.json from backup."
    fi
fi

if [ "$PUID" -ne 0 ] && [ "$PGID" -ne 0 ]; then
    echo "[*] Setting user to PUID=${PUID} and group to PGID=${PGID} to match NAS permissions..."
    
    # 根据传入的 PUID 和 PGID 创建对应的用户组和用户
    groupadd -o -g "$PGID" appgroup 2>/dev/null || true
    useradd -o -u "$PUID" -g "$PGID" -s /bin/bash appuser 2>/dev/null || true
    
    # 修正需要挂载出来的目录的所有权，保证宿主机用户有读写权限
    chown -R "$PUID":"$PGID" /app/workspace /app/models /app/config
    
    # 使用 gosu 降权，以非 root 用户身份执行后续命令 (uvicorn)
    exec gosu appuser "$@"
else
    echo "[*] Running as root (PUID/PGID not set or set to 0)"
    exec "$@"
fi
