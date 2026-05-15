const { ref, computed } = Vue;
import { store } from '../store.js';
import { getAsrModels } from '../api.js';

export default {
    name: 'WhisperApi',
    template: `
        <div>
            <!-- 云端引擎：基础设置卡片 -->
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5; border-top: none;">
                <template #header>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="card-title"><el-icon style="margin-right:4px;"><Setting /></el-icon>基础设置 (Basic)</span>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 13px; color: #909399;">切换方案:</span>
                            <el-select v-model="store.config.online_asr_settings.active_profile_id" size="small" style="width: 150px;">
                                <el-option v-for="p in store.config.online_asr_settings.profiles" :key="p.id" :label="p.name" :value="p.id"></el-option>
                            </el-select>
                            <el-dropdown trigger="click" @command="handleProfileCommand">
                                <el-button type="info" size="small" plain icon="Operation"></el-button>
                                <template #dropdown>
                                    <el-dropdown-menu>
                                        <el-dropdown-item command="add" icon="Plus">新增方案</el-dropdown-item>
                                        <el-dropdown-item command="rename" icon="Edit">重命名当前方案</el-dropdown-item>
                                        <el-dropdown-item command="delete" icon="Delete" divided style="color: #F56C6C;">删除当前方案</el-dropdown-item>
                                    </el-dropdown-menu>
                                </template>
                            </el-dropdown>
                        </div>
                    </div>
                </template>
                <el-form :model="activeProfile" label-width="140px" label-position="left" size="default">
                    <el-form-item>
                        <template #label>
                            <span style="display: inline-flex; align-items: center;">
                                Model Name
                                <el-tooltip content="指定调用的云端识别模型名称。通常填写 'whisper-1'，你也可以点击右侧按钮直接从服务商处拉取可用模型列表。" placement="top" trigger="click">
                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                </el-tooltip>
                            </span>
                        </template>
                        <div style="display: flex; gap: 10px; width: 100%;">
                            <el-select v-model="activeProfile.model_name" placeholder="请选择或输入模型名称" filterable allow-create default-first-option style="flex: 1;">
                                <el-option v-for="model in store.dicts.asr_models" :key="model" :label="model" :value="model"></el-option>
                            </el-select>
                            <el-button type="primary" plain @click="refreshAsrModels" :loading="isFetchingAsrModels" title="从 API 供应商拉取可用模型">
                                <el-icon><Refresh /></el-icon>
                            </el-button>
                        </div>
                    </el-form-item>

                    <el-form-item>
                        <template #label>
                            <span style="display: inline-flex; align-items: center;">
                                识别语言
                                <el-tooltip content="指定原视频语言。自动检测可能在无声前奏中误判，明确指定可提升准确率和速度。" placement="top" trigger="click">
                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                </el-tooltip>
                            </span>
                        </template>
                        <el-select v-model="store.config.online_asr_settings.language" placeholder="自动检测 (Auto)" clearable filterable style="width: 100%;">
                            <el-option-group label="常用语言">
                                <el-option v-for="lang in pinnedLanguages" :key="lang.code" :label="\`\${lang.name} (\${lang.code})\`" :value="lang.code"></el-option>
                            </el-option-group>
                            <el-option-group label="其他语言 (A-Z)">
                                <el-option v-for="lang in otherLanguages" :key="lang.code" :label="\`\${lang.name} (\${lang.code})\`" :value="lang.code"></el-option>
                            </el-option-group>
                        </el-select>
                    </el-form-item>
                </el-form>
            </el-card>

            <!-- 云端引擎：高级设置折叠面板 -->
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <el-collapse v-model="activeApiCollapse" style="border-top: none; border-bottom: none;">
                    <el-collapse-item name="1">
                        <template #title>
                            <span class="card-title"><el-icon style="margin-right: 5px;"><Tools /></el-icon> 高级设置 (Advanced Settings)</span>
                        </template>
                        <el-form :model="activeProfile" label-width="190px" label-position="left" size="small">
                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        API Base URL
                                        <el-tooltip content="兼容 OpenAI 格式的 API 接口地址。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-input v-model="activeProfile.base_url" placeholder="例如: https://api.openai.com/v1"></el-input>
                            </el-form-item>

                            <el-form-item label="API Key">
                                <el-input v-model="activeProfile.api_key" type="password" show-password placeholder="sk-..."></el-input>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        API 访问代理
                                        <el-tooltip content="调用云端语音识别 API 时，通过配置的全局网络代理进行访问。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-switch v-model="store.config.online_asr_settings.use_network_proxy" :disabled="!store.config.system_settings.enable_global_proxy"></el-switch>
                            </el-form-item>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        Prompt 引导词
                                        <el-tooltip content="提供专有名词、人名或特定语言风格，引导模型正确输出。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <el-input type="textarea" v-model="activeProfile.prompt" :rows="3" placeholder="在此输入引导词 (可选)"></el-input>
                            </el-form-item>
                            
                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">
                                        网络超时设置
                                        <el-tooltip content="左侧: 连接超时(秒)；右侧: 等待云端响应的最长超时(秒)。音频较长时请调大右侧数值以防止假死报错。" placement="top" trigger="click">
                                            <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                        </el-tooltip>
                                    </span>
                                </template>
                                <div style="display: flex; gap: 10px; align-items: center;">
                                    <el-input-number v-model="activeProfile.timeout_settings.connect" :min="3" :max="60" :step="1" style="width: 100px;"></el-input-number>
                                    <span>/</span>
                                    <el-input-number v-model="activeProfile.timeout_settings.read" :min="30" :max="3600" :step="30" style="width: 120px;"></el-input-number>
                                    <span style="color: #909399; font-size: 13px;">秒</span>
                                </div>
                            </el-form-item>

                            <el-divider border-style="dashed" style="margin: 15px 0;"></el-divider>

                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">翻译为纯英文<el-tooltip content="无视原视频语言，强制模型直接听译并输出纯英文字幕（单向操作）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                </template>
                                <el-switch v-model="activeProfile.translate"></el-switch>
                            </el-form-item>
                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">说话人识别 (Diarization)<el-tooltip content="自动区分不同的说话人并标注标签（注：仅部分如 Lemonfox 等增强型代理接口支持，OpenAI 官方原生暂不支持）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                </template>
                                <el-switch v-model="activeProfile.speaker_labels"></el-switch>
                            </el-form-item>
                            <el-form-item>
                                <template #label>
                                    <span style="display: inline-flex; align-items: center;">词级时间戳 (Word)<el-tooltip content="精确到每一个单词的发音时间戳，而不是按长句子划分时间。会略微拖慢生成速度。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                </template>
                                <el-switch v-model="activeProfile.word_timestamps"></el-switch>
                            </el-form-item>
                        </el-form>
                    </el-collapse-item>
                </el-collapse>
            </el-card>
        </div>
    `,
    setup() {
        const pinnedCodes = ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'ru'];
        const pinnedLanguages = computed(() => store.dicts.languages.filter(l => pinnedCodes.includes(l.code)));
        const otherLanguages = computed(() => store.dicts.languages.filter(l => !pinnedCodes.includes(l.code)));

        const activeApiCollapse = ref([]);
        const isFetchingAsrModels = ref(false);

        const activeProfile = computed(() => {
            const id = store.config.online_asr_settings.active_profile_id;
            return store.config.online_asr_settings.profiles.find(p => p.id === id) || store.config.online_asr_settings.profiles[0];
        });

        // 方案管理逻辑
        const handleProfileCommand = async (command) => {
            const settings = store.config.online_asr_settings;
            if (command === 'add') {
                const newId = 'profile_' + Date.now();
                const newProfile = JSON.parse(JSON.stringify(activeProfile.value));
                newProfile.id = newId;
                newProfile.name = '新方案_' + newId.substring(newId.length - 4);
                settings.profiles.push(newProfile);
                settings.active_profile_id = newId;
                ElementPlus.ElMessage.success("已创建并切换到新方案。");
            } else if (command === 'rename') {
                try {
                    const { value } = await ElementPlus.ElMessageBox.prompt('请输入方案名称', '重命名方案', {
                        inputValue: activeProfile.value.name,
                        confirmButtonText: '确定',
                        cancelButtonText: '取消'
                    });
                    if (value) activeProfile.value.name = value;
                } catch (e) {}
            } else if (command === 'delete') {
                if (settings.profiles.length <= 1) {
                    ElementPlus.ElMessage.warning("至少需要保留一个方案！");
                    return;
                }
                try {
                    await ElementPlus.ElMessageBox.confirm('确定要删除当前方案吗？', '警告', { type: 'warning' });
                    const idx = settings.profiles.findIndex(p => p.id === settings.active_profile_id);
                    settings.profiles.splice(idx, 1);
                    settings.active_profile_id = settings.profiles[0].id;
                    ElementPlus.ElMessage.success("方案已删除");
                } catch (e) {}
            }
        };

        const refreshAsrModels = async () => {
            if (!activeProfile.value.api_key) {
                ElementPlus.ElMessage.warning("请先填写云端 API Key！");
                return;
            }
            isFetchingAsrModels.value = true;
            try {
                const models = await getAsrModels(activeProfile.value.api_key, activeProfile.value.base_url);
                store.dicts.asr_models = models;
                ElementPlus.ElMessage.success(`成功拉取 ${models.length} 个可用语音模型！`);
            } catch (e) {
                ElementPlus.ElMessage.error(e.message);
            } finally {
                isFetchingAsrModels.value = false;
            }
        };

        return { 
            store, pinnedLanguages, otherLanguages, activeProfile, handleProfileCommand,
            activeApiCollapse, isFetchingAsrModels, refreshAsrModels 
        };
    }
};