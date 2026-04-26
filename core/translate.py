import os
import time
from openai import OpenAI

DEFAULT_SYSTEM_PROMPT = """### 🚫 格式死命令：
1. **保留原文结构**：这是字幕片段，不要合并，不要遗漏。
2. **保留时间轴**：所有时间戳（如 00:00:01,000 --> ...）必须原样保留，不得修改。
3. **只输出结果**：不要加“好的”、“片段翻译如下”等废话，直接输出 SRT 格式文本。

### 🎯 风格要求：
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

def translate_batch(client, model_name, system_prompt, batch_content, batch_index, total_batches, progress_callback=None):
    """
    发送单个分块进行翻译
    """
    msg = f"⏳ 正在翻译第 {batch_index}/{total_batches} 批次 (约 {len(batch_content)} 条)..."
    if progress_callback:
        progress_callback(msg)
    else:
        print(f"   {msg}")
        
    text_to_translate = "\n\n".join(batch_content)

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text_to_translate}
            ],
            temperature=1.0,  # 稍微收敛一些，防止通用翻译时产生过度幻觉
            max_tokens=4096,
            stream=False
        )

        translated_text = completion.choices[0].message.content
        # 清除大模型偶尔自作聪明加上去的 markdown 代码块包裹
        translated_text = translated_text.replace("```srt", "").replace("```", "").strip()
        
        return translated_text

    except Exception as e:
        error_msg = f"❌ 本批次翻译失败: {e}"
        if progress_callback:
            progress_callback(error_msg)
        else:
            print(f"   {error_msg}")
        return None

def run_llm_translation(
    input_srt_path: str, 
    output_srt_path: str, 
    llm_config: dict, 
    progress_callback=None
):
    """
    执行 LLM 翻译任务的核心调度函数。
    llm_config 结构示例:
    {
        "api_key": "sk-...",
        "base_url": "https://api.siliconflow.cn/v1",
        "model_name": "Pro/deepseek-ai/DeepSeek-V3.2",
        "batch_size": 50,
        "system_prompt": "..."
    }
    """
    api_key = llm_config.get("api_key", "").strip()
    base_url = llm_config.get("base_url", "https://api.openai.com/v1").strip()
    model_name = llm_config.get("model_name", "Pro/deepseek-ai/DeepSeek-V3.2").strip()
    target_language_code = llm_config.get("target_language", "zh").strip()
    batch_size = llm_config.get("batch_size", 50)
    
    # 构建固定不可更改的前半段语言指令
    lang_map = {
        "zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文", 
        "fr": "法文", "de": "德文", "es": "西班牙文", "ru": "俄文"
    }
    lang_name = lang_map.get(target_language_code, target_language_code)
    fixed_prompt = f"你是一位精通各国文化的专业影视字幕翻译。\n任务：将用户提供的 SRT 字幕片段翻译成【{lang_name}】。\n\n"

    # 提取并组合后半段的风格指令
    custom_prompt = llm_config.get("system_prompt", "").strip()
    if not custom_prompt:
        custom_prompt = DEFAULT_SYSTEM_PROMPT
        
    full_system_prompt = fixed_prompt + custom_prompt

    if not api_key:
        raise ValueError("缺少大模型 API Key，请先在设置中配置。")

    if not os.path.exists(input_srt_path):
        raise FileNotFoundError(f"找不到输入的字幕文件: {input_srt_path}")

    client = OpenAI(api_key=api_key, base_url=base_url)

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

    # 清空并准备输出文件
    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write("")

    success_count = 0
    total_batches = (total_blocks + batch_size - 1) // batch_size
    
    for i in range(0, total_blocks, batch_size):
        batch = srt_blocks[i : i + batch_size]
        current_batch_num = (i // batch_size) + 1
        
        translated_chunk = translate_batch(
            client=client, 
            model_name=model_name, 
            system_prompt=full_system_prompt, 
            batch_content=batch, 
            batch_index=current_batch_num, 
            total_batches=total_batches,
            progress_callback=progress_callback
        )
        
        if translated_chunk:
            with open(output_srt_path, "a", encoding="utf-8") as f:
                f.write(translated_chunk + "\n\n")
            success_count += len(batch)
        else:
            warn_msg = f"⚠️ 跳过第 {current_batch_num} 批次，建议稍后手动检查。"
            if progress_callback:
                progress_callback(warn_msg)
            else:
                print(warn_msg)
        
        time.sleep(1)

    finish_msg = f"🎉 翻译完毕！共成功处理 {success_count}/{total_blocks} 条字幕。"
    if progress_callback:
        progress_callback(finish_msg)
    else:
        print(finish_msg)

if __name__ == "__main__":
    print("本脚本已重构为通用核心模块，请通过 WebUI 工作流或主程序调用。")