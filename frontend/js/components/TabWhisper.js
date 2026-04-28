const { ref, computed, watch } = Vue;
import { store, addLog, connectTaskMonitor } from '../store.js';
import { executeTask, getAsrModels } from '../api.js';

export default {
    name: 'TabWhisper',
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
                    
            <!-- 本地引擎：基础设置卡片 -->
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5; border-top: none;">
                <template #header>
                    <div class="card-title">⚙️ 基础设置 (Basic)</div>
                </template>
                <el-form :model="store.config" label-width="140px" size="default" label-position="left">
                    <el-form-item>
                        <template #label>
                            <span style="display: inline-flex; align-items: center;">
                                模型大小
                                <el-tooltip content="模型体积越大，识别准确率越高，但需要的显存和处理时间也成倍增加。" placement="top" trigger="click">
                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
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
                                <el-tooltip content="指定原视频语言。自动检测可能在无声前奏中误判，明确指定可提升准确率和速度。" placement="top" trigger="click">
                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
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
            <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                <el-collapse style="border-top: none; border-bottom: none;">
                <el-collapse-item name="1">
                    <template #title>
                        <span class="card-title"><el-icon style="margin-right: 5px;"><Tools /></el-icon> 高级设置 (Advanced Settings)</span>
                    </template>
                    
                    <el-tabs type="border-card" size="small" stretch>
                        <!-- 第一类：文本与上下文 -->
                        <el-tab-pane label="文本/上下文">
                            <el-form :model="store.config" size="small" label-position="top">
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">
                                            Initial Prompt (初始提示词)
                                            <el-tooltip content="提供专有名词、人名或特定语言风格，引导模型正确输出。例如：'这是一个关于 EchoSRT 的教程。'" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip>
                                        </span>
                                    </template>
                                    <el-input type="textarea" v-model="store.config.transcribe_settings.initial_prompt" placeholder="引导词、专有名词、人名等 (空则不使用)"></el-input>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">
                                            Hotwords (热词增强)
                                            <el-tooltip content="提供热词，模型会在遇到模糊发音时优先匹配这些词汇（部分底层引擎可能不支持）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip>
                                        </span>
                                    </template>
                                    <el-input type="textarea" v-model="store.config.transcribe_settings.hotwords" placeholder="希望模型优先识别的词语"></el-input>
                                </el-form-item>
                                <el-row :gutter="20">
                                    <el-col :span="12">
                                        <el-checkbox v-model="store.config.transcribe_settings.condition_on_previous_text">
                                            <span style="display: inline-flex; align-items: center;">参考上一句 (减少幻觉)<el-tooltip content="让模型结合上一句的内容来识别当前句。若视频背景噪音大，关闭此项有时能减少胡言乱语（幻觉）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                        </el-checkbox>
                                    </el-col>
                                    <el-col :span="12">
                                        <el-checkbox v-model="store.config.transcribe_settings.suppress_blank">
                                            <span style="display: inline-flex; align-items: center;">抑制空白输出<el-tooltip content="如果模型预测结果为纯空白，强制其重试生成文字。建议保持开启。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                        </el-checkbox>
                                    </el-col>
                                </el-row>
                                <el-form-item style="margin-top: 15px;">
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">抑制词 ID 数组 (Suppress Tokens)<el-tooltip content="强制禁止模型输出特定的 Token 内部 ID。-1 通常代表抑制某些非发音标记。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input v-model="suppressTokensStr" placeholder="例如: -1"></el-input>
                                </el-form-item>
                            </el-form>
                        </el-tab-pane>

                        <!-- 第二类：解码与搜索 -->
                        <el-tab-pane label="解码/搜索">
                            <el-form :model="store.config" size="small" label-position="right" label-width="120px">
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">Beam Size<el-tooltip content="束搜索候选数量。值越大（如5-10）结果越准但越慢；设为1（贪婪解码）速度最快但可能出错。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.beam_size" :min="1" :max="20"></el-input-number>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">Best Of<el-tooltip content="当非贪婪解码时，保留的最佳候选结果数。一般与 Beam Size 保持一致。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.best_of" :min="1" :max="20"></el-input-number>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">Patience<el-tooltip content="束搜索耐心因子。默认 1.0。调大可探索更多可能路径，改善结果，但增加耗时。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.patience" :step="0.1" :min="0"></el-input-number>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">长度/重复惩罚<el-tooltip content="左侧: 控制输出句子的长短倾向（<1短句，>1长句）。右侧: 惩罚重复词汇，防止陷入死循环复读（>1生效）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.length_penalty" :step="0.1" style="width: 100px; margin-right: 10px;"></el-input-number>
                                    <el-input-number v-model="store.config.transcribe_settings.repetition_penalty" :step="0.1" :min="1.0" style="width: 100px;"></el-input-number>
                                </el-form-item>
                                
                                <el-divider border-style="dashed">
                                    <span style="display: inline-flex; align-items: center;">Temperature 递进数组<el-tooltip content="当识别质量不达标时，模型会按此数组依次提升温度值，增加随机性并重试解码。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                </el-divider>
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
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">VAD 智能静音过滤<el-tooltip content="在识别前剔除无声或纯噪音片段。强烈推荐开启，大幅提升速度并减少环境噪音导致的幻觉！" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-switch v-model="store.config.vad_settings.vad_filter" active-text="强烈推荐开启"></el-switch>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">压缩比阈值<el-tooltip content="当某段文本的压缩比高于此值时，模型会认为自己在重复废话，并触发温度回退重试。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.compression_ratio_threshold" :step="0.1"></el-input-number>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">对数概率阈值<el-tooltip content="如果识别结果的平均置信度（Log Prob）低于此值，将触发温度回退重试。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.log_prob_threshold" :step="0.1"></el-input-number>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">无声判定阈值<el-tooltip content="如果某段音频被判定为完全静音的概率高于此值，将直接跳过不输出文字。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input-number v-model="store.config.transcribe_settings.no_speech_threshold" :step="0.05" :min="0" :max="1"></el-input-number>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">幻觉静音截断阈值<el-tooltip content="遇到长达此设置（秒）的静音时，强行截断当前句子，防止模型产生幻觉。空则默认禁用。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input v-model="nullableFields.hallucination_silence_threshold" placeholder="空则禁用 (Null)"></el-input>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">语言探测阈值<el-tooltip content="在多语言模式下，如果检测到新语言的置信度低于此值，将强制退回前一个语言的设定。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-slider v-model="store.config.transcribe_settings.language_detection_threshold" :min="0" :max="1" :step="0.1" show-input></el-slider>
                                </el-form-item>
                            </el-form>
                        </el-tab-pane>

                        <!-- 第四类：杂项 -->
                        <el-tab-pane label="系统/杂项">
                            <el-form :model="store.config" size="small" label-position="right" label-width="140px">
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">翻译为纯英文<el-tooltip content="无视原视频语言，强制 Whisper 模型直接听译并输出纯英文字幕（单向操作）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-switch v-model="store.config.transcribe_settings.task" active-value="translate" inactive-value="transcribe"></el-switch>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">多语言交替模式<el-tooltip content="允许在同一个音频中自动识别出交替出现的多种不同语言（需要配合常规多语言模型使用）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-switch v-model="store.config.transcribe_settings.multilingual"></el-switch>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">词级时间戳 (Word)<el-tooltip content="精确到每一个单词的发音时间戳，而不是按长句子划分时间。会略微拖慢速度。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-switch v-model="store.config.transcribe_settings.word_timestamps"></el-switch>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">关闭时间戳<el-tooltip content="强制模型不计算和输出时间戳。警告：开启后可能导致生成 SRT 字幕文件失败！" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-switch v-model="store.config.transcribe_settings.without_timestamps" active-color="#f56c6c"></el-switch>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">最大新 Token 数<el-tooltip content="限制每次切片最多生成的文字标记数量。留空表示无限制。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input v-model="nullableFields.max_new_tokens" placeholder="空则无限制 (Null)"></el-input>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">音频切片长度 (秒)<el-tooltip content="强制将音频切分成固定的秒数送入模型。留空则由模型自动判断切分。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input v-model="nullableFields.chunk_length" placeholder="空则自动 (Null)"></el-input>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">模型下载存放目录<el-tooltip content="指定模型文件在本地硬盘的存放路径文件夹。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input v-model="store.config.model_settings.download_root"></el-input>
                                </el-form-item>
                                <el-form-item>
                                    <template #label>
                                        <span style="display: inline-flex; align-items: center;">HF Token (选填)<el-tooltip content="Hugging Face 访问令牌。用于自动下载某些受权限保护的模型资产。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                    </template>
                                    <el-input v-model="store.config.secrets.hf_token" type="password" show-password></el-input>
                                </el-form-item>
                            </el-form>
                        </el-tab-pane>
                    </el-tabs>
                </el-collapse-item>
                </el-collapse>
                        </el-card>
                </el-tab-pane>
                
                <!-- 引擎 2: 云端 API -->
                <el-tab-pane name="api">
                    <template #label>
                        <span style="font-weight: bold; font-size: 14px; display: inline-flex; align-items: center;">
                            ☁️ 云端 API 引擎
                            <el-icon v-if="store.config.transcribe_settings.engine === 'api'" style="margin-left: 5px; color: #67C23A; font-weight: bold;"><Check /></el-icon>
                        </span>
                    </template>
                    
                    <!-- 云端引擎：基础设置卡片 -->
                    <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5; border-top: none;">
                        <template #header>
                            <div class="card-title">⚙️ 基础设置 (Basic)</div>
                        </template>
                        <el-form :model="store.config.online_asr_settings" label-width="140px" label-position="left" size="default">
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
                                    <el-select v-model="store.config.online_asr_settings.model_name" placeholder="请选择或输入模型名称" filterable allow-create default-first-option style="flex: 1;">
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

                    <!-- 云端引擎：高级设置折叠面板 -->
                    <el-card shadow="never" style="margin-bottom: 20px; border: 1px solid #ebeef5;">
                        <el-collapse v-model="activeApiCollapse" style="border-top: none; border-bottom: none;">
                            <el-collapse-item name="1">
                                <template #title>
                                    <span class="card-title"><el-icon style="margin-right: 5px;"><Tools /></el-icon> 高级设置 (Advanced Settings)</span>
                                </template>
                                <el-form :model="store.config.online_asr_settings" label-width="190px" label-position="left" size="small">
                                    <el-form-item>
                                        <template #label>
                                            <span style="display: inline-flex; align-items: center;">
                                                API Base URL
                                                <el-tooltip content="兼容 OpenAI 格式的 API 接口地址。" placement="top" trigger="click">
                                                    <el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon>
                                                </el-tooltip>
                                            </span>
                                        </template>
                                        <el-input v-model="store.config.online_asr_settings.base_url" placeholder="例如: https://api.openai.com/v1"></el-input>
                                    </el-form-item>

                                    <el-form-item label="API Key">
                                        <el-input v-model="store.config.online_asr_settings.api_key" type="password" show-password placeholder="sk-..."></el-input>
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
                                        <el-input type="textarea" v-model="store.config.online_asr_settings.prompt" :rows="3" placeholder="在此输入引导词 (可选)"></el-input>
                                    </el-form-item>
                                    
                                    <el-divider border-style="dashed" style="margin: 15px 0;"></el-divider>

                                    <el-form-item>
                                        <template #label>
                                            <span style="display: inline-flex; align-items: center;">翻译为纯英文<el-tooltip content="无视原视频语言，强制模型直接听译并输出纯英文字幕（单向操作）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                        </template>
                                        <el-switch v-model="store.config.online_asr_settings.translate"></el-switch>
                                    </el-form-item>
                                    <el-form-item>
                                        <template #label>
                                            <span style="display: inline-flex; align-items: center;">说话人识别 (Diarization)<el-tooltip content="自动区分不同的说话人并标注标签（注：仅部分如 Lemonfox 等增强型代理接口支持，OpenAI 官方原生暂不支持）。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                        </template>
                                        <el-switch v-model="store.config.online_asr_settings.speaker_labels"></el-switch>
                                    </el-form-item>
                                    <el-form-item>
                                        <template #label>
                                            <span style="display: inline-flex; align-items: center;">词级时间戳 (Word)<el-tooltip content="精确到每一个单词的发音时间戳，而不是按长句子划分时间。会略微拖慢生成速度。" placement="top" trigger="click"><el-icon style="margin-left: 4px; cursor: pointer; color: #909399;" @click.stop.prevent><QuestionFilled /></el-icon></el-tooltip></span>
                                        </template>
                                        <el-switch v-model="store.config.online_asr_settings.word_timestamps"></el-switch>
                                    </el-form-item>
                                </el-form>
                            </el-collapse-item>
                        </el-collapse>
                    </el-card>
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
                {{ store.config.transcribe_settings.engine === 'api' ? '▶️ 启动云端 API 识别' : '▶️ 启动本地模型识别' }}
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
        const activeApiCollapse = ref([]); // 云端 API 高级面板默认折叠

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

        // 云端 API 引擎模型拉取逻辑
        const isFetchingAsrModels = ref(false);
        const refreshAsrModels = async () => {
            if (!store.config.online_asr_settings.api_key) {
                ElementPlus.ElMessage.warning("请先填写云端 API Key！");
                return;
            }
            isFetchingAsrModels.value = true;
            try {
                const models = await getAsrModels(store.config.online_asr_settings.api_key, store.config.online_asr_settings.base_url);
                store.dicts.asr_models = models;
                ElementPlus.ElMessage.success(`成功拉取 ${models.length} 个可用语音模型！`);
            } catch (e) {
                ElementPlus.ElMessage.error(e.message);
            } finally {
                isFetchingAsrModels.value = false;
            }
        };

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

        return { 
            store, pinnedLanguages, otherLanguages, 
            suppressTokensStr, nullableFields,
            addTemperature, removeTemperature, runTranscribe,
            isFetchingAsrModels, refreshAsrModels, activeApiCollapse
        };
    }
};