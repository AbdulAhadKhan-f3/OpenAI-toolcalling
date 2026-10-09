"""Shared OpenAI-compatible model client."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "ollama"),
                base_url=os.getenv("OPENAI_BASE_URL"),
                timeout=float(os.getenv("LLM_TIMEOUT", "120")))
