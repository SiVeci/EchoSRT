const { ref, watch, nextTick } = Vue;
import { store } from '../store.js';
import { API_BASE } from '../api.js';

export default {
    name: 'GlobalConsole',
    template: `
        <el-card class="box-card" shadow="never">
            <template #header>
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="card-title">⏱️ 任务监视器</span>
                </div>
            </template>

            <!-- 产物下载区 (只有资产就绪时才可点击) -->
            <div class="download-actions" style="margin-bottom: 25px; display: flex; flex-direction: column; gap: 12px;">
                <el-button type="primary" plain @click="downloadSrt('original')" :disabled="!store.assets.hasOriginalSrt" style="width: 100%; margin-left: 0;">
                    <el-icon style="margin-right: 5px;"><Download /></el-icon> 下载原声字幕 (SRT)
                </el-button>
                <el-button type="success" plain @click="downloadSrt('translated')" :disabled="!store.assets.hasTranslatedSrt" style="width: 100%; margin-left: 0;">
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

            <!-- 日志终端 (可折叠) -->
            <el-collapse v-model="activeCollapse" style="border-top: none; border-bottom: none;">
                <el-collapse-item name="1">
                    <template #title>
                        <span class="card-title" style="font-size: 14px;">📝 运行日志</span>
                    </template>
                    <div class="log-container" ref="logBox">
                        <div v-for="(log, index) in store.logs" :key="index" :class="'log-' + log.type">
                            <span style="color:#808080;">[{{ log.time }}]</span> {{ log.message }}
                        </div>
                    </div>
                </el-collapse-item>
            </el-collapse>
        </el-card>
    `,
    setup() {
        const logBox = ref(null);
        const activeCollapse = ref([]); // 默认折叠，需要看时可展开

        // 监听日志数组的长度变化，自动将滚动条拉到最底部
        watch(() => store.logs.length, () => {
            nextTick(() => {
                if (logBox.value) {
                    logBox.value.scrollTop = logBox.value.scrollHeight;
                }
            });
        });

        // 当用户主动展开日志面板时，立即滚动到最底部以展示最新日志
        watch(activeCollapse, (newVal) => {
            if (newVal.includes('1')) {
                nextTick(() => {
                    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight;
                });
            }
        });

        const downloadSrt = async (type) => {
            if (!store.taskId) return;
            try {
                // 需要先获取一次任务列表拿到 base_name
                const { getTasks } = await import('../api.js');
                const tasks = await getTasks();
                const task = tasks.find(t => t.task_id === store.taskId);
                const baseName = task ? task.base_name : 'download';
                
                const { downloadAsset } = await import('../api.js');
                downloadAsset(store.taskId, type, baseName);
            } catch (e) {
                console.error("下载失败", e);
            }
        };

        return { store, logBox, activeCollapse, downloadSrt };
    }
};