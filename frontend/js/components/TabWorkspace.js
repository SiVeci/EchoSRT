const { ref, onMounted, watch } = Vue;
import { store, addLog } from '../store.js';
import { uploadAsset, getTasks, deleteTask, updateConfig } from '../api.js';

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
                <el-progress :percentage="uploadPercent" :stroke-width="18" text-inside></el-progress>
                <div style="text-align: center; margin-top: 8px; font-size: 13px; color: #909399;">
                    正在上传并初始化任务，请勿刷新页面...
                </div>
            </div>

            <!-- 成功提示展示区 -->
            <div v-if="currentFileName && !isUploading" style="margin-top: 20px; padding: 15px; background-color: #f0f9eb; border-radius: 4px; color: #67C23A; text-align: center; border: 1px solid #e1f3d8;">
                <el-icon style="vertical-align: middle; margin-right: 5px; font-size: 18px;"><CircleCheck /></el-icon>
                源文件 <strong>{{ currentFileName }}</strong> 已就绪
            </div>
            </el-card>

            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <el-collapse v-model="activeCollapse" style="border-top: none; border-bottom: none;">
                    <el-collapse-item name="1">
                        <template #title>
                            <span class="card-title">🕰️ 历史任务记录</span>
                        </template>
                <el-table :data="taskList" style="width: 100%" height="280" v-loading="isLoadingTasks" :empty-text="'暂无历史任务'">
                    <el-table-column prop="base_name" label="任务名称 (源文件名)" min-width="180" show-overflow-tooltip></el-table-column>
                    <el-table-column label="创建时间" width="160">
                        <template #default="scope">
                            {{ new Date(scope.row.created_at * 1000).toLocaleString() }}
                        </template>
                    </el-table-column>
                    <el-table-column label="资产状态" width="220">
                        <template #default="scope">
                            <el-tag size="small" :type="scope.row.has_video ? 'success' : 'info'" effect="plain" style="margin-right: 4px;">视频</el-tag>
                            <el-tag size="small" :type="scope.row.has_audio ? 'success' : 'info'" effect="plain" style="margin-right: 4px;">音频</el-tag>
                            <el-tag size="small" :type="scope.row.has_original_srt ? 'success' : 'info'" effect="plain" style="margin-right: 4px;">原声</el-tag>
                            <el-tag size="small" :type="scope.row.has_translated_srt ? 'success' : 'info'" effect="plain">翻译</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" width="160" fixed="right">
                        <template #default="scope">
                            <el-button size="small" type="primary" plain @click="loadTask(scope.row)" :disabled="store.taskId === scope.row.task_id">加载</el-button>
                            <el-button size="small" type="danger" plain @click="removeTask(scope.row)">删除</el-button>
                        </template>
                    </el-table-column>
                </el-table>
                    </el-collapse-item>
                </el-collapse>
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
        const uploadPercent = ref(0);
        const currentFileName = ref("");
        const taskList = ref([]);
        const isLoadingTasks = ref(false);
        const activeCollapse = ref([]); // 默认折叠状态
        
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

        const handleUpload = async (options) => {
            addLog(`开始上传源文件: ${options.file.name}...`, "info");
            isUploading.value = true;
            uploadPercent.value = 0;
            
            try {
                // 传入 null 作为 taskId，让后端生成全新任务。资产类型默认按 video 处理（后端会根据后缀保存）
                const res = await uploadAsset(options.file, 'video', null, (percent) => {
                    uploadPercent.value = percent;
                });
                
                // --- 核心：更新全局状态，点亮其他组件 ---
                store.taskId = res.task_id;
                store.activeStep = 1; // 进度条跳到第2步：资产就绪
                
                // 重置并点亮资产状态
                store.assets = {
                    hasVideo: true,
                    hasAudio: false,
                    hasOriginalSrt: false,
                    hasTranslatedSrt: false
                };
                
                currentFileName.value = options.file.name;
                addLog(`✅ 上传成功！任务分配 ID: ${res.task_id}`, "success");
                ElementPlus.ElMessage.success("上传成功，任务工作区已就绪！");
                
                fetchTasks(); // 上传完成后刷新历史列表
            } catch (e) {
                addLog(`❌ 上传失败: ${e.message}`, "error");
                ElementPlus.ElMessage.error(`上传失败: ${e.message}`);
            } finally {
                isUploading.value = false;
            }
        };

        const loadTask = (task) => {
            store.taskId = task.task_id;
            store.assets = {
                hasVideo: task.has_video,
                hasAudio: task.has_audio,
                hasOriginalSrt: task.has_original_srt,
                hasTranslatedSrt: task.has_translated_srt
            };
            currentFileName.value = task.base_name;
            
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

        return {
            isUploading,
            uploadPercent,
            currentFileName,
            taskList,
            isLoadingTasks,
            activeCollapse,
            proxyEnabled,
            proxyProtocol,
            proxyHost,
            proxyPort,
            handleProxyChange,
            handleUpload,
            loadTask,
            removeTask,
            store
        };
    }
};