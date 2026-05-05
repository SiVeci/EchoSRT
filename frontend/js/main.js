const { createApp, ref, onMounted, watch } = Vue;

// 引入组件
import TabWorkspace from './components/TabWorkspace.js';
import TabAudio from './components/TabAudio.js';
import TabWhisper from './components/TabWhisper.js';
import TabLLM from './components/TabLLM.js';
import GlobalConsole from './components/GlobalConsole.js';
import GlobalSettings from './components/GlobalSettings.js';

// 引入全局状态与网络请求
import { store, addLog, connectTaskMonitor } from './store.js';
import { getConfig, getLanguages, getModels, executeTask, getTaskStatus, getTasks, getPipelineStatus, getSystemInfo } from './api.js';

const app = createApp({
    components: {
        TabWorkspace,
        TabAudio,
        TabWhisper,
        'tab-llm': TabLLM,
        GlobalConsole,
        GlobalSettings
    },
    setup() {
        // 控制当前激活的 Tab 页面，默认停留在第一页
        const activeTab = ref('workspace');

        // 监听运行状态，同步到 localStorage
        watch(() => store.isProcessing, (isProcessing) => {
            if (isProcessing && store.taskId) {
                localStorage.setItem("echo_srt_active_task", store.taskId);
            } else {
                localStorage.removeItem("echo_srt_active_task");
            }
        });

        // 页面加载时，拉取后端配置与字典数据
        onMounted(async () => {
            addLog("正在初始化应用，拉取后端配置...", "info");
            try {
                const [configData, langData, modelData, sysInfo] = await Promise.all([
                    getConfig(),
                    getLanguages(),
                    getModels(),
                    getSystemInfo()
                ]);
                
                // 将后端拉取到的配置镜像同步到全局 Store
                if(configData.system_settings) Object.assign(store.config.system_settings, configData.system_settings);
                if(configData.secrets) Object.assign(store.config.secrets, configData.secrets);
                if(configData.model_settings) Object.assign(store.config.model_settings, configData.model_settings);
                if(configData.transcribe_settings) Object.assign(store.config.transcribe_settings, configData.transcribe_settings);
                if(configData.vad_settings) Object.assign(store.config.vad_settings, configData.vad_settings);
                if(configData.ffmpeg_settings) Object.assign(store.config.ffmpeg_settings, configData.ffmpeg_settings);
                if(configData.llm_settings) Object.assign(store.config.llm_settings, configData.llm_settings);
                if(configData.online_asr_settings) Object.assign(store.config.online_asr_settings, configData.online_asr_settings);

                // 加载字典
                store.dicts.languages = langData;
                store.dicts.models = modelData;
                store.systemInfo = sysInfo;

                addLog("✅ 基础配置加载完成，就绪！", "success");
                
                // 探测并恢复意外中断的任务状态
                await restoreActiveTask();
            } catch (e) {
                addLog(`❌ 初始化失败: ${e.message}`, "error");
                ElementPlus.ElMessage.error("无法连接到后端服务，请检查 app.py 是否启动。");
            }
            
            // [新增] 启动全局流水线状态轮询
            setInterval(async () => {
                try {
                    const status = await getPipelineStatus();
                    store.pipelineStatus = status;
                    
                    // 自动根据流水线状态，动态更新右侧进度条和焦点菊花图
                    if (store.taskId && status[store.taskId]) {
                        const state = status[store.taskId].current_step;
                        if (state === 'pending_extract' || state === 'extracting') store.activeStep = 2;
                        else if (state === 'pending_transcribe' || state === 'transcribing') store.activeStep = 3;
                        else if (state === 'pending_translate' || state === 'translating') store.activeStep = 4;
                        else if (state === 'completed') {
                            if (store.assets.hasTranslatedSrt) store.activeStep = 5;
                            else if (store.assets.hasOriginalSrt) store.activeStep = 4;
                            else if (store.assets.hasAudio) store.activeStep = 3;
                            else if (store.assets.hasVideo) store.activeStep = 2;
                            else store.activeStep = 1;
                        }
                        
                        store.isProcessing = (state !== 'completed' && state !== 'error');
                    }
                } catch (e) {}
            }, 2000);
        });

        const restoreActiveTask = async () => {
            const activeTaskId = localStorage.getItem("echo_srt_active_task");
            if (!activeTaskId) return;
            
            addLog(`🔄 发现未完成的任务记录，正在探测后端状态...`, "warning");
            try {
                // 1. 恢复任务面板的资产标识
                const tasks = await getTasks();
                const taskMeta = tasks.find(t => t.task_id === activeTaskId);
                if (taskMeta) {
                    store.taskId = activeTaskId;
                    store.assets.hasVideo = taskMeta.has_video;
                    store.assets.hasAudio = taskMeta.has_audio;
                    store.assets.hasOriginalSrt = taskMeta.has_original_srt;
                    store.assets.hasTranslatedSrt = taskMeta.has_translated_srt;
                }

                // 2. 问询后端最新切片
                const statusData = await getTaskStatus(activeTaskId);
                if (statusData.status === "processing") {
                    store.isProcessing = true;
                    addLog(`⚡ 后端任务仍在运行，正在重新接管数据流...`, "success");
                    connectTaskMonitor(activeTaskId, null, null);
                } else {
                    localStorage.removeItem("echo_srt_active_task");
                }
            } catch (e) {
                console.error("恢复任务状态失败", e);
                localStorage.removeItem("echo_srt_active_task");
            }
        };

        // 智能启动工作流
        const runPipeline = async (includeTranslation = true) => {
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
            
            // 3. 如果是全量工作流，检查并加入翻译步骤
            if (includeTranslation) {
                if (!store.config.llm_settings.api_key) {
                    ElementPlus.ElMessage.warning("请前往【LLM 翻译】页填写 API Key！留空无法执行全量工作流。");
                    return;
                }
                steps.push("translate");
            }

            if (steps.length === 0) {
                ElementPlus.ElMessage.info("当前没有可执行的任务步骤，请检查文件状态或配置！");
                return;
            }

            store.isProcessing = true;
            addLog(`🚀 启动工作流，执行链路: [ ${steps.join(" ➡️ ")} ]`, "success");

            connectTaskMonitor(
                store.taskId,
                () => {
                    // 批量点亮右侧产物下载按钮的状态
                    if (steps.includes("extract")) store.assets.hasAudio = true;
                    if (steps.includes("transcribe")) store.assets.hasOriginalSrt = true;
                    if (steps.includes("translate")) store.assets.hasTranslatedSrt = true;
                    
                    // 动态更新完成后的进度条指示
                    if (includeTranslation || store.assets.hasTranslatedSrt) {
                        store.activeStep = 5; // 全量进度条圆满
                        addLog("🎉 全量工作流完美收官！", "success");
                    } else {
                        store.activeStep = 4; // 停留在翻译待命状态
                        addLog("🎉 提取工作流执行完毕！原声字幕已生成。", "success");
                    }
                    
                    ElementPlus.ElMessage.success("🎉 流程顺利完成！请在右侧控制台下载产物。");
                },
                (error) => {
                    ElementPlus.ElMessage.error(`工作流异常: ${error.message}`);
                }
            );

            try {
                await executeTask(store.taskId, steps, store.config);
            } catch (e) {
                addLog(`请求启动工作流失败: ${e.message}`, "error");
                store.isProcessing = false;
            }
        };

        return {
            activeTab,
            store,
            runPipeline
        };
    }
});

// 注册 Element Plus 所有原生图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
}

app.use(ElementPlus);
app.mount("#app");