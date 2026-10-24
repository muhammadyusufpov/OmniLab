"""Bounded, server-side Groq chat for the chemistry workspace."""

import hashlib
import json
import logging
import os
import time
from urllib import error, request as urlrequest

from django.core.cache import cache
from django.http import JsonResponse

from .views import get_client_network_address, increment_reaction_request_count


logger = logging.getLogger(__name__)
GROQ_BASE = "https://api.groq.com/openai/v1"
MAX_QUESTION = 1000
MAX_HISTORY = 10
MAX_HISTORY_TEXT = 12000
MAX_RESPONSE_BYTES = 262144


def family_for(model_id):
    lowered = model_id.lower()
    if "deepseek" in lowered:
        return "DeepSeek"
    if "qwen" in lowered or "qwq" in lowered:
        return "Qwen"
    return None


def groq_request(path, key, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        GROQ_BASE + path,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST" if data is not None else "GET",
    )
    with urlrequest.urlopen(req, timeout=15) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Groq response too large")
    return json.loads(raw)


def available_models(key):
    # Models are account-specific and change. Never advertise retired IDs.
    cache_key = "omnilab:groq:models:" + hashlib.sha256(key.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = groq_request("/models", key)
    models = {"DeepSeek": [], "Qwen": []}
    for item in data.get("data", []):
        model_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(model_id, str):
            continue
        family = family_for(model_id)
        if family and item.get("active", True):
            models[family].append(model_id)
    for family in models:
        models[family] = sorted(set(models[family]))
    cache.set(cache_key, models, 300)
    return models


def chat_models(request):
    if request.method != "GET":
        return JsonResponse({"message": "Only GET requests are accepted."}, status=405)
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return JsonResponse({"message": "Chat is not configured yet."}, status=503)
    try:
        models = available_models(key)
    except (error.URLError, ValueError, json.JSONDecodeError, KeyError):
        logger.warning("Groq model list unavailable", exc_info=False)
        return JsonResponse({"message": "Models are unavailable. Try again later."}, status=503)
    return JsonResponse({"models": models})


def validate_history(history):
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        return None
    messages = []
    total = 0
    for index, item in enumerate(history):
        if not isinstance(item, dict) or set(item) != {"role", "content"}:
            return None
        role, content = item["role"], item["content"]
        if role != ("user" if index % 2 == 0 else "assistant"):
            return None
        if not isinstance(content, str) or not content.strip() or len(content) > 4000:
            return None
        total += len(content)
        messages.append({"role": role, "content": content.strip()})
    if len(messages) % 2 or total > MAX_HISTORY_TEXT:
        return None
    return messages


def chat_reply(request):
    if request.method != "POST":
        return JsonResponse({"message": "Only POST requests are accepted."}, status=405)
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return JsonResponse({"message": "Chat is not configured yet."}, status=503)
    if len(request.body) > 20000:
        return JsonResponse({"message": "Message is too long."}, status=400)
    try:
        body = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"message": "Invalid message."}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"message": "Invalid message."}, status=400)
    model = body.get("model")
    question = body.get("question")
    history = validate_history(body.get("history", []))
    if (
        not isinstance(model, str)
        or not isinstance(question, str)
        or not question.strip()
        or len(question) > MAX_QUESTION
        or history is None
    ):
        return JsonResponse({"message": "Check the model and question."}, status=400)
    try:
        models = available_models(key)
    except (error.URLError, ValueError, json.JSONDecodeError, KeyError):
        return JsonResponse({"message": "Models are unavailable. Try again later."}, status=503)
    if model not in models["DeepSeek"] + models["Qwen"]:
        return JsonResponse({"message": "This model is no longer available."}, status=400)

    # The SQLite counter is shared by all Gunicorn workers on this host.
    window = int(time.time()) // 600
    digest = hashlib.sha256(("groq:" + get_client_network_address(request)).encode()).hexdigest()
    if increment_reaction_request_count(digest, window) > 12:
        return JsonResponse({"message": "Chat limit reached. Try again in ten minutes."}, status=429)
    try:
        result = groq_request("/chat/completions", key, {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are OmniLab's chemistry study assistant. Give clear educational explanations. The lab's predicted reactions are not verified experiments. Never claim a prediction is confirmed, and do not replace teacher supervision or lab safety rules."},
                *history,
                {"role": "user", "content": question.strip()},
            ],
            "max_completion_tokens": 1024,
        })
        answer = result["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Empty Groq answer")
    except error.HTTPError as exc:
        # Never return provider details or credentials to the browser.
        logger.warning("Groq chat HTTP status %s", exc.code)
        status = 429 if exc.code == 429 else 503
        return JsonResponse({"message": "Chat is busy. Try again shortly."}, status=status)
    except (error.URLError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        logger.warning("Groq chat unavailable", exc_info=False)
        return JsonResponse({"message": "Chat is unavailable. Try again later."}, status=503)
    return JsonResponse({"answer": answer.strip(), "model": model})
