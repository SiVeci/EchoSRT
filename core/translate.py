import os
import time
import httpx
import asyncio
from openai import AsyncOpenAI

DEFAULT_SYSTEM_PROMPT = """### 🎯 风格要求：
1. **自然流畅**：符合目标语言母语者的表达习惯。
2. **专业严谨**：准确翻译专有名词和术语。
3. **结合语境**：根据前后文调整语气和用词。"""

def parse_srt(content: str) -> list:
    """
    将 SRT 内容解析为独立的字幕块列表
    """
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    blocks = content.split('\n\n')
    return [b.strip() for b in blocks if b.strip()]

async def translate_batch(client, model_name, system_prompt, batch_content, batch_index, total_batches, semaphore, progress_state, progress_callback=None):
    """
    发送单个分块进行翻译 (异步并发)
    """
    async with semaphore:
        text_to_translate = "\n\n".join(batch_content)

        try:
            completion = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text_to_translate}
                ],
                temperature=1.0,
                max_tokens=4096,
                stream=False
            )

            translated_text = completion.choices[0].message.content
            translated_text = translated_text.replace("```srt", "").replace("```", "").strip()
            
            progress_state["completed"] += 1
            msg = f"⚡ 正在全速并发翻译中... (已完成 {progress_state['completed']}/{total_batches} 批)"
            
            if progress_callback:
                progress_callback(msg)
            else:
                print(f"   {msg}")
                
            return (batch_index, translated_text)

        except Exception as e:
            error_msg = f"❌ 第 {batch_index} 批次翻译失败: {e}"
            if progress_callback:
                progress_callback(error_msg)
            else:
                print(f"   {error_msg}")
            raise Exception(f"大模型接口请求失败: {e}")

async def run_llm_translation(
    input_srt_path: str, 
    output_srt_path: str, 
    llm_config: dict, 
    system_config: dict,
    progress_callback=None
):
    """
    执行 LLM 翻译任务的核心调度函数。
    """
    api_key = llm_config.get("api_key", "").strip()
    base_url = llm_config.get("base_url", "https://api.openai.com/v1").strip()
    model_name = llm_config.get("model_name", "Pro/deepseek-ai/DeepSeek-V3.2").strip()
    target_language_code = llm_config.get("target_language", "zh").strip()
    batch_size = llm_config.get("batch_size", 50)
    concurrent_workers = llm_config.get("concurrent_workers", 3)
    use_proxy = llm_config.get("use_network_proxy", False)
    proxy_url = system_config.get("network_proxy", "")
    
    lang_map = {
        "zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文", 
        "fr": "法文", "de": "德文", "es": "西班牙文", "ru": "俄文"
    }
    lang_name = lang_map.get(target_language_code, target_language_code)

    fixed_role_and_lang = f"你是一位精通各国文化的专业影视字幕翻译。\n任务：将用户提供的 SRT 字幕片段翻译成【{lang_name}】。\n\n"
    fixed_format_instructions = """### 🚫 格式死命令：
1. **保留原文结构**：这是字幕片段，不要合并，不要遗漏。
2. **保留时间轴**：所有时间戳（如 00:00:01,000 --> ...）必须原样保留，不得修改。
3. **只输出结果**：不要加“好的”、“片段翻译如下”等废话，直接输出 SRT 格式文本。

"""

    custom_style_prompt = llm_config.get("system_prompt", "").strip()
    if not custom_style_prompt:
        custom_style_prompt = DEFAULT_SYSTEM_PROMPT
        
    full_system_prompt = fixed_role_and_lang + fixed_format_instructions + custom_style_prompt

    if not api_key:
        raise ValueError("缺少大模型 API Key，请先在设置中配置。")

    if not os.path.exists(input_srt_path):
        raise FileNotFoundError(f"找不到输入的字幕文件: {input_srt_path}")

    if not base_url:
        base_url = "https://api.openai.com/v1"

    client_params = {
        "api_key": api_key, 
        "base_url": base_url,
        "timeout": 120.0,
        "max_retries": 2
    }
    if use_proxy and proxy_url:
        client_params["http_client"] = httpx.AsyncClient(proxy=proxy_url)

    client = AsyncOpenAI(**client_params)

    if progress_callback:
        progress_callback("📖 正在读取并解析原生字幕...")

    with open(input_srt_path, "r", encoding="utf-8") as f:
        full_content = f.read()
    
    srt_blocks = parse_srt(full_content)
    total_blocks = len(srt_blocks)
    
    if total_blocks == 0:
        raise ValueError("未检测到任何有效字幕块，请检查字幕文件内容。")

    msg = f"📊 共解析到 {total_blocks} 条字幕，准备分批请求模型..."
    if progress_callback:
        progress_callback(msg)
    else:
        print(msg)

    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write("")

    success_count = 0
    total_batches = (total_blocks + batch_size - 1) // batch_size
    
    semaphore = asyncio.Semaphore(concurrent_workers)
    progress_state = {"completed": 0}
    tasks = []
    
    for i in range(0, total_blocks, batch_size):
        batch = srt_blocks[i : i + batch_size]
        current_batch_num = (i // batch_size) + 1
        
        tasks.append(
            translate_batch(
                client=client, 
                model_name=model_name, 
                system_prompt=full_system_prompt, 
                batch_content=batch, 
                batch_index=current_batch_num, 
                total_batches=total_batches,
                semaphore=semaphore,
                progress_state=progress_state,
                progress_callback=progress_callback
            )
        )
        
    results = await asyncio.gather(*tasks)
    
    for idx, translated_chunk in results:
        if translated_chunk:
            with open(output_srt_path, "a", encoding="utf-8") as f:
                f.write(translated_chunk + "\n\n")
            
            batch_start = (idx - 1) * batch_size
            batch_end = batch_start + batch_size
            success_count += len(srt_blocks[batch_start:batch_end])

    finish_msg = f"🎉 翻译完毕！共成功处理 {success_count}/{total_blocks} 条字幕。"
    if progress_callback:
        progress_callback(finish_msg)
    else:
        print(finish_msg)

if __name__ == "__main__":
    print("本脚本已重构为通用核心模块，请通过 WebUI 工作流或主程序调用。")