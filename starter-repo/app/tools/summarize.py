"""Summarize text using the configured LLM."""
from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

DEFAULT_MODEL = "bedrock_converse:openai.gpt-oss-120b-1:0"


@tool
def summarize(text: str, focus: str = "") -> str:
    """Produce a concise 3-sentence summary of the given text. Use this to distill long documents into key points."""
    model = init_chat_model(os.getenv("MONK_MODEL", DEFAULT_MODEL))
    focus_instruction = f" Emphasise aspects related to: {focus}." if focus else ""
    messages = [
        SystemMessage(content=f"Summarize the following text in exactly 3 sentences.{focus_instruction}"),
        HumanMessage(content=text[:10000]),
    ]
    return model.invoke(messages).content


if __name__ == "__main__":
    print(summarize.invoke({"text": "LangGraph is a library for building stateful AI agents.", "focus": ""}))
