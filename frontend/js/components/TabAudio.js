const { ref } = Vue;
import { store, addLog } from '../store.js';
import { executeTask, WS_BASE, uploadAsset } from '../api.js';

export default {
    name: 'TabAudio',
    template: `
        <div class="audio-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                将从上一步上传的视频中提取 16kHz 单声道无损 WAV 音频，专为 Whisper 引擎优化。如果您没有视频，也可以在此直接上传独立的音频文件。
            </el-alert>

            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <template #header>
                    <div class="card-title">📥 独立音频输入通道</div>
                </template>
                <div class="section-desc">
                    如果您已经拥有独立的音频文件，可在此直接上传，跳过视频提取步骤。
                </div>
                <el-upload
                    action="#"
                    :auto-upload="true"
                    :http-request="handleAudioUpload"
                    :show-file-list="false"
                    accept="audio/*"
                    :disabled="store.isProcessing || isUploading"
                >
                    <el-button type="success" plain :loading="isUploading">
                        <el-icon style="margin-right: 5px;"><Upload /></el-icon> 直接上传外部音频
                    </el-button>
                </el-upload>
            </el-card>

            <!-- FFmpeg 参数配置表单 -->
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <el-collapse v-model="activeCollapse" style="border-top: none; border-bottom: none;">
                    <el-collapse-item name="1">
                        <template #title>
                            <span class="card-title">⚙️ 提取参数 (FFmpeg)</span>
                        </template>
                        <el-form :model="store.config.ffmpeg_settings" label-width="140px" label-position="left" size="default">
                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        音轨选择 (Map)
                                        <el-tooltip content="默认 0:a:0 代表第一条音轨。对于多音轨视频（如中英双语版），可修改为 0:a:1 提取第二条。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-input v-model="store.config.ffmpeg_settings.audio_track" placeholder="例如: 0:a:0"></el-input>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        开始时间 (-ss)
                                        <el-tooltip content="留空表示从头开始。格式支持纯秒数 (120) 或标准时间戳 (00:02:00)。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-input v-model="store.config.ffmpeg_settings.start_time" placeholder="例如: 00:01:00 (空则从头开始)"></el-input>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        结束时间 (-to)
                                        <el-tooltip content="留空表示提取到视频末尾。格式同上。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-input v-model="store.config.ffmpeg_settings.end_time" placeholder="例如: 00:05:00 (空则直到末尾)"></el-input>
                            </el-form-item>
                        </el-form>
                    </el-collapse-item>
                </el-collapse>
            </el-card>

            <!-- 操作按钮与状态指示 -->
            <div class="action-bar">
                <el-button 
                    type="primary" 
                    size="large" 
                    @click="runExtract" 
                    :loading="store.isProcessing"
                    :disabled="!store.assets.hasVideo"
                >
                    <el-icon style="margin-right: 5px;"><VideoPlay /></el-icon> 仅执行音频提取
                </el-button>
                
                <span v-if="!store.assets.hasVideo" class="status-text-error">
                    ⚠️ 请先在工作区上传视频
                </span>
                <span v-else-if="store.assets.hasAudio" class="status-text-success">
                    ✅ 音频已就绪，可直接前往下一步
                </span>
            </div>
            
            <!-- FFmpeg 提取进度动态显示 -->
            <div v-if="extractedTime && store.isProcessing" style="margin-top: 15px; color: #409EFF; font-size: 14px;">
                <el-icon class="is-loading" style="margin-right: 5px;"><Loading /></el-icon>
                正在提取音频，已处理至：<strong>{{ extractedTime }}</strong> ...
            </div>
        </div>
    `,
    setup() {
        const isUploading = ref(false);
        const extractedTime = ref("");
        const activeCollapse = ref([]); // 默认折叠状态

        // 处理独立上传音频
        const handleAudioUpload = async (options) => {
            addLog(`开始上传外部音频: ${options.file.name}...`, "info");
            isUploading.value = true;
            try {
                const res = await uploadAsset(options.file, 'audio', store.taskId, null);
                store.taskId = res.task_id;
                store.assets.hasAudio = true;
                store.activeStep = 2; // 进度条更新：资产/音频已就绪
                addLog(`✅ 外部音频上传成功！任务 ID: ${res.task_id}`, "success");
                ElementPlus.ElMessage.success("音频上传成功，请前往【原声识别】页！");
            } catch (e) {
                addLog(`❌ 音频上传失败: ${e.message}`, "error");
                ElementPlus.ElMessage.error(`上传失败: ${e.message}`);
            } finally {
                isUploading.value = false;
            }
        };

        // 调用后端的单步提取流
        const runExtract = async () => {
            if (!store.taskId || !store.assets.hasVideo) return;
            store.isProcessing = true;
            store.activeStep = 2; // 更新进度条状态
            extractedTime.value = "";
            addLog("▶️ 启动 FFmpeg 音频提取...", "info");

            const ws = new WebSocket(`${WS_BASE}/ws/progress/${store.taskId}`);
            ws.onopen = () => addLog("已连接到后端监视器...", "success");
            ws.onerror = () => { addLog("WebSocket 连接异常！", "error"); store.isProcessing = false; };
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === "processing") {
                    if (data.extracted_time) extractedTime.value = data.extracted_time;
                    else if (data.message) addLog(data.message, "info");
                } else if (data.status === "completed") {
                    store.isProcessing = false;
                    store.assets.hasAudio = true;
                    store.activeStep = 3; // 音频提取完毕，进入识别待命
                    addLog("🎉 音频提取完毕！", "success");
                    ElementPlus.ElMessage.success("提取完毕！");
                    ws.close();
                } else if (data.status === "error") {
                    store.isProcessing = false;
                    addLog(`❌ 发生错误: ${data.message}`, "error");
                    ElementPlus.ElMessage.error(`任务失败: ${data.message}`);
                    ws.close();
                }
            };
            try {
                await executeTask(store.taskId, ["extract"], store.config);
            } catch (e) {
                addLog(`请求启动任务失败: ${e.message}`, "error");
                store.isProcessing = false;
                ws.close();
            }
        };

        return { store, isUploading, extractedTime, activeCollapse, handleAudioUpload, runExtract };
    }
};