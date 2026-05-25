import os

if os.getenv("NVIDIA_API_KEY") or os.getenv("LLM_API_KEY"):
    print("HAS_KEY")
else:
    print("NO_KEY")
