import os
import re
import time
import httpx
import asyncio
import traceback
import openai
from openai import AsyncOpenAI, APIStatusError, APIConnectionError
from api.services.config_service import SUPPORTED_LANGUAGES

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

async def translate_batch(client, model_name, system_prompt, batch_content, batch_index, total_batches, semaphore, progress_state, previous_context="", progress_callback=None):
    """
    发送单个分块进行翻译 (异步并发)
    """
    async with semaphore:
        text_to_translate = "\n\n".join(batch_content)
        user_content = text_to_translate
        
        if previous_context:
            user_content = f"【以下是上一段原文结尾，仅供上下文衔接参考，🚫禁止翻译该部分🚫】：\n{previous_context}\n\n====================\n\n【👇请严格按照原格式，正式翻译以下字幕片段👇】：\n{text_to_translate}"

        try:
            completion = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=1.0,
                max_tokens=4096,
                stream=False
            )

            if not completion.choices or not completion.choices[0].message.content:
                raise Exception(f"大模型返回了空内容或遇到了安全拦截。响应: {completion}")
            translated_text = completion.choices[0].message.content
            translated_text = re.sub(r'<think>.*?</think>', '', translated_text, flags=re.DOTALL)
            translated_text = translated_text.replace("```srt", "").replace("```", "").strip()
            
            progress_state["completed"] += 1
            msg = f"⚡ 正在全速并发翻译中... (已完成 {progress_state['completed']}/{total_batches} 批)"
            
            if progress_callback:
                progress_callback(msg)
            else:
                print(f"   {msg}")
                
            parsed_blocks = []
            # 尝试将大模型返回的 SRT 文本解析为块
            blocks = translated_text.replace('\r\n', '\n').replace('\r', '\n').split('\n\n')
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # 尝试匹配时间轴
                    time_match = re.search(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1])
                    if time_match:
                        start, end = time_match.group(1), time_match.group(2)
                        text = "\n".join(lines[2:])
                        parsed_blocks.append((start, end, text))
            
            if not parsed_blocks:
                parsed_blocks = translated_text
                
            return (batch_index, parsed_blocks, batch_content)

        except Exception as e:
            if isinstance(e, APIStatusError):
                error_message = f"❌ 第 {batch_index} 批次大模型 API 返回状态错误 (HTTP Status: {e.status_code})！\n"
                error_message += f"   - 错误详情 (Response): {e.response.text}\n"
                print(error_message)
                if progress_callback: progress_callback(error_message)
                raise Exception(error_message)
                
            elif isinstance(e, APIConnectionError):
                error_message = f"❌ 第 {batch_index} 批次无法连接到大模型 API 服务器！请检查网络或代理设置。\n   - 错误根源: {e.__cause__}\n"
                print(error_message)
                if progress_callback: progress_callback(error_message)
                raise Exception(error_message)
                
            else:
                error_msg = f"❌ 第 {batch_index} 批次翻译发生未知错误: {e}"
                print(error_msg)
                traceback.print_exc()
                if progress_callback: progress_callback(error_msg)
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
    enable_global_proxy = system_config.get("enable_global_proxy", False)
    proxy_url = system_config.get("network_proxy", "")
    
    actual_use_proxy = enable_global_proxy and use_proxy and proxy_url
    
    lang_name = SUPPORTED_LANGUAGES.get(target_language_code, target_language_code).capitalize()

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

    # 提取用户配置的超时时间，并做下限防呆保护
    timeout_cfg = llm_config.get("timeout_settings", {})
    try:
        user_connect = max(float(timeout_cfg.get("connect", 10.0)), 3.0)
        user_read = max(float(timeout_cfg.get("read", 120.0)), 30.0)
    except (TypeError, ValueError):
        user_connect, user_read = 10.0, 120.0
        
    # 组装精细化的 httpx Timeout 控制器
    timeout_config = httpx.Timeout(connect=user_connect, read=user_read, write=20.0, pool=10.0)

    client_params = {
        "api_key": api_key, 
        "base_url": base_url,
        "max_retries": 2
    }
    if actual_use_proxy:
        client_params["http_client"] = httpx.AsyncClient(proxy=proxy_url, timeout=timeout_config)
    else:
        client_params["http_client"] = httpx.AsyncClient(proxy=None, trust_env=False, timeout=timeout_config)

    client = AsyncOpenAI(**client_params)

    try:
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
            
            prev_context = ""
            if i > 0:
                prev_batch = srt_blocks[max(0, i - 3) : i]
                prev_context = "\n\n".join(prev_batch)
            
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
                    previous_context=prev_context,
                    progress_callback=progress_callback
                )
            )
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, Exception):
                raise res
        
        # 按 batch_index 排序确保写入顺序正确
        results.sort(key=lambda x: x[0])
        
        current_global_idx = 1
        
        for idx, parsed_blocks, original_batch in results:
            if isinstance(parsed_blocks, list):
                with open(output_srt_path, "a", encoding="utf-8") as f:
                    for i, block in enumerate(parsed_blocks):
                        start, end, text = block
                        # 强制对齐: 如果数量一致，强制使用原视频时间轴，防格式雪崩
                        if len(parsed_blocks) == len(original_batch):
                            orig_match = re.search(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", original_batch[i])
                            if orig_match:
                                start, end = orig_match.group(1), orig_match.group(2)
                                
                        f.write(f"{current_global_idx}\n{start} --> {end}\n{text}\n\n")
                        current_global_idx += 1
                success_count += len(parsed_blocks)
            else:
                # 极端后备: 直接写入文本
                with open(output_srt_path, "a", encoding="utf-8") as f:
                    f.write(parsed_blocks + "\n\n")

        finish_msg = f"🎉 翻译完毕！共成功处理 {success_count}/{total_blocks} 条字幕。"
        if progress_callback:
            progress_callback(finish_msg)
        else:
            print(finish_msg)
            
    finally:
        # [内存/句柄泄漏修复] 强制关闭并清理底层的 AsyncClient
        try:
            await client_params["http_client"].aclose()
        except Exception:
            pass

if __name__ == "__main__":
    print("本脚本已重构为通用核心模块，请通过 WebUI 工作流或主程序调用。")