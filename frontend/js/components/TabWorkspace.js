const { ref } = Vue;
import { store, addLog } from '../store.js';
import { uploadAsset } from '../api.js';

export default {
    name: 'TabWorkspace',
    template: `
        <div class="workspace-container">
            <div style="margin-bottom: 20px; color: #606266; font-size: 14px;">
                请将需要处理的视频拖拽至下方区域。这将会为你初始化一个全新的工作流任务。
            </div>
            
            <!-- 拖拽上传区 -->
            <el-upload
                class="upload-demo"
                drag
                action="#"
                :auto-upload="true"
                :http-request="handleUpload"
                :show-file-list="false"
                accept="video/*,audio/*"
                :disabled="isUploading"
            >
                <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                <div class="el-upload__text">
                    将音/视频文件拖到此处，或 <em>点击上传</em>
                </div>
            </el-upload>
            
            <!-- 上传进度条 -->
            <div v-if="isUploading" style="margin-top: 20px;">
                <el-progress :percentage="uploadPercent" :stroke-width="18" text-inside></el-progress>
                <div style="text-align: center; margin-top: 8px; font-size: 13px; color: #909399;">
                    正在上传并初始化任务，请勿刷新页面...
                </div>
            </div>

            <!-- 成功提示展示区 -->
            <div v-if="currentFileName && !isUploading" style="margin-top: 20px; padding: 15px; background-color: #f0f9eb; border-radius: 4px; color: #67C23A; text-align: center; border: 1px solid #e1f3d8;">
                <el-icon style="vertical-align: middle; margin-right: 5px; font-size: 18px;"><CircleCheck /></el-icon>
                源文件 <strong>{{ currentFileName }}</strong> 已就绪
            </div>
        </div>
    `,
    setup() {
        const isUploading = ref(false);
        const uploadPercent = ref(0);
        const currentFileName = ref("");

        const handleUpload = async (options) => {
            addLog(`开始上传源文件: ${options.file.name}...`, "info");
            isUploading.value = true;
            uploadPercent.value = 0;
            
            try {
                // 传入 null 作为 taskId，让后端生成全新任务。资产类型默认按 video 处理（后端会根据后缀保存）
                const res = await uploadAsset(options.file, 'video', null, (percent) => {
                    uploadPercent.value = percent;
                });
                
                // --- 核心：更新全局状态，点亮其他组件 ---
                store.taskId = res.task_id;
                store.activeStep = 1; // 进度条跳到第2步：资产就绪
                
                // 重置并点亮资产状态
                store.assets = {
                    hasVideo: true,
                    hasAudio: false,
                    hasOriginalSrt: false,
                    hasTranslatedSrt: false
                };
                
                currentFileName.value = options.file.name;
                addLog(`✅ 上传成功！任务分配 ID: ${res.task_id}`, "success");
                ElementPlus.ElMessage.success("上传成功，任务工作区已就绪！");
                
            } catch (e) {
                addLog(`❌ 上传失败: ${e.message}`, "error");
                ElementPlus.ElMessage.error(`上传失败: ${e.message}`);
            } finally {
                isUploading.value = false;
            }
        };

        return {
            isUploading,
            uploadPercent,
            currentFileName,
            handleUpload,
            store
        };
    }
};