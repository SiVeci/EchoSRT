const { ref } = Vue;
import { store, addLog, connectTaskMonitor } from '../store.js';
import { executeTask, retryTask, uploadAsset, updateConfig } from '../api.js';

export default {
    name: 'TabAudio',
    template: `
        <div class="audio-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                将从上一步上传的视频中提取 16kHz 单声道无损 WAV 音频，专为 Whisper 引擎优化。如果您没有视频，也可以在此直接上传独立的音频文件。
            </el-alert>

            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <template #header>
                    <div class="card-title"><el-icon style="margin-right:4px;"><Upload /></el-icon>独立音频输入通道</div>
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
                            <span class="card-title"><el-icon style="margin-right:4px;"><Setting /></el-icon>提取参数 (FFmpeg)</span>
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
                    <el-icon style="margin-right: 5px;"><VideoPlay /></el-icon> 
                    {{ ((store.pipelineStatus[store.taskId]?.current_step === 'interrupted' || store.pipelineStatus[store.taskId]?.current_step === 'error') && (!store.pipelineStatus[store.taskId]?.interrupted_step || store.pipelineStatus[store.taskId]?.interrupted_step === 'extracting' || store.pipelineStatus[store.taskId]?.interrupted_step === 'pending_extract')) ? '继续执行 (断点重试)' : '仅执行音频提取' }}
                </el-button>
                
                <span v-if="!store.assets.hasVideo" class="status-text-error">
                    请先在工作区上传视频
                </span>
                <span v-else-if="store.assets.hasAudio" class="status-text-success">
                    音频已就绪，可直接前往下一步
                </span>
            </div>
            
            <!-- FFmpeg 提取进度动态显示 -->
            <div v-if="store.taskState.extractedTime && store.isProcessing && store.activeStep === 2" style="margin-top: 15px; color: #409EFF; font-size: 14px;">
                <el-icon class="is-loading" style="margin-right: 5px;"><Loading /></el-icon>
                正在提取音频，已处理至：<strong>{{ store.taskState.extractedTime }}</strong> ...
            </div>
        </div>
    `,
    setup() {
        const isUploading = ref(false);
        const activeCollapse = ref([]); // 默认折叠状态

        // 处理独立上传音频
        const handleAudioUpload = async (options) => {
            addLog(`开始上传外部音频: ${options.file.name}...`, "info");
            isUploading.value = true;
            try {
                const res = await uploadAsset(options.file, 'audio', store.taskId, null);
                store.taskId = res.task_id;
                store.currentTaskName = options.file.name;
                store.assets.hasAudio = true;
                store.activeStep = 2; // 进度条更新：资产/音频已就绪
                store.refreshTasksTrigger++;
                addLog(`外部音频上传成功！任务 ID: ${res.task_id}`, "success");
                ElementPlus.ElMessage.success("音频上传成功，请前往【原声识别】页！");
            } catch (e) {
                addLog(`音频上传失败: ${e.message}`, "error");
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
            store.taskState.extractedTime = "";

            const statusObj = store.pipelineStatus[store.taskId];
            const currentStatus = statusObj?.current_step;
            const interruptedStep = statusObj?.interrupted_step;
            const isRetry = (currentStatus === 'interrupted' || currentStatus === 'error') && (!interruptedStep || interruptedStep === 'extracting' || interruptedStep === 'pending_extract');
            addLog(isRetry ? "正在尝试断点重试任务..." : "启动 FFmpeg 音频提取...", "info");

            connectTaskMonitor(
                store.taskId,
                () => {
                    store.assets.hasAudio = true;
                    store.activeStep = 3; // 音频提取完毕，进入识别待命
                    addLog("音频提取完毕！", "success");
                    ElementPlus.ElMessage.success("提取完毕！");
                },
                () => {}
            );

            // 执行前单独触发落盘保存
            try { await updateConfig(store.config); } catch (e) {}

            try {
                if (isRetry) {
                    await retryTask(store.taskId);
                } else {
                    await executeTask(store.taskId, ["extract"], store.config);
                }
            } catch (e) {
                addLog(`请求启动任务失败: ${e.message}`, "error");
                store.isProcessing = false;
            }
        };

        return { store, isUploading, activeCollapse, handleAudioUpload, runExtract };
    }
};