const { ref } = Vue;
import { store, addLog } from '../store.js';
import { executeTask, WS_BASE, uploadAsset } from '../api.js';

export default {
    name: 'TabLLM',
    template: `
        <div class="llm-container">
            <el-alert title="提示" type="info" show-icon style="margin-bottom: 20px;" :closable="false">
                使用大语言模型 (如 DeepSeek, Qwen, ChatGPT 等) 对提取出的原生字幕进行上下文连贯的批量翻译和润色。如果你已经有了外部的生肉字幕，也可以直接在此处上传并开始翻译。
            </el-alert>

            <!-- 独立上传字幕区 -->
            <div style="margin-bottom: 25px; padding: 15px; border: 1px dashed #dcdfe6; border-radius: 8px; background-color: #fafafa;">
                <div style="margin-bottom: 10px; font-size: 13px; color: #606266; font-weight: bold;">[独立通道] 已有生肉字幕？</div>
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
            </div>

            <!-- LLM 参数配置表单 -->
            <el-form :model="store.config.llm_settings" label-width="140px" label-position="left" size="default">
                <el-form-item label="API Base URL">
                    <el-input v-model="store.config.llm_settings.base_url" placeholder="例如: https://api.siliconflow.cn/v1"></el-input>
                </el-form-item>

                <el-form-item label="API Key">
                    <el-input v-model="store.config.llm_settings.api_key" type="password" show-password placeholder="sk-..."></el-input>
                </el-form-item>

                <el-form-item label="Model Name">
                    <el-input v-model="store.config.llm_settings.model_name" placeholder="例如: Pro/deepseek-ai/DeepSeek-V3.2"></el-input>
                </el-form-item>

                <el-form-item>
                    <template #label>
                        <span style="display: inline-flex; align-items: center;">
                            翻译批次大小
                            <el-tooltip content="每次发给大模型的字幕行数。太小会导致缺乏上下文，太大可能超出模型单次输出上限或导致漏翻。" placement="top">
                                <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;"><QuestionFilled /></el-icon>
                            </el-tooltip>
                        </span>
                    </template>
                    <el-slider v-model="store.config.llm_settings.batch_size" :min="10" :max="200" :step="10" show-input></el-slider>
                </el-form-item>

                <el-form-item>
                    <template #label>
                        <span style="display: inline-flex; align-items: center;">
                            System Prompt
                            <el-tooltip content="控制大模型翻译风格的系统提示词。如果留空，将使用内置的高质量通用影视翻译提示词。" placement="top">
                                <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;"><QuestionFilled /></el-icon>
                            </el-tooltip>
                        </span>
                    </template>
                    <el-input 
                        type="textarea" 
                        v-model="store.config.llm_settings.system_prompt" 
                        :rows="6"
                        placeholder="你是一位精通各国文化的专业影视字幕翻译... (留空则使用内置默认提示词。你可以在此填入之前的限制级翻译指令或要求输出双语)"
                    ></el-input>
                </el-form-item>
            </el-form>

            <!-- 操作按钮与状态指示 -->
            <div style="margin-top: 30px; display: flex; align-items: center;">
                <el-button 
                    type="primary" 
                    size="large" 
                    @click="runTranslate" 
                    :loading="store.isProcessing"
                    :disabled="!store.assets.hasOriginalSrt"
                >
                    <el-icon style="margin-right: 5px;"><ChatDotSquare /></el-icon> 开始执行智能翻译
                </el-button>
                
                <span v-if="!store.assets.hasOriginalSrt" style="color: #F56C6C; margin-left: 15px; font-size: 13px;">
                    ⚠️ 请先在前方提供原声字幕
                </span>
                <span v-else-if="store.assets.hasTranslatedSrt" style="color: #67C23A; margin-left: 15px; font-size: 13px;">
                    ✅ 翻译字幕已生成，请在右侧下载
                </span>
            </div>
        </div>
    `,
    setup() {
        const isUploading = ref(false);

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

            const ws = new WebSocket(`${WS_BASE}/ws/progress/${store.taskId}`);
            ws.onopen = () => addLog("已连接到后端，等待大模型响应...", "success");
            ws.onerror = () => { addLog("WebSocket 连接异常！", "error"); store.isProcessing = false; };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === "processing") {
                    if (data.message) {
                        // 简单判断日志情绪，渲染不同的颜色
                        if (data.message.includes("❌")) addLog(data.message, "error");
                        else if (data.message.includes("⚠️")) addLog(data.message, "warning");
                        else addLog(data.message, "info");
                    }
                } else if (data.status === "completed") {
                    store.isProcessing = false;
                    store.assets.hasTranslatedSrt = true;
                    store.activeStep = 5; // 整个流水线全部完成！
                    addLog("🎉 智能翻译全部完成！", "success");
                    ElementPlus.ElMessage.success("翻译成功！请点击右上角下载熟肉字幕。");
                    ws.close();
                } else if (data.status === "error") {
                    store.isProcessing = false;
                    addLog(`❌ 发生错误: ${data.message}`, "error");
                    ElementPlus.ElMessage.error(`翻译失败: ${data.message}`);
                    ws.close();
                }
            };

            try {
                await executeTask(store.taskId, ["translate"], store.config);
            } catch (e) {
                addLog(`请求启动翻译失败: ${e.message}`, "error");
                store.isProcessing = false;
                ws.close();
            }
        };

        return { store, isUploading, handleSrtUpload, runTranslate };
    }
};
