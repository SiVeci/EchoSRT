# JavaScript 前端 API

前端通过 `api.js` 封装所有 HTTP 请求，通过 `store.js` 管理全局响应式状态。

---

## api.js — HTTP 封装

```javascript
// api.js
export const API_BASE = window.location.origin;
export const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

// 核心函数示例
export const executeTask = async (taskId, steps, config) => {
    const payload = { task_id: taskId, steps, ...config };
    const res = await fetch(`${API_BASE}/api/task/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    return await res.json();
};

export const uploadAsset = (file, assetType, taskId, onProgress) => {
    // 使用 XMLHttpRequest 实现带进度回调的上传
    // ...
};
```

### 核心函数列表

| 函数 | 端点 | 说明 |
|------|------|------|
| `getConfig()` | `GET /api/config` | 获取完整配置镜像 |
| `updateConfig(config)` | `POST /api/config` | 同步本地配置到后端 |
| `restoreConfig()` | `POST /api/config/restore` | 恢复默认配置 |
| `uploadAsset(...)` | `POST /api/upload/{type}` | 带进度的文件上传 |
| `executeTask(...)` | `POST /api/task/execute` | 启动异步工作流 |
| `retryTask(id)` | `POST /api/task/{id}/retry` | 重试中断/出错的任务（断点续传） |
| `cancelTask(id)` | `POST /api/task/{id}/cancel` | 中断单个正在执行的任务 |
| `cancelAllTasks()` | `POST /api/tasks/cancel_all` | 中断所有正在执行的任务 |
| `getTasks()` | `GET /api/tasks` | 获取工作区所有任务 |
| `getTaskAssets(id)` | `GET /api/task/{id}/assets` | 获取单个任务资产详情 |
| `deleteTask(id)` | `DELETE /api/task/{id}` | 彻底删除任务及其所有关联状态 |
| `deleteTaskAsset(id, type)` | `DELETE /api/task/{id}/asset/{type}` | 删除任务下的特定资产 (video/audio/original/translated) |
| `reorderTasks(ids)` | `POST /api/tasks/reorder` | 批量调整任务排序 |
| `downloadAsset(id, type)` | `GET /api/download/{id}?type=...` | 下载产物 (original/translated/audio/video) |
| `getTaskStatus(id)` | `GET /api/task/{id}/status` | 查询任务最新状态快照 |
| `getPipelineStatus()` | `GET /api/pipeline/status` | 获取全局流水线概览 |
| `getModels()` | `GET /api/models` | 获取本地 Whisper 模型列表及下载状态 |
| `deleteModel(id)` | `DELETE /api/models/{id}` | 删除已下载的模型文件 |
| `downloadModel(id, settings)` | `POST /api/models/{id}/download` | 触发后台异步下载模型 |
| `getDownloadStatus()` | `GET /api/models/download_status` | 获取模型下载进度 |
| `getLLMModels(apiKey, baseUrl)` | `POST /api/llm/models` | 拉取 LLM 可用模型列表 |
| `getLocalLLMModels()` | `GET /api/llm/local_models` | 获取本地 GGUF 模型列表 |
| `getASRModels(apiKey, baseUrl)` | `POST /api/asr/models` | 拉取 ASR 可用模型列表 |
| `getSystemInfo()` | `GET /api/system/info` | 获取后端系统信息 (CPU/GPU) |
| `getLanguages()` | `GET /api/languages` | 获取支持的语言代码列表 |
| `testProxy(url)` | `POST /api/proxy/test` | 测试代理连通性 |

---

## store.js — 响应式状态

EchoSRT 前端使用 Vue 3 的 `reactive` 实现轻量级状态管理：

```javascript
// store.js
export const store = reactive({
    taskId: null,           // 当前激活的任务 ID
    activeStep: 0,          // 全局进度条步数 (0-5)
    isProcessing: false,    // 是否正在处理任务
    pipelineStatus: {},     // 记录所有任务的 current_step
    assets: {               // 当前任务资产就绪状态
        hasVideo: false,
        hasAudio: false,
        hasOriginalSrt: false,
        hasTranslatedSrt: false
    },
    config: { ... },        // 镜像后端的配置项
    logs: [],               // 全局控制台日志记录
    systemInfo: { ... }     // 硬件与系统信息
});
```

### WebSocket 任务监控

```javascript
// store.js
export const connectTaskMonitor = (taskId, onSuccess, onError) => {
    const ws = new WebSocket(`${WS_BASE}/ws/progress/${taskId}`);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // 根据 data.step 自动驱动 store.activeStep
        // 根据 data.progress 自动驱动 store.logs
    };
    
    return ws;
};
```

### 系统级下载监控

```javascript
// store.js
export const connectSystemDownloadMonitor = (modelId, onSuccess, onError) => {
    const ws = new WebSocket(`${WS_BASE}/ws/progress/sys_download_${modelId}`);
    // 同步更新 store.downloadingModels 字典
};
```

---

## 消息分发逻辑

1. **日志系统**：所有 WebSocket 接收到的进度信息通过 `addLog()` 函数格式化并推入 `store.logs`。
2. **防卡顿处理**：`addLog` 内部限制日志数组长度上限为 1000 条，超过则自动剔除头部，防止长任务占用过多内存。
3. **状态路由**：`onmessage` 回调会自动根据任务当前所处阶段（`extract_audio` / `transcribing` / `translating`）切换 UI 的激活步骤和指示器。

---

## 相关文档

- [REST API](RESTAPI参考) — 完整 HTTP 端点文档
- [WebSocket 通信](WebSocket通信) — 实时推送协议
- [状态管理](状态管理) — 后端状态流转原理说明
