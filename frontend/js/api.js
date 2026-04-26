/* 封装所有的后端 API 请求与 WebSocket 连接逻辑 */
export const API_BASE = "http://127.0.0.1:8000";
export const WS_BASE = "ws://127.0.0.1:8000";

// --- 通用 GET 请求 ---
async function fetchGet(endpoint) {
    const res = await fetch(`${API_BASE}${endpoint}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
}

// --- 配置与字典接口 ---
export const getConfig = () => fetchGet('/api/config');
export const restoreConfig = async () => {
    const res = await fetch(`${API_BASE}/api/config/restore`, { method: "POST" });
    if (!res.ok) throw new Error("恢复配置失败");
    return await res.json();
};
export const getLanguages = () => fetchGet('/api/languages');
export const getModels = () => fetchGet('/api/models');

// --- 核心操作接口 ---
export const uploadAsset = (file, assetType, taskId, onProgress) => {
    return new Promise((resolve, reject) => {
        const formData = new FormData();
        formData.append("file", file);
        if (taskId) formData.append("task_id", taskId);

        const xhr = new XMLHttpRequest();
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable && onProgress) {
                const percent = Math.round((e.loaded / e.total) * 100);
                onProgress(percent);
            }
        };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try { resolve(JSON.parse(xhr.responseText)); } catch (err) { reject(new Error("解析响应失败")); }
            } else {
                let errMsg = `HTTP ${xhr.status}`;
                try { errMsg = JSON.parse(xhr.responseText).detail || errMsg; } catch(e) {}
                reject(new Error(errMsg));
            }
        };
        xhr.onerror = () => reject(new Error("网络异常或跨域拦截"));
        xhr.open("POST", `${API_BASE}/api/upload/${assetType}`, true);
        xhr.send(formData);
    });
};

export const executeTask = async (taskId, steps, config) => {
    const payload = { task_id: taskId, steps, ...config };
    const res = await fetch(`${API_BASE}/api/task/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    if (!res.ok) {
        let errMsg = "请求失败";
        try { errMsg = (await res.json()).detail || errMsg; } catch(e) {}
        throw new Error(errMsg);
    }
    return await res.json();
};