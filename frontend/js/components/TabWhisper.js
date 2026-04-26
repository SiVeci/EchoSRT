const { ref, computed, watch } = Vue;
import { store, addLog } from '../store.js';
import { executeTask, WS_BASE } from '../api.js';

export default {
    name: 'TabWhisper',
    template: `
        <div class="whisper-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                将提取出的音频输入 faster-whisper 引擎进行识别，生成带有精确时间轴的原始语言字幕 (SRT)。如果你已有现成的原生字幕文件，可直接跳到下一页 [LLM 翻译] 进行独立上传。
            </el-alert>

            <!-- 基础设置卡片 -->
            <el-card class="box-card" shadow="never" style="margin-bottom: 15px; border: 1px solid #ebeef5;">
                <template #header>
                    <div style="font-weight: bold; color: #303133;">⚙️ 基础设置 (Basic)</div>
                </template>
                <el-form :model="store.config" label-width="140px" size="default" label-position="left">
                    <el-form-item>
                        <template #label>
                            <span style="display: inline-flex; align-items: center;">
                                模型大小
                                <el-tooltip content="模型体积越大，识别准确率越高，但需要的显存和处理时间也成倍增加。" placement="top">
                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;"><QuestionFilled /></el-icon>
                                </el-tooltip>
                            </span>
                        </template>
                        <el-select v-model="store.config.model_settings.model_size" placeholder="选择模型" filterable style="width: 100%;">
                            <el-option-group v-for="group in store.dicts.models" :key="group.label" :label="group.label">
                                <el-option v-for="model in group.options" :key="model" :label="model" :value="model"></el-option>
                            </el-option-group>
                        </el-select>
                    </el-form-item>
                    
                    <el-form-item>
                        <template #label>
                            <span style="display: inline-flex; align-items: center;">
                                识别语言
                                <el-tooltip content="指定原视频语言。自动检测可能在无声前奏中误判，明确指定可提升准确率和速度。" placement="top">
                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;"><QuestionFilled /></el-icon>
                                </el-tooltip>
                            </span>
                        </template>
                        <el-select v-model="store.config.transcribe_settings.language" placeholder="自动检测 (Auto)" clearable filterable style="width: 100%;">
                            <el-option-group label="🌟 常用语言">
                                <el-option v-for="lang in pinnedLanguages" :key="lang.code" :label="\`\${lang.name} (\${lang.code})\`" :value="lang.code"></el-option>
                            </el-option-group>
                            <el-option-group label="🌐 其他语言 (A-Z)">
                                <el-option v-for="lang in otherLanguages" :key="lang.code" :label="\`\${lang.name} (\${lang.code})\`" :value="lang.code"></el-option>
                            </el-option-group>
                        </el-select>
                    </el-form-item>
                </el-form>
            </el-card>

            <!-- 高级设置折叠面板 -->
            <el-collapse>
                <el-collapse-item name="1">
                    <template #title>
                        <span style="font-weight: bold; color: #606266; font-size: 14px;"><el-icon style="margin-right: 5px;"><Tools /></el-icon> 高级设置 (Advanced Settings)</span>
                    </template>
                    
                    <el-tabs type="border-card" size="small" stretch>
                        <!-- 第一类：文本与上下文 -->
                        <el-tab-pane label="文本/上下文">
                            <el-form :model="store.config" size="small" label-position="top">
                                <el-form-item label="Initial Prompt (初始提示词)">
                                    <el-input type="textarea" v-model="store.config.transcribe_settings.initial_prompt" placeholder="引导词、专有名词、人名等 (空则不使用)"></el-input>
                                </el-form-item>
                                <el-form-item label="Hotwords (热词增强)">
                                    <el-input type="textarea" v-model="store.config.transcribe_settings.hotwords" placeholder="希望模型优先识别的词语"></el-input>
                                </el-form-item>
                                <el-row :gutter="20">
                                    <el-col :span="12">
                                        <el-checkbox v-model="store.config.transcribe_settings.condition_on_previous_text">参考上一句 (减少幻觉)</el-checkbox>
                                    </el-col>
                                    <el-col :span="12">
                                        <el-checkbox v-model="store.config.transcribe_settings.suppress_blank">抑制空白输出</el-checkbox>
                                    </el-col>
                                </el-row>
                                <el-form-item label="抑制词 ID 数组 (Suppress Tokens)" style="margin-top: 15px;">
                                    <el-input v-model="suppressTokensStr" placeholder="例如: -1"></el-input>
                                </el-form-item>
                            </el-form>
                        </el-tab-pane>

                        <!-- 第二类：解码与搜索 -->
                        <el-tab-pane label="解码/搜索">
                            <el-form :model="store.config" size="small" label-position="right" label-width="120px">
                                <el-form-item label="Beam Size">
                                    <el-input-number v-model="store.config.transcribe_settings.beam_size" :min="1" :max="20"></el-input-number>
                                </el-form-item>
                                <el-form-item label="Best Of">
                                    <el-input-number v-model="store.config.transcribe_settings.best_of" :min="1" :max="20"></el-input-number>
                                </el-form-item>
                                <el-form-item label="Patience">
                                    <el-input-number v-model="store.config.transcribe_settings.patience" :step="0.1" :min="0"></el-input-number>
                                </el-form-item>
                                <el-form-item label="长度/重复惩罚">
                                    <el-input-number v-model="store.config.transcribe_settings.length_penalty" :step="0.1" style="width: 100px; margin-right: 10px;"></el-input-number>
                                    <el-input-number v-model="store.config.transcribe_settings.repetition_penalty" :step="0.1" :min="1.0" style="width: 100px;"></el-input-number>
                                </el-form-item>
                                
                                <el-divider border-style="dashed">Temperature 递进数组</el-divider>
                                <div v-for="(temp, index) in store.config.transcribe_settings.temperature" :key="index" style="display: flex; align-items: center; margin-bottom: 8px;">
                                    <el-tag type="info" style="margin-right: 10px; width: 40px; text-align: center;"># {{ index + 1 }}</el-tag>
                                    <el-input-number v-model="store.config.transcribe_settings.temperature[index]" :step="0.2" :min="0.0" :max="1.0" style="width: 110px;"></el-input-number>
                                    <el-button type="primary" circle size="small" @click="addTemperature(index)" style="margin-left: 10px;"><el-icon><Plus /></el-icon></el-button>
                                    <el-button type="danger" circle size="small" @click="removeTemperature(index)" :disabled="store.config.transcribe_settings.temperature.length <= 1" style="margin-left: 5px;"><el-icon><Minus /></el-icon></el-button>
                                </div>
                            </el-form>
                        </el-tab-pane>

                        <!-- 第三类：阈值过滤 -->
                        <el-tab-pane label="阈值过滤">
                            <el-form :model="store.config" size="small" label-position="right" label-width="180px">
                                <el-form-item label="VAD 智能静音过滤">
                                    <el-switch v-model="store.config.vad_settings.vad_filter" active-text="强烈推荐开启"></el-switch>
                                </el-form-item>
                                <el-form-item label="压缩比阈值">
                                    <el-input-number v-model="store.config.transcribe_settings.compression_ratio_threshold" :step="0.1"></el-input-number>
                                </el-form-item>
                                <el-form-item label="对数概率阈值">
                                    <el-input-number v-model="store.config.transcribe_settings.log_prob_threshold" :step="0.1"></el-input-number>
                                </el-form-item>
                                <el-form-item label="无声判定阈值">
                                    <el-input-number v-model="store.config.transcribe_settings.no_speech_threshold" :step="0.05" :min="0" :max="1"></el-input-number>
                                </el-form-item>
                                <el-form-item label="幻觉静音截断阈值">
                                    <el-input v-model="nullableFields.hallucination_silence_threshold" placeholder="空则禁用 (Null)"></el-input>
                                </el-form-item>
                                <el-form-item label="语言探测阈值">
                                    <el-slider v-model="store.config.transcribe_settings.language_detection_threshold" :min="0" :max="1" :step="0.1" show-input></el-slider>
                                </el-form-item>
                            </el-form>
                        </el-tab-pane>

                        <!-- 第四类：杂项 -->
                        <el-tab-pane label="系统/杂项">
                            <el-form :model="store.config" size="small" label-position="right" label-width="140px">
                                <el-form-item label="翻译为纯英文">
                                    <el-switch v-model="store.config.transcribe_settings.task" active-value="translate" inactive-value="transcribe"></el-switch>
                                </el-form-item>
                                <el-form-item label="多语言交替模式">
                                    <el-switch v-model="store.config.transcribe_settings.multilingual"></el-switch>
                                </el-form-item>
                                <el-form-item label="词级时间戳 (Word)">
                                    <el-switch v-model="store.config.transcribe_settings.word_timestamps"></el-switch>
                                </el-form-item>
                                <el-form-item label="关闭时间戳">
                                    <el-switch v-model="store.config.transcribe_settings.without_timestamps" active-color="#f56c6c"></el-switch>
                                </el-form-item>
                                <el-form-item label="最大新 Token 数">
                                    <el-input v-model="nullableFields.max_new_tokens" placeholder="空则无限制 (Null)"></el-input>
                                </el-form-item>
                                <el-form-item label="音频切片长度 (秒)">
                                    <el-input v-model="nullableFields.chunk_length" placeholder="空则自动 (Null)"></el-input>
                                </el-form-item>
                                <el-form-item label="模型下载存放目录">
                                    <el-input v-model="store.config.model_settings.download_root"></el-input>
                                </el-form-item>
                                <el-form-item label="HF Token (选填)">
                                    <el-input v-model="store.config.secrets.hf_token" type="password" show-password></el-input>
                                </el-form-item>
                            </el-form>
                        </el-tab-pane>
                    </el-tabs>
                </el-collapse-item>
            </el-collapse>

            <!-- 操作按钮与状态指示 -->
            <div style="margin-top: 30px; display: flex; align-items: center;">
                <el-button 
                    type="primary" 
                    size="large" 
                    @click="runTranscribe" 
                    :loading="store.isProcessing"
                    :disabled="!store.assets.hasAudio"
                >
                    <el-icon style="margin-right: 5px;"><Microphone /></el-icon> 开始执行原声识别
                </el-button>
                
                <span v-if="!store.assets.hasAudio" style="color: #F56C6C; margin-left: 15px; font-size: 13px;">
                    ⚠️ 请先在前方提供音频
                </span>
                <span v-else-if="store.assets.hasOriginalSrt" style="color: #67C23A; margin-left: 15px; font-size: 13px;">
                    ✅ 原声字幕已生成，可前往翻译
                </span>
            </div>
            
            <!-- 模型下载进度提示 -->
            <div v-if="downloadedMB !== null && store.isProcessing" style="margin-top: 15px;">
                <div style="display: inline-flex; justify-content: center; align-items: center; padding: 10px 15px; background-color: #ecf5ff; color: #409EFF; border-radius: 4px; font-size: 14px;">
                    <el-icon class="is-loading" style="margin-right: 8px; font-size: 18px;"><Loading /></el-icon>
                    <span>首次加载较慢，正在读取或下载模型... (已下载: {{ downloadedMB }} MB)</span>
                </div>
            </div>
        </div>
    `,
    setup() {
        // 语言列表分组计算
        const pinnedCodes = ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'];
        const pinnedLanguages = computed(() => store.dicts.languages.filter(l => pinnedCodes.includes(l.code)));
        const otherLanguages = computed(() => store.dicts.languages.filter(l => !pinnedCodes.includes(l.code)));

        // 本地中间状态 (处理无法直接双向绑定的特殊数据类型)
        const suppressTokensStr = ref(store.config.transcribe_settings.suppress_tokens ? store.config.transcribe_settings.suppress_tokens.join(",") : "-1");
        const nullableFields = ref({
            hallucination_silence_threshold: store.config.transcribe_settings.hallucination_silence_threshold ?? "",
            max_new_tokens: store.config.transcribe_settings.max_new_tokens ?? "",
            chunk_length: store.config.transcribe_settings.chunk_length ?? ""
        });
        const downloadedMB = ref(null);

        // 实时同步本地临时状态到全局 config (适配一键全量工作流)
        watch(suppressTokensStr, (val) => {
            store.config.transcribe_settings.suppress_tokens = val.split(",").map(s => parseInt(s.trim())).filter(n => !isNaN(n));
        });
        watch(nullableFields, (val) => {
            const parseNull = (v) => (v === "" || v === null || v === undefined) ? null : Number(v);
            store.config.transcribe_settings.hallucination_silence_threshold = parseNull(val.hallucination_silence_threshold);
            store.config.transcribe_settings.max_new_tokens = parseNull(val.max_new_tokens);
            store.config.transcribe_settings.chunk_length = parseNull(val.chunk_length);
        }, { deep: true });

        // 温度数组增删逻辑
        const addTemperature = (index) => {
            const tempArray = store.config.transcribe_settings.temperature;
            let nextVal = tempArray[index] + 0.2;
            if (nextVal > 1.0) nextVal = 1.0;
            tempArray.splice(index + 1, 0, parseFloat(nextVal.toFixed(1)));
        };
        const removeTemperature = (index) => {
            const tempArray = store.config.transcribe_settings.temperature;
            if (tempArray.length > 1) tempArray.splice(index, 1);
        };

        // 启动识别
        const runTranscribe = async () => {
            if (!store.taskId || !store.assets.hasAudio) return;

            store.isProcessing = true;
            store.activeStep = 3; // 进度条跳到原声识别
            downloadedMB.value = null;
            addLog("▶️ 启动 Whisper 识别引擎...", "info");

            const ws = new WebSocket(`${WS_BASE}/ws/progress/${store.taskId}`);
            ws.onopen = () => addLog("等待模型分配资源...", "success");
            ws.onerror = () => { addLog("WebSocket 连接异常！", "error"); store.isProcessing = false; };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === "processing") {
                    if (data.step === "downloading") {
                        if (data.downloaded_mb !== undefined) downloadedMB.value = data.downloaded_mb;
                    } else if (data.step === "transcribing") {
                        downloadedMB.value = null; // 隐藏下载进度
                        if (data.progress) {
                            addLog(`[${data.progress}] ${data.text}`, "progress");
                        } else if (data.message) {
                            addLog(data.message, "info");
                        }
                    }
                } else if (data.status === "completed") {
                    store.isProcessing = false;
                    store.assets.hasOriginalSrt = true;
                    store.activeStep = 4; // 进入 LLM 翻译待命状态
                    addLog("🎉 原声字幕提取完毕！", "success");
                    ElementPlus.ElMessage.success("识别成功！已生成 SRT 原生字幕。");
                    ws.close();
                } else if (data.status === "error") {
                    store.isProcessing = false;
                    addLog(`❌ 发生错误: ${data.message}`, "error");
                    ElementPlus.ElMessage.error(`识别失败: ${data.message}`);
                    ws.close();
                }
            };

            try {
                await executeTask(store.taskId, ["transcribe"], store.config);
            } catch (e) {
                addLog(`请求启动任务失败: ${e.message}`, "error");
                store.isProcessing = false;
                ws.close();
            }
        };

        return { 
            store, pinnedLanguages, otherLanguages, 
            suppressTokensStr, nullableFields, downloadedMB,
            addTemperature, removeTemperature, runTranscribe
        };
    }
};