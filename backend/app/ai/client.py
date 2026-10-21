"""Gemini REST client. Only the backend calls this; the key never leaves the server."""
from __future__ import annotations

import json

import httpx


class AIError(Exception):
    """kind: quota | auth | overloaded | timeout | bad_response | http | network | disabled"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


CITED_ITEM = {
    "type": "OBJECT",
    "properties": {
        "text": {"type": "STRING"},
        "citations": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["text", "citations"],
}

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "overview": {"type": "STRING"},
        "overview_citations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "key_points": {"type": "ARRAY", "items": CITED_ITEM},
        "agreements": {"type": "ARRAY", "items": CITED_ITEM},
        "disagreements": {"type": "ARRAY", "items": CITED_ITEM},
        "uncertainties": {"type": "ARRAY", "items": CITED_ITEM},
        "perspectives_status": {"type": "STRING", "enum": ["supported", "insufficient_evidence"]},
        "perspectives": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "claims": {"type": "ARRAY", "items": CITED_ITEM},
                    "caveats": {"type": "STRING"},
                },
                "required": ["name", "summary", "claims", "caveats"],
            },
        },
        "limitations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "background_topics": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": [
        "overview", "overview_citations", "key_points", "agreements", "disagreements", "uncertainties",
        "perspectives_status", "perspectives", "limitations", "background_topics",
    ],
}


class GeminiClient:
    def __init__(self, api_key: str, config: dict):
        self.api_key = api_key
        self.config = config
        self.model = config["model"]
        self.last_model_used = self.model

    def generate(self, system_prompt: str, user_payload: str, schema: dict | None = None) -> dict:
        if not self.api_key:
            raise AIError("disabled", "GEMINI_API_KEY is not configured")
        models = [self.config["model"], *self.config.get("fallback_models", [])]
        last_error: AIError | None = None
        tried: list[str] = []
        for model in models:
            try:
                result = self._call(model, system_prompt, user_payload, schema or RESPONSE_SCHEMA)
                self.last_model_used = model
                return result
            except AIError as exc:
                last_error = exc
                tried.append(str(exc)[:120])
                # Fall back when this model is unavailable, overloaded, rate-limited or
                # slow; an invalid key ("auth") would fail the same way on every model.
                if exc.kind == "auth":
                    raise
        assert last_error is not None
        raise AIError(last_error.kind, " | ".join(tried))

    def _call(self, model: str, system_prompt: str, user_payload: str, schema: dict) -> dict:
        generation_config = {
            "temperature": self.config.get("temperature", 0.2),
            "maxOutputTokens": self.config.get("max_output_tokens", 4096),
            "responseMimeType": "application/json",
            "responseSchema": schema,
        }
        if self.config.get("thinking_level") and model.startswith("gemini-3"):
            # Gemini 3 models: low thinking keeps answers fast and within the token limit.
            generation_config["thinkingConfig"] = {"thinkingLevel": self.config["thinking_level"]}
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_payload}]}],
            "generationConfig": generation_config,
        }
        url = self.config["endpoint"].format(model=model)
        try:
            resp = httpx.post(
                url,
                json=body,
                headers={"x-goog-api-key": self.api_key},
                timeout=self.config.get("request_timeout_seconds", 90),
            )
        except httpx.TimeoutException as exc:
            raise AIError("timeout", f"{model}: request timed out") from exc
        except httpx.HTTPError as exc:
            raise AIError("network", f"{model}: {type(exc).__name__}") from exc
        if resp.status_code == 429:
            raise AIError("quota", f"{model}: rate limit or quota exceeded (HTTP 429)")
        if resp.status_code in (500, 502, 503, 504):
            raise AIError("overloaded", f"{model}: provider busy or unavailable (HTTP {resp.status_code})")
        if resp.status_code in (401, 403):
            raise AIError("auth", f"{model}: API key rejected (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise AIError("http", f"{model}: HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            candidate = data["candidates"][0]
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"])
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            reason = (data.get("candidates") or [{}])[0].get("finishReason") or data.get("promptFeedback")
            raise AIError("bad_response", f"{model}: unusable response ({reason})") from exc
