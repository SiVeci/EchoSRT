const { createApp, ref, onMounted } = Vue;

// 引入组件
import TabWorkspace from './components/TabWorkspace.js';
import TabAudio from './components/TabAudio.js';
import TabWhisper from './components/TabWhisper.js';
import TabLLM from './components/TabLLM.js';
import GlobalConsole from './components/GlobalConsole.js';

// 引入全局状态与网络请求
import { store, addLog } from './store.js';
import { getConfig, getLanguages, getModels, executeTask, WS_BASE } from './api.js';

const app = createApp({
    components: {
        TabWorkspace,
        TabAudio,
        TabWhisper,
        'tab-llm': TabLLM,
        GlobalConsole
    },
    setup() {
        // 控制当前激活的 Tab 页面，默认停留在第一页
        const activeTab = ref('workspace');

        // 页面加载时，拉取后端配置与字典数据
        onMounted(async () => {
            addLog("正在初始化应用，拉取后端配置...", "info");
            try {
                const [configData, langData, modelData] = await Promise.all([
                    getConfig(),
                    getLanguages(),
                    getModels()
                ]);
                
                // 将后端拉取到的配置镜像同步到全局 Store
                if(configData.secrets) Object.assign(store.config.secrets, configData.secrets);
                if(configData.model_settings) Object.assign(store.config.model_settings, configData.model_settings);
                if(configData.transcribe_settings) Object.assign(store.config.transcribe_settings, configData.transcribe_settings);
                if(configData.vad_settings) Object.assign(store.config.vad_settings, configData.vad_settings);
                if(configData.ffmpeg_settings) Object.assign(store.config.ffmpeg_settings, configData.ffmpeg_settings);
                if(configData.llm_settings) Object.assign(store.config.llm_settings, configData.llm_settings);

                // 加载字典
                store.dicts.languages = langData;
                store.dicts.models = modelData;

                addLog("✅ 基础配置加载完成，就绪！", "success");
            } catch (e) {
                addLog(`❌ 初始化失败: ${e.message}`, "error");
                ElementPlus.ElMessage.error("无法连接到后端服务，请检查 app.py 是否启动。");
            }
        });

        // 一键启动全量工作流
        const runFullPipeline = async () => {
            if (!store.taskId) {
                ElementPlus.ElMessage.warning("请先在【任务工作区】上传视频或指定一个任务！");
                return;
            }
            
            // 🧠 智能组装需要执行的流水线步骤
            const steps = [];
            // 1. 如果有视频且没提取音频，必须先提音
            if (!store.assets.hasAudio && store.assets.hasVideo) steps.push("extract");
            // 2. 如果没有原生字幕，且具备音频条件，则执行识别
            if (!store.assets.hasOriginalSrt && (store.assets.hasAudio || steps.includes("extract"))) steps.push("transcribe");
            // 3. 如果填写了大模型 API Key，则附带智能翻译功能
            if (store.config.llm_settings.api_key) steps.push("translate");

            if (steps.length === 0) {
                ElementPlus.ElMessage.info("当前没有可执行的任务步骤，请检查文件状态或配置！");
                return;
            }

            store.isProcessing = true;
            addLog(`🚀 启动全量工作流，执行链路: [ ${steps.join(" ➡️ ")} ]`, "success");

            const ws = new WebSocket(`${WS_BASE}/ws/progress/${store.taskId}`);
            ws.onopen = () => addLog("已连接到全局监视器，等待引擎响应...", "info");
            ws.onerror = () => { addLog("WebSocket 连接异常！", "error"); store.isProcessing = false; };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === "processing") {
                    // 动态更新右侧的垂直步骤条
                    if (data.step === "extract_audio") store.activeStep = 2;
                    else if (data.step === "downloading" || data.step === "transcribing") store.activeStep = 3;
                    else if (data.step === "translating") store.activeStep = 4;

                    // 智能分类并渲染日志
                    if (data.progress) {
                        addLog(`[${data.progress}] ${data.text}`, "progress");
                    } else if (data.message) {
                        if (data.message.includes("❌")) addLog(data.message, "error");
                        else if (data.message.includes("⚠️")) addLog(data.message, "warning");
                        else addLog(data.message, "info");
                    }
                } else if (data.status === "completed") {
                    store.isProcessing = false;
                    // 批量点亮右侧产物下载按钮的状态
                    if (steps.includes("extract")) store.assets.hasAudio = true;
                    if (steps.includes("transcribe")) store.assets.hasOriginalSrt = true;
                    if (steps.includes("translate")) store.assets.hasTranslatedSrt = true;
                    
                    store.activeStep = 5; // 进度条圆满
                    addLog("🎉 全量工作流完美收官！", "success");
                    ElementPlus.ElMessage.success("🎉 全流程顺利完成！请在右侧控制台下载产物。");
                    ws.close();
                } else if (data.status === "error") {
                    store.isProcessing = false;
                    addLog(`❌ 工作流中断: ${data.message}`, "error");
                    ElementPlus.ElMessage.error(`任务失败: ${data.message}`);
                    ws.close();
                }
            };

            try {
                await executeTask(store.taskId, steps, store.config);
            } catch (e) {
                addLog(`请求启动工作流失败: ${e.message}`, "error");
                store.isProcessing = false;
                ws.close();
            }
        };

        return {
            activeTab,
            store,
            runFullPipeline
        };
    }
});

// 注册 Element Plus 所有原生图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

app.use(ElementPlus);
app.mount("#app");