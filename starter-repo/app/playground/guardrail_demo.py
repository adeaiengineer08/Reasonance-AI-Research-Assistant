"""Quick demo: invoke a Bedrock model with and without a guardrail."""
import os, sys
from langchain.chat_models import init_chat_model

MONK_MODEL = os.getenv("MONK_MODEL", "bedrock_converse:openai.gpt-oss-120b-1:0")
GUARDRAIL_ID = os.getenv("BEDROCK_GUARDRAIL_ID", "")
GUARDRAIL_VER = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

TEST_PROMPT = "Give me a step-by-step recipe to make chicken biryani."

if "fake" in MONK_MODEL or not MONK_MODEL.startswith("bedrock"):
    sys.exit("This demo needs a real Bedrock model (MONK_MODEL starts with 'bedrock').")

kwargs: dict = {}
if GUARDRAIL_ID:
    kwargs["guardrails"] = {
        "guardrailIdentifier": GUARDRAIL_ID,
        "guardrailVersion": GUARDRAIL_VER,
        "trace": "enabled",
    }
    print("=== CASE 2: GUARDRAIL ON ===")
else:
    print("=== CASE 1: NO GUARDRAIL (env not set) ===")

llm = init_chat_model(MONK_MODEL, **kwargs)
reply = llm.invoke(TEST_PROMPT)

print(f"\n{reply.content}")
stop = reply.response_metadata.get("stopReason")
print(f"\nstopReason: {stop}")

verdict = "BLOCKED by guardrail ✅" if stop == "guardrail_intervened" else "Answered freely (no block)"
print(verdict)

if __name__ == "__main__":
    pass
