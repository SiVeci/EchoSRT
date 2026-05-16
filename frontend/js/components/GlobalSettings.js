const { ref, watch, computed } = Vue;
import { store } from '../store.js';
import { getConfig, updateConfig, restoreConfig, testProxy, getLibraryPaths, addLibraryPath, deleteLibraryPath } from '../api.js';

export default {
    name: 'GlobalSettings',
    template: `
        <el-dialog v-model="store.showGlobalSettings" width="650px" destroy-on-close>
            <template #header>
                <el-icon style="margin-right:4px;"><Setting /></el-icon> 全局设置与配置管理
            </template>
            <div style="margin-bottom: 20px;">
                <div style="font-weight: bold; color: #303133; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                    <el-icon style="font-size: 18px; color: #409EFF;"><Position /></el-icon> 全局网络代理
                </div>
                <div style="color: #909399; font-size: 13px; margin-bottom: 15px;">
                    配置后可加速大模型下载及云端 API 请求。开启开关并填写完整后自动生效。
                </div>
                <div style="display: flex; align-items: center; gap: 15px; background: #f5f7fa; padding: 15px; border-radius: 4px;">
                    <el-switch v-model="proxyEnabled" @change="handleSwitchChange" active-text="开启" inactive-text="关闭"></el-switch>
                    
                    <div style="display: flex; align-items: center; gap: 8px;" :style="{ opacity: proxyEnabled ? 1 : 0.5, pointerEvents: proxyEnabled ? 'auto' : 'none', filter: proxyEnabled ? 'none' : 'grayscale(100%)' }">
                        <el-select v-model="proxyProtocol" @change="handleInputChange" style="width: 105px;">
                            <el-option label="HTTP" value="http://"></el-option>
                            <el-option label="SOCKS5" value="socks5://"></el-option>
                        </el-select>
                        <el-input v-model="proxyHost" @blur="handleInputChange" @keyup.enter="handleInputChange" placeholder="IP/域名 (如 127.0.0.1)" style="width: 135px;"></el-input>
                        <span style="font-weight: bold; color: #909399;">:</span>
                        <el-input-number v-model="proxyPort" @change="handleInputChange" @blur="handleInputChange" @keyup.enter="handleInputChange" :min="1" :max="65535" :controls="false" placeholder="端口" style="width: 70px;"></el-input-number>
                        <el-button type="info" plain :loading="isTestingProxy" :disabled="!proxyEnabled || !proxyHost || !proxyPort" @click="handleTestProxy" style="margin-left: 5px;">
                            <el-icon style="margin-right: 4px;"><Link /></el-icon> 测试
                        </el-button>
                    </div>
                </div>
            </div>

            <el-divider border-style="dashed"></el-divider>

            <div style="margin-bottom: 20px;">
                <div style="font-weight: bold; color: #303133; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                    <el-icon style="font-size: 18px; color: #F56C6C;"><Cpu /></el-icon> GPU 显存调度管理
                </div>
                <div style="color: #909399; font-size: 13px; margin-bottom: 15px;">
                    针对具有 12GB 或更低显存的用户，开启此项可防止本地识别与本地翻译同时加载导致的溢出崩溃。
                </div>
                <div style="display: flex; align-items: center; gap: 15px; background: #fdf6f6; padding: 15px; border-radius: 4px; border: 1px solid #fde2e2;">
                    <el-switch v-model="store.config.system_settings.vram_mutual_exclusion" active-text="开启显存互斥排队" @change="handleSaveConfig"></el-switch>
                    <div style="font-size: 12px; color: #F56C6C; flex: 1; line-height: 1.3;">
                        开启后，本地识别与本地翻译将互不抢占显存；24GB 显存用户可关闭此项以提速。
                    </div>
                </div>
            </div>

            <el-divider border-style="dashed"></el-divider>

            <div style="margin-bottom: 20px;">
                <div style="font-weight: bold; color: #303133; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                    <el-icon style="font-size: 18px; color: #E6A23C;"><FolderOpened /></el-icon> 媒体库扫描管理
                </div>
                <div style="color: #909399; font-size: 13px; margin-bottom: 15px;">
                    添加本地或 NAS 挂载目录，自动扫描视频文件。Docker 用户请确保已将目录挂载至容器内。
                </div>
                
                <div style="margin-bottom: 15px;">
                    <el-input v-model="newLibraryPath" placeholder="请输入绝对路径 (如 D:\\Movies 或 /mnt/media)" @keyup.enter="handleAddPath">
                        <template #append>
                            <el-button @click="handleAddPath" icon="Plus">添加路径</el-button>
                        </template>
                    </el-input>
                </div>

                <div v-if="libraryPaths.length > 0" style="border: 1px solid #ebeef5; border-radius: 4px; padding: 10px; background: #fafafa;">
                    <div v-for="path in libraryPaths" :key="path" style="display: flex; justify-content: space-between; align-items: center; padding: 5px 0; border-bottom: 1px solid #eee;">
                        <span style="font-size: 13px; color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 480px;">{{ path }}</span>
                        <el-button type="danger" link icon="Delete" @click="handleDeletePath(path)"></el-button>
                    </div>
                </div>
                <el-empty v-else description="暂未配置扫描路径" :image-size="40" style="padding: 20px 0;"></el-empty>
            </div>

            <el-divider border-style="dashed"></el-divider>

            <div style="margin-top: 20px;">
                <div style="font-weight: bold; color: #303133; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                    <el-icon style="font-size: 18px; color: #67C23A;"><Document /></el-icon> 配置管理
                </div>
                <div style="color: #909399; font-size: 13px; margin-bottom: 15px;">
                    手动保存当前面板上的所有参数设置；或当设置混乱时，将其恢复为系统的初始默认状态。
                </div>
                <div style="display: flex; gap: 15px;">
                    <el-button type="primary" plain icon="DocumentChecked" @click="handleSaveConfig">手动保存当前配置</el-button>
                    <el-button type="danger" plain icon="RefreshLeft" @click="handleRestoreConfig">恢复系统默认配置</el-button>
                </div>
            </div>

            <template #footer>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #c0c4cc; font-size: 13px;">EchoSRT {{ store.appVersion }}</span>
                    <el-button @click="store.showGlobalSettings = false">关 闭</el-button>
                </div>
            </template>
        </el-dialog>
    `,
    setup() {
        const proxyEnabled = ref(false);
        const proxyProtocol = ref("http://");
        const proxyHost = ref("");
        const proxyPort = ref(null);
        const isTestingProxy = ref(false);

        watch(() => store.config.system_settings, (newSettings) => {
            if (newSettings) {
                if (proxyEnabled.value !== newSettings.enable_global_proxy) {
                    proxyEnabled.value = !!newSettings.enable_global_proxy;
                }
                const proxyStr = newSettings.network_proxy || "";
                const currentUIStr = `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}`;
                const currentUIStrSocks5h = `${proxyProtocol.value.replace('socks5://', 'socks5h://')}${proxyHost.value}:${proxyPort.value}`;
                
                if (proxyStr && proxyStr !== currentUIStr && proxyStr !== currentUIStrSocks5h) {
                    let protocol = "http://", rest = proxyStr;
                    if (proxyStr.startsWith("socks5://") || proxyStr.startsWith("socks5h://")) {
                        protocol = "socks5://"; rest = proxyStr.replace(/^socks5h?:\/\//, "");
                    } else if (proxyStr.startsWith("http://") || proxyStr.startsWith("https://")) {
                        protocol = proxyStr.startsWith("https://") ? "https://" : "http://";
                        rest = proxyStr.replace(/^https?:\/\//, "");
                    }
                    proxyProtocol.value = protocol;
                    const lastColonIdx = rest.lastIndexOf(":");
                    if (lastColonIdx !== -1) {
                        proxyHost.value = rest.substring(0, lastColonIdx);
                        proxyPort.value = parseInt(rest.substring(lastColonIdx + 1)) || null;
                    } else { proxyHost.value = rest; proxyPort.value = null; }
                }
            }
        }, { deep: true, immediate: true });

        const handleSwitchChange = async () => {
            store.config.system_settings.enable_global_proxy = proxyEnabled.value;
            if (!proxyEnabled.value) {
                store.config.llm_settings.use_network_proxy = false;
                store.config.online_asr_settings.use_network_proxy = false;
                store.config.system_settings.use_proxy_for_model_download = false;
            }
            if (proxyHost.value && proxyPort.value) {
                store.config.system_settings.network_proxy = `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}`;
            }
            try { 
                await updateConfig(store.config); 
                if (proxyEnabled.value) ElementPlus.ElMessage.success("全局网络代理总闸已通电，分流开关已激活。");
                else ElementPlus.ElMessage.success("全局代理总闸已断电，所有模块强制直连。");
            } catch (e) {}
        };

        const handleInputChange = async () => {
            if (proxyHost.value && proxyPort.value) {
                store.config.system_settings.network_proxy = `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}`;
                try { await updateConfig(store.config); } catch (e) {}
            }
        };

        const handleSaveConfig = async () => {
            try { await updateConfig(store.config); ElementPlus.ElMessage.success("所有配置已成功保存！"); }
            catch(e) { ElementPlus.ElMessage.error("保存配置失败: " + e.message); }
        };

        const handleTestProxy = async () => {
            if (!proxyHost.value || !proxyPort.value) return;
            const fullProxy = `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}`;
            isTestingProxy.value = true;
            try {
                await testProxy(fullProxy);
                ElementPlus.ElMessage.success("代理服务器连接成功！");
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || "代理服务器连接失败，请检查配置。");
            } finally {
                isTestingProxy.value = false;
            }
        };

        const handleRestoreConfig = async () => {
            try {
                await ElementPlus.ElMessageBox.confirm("此操作将覆盖当前所有的设置，并恢复为系统默认状态，是否继续？", "高危警告", { confirmButtonText: '确定恢复', cancelButtonText: '取消', type: 'warning' });
                const loading = ElementPlus.ElLoading.service({ lock: true, text: '正在恢复默认配置...' });
                try {
                    const newConfig = await restoreConfig();
                    Object.keys(newConfig).forEach(key => {
                        if (store.config[key] && typeof store.config[key] === 'object') Object.assign(store.config[key], newConfig[key]);
                        else store.config[key] = newConfig[key];
                    });
                    ElementPlus.ElMessage.success("已恢复系统默认配置！");
                } finally { loading.close(); }
            } catch (e) { if (e !== 'cancel') ElementPlus.ElMessage.error("恢复配置失败: " + (e.message || e)); }
        };

        // --- 媒体库扫描管理逻辑 ---
        const libraryPaths = computed(() => store.config.library?.library_paths || []);
        const newLibraryPath = ref("");

        const handleAddPath = async () => {
            const path = newLibraryPath.value.trim();
            if (!path) return;
            try {
                const res = await addLibraryPath(path);
                // 同步更新全局 store，确保后续“保存配置”时数据一致
                if (store.config.library) {
                    store.config.library.library_paths = res.paths;
                }
                newLibraryPath.value = "";
                ElementPlus.ElMessage.success("扫描路径添加成功");
            } catch (e) {
                ElementPlus.ElMessage.error(e.message || "添加失败");
            }
        };

        const handleDeletePath = async (path) => {
            try {
                const res = await deleteLibraryPath(path);
                // 同步更新全局 store
                if (store.config.library) {
                    store.config.library.library_paths = res.paths;
                }
                ElementPlus.ElMessage.success("扫描路径已移除");
            } catch (e) {
                ElementPlus.ElMessage.error("移除失败");
            }
        };

        return { 
            store, proxyEnabled, proxyProtocol, proxyHost, proxyPort, isTestingProxy, 
            handleSwitchChange, handleInputChange, handleSaveConfig, handleRestoreConfig, handleTestProxy,
            libraryPaths, newLibraryPath, handleAddPath, handleDeletePath
        };
        }
        };