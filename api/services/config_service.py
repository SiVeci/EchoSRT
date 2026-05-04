import os
import json
import shutil
import urllib.request
import urllib.error
import socket
import urllib.parse
from fastapi import HTTPException
from faster_whisper import available_models

SUPPORTED_LANGUAGES = {
    "af": "afrikaans", "am": "amharic", "ar": "arabic", "as": "assamese", "az": "azerbaijani", 
    "ba": "bashkir", "be": "belarusian", "bg": "bulgarian", "bn": "bengali", "bo": "tibetan", 
    "br": "breton", "bs": "bosnian", "ca": "catalan", "cs": "czech", "cy": "welsh", 
    "da": "danish", "de": "german", "el": "greek", "en": "english", "es": "spanish", 
    "et": "estonian", "eu": "basque", "fa": "persian", "fi": "finnish", "fo": "faroese", 
    "fr": "french", "gl": "galician", "gu": "gujarati", "ha": "hausa", "haw": "hawaiian", 
    "he": "hebrew", "hi": "hindi", "hr": "croatian", "ht": "haitian creole", "hu": "hungarian", 
    "hy": "armenian", "id": "indonesian", "is": "icelandic", "it": "italian", "ja": "japanese", 
    "jw": "javanese", "ka": "georgian", "kk": "kazakh", "km": "khmer", "kn": "kannada", 
    "ko": "korean", "la": "latin", "lb": "luxembourgish", "ln": "lingala", "lo": "lao", 
    "lt": "lithuanian", "lv": "latvian", "mg": "malagasy", "mi": "maori", "mk": "macedonian", 
    "ml": "malayalam", "mn": "mongolian", "mr": "marathi", "ms": "malay", "mt": "maltese", 
    "my": "myanmar", "ne": "nepali", "nl": "dutch", "nn": "nynorsk", "no": "norwegian", 
    "oc": "occitan", "pa": "punjabi", "pl": "polish", "ps": "pashto", "pt": "portuguese", 
    "ro": "romanian", "ru": "russian", "sa": "sanskrit", "sd": "sindhi", "si": "sinhala", 
    "sk": "slovak", "sl": "slovenian", "sn": "shona", "so": "somali", "sq": "albanian", 
    "sr": "serbian", "su": "sundanese", "sv": "swedish", "sw": "swahili", "ta": "tamil", 
    "te": "telugu", "tg": "tajik", "th": "thai", "tk": "turkmen", "tl": "tagalog", 
    "tr": "turkish", "tt": "tatar", "uk": "ukrainian", "ur": "urdu", "uz": "uzbek", 
    "vi": "vietnamese", "yi": "yiddish", "yo": "yoruba", "zh": "chinese"
}

CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.example.json")

def set_global_proxy(system_settings: dict):
    proxy_url = system_settings.get("network_proxy", "").strip()
    enable_global = system_settings.get("enable_global_proxy", False)
    
    if enable_global and proxy_url:
        proxy = proxy_url
        if proxy.startswith("socks5://"): proxy = proxy.replace("socks5://", "socks5h://", 1)
        elif not proxy.startswith("http://") and not proxy.startswith("https://") and not proxy.startswith("socks5h://"):
            proxy = f"http://{proxy}"
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]: os.environ[k] = proxy
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
        print(f"[*] 已动态应用全局网络代理: {proxy}")
    else:
        for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY"]: os.environ.pop(k, None)
        if not enable_global:
            print("[*] 全局代理总闸已关闭，恢复纯净直连模式。")

def get_config():
    if not os.path.exists(CONFIG_PATH) and os.path.exists(EXAMPLE_CONFIG_PATH):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copy(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e: raise HTTPException(status_code=500, detail=f"读取配置失败: {str(e)}")

def restore_config():
    if not os.path.exists(EXAMPLE_CONFIG_PATH): raise HTTPException(status_code=404, detail="找不到默认配置文件")
    os.makedirs(CONFIG_DIR, exist_ok=True)
    shutil.copy(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e: raise HTTPException(status_code=500, detail=f"读取恢复后的配置失败: {str(e)}")

def update_config(payload: dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(payload, f, indent=2, ensure_ascii=False)
        set_global_proxy(payload.get("system_settings", {}))
        return {"message": "配置已保存并生效"}
    except Exception as e: raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")

def test_proxy(proxy_url: str):
    proxy_url = proxy_url.strip()
    if not proxy_url: return {"status": "ok", "message": "未配置代理"}
    try:
        if "://" not in proxy_url: proxy_url = f"http://{proxy_url}"
        parsed = urllib.parse.urlparse(proxy_url)
        if not parsed.hostname or not parsed.port: raise ValueError("代理地址或端口格式无效")
        with socket.create_connection((parsed.hostname, parsed.port), timeout=3.0): pass
        return {"status": "ok", "message": "代理服务器连接成功"}
    except Exception as e: raise HTTPException(status_code=400, detail=f"代理服务器连接失败，请检查配置。({str(e)})")

def get_languages():
    langs = [{"code": k, "name": v.capitalize()} for k, v in SUPPORTED_LANGUAGES.items()]
    return sorted(langs, key=lambda x: x["name"])

def get_models():
    models = available_models()
    return [
        {"label": "✨ 常规多语言模型 (Standard)", "options": [m for m in models if "distil" not in m and not m.endswith(".en")]},
        {"label": "⚡ 蒸馏加速模型 (Distilled)", "options": [m for m in models if "distil" in m]},
        {"label": "🇬🇧 纯英文模型 (English Only)", "options": [m for m in models if m.endswith(".en")]}
    ]

def _fetch_openai_models(api_key: str, base_url: str, filter_keywords=None):
    if not api_key: raise HTTPException(status_code=400, detail="请先填写 API Key")
    req = urllib.request.Request(f"{base_url.strip().rstrip('/')}/models")
    req.add_header("accept", "application/json")
    req.add_header("authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            model_ids = [m["id"] for m in data.get("data", []) if "id" in m]
            if filter_keywords:
                filtered = [m for m in model_ids if any(kw in m.lower() for kw in filter_keywords)]
                return filtered if filtered else model_ids
            return model_ids
    except urllib.error.HTTPError as e: raise HTTPException(status_code=e.code, detail=f"获取失败: {e.read().decode('utf-8')}")
    except Exception as e: raise HTTPException(status_code=400, detail=f"拉取模型列表异常: {str(e)}")

def get_llm_models(api_key: str, base_url: str):
    return _fetch_openai_models(api_key, base_url)

def get_asr_models(api_key: str, base_url: str):
    return _fetch_openai_models(api_key, base_url, filter_keywords=["whisper", "asr", "audio", "speech", "stt", "sensevoice", "paraformer"])