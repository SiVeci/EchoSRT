from fastapi import APIRouter, HTTPException, Body
from ..services import config_service

router = APIRouter()

@router.get("/config")
async def get_config():
    return config_service.get_config()

@router.post("/config/restore")
async def restore_config():
    return config_service.restore_config()

@router.post("/config")
async def update_config(payload: dict = Body(...)):
    return config_service.update_config(payload)

@router.post("/proxy/test")
async def test_proxy(payload: dict = Body(...)):
    return config_service.test_proxy(payload.get("proxy_url", ""))

@router.get("/languages")
async def get_languages():
    return config_service.get_languages()

@router.get("/models")
async def get_models():
    return config_service.get_models()

@router.get("/llm/models")
async def get_llm_models(api_key: str, base_url: str = "https://api.openai.com/v1"):
    return config_service.get_llm_models(api_key, base_url)

@router.get("/asr/models")
async def get_asr_models(api_key: str, base_url: str = "https://api.openai.com/v1"):
    return config_service.get_asr_models(api_key, base_url)