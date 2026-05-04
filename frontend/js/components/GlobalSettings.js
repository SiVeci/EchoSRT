const { ref, watch } = Vue;
import { store } from '../store.js';
import { updateConfig, restoreConfig, testProxy } from '../api.js';

export default {
    name: 'GlobalSettings',
    template: `
        <el-dialog v-model="store.showGlobalSettings" title="⚙️ 全局设置与配置管理" width="650px" destroy-on-close>
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
                        <el-input v-model="proxyHost" @blur="handleInputChange" @keyup.enter="handleInputChange" placeholder="IP/域名 (如 127.0.0.1)" style="width: 180px;"></el-input>
                        <span style="font-weight: bold; color: #909399;">:</span>
                        <el-input-number v-model="proxyPort" @change="handleInputChange" @blur="handleInputChange" @keyup.enter="handleInputChange" :min="1" :max="65535" :controls="false" placeholder="端口" style="width: 75px;"></el-input-number>
                        <el-button type="info" plain :loading="isTestingProxy" :disabled="!proxyEnabled || !proxyHost || !proxyPort" @click="handleTestProxy" style="margin-left: 5px;">
                            <el-icon style="margin-right: 4px;"><Link /></el-icon> 测试连通性
                        </el-button>
                    </div>
                </div>
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
                if (proxyEnabled.value) ElementPlus.ElMessage.success("⚡ 全局网络代理总闸已通电！分流开关已激活。");
                else ElementPlus.ElMessage.success("🔌 全局代理总闸已断电！所有模块强制直连。");
            } catch (e) {}
        };

        const handleInputChange = async () => {
            if (proxyHost.value && proxyPort.value) {
                store.config.system_settings.network_proxy = `${proxyProtocol.value}${proxyHost.value}:${proxyPort.value}`;
                try { await updateConfig(store.config); } catch (e) {}
            }
        };

        const handleSaveConfig = async () => {
            try { await updateConfig(store.config); ElementPlus.ElMessage.success("🎉 所有配置已成功保存！"); } 
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
                    ElementPlus.ElMessage.success("✅ 已恢复系统默认配置！");
                } finally { loading.close(); }
            } catch (e) { if (e !== 'cancel') ElementPlus.ElMessage.error("恢复配置失败: " + (e.message || e)); }
        };

        return { store, proxyEnabled, proxyProtocol, proxyHost, proxyPort, isTestingProxy, handleSwitchChange, handleInputChange, handleSaveConfig, handleRestoreConfig, handleTestProxy };
    }
};