const { ref, onMounted, watch } = Vue;
import { store, addLog } from '../store.js';
import { uploadAsset, getTasks, deleteTask, updateConfig, executeTask } from '../api.js';

export default {
    name: 'TabWorkspace',
    template: `
        <div class="workspace-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                请将需要处理的视频或音频源文件拖拽至下方区域以新建任务。💡 提示：在此处上传的任何格式音频都会自动经过标准化重采样，以获取最佳的 AI 识别准确率。
            </el-alert>
        
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <template #header>
                    <div class="card-title">📁 新建任务</div>
                </template>
            <el-upload
                class="compact-upload"
                drag
                multiple
                action="#"
                :auto-upload="true"
                :http-request="handleUpload"
                :show-file-list="false"
                accept="video/*,audio/*"
                :disabled="isUploading"
            >
                <div class="el-upload__text" style="display: flex; align-items: center; justify-content: center; gap: 10px;">
                    <el-icon style="font-size: 24px; color: #409EFF;"><upload-filled /></el-icon>
                    <span style="font-size: 15px;">拖拽上传源文件 (视频/音频)，或 <em>点击浏览</em></span>
                </div>
            </el-upload>
            
            <!-- 上传进度条 -->
            <div v-if="isUploading" style="margin-top: 20px;">
                <el-progress :percentage="currentUploadProgress" :stroke-width="18" text-inside></el-progress>
                <div style="text-align: center; margin-top: 8px; font-size: 13px; color: #909399;">
                    <el-icon class="is-loading" style="margin-right: 5px;"><Loading /></el-icon>
                    正在上传: <strong>{{ currentUploadName }}</strong> (队列排队: {{ queueRemaining }} 个)...
                </div>
            </div>
            </el-card>

            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <template #header>
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <span class="card-title">🚥 流水线看板与资产库</span>
                        <div style="display: flex; gap: 10px;">
                            <el-button type="danger" size="small" plain :disabled="taskList.length === 0" @click="clearAllTasks">
                                <el-icon><Delete /></el-icon> 一键清空
                            </el-button>
                            <el-button type="success" size="small" plain :disabled="selectedTasks.length === 0" @click="batchRun(false)">
                                批量提取+识别
                            </el-button>
                            <el-button type="primary" size="small" :disabled="selectedTasks.length === 0" @click="batchRun(true)">
                                批量全量(含翻译)
                            </el-button>
                        </div>
                    </div>
                </template>
                
                <el-table :data="taskList" style="width: 100%" height="320" v-loading="isLoadingTasks" :empty-text="'暂无任务记录'" @selection-change="handleSelectionChange">
                    <el-table-column type="selection" width="50"></el-table-column>
                    <el-table-column prop="base_name" label="任务名称 (源文件名)" min-width="180" show-overflow-tooltip></el-table-column>
                    <el-table-column label="实时状态" width="130">
                        <template #default="scope">
                            <el-tag v-if="store.pipelineStatus[scope.row.task_id]" size="small" :type="getStatusType(store.pipelineStatus[scope.row.task_id].current_step)" effect="dark">
                                {{ getStatusText(store.pipelineStatus[scope.row.task_id].current_step) }}
                            </el-tag>
                            <el-tag v-else size="small" type="info">已空闲</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column label="资产检查" width="200">
                        <template #default="scope">
                            <el-tag size="small" :type="scope.row.has_video ? 'success' : 'info'" effect="plain" style="margin-right: 4px;">视频</el-tag>
                            <el-tag size="small" :type="scope.row.has_audio ? 'success' : 'info'" effect="plain" style="margin-right: 4px;">音频</el-tag>
                            <el-tag size="small" :type="scope.row.has_original_srt ? 'success' : 'info'" effect="plain" style="margin-right: 4px;">原声</el-tag>
                            <el-tag size="small" :type="scope.row.has_translated_srt ? 'success' : 'info'" effect="plain">翻译</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column label="焦点操作" width="160" fixed="right">
                        <template #default="scope">
                            <el-button size="small" type="primary" plain @click="loadTask(scope.row)" :disabled="store.taskId === scope.row.task_id">监视</el-button>
                            <el-button size="small" type="danger" plain @click="removeTask(scope.row)">删除</el-button>
                        </template>
                    </el-table-column>
                </el-table>
            </el-card>

            <!-- 全局网络代理设置 (单行紧凑布局) -->
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5; padding: 5px 0;">
                <div style="display: flex; align-items: center; justify-content: flex-start; flex-wrap: wrap; gap: 40px;">
                    <div style="font-weight: bold; color: #303133; display: flex; align-items: center; gap: 8px;">
                        <el-icon style="font-size: 18px; color: #409EFF;"><Position /></el-icon>
                        <span>代理设置</span>
                        <el-tooltip content="加速大模型下载及 API 请求。开启开关并填写完整后自动生效。" placement="top">
                            <el-icon style="color: #909399; cursor: pointer;"><QuestionFilled /></el-icon>
                        </el-tooltip>
                    </div>
                    
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <el-switch v-model="proxyEnabled" @change="handleProxyChange" active-text="开启" inactive-text="关闭"></el-switch>
                        
                        <div style="display: flex; align-items: center; gap: 8px;" :style="{ opacity: proxyEnabled ? 1 : 0.5, pointerEvents: proxyEnabled ? 'auto' : 'none', filter: proxyEnabled ? 'none' : 'grayscale(100%)' }">
                            <el-select v-model="proxyProtocol" @change="handleProxyChange" style="width: 105px; --el-input-text-align: center;">
                                <el-option label="HTTP" value="http://" style="text-align: center;"></el-option>
                                <el-option label="SOCKS5" value="socks5://" style="text-align: center;"></el-option>
                            </el-select>
                            <el-input v-model="proxyHost" @blur="handleProxyChange" @keyup.enter="handleProxyChange" placeholder="IP / 域名 (如 127.0.0.1)" style="width: 180px;"></el-input>
                            <span style="font-weight: bold; color: #909399;">:</span>
                            <el-input-number v-model="proxyPort" @change="handleProxyChange" @blur="handleProxyChange" @keyup.enter="handleProxyChange" :min="1" :max="65535" :controls="false" placeholder="端口" style="width: 75px; --el-input-text-align: center;"></el-input-number>
                        </div>
                    </div>
                </div>
            </el-card>
        </div>
    `,
    setup() {
        const isUploading = ref(false);
        const currentUploadProgress = ref(0);
        const currentUploadName = ref("");
        const queueRemaining = ref(0);
        const taskList = ref([]);
        const selectedTasks = ref([]);
        const isLoadingTasks = ref(false);
        
        // 代理 UI 状态变量
        const proxyEnabled = ref(false);
        const proxyProtocol = ref("http://");
        const proxyHost = ref("");
        const proxyPort = ref(null);

        // 解析后端传来的代理字符串，映射到前端 UI
        const parseProxyString = (proxyStr) => {
            if (!proxyStr) {
                proxyEnabled.value = false;
                return;
            }
            proxyEnabled.value = true;
            
            let protocol = "http://";
            let rest = proxyStr;
            
            if (proxyStr.startsWith("socks5://") || proxyStr.startsWith("socks5h://")) {
                protocol = "socks5://"; // UI 统一显示 socks5://
                rest = proxyStr.replace(/^socks5h?:\/\//, "");
            } else if (proxyStr.startsWith("http://") || proxyStr.startsWith("https://")) {
                protocol = proxyStr.startsWith("https://") ? "https://" : "http://";
                rest = proxyStr.replace(/^https?:\/\//, "");
            }
            
            proxyProtocol.value = protocol;
            
            const lastColonIdx = rest.lastIndexOf(":");
            if (lastColonIdx !== -1) {
                proxyHost.value = rest.substring(0, lastColonIdx);
                proxyPort.value = parseInt(rest.substring(lastColonIdx + 1)) || null;
            } else {
                proxyHost.value = rest;
                proxyPort.value = null;
            }
        };

        // 监听全局 store 的变化，初始化拆解数据 (从后端拉取配置后触发)
        watch(() => store.config.system_settings.network_proxy, (newVal) => {
            // 如果 UI 目前拼接的值和后端值一致，不再重复解析，防止相互循环触发
            const currentUIStr = proxyEnabled.value ? `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}` : "";
            const currentUIStrSocks5h = proxyEnabled.value ? `${proxyProtocol.value.replace('socks5://', 'socks5h://')}${proxyHost.value}:${proxyPort.value}` : "";
            if (newVal !== currentUIStr && newVal !== currentUIStrSocks5h) {
                parseProxyString(newVal);
            }
        }, { immediate: true });

        const fetchTasks = async () => {
            isLoadingTasks.value = true;
            try { taskList.value = await getTasks(); } 
            catch (e) { ElementPlus.ElMessage.error("获取历史任务失败"); }
            finally { isLoadingTasks.value = false; }
        };

        onMounted(() => {
            fetchTasks();
        });

        const handleSelectionChange = (val) => { selectedTasks.value = val; };

        const getStatusType = (step) => {
            const map = {
                'pending_extract': 'info', 'extracting': 'warning',
                'pending_transcribe': 'info', 'transcribing': 'warning',
                'pending_translate': 'info', 'translating': 'warning',
                'completed': 'success', 'error': 'danger'
            };
            return map[step] || 'info';
        };
        const getStatusText = (step) => {
            const map = {
                'pending_extract': '排队提音中', 'extracting': '▶ 正在提音',
                'pending_transcribe': '排队识别中', 'transcribing': '▶ 正在识别',
                'pending_translate': '排队翻译中', 'translating': '▶ 正在翻译',
                'completed': '✔ 完毕收工', 'error': '✖ 发生错误'
            };
            return map[step] || step;
        };

        const handleProxyChange = async () => {
            // 1. 如果用户关闭了开关，则安全置空并发送给后端
            if (!proxyEnabled.value) {
                store.config.system_settings.network_proxy = "";
                await saveProxyConfig("已恢复直连模式");
                return;
            }
            
            // 2. 如果开启了开关，拦截“半残状态”进行温和提示
            if (!proxyHost.value || !proxyPort.value) {
                ElementPlus.ElMessage.warning("⚠️ 请完整填写代理的 IP/域名 和 端口号！");
                return;
            }
            
            // 3. 校验通过，拼接字符串并发给后端
            const fullProxy = `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}`;
            if (store.config.system_settings.network_proxy === fullProxy) return; // 无变化不保存
            
            store.config.system_settings.network_proxy = fullProxy;
            await saveProxyConfig("全局网络代理已生效！");
        };

        const saveProxyConfig = async (successMsg) => {
            try {
                await updateConfig(store.config);
                ElementPlus.ElMessage.success(successMsg);
            } catch (e) {
                ElementPlus.ElMessage.error("代理配置保存失败");
            }
        };

        // 多文件批量串行上传队列
        const uploadQueue = [];
        let isProcessingQueue = false;
        
        const processUploadQueue = async () => {
            if (isProcessingQueue || uploadQueue.length === 0) return;
            isProcessingQueue = true;
            isUploading.value = true;

            while (uploadQueue.length > 0) {
                const options = uploadQueue.shift();
                queueRemaining.value = uploadQueue.length;
                currentUploadName.value = options.file.name;
                currentUploadProgress.value = 0;
                addLog(`开始上传源文件: ${options.file.name} (队列剩余: ${uploadQueue.length} 个)...`, "info");
                
                try {
                    // 智能判断上传的是视频还是纯音频，并调用后端 API
                    const assetType = options.file.type.startsWith('audio') ? 'audio' : 'video';
                    const res = await uploadAsset(options.file, assetType, null, (percent) => {
                        currentUploadProgress.value = percent;
                    });
                    addLog(`✅ 上传成功！任务分配 ID: ${res.task_id}`, "success");
                } catch (e) {
                    addLog(`❌ 上传失败 [${options.file.name}]: ${e.message}`, "error");
                } finally {
                    // 每当有一个文件物理上传完毕，立刻刷新一次看板，实现“边传边显示”的效果
                    fetchTasks();
                }
            }

            isProcessingQueue = false;
            isUploading.value = false;
            ElementPlus.ElMessage.success("批量上传分配完成，请在列表中勾选任务下发执行！");
        };
        
        let uploadDebounceTimer = null;
        const handleUpload = (options) => {
            // 拦截默认的并发上传，将文件加入排队数组
            uploadQueue.push(options);
            // 巧用防抖(Debounce)：等待 Element Plus 把同一批拖入的文件全部塞进队列后，再统一唤醒消费者
            if (uploadDebounceTimer) clearTimeout(uploadDebounceTimer);
            uploadDebounceTimer = setTimeout(() => {
                processUploadQueue();
            }, 100);
        };

        // 批量将任务下发到后端 Worker 车间
        const batchRun = async (includeTranslation) => {
            if (selectedTasks.value.length === 0) return;
            
            if (includeTranslation && !store.config.llm_settings.api_key) {
                ElementPlus.ElMessage.warning("执行全量流水线前，请先在【LLM 翻译】页填写 API Key！");
                return;
            }

            for (const task of selectedTasks.value) {
                const steps = [];
                if (!task.has_audio && task.has_video) steps.push("extract");
                if (!task.has_original_srt && (task.has_audio || steps.includes("extract"))) steps.push("transcribe");
                if (includeTranslation) steps.push("translate");

                if (steps.length > 0) {
                    try {
                        await executeTask(task.task_id, steps, store.config);
                        addLog(`🚀 任务 ${task.base_name} 已加入调度车间`, "success");
                    } catch (e) {
                        addLog(`❌ 任务 ${task.base_name} 调度失败: ${e.message}`, "error");
                    }
                }
            }
            ElementPlus.ElMessage.success("批量分配完成，请在看板中观察流转进度！");
        };

        const loadTask = (task) => {
            store.taskId = task.task_id;
            store.assets = {
                hasVideo: task.has_video,
                hasAudio: task.has_audio,
                hasOriginalSrt: task.has_original_srt,
                hasTranslatedSrt: task.has_translated_srt
            };
            
            // 清空旧日志，迎接焦点任务的新日志
            store.logs.splice(0, store.logs.length);
            addLog(`👀 焦点已切换至监视任务: ${task.base_name}`, "info");
            
            // 切断并重新连接 WS，绑定到新任务的输出流
            connectTaskMonitor(task.task_id, null, null);

            // 智能推导进度条应该亮到哪一步
            if (task.has_translated_srt) store.activeStep = 5;
            else if (task.has_original_srt) store.activeStep = 4;
            else if (task.has_audio) store.activeStep = 3;
            else if (task.has_video) store.activeStep = 2;
            else store.activeStep = 1;
            
            addLog(`📂 已加载历史任务: ${task.base_name}`, "info");
            ElementPlus.ElMessage.success("任务加载成功！");
        };

        const removeTask = async (task) => {
            try {
                await ElementPlus.ElMessageBox.confirm(`确定要彻底删除任务 "${task.base_name}" 及其所有产生的文件吗？此操作不可逆。`, '警告', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' });
                await deleteTask(task.task_id);
                if (store.taskId === task.task_id) {
                    store.taskId = null;
                    store.activeStep = 0;
                }
                ElementPlus.ElMessage.success("任务已删除");
                fetchTasks();
            } catch (e) { if(e !== 'cancel') ElementPlus.ElMessage.error(e.message || "删除失败"); }
        };

        const clearAllTasks = async () => {
            if (taskList.value.length === 0) return;
            try {
                await ElementPlus.ElMessageBox.confirm('确定要清空所有历史任务及其产生的物理文件吗？此操作将腾出大量磁盘空间且不可逆。', '高危预警', { 
                    confirmButtonText: '全部清空', 
                    cancelButtonText: '取消', 
                    type: 'error' 
                });
                
                isLoadingTasks.value = true;
                let successCount = 0;
                // 高并发发出删除请求
                await Promise.all(taskList.value.map(async (task) => {
                    try {
                        await deleteTask(task.task_id);
                        successCount++;
                    } catch (e) {}
                }));
                
                store.taskId = null;
                store.activeStep = 0;
                store.assets = { hasVideo: false, hasAudio: false, hasOriginalSrt: false, hasTranslatedSrt: false };
                
                ElementPlus.ElMessage.success(`清理完成！已释放 ${successCount} 个任务的磁盘空间。`);
                fetchTasks();
            } catch (e) { /* 用户点击取消 */ }
        };

        return {
            isUploading,
            currentUploadProgress,
            currentUploadName,
            queueRemaining,
            taskList,
            selectedTasks,
            isLoadingTasks,
            proxyEnabled,
            proxyProtocol,
            proxyHost,
            proxyPort,
            handleProxyChange,
            handleSelectionChange,
            handleUpload,
            loadTask,
            removeTask,
            clearAllTasks,
            batchRun,
            getStatusType,
            getStatusText,
            store
        };
    }
};