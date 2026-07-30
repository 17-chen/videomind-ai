ZH_CN_MESSAGES: dict[str, str] = {
    "internal_server_error": "服务器内部错误",
    "video_already_processing": "视频正在处理中，请勿重复触发",
    "video_not_found": "未找到该视频",
    "video_processing_started": "视频处理任务已启动",
    "transcript_required": "请先完成视频转写，再启动 AI 分析",
    "llm_key_required": "需要配置 DeepSeek API Key 才能使用 AI 视频分析",
    "openai_key_required_for_analysis": "需要配置 LLM API Key 才能使用 AI 视频分析",
    "ai_analysis_failed": "AI 视频分析失败",
    "embedding_source_required": "请先完成视频转写或 AI 分析，再写入知识库",
    "video_indexed": "视频已写入向量知识库",
    "rag_answer_failed": "视频知识库问答失败",
    "no_relevant_videos": "暂时没有检索到相关视频内容",
    "chroma_unavailable": "ChromaDB 暂不可用，请确认向量数据库服务已经启动",
    "yt_dlp_missing": "yt-dlp 未安装，无法下载视频",
    "video_download_failed": "视频下载失败",
    "video_output_missing": "视频下载已结束，但没有找到输出文件",
    "ffmpeg_missing": "ffmpeg 未安装或不在 PATH 中",
    "video_file_missing": "视频文件不存在",
    "audio_extraction_timeout": "音频提取超时",
    "audio_extraction_failed": "音频提取失败",
    "audio_output_missing": "音频提取失败，没有生成输出文件",
    "asr_disabled": "当前未启用音频转写服务。请优先使用带字幕的视频，或后续配置本地 ASR。",
    "openai_key_required": "需要配置 OPENAI_API_KEY 才能使用 OpenAI Whisper 转写",
    "audio_file_missing": "音频文件不存在",
    "whisper_failed": "Whisper 转写失败",
    "whisper_empty": "Whisper 返回了空转写结果",
}


def t(message_key: str) -> str:
    return ZH_CN_MESSAGES.get(message_key, message_key)
