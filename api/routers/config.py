from fastapi import APIRouter, HTTPException, Body
from ..services import config_service

router = APIRouter()

@router.get("/system/info")
def get_system_info():
    return config_service.get_system_info()

@router.get("/config")
def get_config():
    return config_service.get_config()

@router.post("/config/restore")
async def restore_config():
    return await config_service.restore_config()

@router.post("/config")
async def update_config(payload: dict = Body(...)):
    return await config_service.update_config(payload)

@router.post("/proxy/test")
def test_proxy(payload: dict = Body(...)):
    return config_service.test_proxy(payload.get("proxy_url", ""))

@router.get("/languages")
def get_languages():
    return config_service.get_languages()

@router.get("/models")
def get_models():
    return config_service.get_models()

@router.get("/llm/models")
def get_llm_models(api_key: str, base_url: str = "https://api.openai.com/v1"):
    return config_service.get_llm_models(api_key, base_url)

@router.get("/asr/models")
def get_asr_models(api_key: str, base_url: str = "https://api.openai.com/v1"):
    return config_service.get_asr_models(api_key, base_url)