const { ref } = Vue;
import WhisperLocal from './WhisperLocal.js';
import WhisperApi from './WhisperApi.js';
import { store, addLog, connectTaskMonitor } from '../store.js';
import { executeTask } from '../api.js';

export default {
    name: 'TabWhisper',
    components: { WhisperLocal, WhisperApi },
    template: `
        <div class="whisper-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                将提取出的音频输入 faster-whisper 引擎进行识别，生成带有精确时间轴的原始语言字幕 (SRT)。如果你已有现成的原生字幕文件，可直接跳到下一页 [LLM 翻译] 进行独立上传。
            </el-alert>

            <el-tabs v-model="store.config.transcribe_settings.engine" style="margin-bottom: 20px;">
                <!-- 引擎 1: 本地 GPU -->
                <el-tab-pane name="local">
                    <template #label>
                        <span style="font-weight: bold; font-size: 14px; display: inline-flex; align-items: center;">
                            🖥️ 本地 GPU 引擎
                            <el-icon v-if="store.config.transcribe_settings.engine === 'local'" style="margin-left: 5px; color: #67C23A; font-weight: bold;"><Check /></el-icon>
                        </span>
                    </template>
                    <whisper-local></whisper-local>
                </el-tab-pane>
                
                <!-- 引擎 2: 云端 API -->
                <el-tab-pane name="api">
                    <template #label>
                        <span style="font-weight: bold; font-size: 14px; display: inline-flex; align-items: center;">
                            ☁️ 云端 API 引擎
                            <el-icon v-if="store.config.transcribe_settings.engine === 'api'" style="margin-left: 5px; color: #67C23A; font-weight: bold;"><Check /></el-icon>
                        </span>
                    </template>
                    <whisper-api></whisper-api>
                </el-tab-pane>
            </el-tabs>

            <!-- 操作按钮与状态指示 -->
            <div class="action-bar">
                <el-button 
                    type="primary" 
                    size="large" 
                    @click="runTranscribe" 
                    :loading="store.isProcessing"
                    :disabled="!store.assets.hasAudio"
                >
                <el-icon style="margin-right: 5px;"><Microphone /></el-icon>
                {{ store.config.transcribe_settings.engine === 'api' ? ' 启动云端 API 识别' : ' 启动本地模型识别' }}
                </el-button>
                
                <span v-if="!store.assets.hasAudio" class="status-text-error">
                    ⚠️ 请先在前方提供音频
                </span>
                <span v-else-if="store.assets.hasOriginalSrt" class="status-text-success">
                    ✅ 原声字幕已生成，可前往翻译
                </span>
            </div>
            
            <!-- 模型下载进度提示 -->
            <div v-if="store.taskState.downloadedMB !== null && store.isProcessing && store.activeStep === 3" style="margin-top: 15px;">
                <div style="display: inline-flex; justify-content: center; align-items: center; padding: 10px 15px; background-color: #ecf5ff; color: #409EFF; border-radius: 4px; font-size: 14px;">
                    <el-icon class="is-loading" style="margin-right: 8px; font-size: 18px;"><Loading /></el-icon>
                    <span>首次加载较慢，正在读取或下载模型... (已下载: {{ store.taskState.downloadedMB }} MB)</span>
                </div>
            </div>
        </div>
    `,
    setup() {
        // 启动识别
        const runTranscribe = async () => {
            if (!store.taskId || !store.assets.hasAudio) return;

            store.isProcessing = true;
            store.activeStep = 3; // 进度条跳到原声识别
            store.taskState.downloadedMB = null;
            const engineName = store.config.transcribe_settings.engine === 'api' ? "云端 API" : "本地 Whisper";
            addLog(`▶️ 启动 ${engineName} 识别引擎...`, "info");

            connectTaskMonitor(
                store.taskId,
                () => {
                    store.assets.hasOriginalSrt = true;
                    store.activeStep = 4; // 进入 LLM 翻译待命状态
                    addLog("🎉 原声字幕提取完毕！", "success");
                    ElementPlus.ElMessage.success("识别成功！已生成 SRT 原生字幕。");
                },
                () => {}
            );

            try {
                await executeTask(store.taskId, ["transcribe"], store.config);
            } catch (e) {
                addLog(`请求启动任务失败: ${e.message}`, "error");
                store.isProcessing = false;
            }
        };

        return { store, runTranscribe };
    }
};