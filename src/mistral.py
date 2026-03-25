import os
from dotenv import load_dotenv
import httpx

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_COMPLETION_URL = os.getenv("MISTRAL_COMPLETION_URL")


def mistral_completion(system: str | None, user: str) -> str:
    """
    Send text to Mistral Chat API and return the response.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    if not MISTRAL_API_KEY or not MISTRAL_COMPLETION_URL:
        print("[mistral] error: MISTRAL_API_KEY or MISTRAL_COMPLETION_URL not found in environment variables")
        raise ValueError("MISTRAL_API_KEY or MISTRAL_COMPLETION_URL not found in environment variables")
    try:
        with httpx.Client() as client:
            response = client.post(
                MISTRAL_COMPLETION_URL,
                json={"messages": messages, "model": "mistral-large-latest"},
                headers={
                    "Authorization": "Bearer " + MISTRAL_API_KEY,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
    except Exception as error:
        print(f"[mistral] error: {error}")
        raise error
    try:
        res = response.json()["choices"][0]["message"]["content"]
        return res
    except Exception as error:
        print(f"[mistral] error: {error}")
        print(f"[mistral] response: {response.text}")
        raise error
