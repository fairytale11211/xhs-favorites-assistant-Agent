"""多用户 Agent：基于 CollectionService + BYOK LLM。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from collection_service import CollectionService
from llm_client import LLMCallError, build_llm_client

BASE_SYSTEM_PROMPT = """你是一个小红书收藏管理助手。用户会提出查找收藏帖子的条件，你需要根据需求提供帮助。

# 工作方式：
- 如果用户的问题很简单（如问候、闲聊），你可以直接用自然语言回复，不需要调用工具。
- 如果用户需要查找帖子，请优先使用工具来获取准确结果。

# 工具调用格式（仅在需要时使用）：
如果需要调用工具，请按以下格式输出：
Thought: [你的思考]
Action: function_name(arg1="value1", arg2=value2, ...)

如果已经获得足够信息可以直接回答，请输出：
Action: Finish[最终答案]

# 可用工具:
- `hybrid_search(keyword: str = None, min_likes: int = None, max_likes: int = None, tag: str = None)`:
  混合检索，先精确匹配再语义补充。keyword 应包含5~8个相关词，用逗号分隔。
- `semantic_search(concept: str, top_k: int = 10)`: 抽象概念检索。
- `generate_insight()`: 生成用户偏好画像。

# 重要提示:
- 工具返回的结果中已经包含了帖子的正文预览（前100字），你可以直接引用。
- 输出帖子的链接时，务必使用包含 xsec_token 的完整 URL。
- 如果不需要调用工具，直接输出回答即可，无需格式化。

# 关于结束对话（非常重要，请严格遵守）:
- 你和用户之间的每一轮 Thought/Action/Observation，用户是看不到的（前端界面默认只展示你最终
  Action: Finish[...] 里的内容，Observation 原文只有用户主动点开"思考过程"才可能看到）。
- 所以：一旦某次工具调用的 Observation 已经包含了足够回答用户问题的信息（比如检索到了帖子列表），
  你应该【在下一步立刻】用 Action: Finish[...] 结束，并把 Observation 里对用户有用的具体内容
  （帖子标题、点赞数、标签、链接等）整理进 Finish 的内容里完整呈现给用户。
- 绝对不要说"你已经看到了""如上所示""我在上一轮已经找到"这类话——因为用户实际上没有看到，
  这样回复会导致用户拿到的最终答案里丢失所有实际内容。Finish 的内容必须是自包含的，
  不能依赖用户去看之前的 Observation。
"""


def ask_agent(
    user_input: str,
    service: CollectionService,
    llm_config: dict[str, str],
    history: Optional[list] = None,
) -> dict[str, Any]:
    llm = build_llm_client(llm_config)
    available_tools = service.get_tools(llm)

    memory = service.load_memory()
    memory_text = service.format_memory_for_prompt(memory)
    dynamic_system_prompt = BASE_SYSTEM_PROMPT + memory_text

    history_text = ""
    if history:
        recent = history[-5:]
        history_parts = []
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "助手"
            history_parts.append(f"{role}：{msg.get('content', '')}")
        history_text = "之前的对话摘要：\n" + "\n".join(history_parts)

    prompt_history = []
    if history_text:
        prompt_history.append(history_text)
    prompt_history.append(f"用户请求: {user_input}")

    final_answer = None
    last_observation = None
    trace_lines = []
    observations = []

    for step in range(5):
        full_prompt = "\n".join(prompt_history)
        try:
            llm_output = llm.generate(full_prompt, dynamic_system_prompt)
        except LLMCallError as e:
            trace_lines.append(f"--- Step {step+1} ---")
            trace_lines.append(f"[模型调用失败] {e}")
            error_answer = f"⚠️ 暂时无法获取模型回复：{e}。请稍后重试，或重新发送一次问题。"
            return {"final": error_answer, "trace": "\n".join(trace_lines), "error": True, "contexts": observations}

        trace_lines.append(f"--- Step {step+1} ---")
        trace_lines.append(llm_output.strip())

        match = re.search(
            r"(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)",
            llm_output,
            re.DOTALL,
        )
        if match:
            llm_output = match.group(1).strip()

        action_match = re.search(
            r"Action:\s*(.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)",
            llm_output,
            re.DOTALL,
        )

        if not action_match:
            clean_output = re.sub(r"^Thought:\s*", "", llm_output.strip())
            final_answer = clean_output
            break

        action_str = action_match.group(1).strip()

        if action_str.startswith("Finish"):
            finish_match = re.match(r"Finish\[([\s\S]*)\]", action_str, re.DOTALL)
            if finish_match:
                final_answer = finish_match.group(1).strip()
            else:
                final_answer = action_str[6:].strip()
            break

        tool_name_match = re.search(r"(\w+)\(", action_str)
        if not tool_name_match:
            final_answer = llm_output.strip()
            break

        tool_name = tool_name_match.group(1)
        args_str_match = re.search(r"\((.*)\)", action_str, re.DOTALL)
        kwargs = {}
        if args_str_match:
            args_str = args_str_match.group(1)
            pairs = re.findall(r'(\w+)=("[^"]*"|\d+)', args_str)
            for key, val in pairs:
                if val.isdigit():
                    kwargs[key] = int(val)
                else:
                    kwargs[key] = val.strip('"')

        if tool_name in available_tools:
            try:
                result = available_tools[tool_name](**kwargs)
            except Exception as e:
                result = f"工具执行出错: {e}"
        else:
            result = f"错误：未定义的工具 '{tool_name}'"

        last_observation = result
        observations.append(result)
        trace_lines.append(f"Observation: {result}")
        prompt_history.append(f"Observation: {result}")

    if not final_answer and last_observation:
        final_answer = last_observation

    if final_answer and last_observation and isinstance(last_observation, str):
        observation_has_results = ("🔗" in last_observation) or ("共找到" in last_observation)
        final_answer_looks_empty = ("🔗" not in final_answer) and (len(final_answer) < 150)
        if observation_has_results and final_answer_looks_empty:
            final_answer = last_observation

    if final_answer:
        service.update_memory(memory, user_input, final_answer)
        service.save_memory(memory)
    elif last_observation:
        service.update_memory(memory, user_input, last_observation)
        service.save_memory(memory)

    if not final_answer:
        final_answer = "抱歉，未能获取到有效结果，请重新描述您的问题。"

    return {
        "final": final_answer,
        "trace": "\n".join(trace_lines),
        "error": False,
        "contexts": observations,
    }


def get_service_for_user(user_id: int, llm_config: Optional[dict] = None) -> CollectionService:
    from backend.database import get_user_data_dir

    data_dir = get_user_data_dir(user_id)
    return CollectionService(user_id, data_dir, llm_config)
