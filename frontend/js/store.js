const { reactive } = Vue;

/* 全局状态管理 (轻量级 Pinia 替代) */
export const store = reactive({
    // --- 任务核心状态 ---
    taskId: null,
    activeStep: 0,
    isProcessing: false,
    
    // --- 资产就绪状态 (用于控制各 Tab 的按钮是否可用) ---
    assets: {
        hasVideo: false,
        hasAudio: false,
        hasOriginalSrt: false,
        hasTranslatedSrt: false
    },

    // --- 全局日志系统 ---
    logs: [],

    // --- 全局配置参数 (完整镜像后端的 config.json 结构) ---
    config: {
        secrets: { hf_token: "" },
        model_settings: { model_size: "medium", download_root: "models" },
        transcribe_settings: { 
            engine: "local",
            language: null, 
            task: "transcribe",
            temperature: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            suppress_tokens: [-1]
        },
        vad_settings: { vad_filter: true },
        ffmpeg_settings: { audio_track: "0:a:0", start_time: "", end_time: "" },
        llm_settings: { api_key: "", base_url: "https://api.openai.com/v1", model_name: "Pro/deepseek-ai/DeepSeek-V3.2", target_language: "zh", batch_size: 50, system_prompt: "" },
        online_asr_settings: { provider: "openai", base_url: "https://api.openai.com/v1", api_key: "", model_name: "whisper-1", language: null, prompt: "", translate: false, speaker_labels: false, word_timestamps: false }
    },

    // --- 字典数据 (从后端拉取的下拉框选项) ---
    dicts: {
        languages: [],
        models: [],
        llm_models: [],
        asr_models: []
    }
});

// 统一的日志追加方法
export const addLog = (message, type = "info") => {
    const time = new Date().toLocaleTimeString();
    store.logs.push({ time, message, type });
};