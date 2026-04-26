const { ref, watch, nextTick } = Vue;
import { store } from '../store.js';
import { API_BASE } from '../api.js';

export default {
    name: 'GlobalConsole',
    template: `
        <el-card class="box-card console-card" shadow="never">
            <template #header>
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: bold;">⏱️ 任务监视器</span>
                </div>
            </template>

            <!-- 产物下载区 (只有资产就绪时才可点击) -->
            <div class="download-actions" style="margin-bottom: 25px; display: flex; flex-direction: column; gap: 12px;">
                <el-button type="primary" plain @click="downloadSrt('original')" :disabled="!store.assets.hasOriginalSrt">
                    <el-icon style="margin-right: 5px;"><Download /></el-icon> 下载原声字幕 (SRT)
                </el-button>
                <el-button type="success" plain @click="downloadSrt('translated')" :disabled="!store.assets.hasTranslatedSrt">
                    <el-icon style="margin-right: 5px;"><Download /></el-icon> 下载翻译字幕 (SRT)
                </el-button>
            </div>

            <!-- 垂直步骤条 (贴合侧边栏布局) -->
            <el-steps :active="store.activeStep" finish-status="success" direction="vertical" style="height: 300px; margin-bottom: 25px;">
                <el-step title="准备就绪" description="等待分配任务"></el-step>
                <el-step title="资产就绪" description="音视频/字幕已传"></el-step>
                <el-step title="提取音频" description="FFmpeg 处理中"></el-step>
                <el-step title="原声识别" description="Whisper 推理中"></el-step>
                <el-step title="LLM 翻译" description="大模型翻译中"></el-step>
            </el-steps>

            <!-- 日志终端 -->
            <div class="log-container" ref="logBox">
                <div v-for="(log, index) in store.logs" :key="index" :class="'log-' + log.type">
                    <span style="color:#808080;">[{{ log.time }}]</span> {{ log.message }}
                </div>
            </div>
        </el-card>
    `,
    setup() {
        const logBox = ref(null);

        // 监听日志数组的长度变化，自动将滚动条拉到最底部
        watch(() => store.logs.length, () => {
            nextTick(() => {
                if (logBox.value) {
                    logBox.value.scrollTop = logBox.value.scrollHeight;
                }
            });
        });

        const downloadSrt = (type) => {
            if (!store.taskId) return;
            window.open(`${API_BASE}/api/download/${store.taskId}?type=${type}`, "_blank");
        };

        return { store, logBox, downloadSrt };
    }
};