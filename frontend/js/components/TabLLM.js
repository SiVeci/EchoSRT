const { ref, computed } = Vue;
import { store, addLog, connectTaskMonitor } from '../store.js';
import { executeTask, uploadAsset, getLlmModels } from '../api.js';

export default {
    name: 'TabLLM',
    template: `
        <div class="llm-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                使用大语言模型 (如 DeepSeek, Qwen, ChatGPT 等) 对提取出的原生字幕进行上下文连贯的批量翻译和润色。如果你已经有了外部的生肉字幕，也可以直接在此处上传并开始翻译。
            </el-alert>

            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <template #header>
                    <div class="card-title">📥 独立字幕输入通道</div>
                </template>
                <div class="section-desc">
                    如果您已经拥有外部的生肉字幕文件，可在此直接上传，跳过前面的识别步骤。
                </div>
                <el-upload
                    action="#"
                    :auto-upload="true"
                    :http-request="handleSrtUpload"
                    :show-file-list="false"
                    accept=".srt,.vtt"
                    :disabled="store.isProcessing || isUploading"
                >
                    <el-button type="success" plain :loading="isUploading">
                        <el-icon style="margin-right: 5px;"><Upload /></el-icon> 直接上传外部字幕 (绕过识别)
                    </el-button>
                </el-upload>
            </el-card>

            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <el-collapse v-model="activeCollapse" style="border-top: none; border-bottom: none;">
                    <el-collapse-item name="1">
                        <template #title>
                            <span class="card-title">⚙️ 翻译参数 (LLM)</span>
                        </template>
                        <el-form :model="store.config.llm_settings" label-width="140px" label-position="left" size="default">
                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        API Base URL
                                        <el-tooltip content="兼容 OpenAI 格式的 API 接口地址。官方接口请填 https://api.openai.com/v1，第三方或中转代理服务请填入对应地址。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-input v-model="store.config.llm_settings.base_url" placeholder="例如: https://api.openai.com/v1"></el-input>
                            </el-form-item>

                            <el-form-item label="API Key">
                                <el-input v-model="store.config.llm_settings.api_key" type="password" show-password placeholder="sk-..."></el-input>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        API 访问代理
                                        <el-tooltip content="调用大语言模型 API 时，通过配置的全局网络代理进行访问。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-switch v-model="store.config.llm_settings.use_network_proxy"></el-switch>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        Model Name
                                        <el-tooltip content="指定用于翻译的大语言模型名称。官方接口可填 'gpt-4o' 等，中转代理请视服务商支持填写。点击右侧按钮可直接拉取可用列表。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <div style="display: flex; gap: 10px; width: 100%;">
                                    <el-select v-model="store.config.llm_settings.model_name" placeholder="请选择或输入模型名称" filterable allow-create default-first-option style="flex: 1;">
                                        <el-option v-for="model in store.dicts.llm_models" :key="model" :label="model" :value="model"></el-option>
                                    </el-select>
                                    <el-button type="primary" plain @click="refreshModels" :loading="isFetchingModels" title="从 API 供应商拉取可用模型">
                                        <el-icon><Refresh /></el-icon>
                                    </el-button>
                                </div>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        目标语言
                                        <el-tooltip content="指定原声字幕需要被翻译成的目标语言。大模型将根据此选项生成对应的译文。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-select v-model="store.config.llm_settings.target_language" placeholder="选择翻译目标语言" filterable style="width: 100%;">
                                    <el-option v-for="lang in targetLanguages" :key="lang.code" :label="lang.name + ' (' + lang.code + ')'" :value="lang.code"></el-option>
                                </el-select>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        翻译批次大小
                                        <el-tooltip content="每次发给大模型的字幕行数。太小会导致缺乏上下文，太大可能超出模型单次输出上限或导致漏翻。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-slider v-model="store.config.llm_settings.batch_size" :min="10" :max="200" :step="10" show-input></el-slider>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        并发请求数
                                        <el-tooltip content="同时发送给大模型的翻译请求数。数字越大越快，但过大易触发 API 限流 (429报错)。本地模型请设为1。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-slider v-model="store.config.llm_settings.concurrent_workers" :min="1" :max="20" :step="1" show-input></el-slider>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        System Prompt
                                        <el-tooltip content="控制大模型的翻译风格指令。前缀语言指令会自动生成，你可以在此定制附加的风格要求。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <div style="width: 100%; display: flex; flex-direction: column; gap: 8px;">
                                    <div style="background-color: #f5f7fa; padding: 10px 15px; border-radius: 4px; border: 1px solid #e4e7ed; color: #606266; font-size: 13px; white-space: pre-wrap; line-height: 1.5; max-height: 150px; overflow-y: auto;">{{ fixedPrompt }}</div>
                                    <el-input type="textarea" v-model="store.config.llm_settings.system_prompt" :rows="5"
                                        placeholder="[在此输入附加的自定义风格和格式要求，例如：请输出双语字幕，第一行中文...]&#10;留空则使用内置的【高质量通用影视翻译】格式要求。"
                                    ></el-input>
                                </div>
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
                    @click="runTranslate" 
                    :loading="store.isProcessing"
                    :disabled="!store.assets.hasOriginalSrt"
                >
                    <el-icon style="margin-right: 5px;"><ChatDotSquare /></el-icon> 开始执行智能翻译
                </el-button>
                
                <span v-if="!store.assets.hasOriginalSrt" class="status-text-error">
                    ⚠️ 请先在前方提供原声字幕
                </span>
                <span v-else-if="store.assets.hasTranslatedSrt" class="status-text-success">
                    ✅ 翻译字幕已生成，请在右侧下载
                </span>
            </div>
        </div>
    `,
    setup() {
        const isUploading = ref(false);
        const isFetchingModels = ref(false);
        const activeCollapse = ref([]); // 默认折叠状态

        // 从后端拉取的常用语言字典中，过滤出几个翻译中常用的语言作为目标语言候选
        const targetLanguages = computed(() => {
            const pinnedCodes = ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'];
            return store.dicts.languages.filter(l => pinnedCodes.includes(l.code));
        });

        const fixedPrompt = computed(() => {
            const lang = targetLanguages.value.find(l => l.code === store.config.llm_settings.target_language);
            const langName = lang ? lang.name : '中文';
            return `你是一位精通各国文化的专业影视字幕翻译。\n任务：将用户提供的 SRT 字幕片段翻译成【${langName}】。\n\n### 🚫 格式死命令：\n1. 保留原文结构：这是字幕片段，不要合并，不要遗漏。\n2. 保留时间轴：所有时间戳必须原样保留，不得修改。\n3. 只输出结果：不要加废话，直接输出 SRT 格式文本。`;
        });

        const refreshModels = async () => {
            if (!store.config.llm_settings.api_key) {
                ElementPlus.ElMessage.warning("请先填写 API Key！");
                return;
            }
            isFetchingModels.value = true;
            try {
                const models = await getLlmModels(store.config.llm_settings.api_key, store.config.llm_settings.base_url);
                store.dicts.llm_models = models;
                ElementPlus.ElMessage.success(`成功拉取 ${models.length} 个可用对话模型！`);
            } catch (e) {
                ElementPlus.ElMessage.error(e.message);
            } finally {
                isFetchingModels.value = false;
            }
        };

        const handleSrtUpload = async (options) => {
            addLog(`开始上传外部生肉字幕: ${options.file.name}...`, "info");
            isUploading.value = true;
            try {
                const res = await uploadAsset(options.file, 'srt', store.taskId, null);
                store.taskId = res.task_id;
                store.assets.hasOriginalSrt = true;
                store.activeStep = 4; // 进度条跳到 LLM 翻译待命
                addLog(`✅ 外部字幕上传成功！任务 ID: ${res.task_id}`, "success");
                ElementPlus.ElMessage.success("生肉字幕上传成功，可以直接开始翻译！");
            } catch (e) {
                addLog(`❌ 字幕上传失败: ${e.message}`, "error");
                ElementPlus.ElMessage.error(`上传失败: ${e.message}`);
            } finally {
                isUploading.value = false;
            }
        };

        const runTranslate = async () => {
            if (!store.taskId || !store.assets.hasOriginalSrt) return;
            
            if (!store.config.llm_settings.api_key) {
                ElementPlus.ElMessage.warning("执行失败：请先填写大模型的 API Key！");
                return;
            }

            store.isProcessing = true;
            store.activeStep = 4; // 进度条更新：正在翻译
            addLog("▶️ 启动大模型智能翻译流...", "info");

            connectTaskMonitor(
                store.taskId,
                () => {
                    store.assets.hasTranslatedSrt = true;
                    store.activeStep = 5; // 整个流水线全部完成！
                    addLog("🎉 智能翻译全部完成！", "success");
                    ElementPlus.ElMessage.success("翻译成功！请点击右上角下载熟肉字幕。");
                },
                () => {}
            );

            try {
                await executeTask(store.taskId, ["translate"], store.config);
            } catch (e) {
                addLog(`请求启动翻译失败: ${e.message}`, "error");
                store.isProcessing = false;
            }
        };

        return { store, isUploading, isFetchingModels, activeCollapse, targetLanguages, fixedPrompt, refreshModels, handleSrtUpload, runTranslate };
    }
};