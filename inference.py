import os
import sys

from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.getenv("HF_TOKEN")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")


def build_openai_client() -> OpenAI:
    # The hackathon checklist requires LLM calls to use the OpenAI client
    # configured through these environment variables. Our current agent uses
    # a deterministic local planner, so the client is initialized only for
    # compatibility with that contract.
    api_key = HF_TOKEN or os.getenv("OPENAI_API_KEY") or "unused-openai-key"
    return OpenAI(api_key=api_key, base_url=API_BASE_URL)


def run_inference() -> None:
    _ = build_openai_client(), MODEL_NAME, LOCAL_IMAGE_NAME

    from warehouse_env.inference import run_inference as package_run_inference

    package_run_inference()


if __name__ == "__main__":
    try:
        run_inference()
    except Exception as exc:
        print(f"[FATAL] root inference wrapper crashed: {exc}", file=sys.stderr)
