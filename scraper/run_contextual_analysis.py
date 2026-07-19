"""Executa a análise contextual com recuperação de respostas JSON truncadas.

O V4 Pro pode consumir parte do orçamento de saída com raciocínio e encerrar o
conteúdo no meio de uma string. Este wrapper preserva o pipeline existente, mas
faz uma segunda chamada curta, com maior orçamento de saída e thinking
desativado, quando a primeira resposta estiver truncada ou malformada.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

import contextual_analysis  # noqa: F401  # aplica contexto setorial/noticioso
import deepseek_analysis as base


COMPACT_SYSTEM_SUFFIX = """

Modo de recuperação de formato:
- devolva somente o objeto JSON, sem markdown;
- seja conciso: resumo com até 350 caracteres e tese com até 450 caracteres;
- forneça exatamente 2 pontos fortes e 2 pontos de atenção;
- cada texto de item deve ter até 240 caracteres;
- forneça no máximo 3 itens em monitorar e 2 limitações;
- feche corretamente todas as strings, listas e chaves JSON.
"""


def extract_json(content: str) -> dict[str, Any]:
    """Extrai um objeto JSON completo, aceitando cercas Markdown ocasionais."""
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        decoder = json.JSONDecoder()
        value, _end = decoder.raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("Resposta do DeepSeek não é um objeto JSON")
    return value


def response_error(response: requests.Response) -> str:
    body = (response.text or "").strip().replace("\n", " ")
    return f"DeepSeek HTTP {response.status_code}: {body[:600]}"


def make_payload(
    facts: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    model: str,
    thinking: str,
    compact: bool,
) -> dict[str, Any]:
    system = base.SYSTEM_PROMPT + (COMPACT_SYSTEM_SUFFIX if compact else "")
    user_prompt = base.prompt_for(facts, previous)
    if compact:
        user_prompt = (
            "A tentativa anterior não produziu JSON completo. Gere novamente uma versão curta, "
            "obedecendo exatamente ao esquema e usando somente as evidências fornecidas.\n\n"
            + user_prompt
        )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled" if compact else thinking},
        "max_tokens": 5200 if compact else 4200,
        "stream": False,
    }
    if not compact:
        payload["reasoning_effort"] = "medium"
    return payload


def request_once(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str | None, int]:
    response = session.post(url, headers=headers, json=payload, timeout=(20, 300))
    if response.status_code >= 400:
        raise RuntimeError(response_error(response))
    body = response.json()
    choice = body["choices"][0]
    content = choice.get("message", {}).get("content")
    finish_reason = choice.get("finish_reason")
    if not content:
        raise RuntimeError(f"DeepSeek retornou conteúdo vazio; finish_reason={finish_reason}")
    parsed = extract_json(content)
    return parsed, finish_reason, len(content)


def request_deepseek_resilient(
    facts: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    api_key: str,
    model: str,
    base_url: str,
    thinking: str,
    session: requests.Session,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    errors: list[str] = []

    # A primeira tentativa mantém o raciocínio solicitado. A segunda privilegia
    # exclusivamente a emissão de um JSON curto e completo.
    for compact in (False, True):
        payload = make_payload(
            facts,
            previous,
            model=model,
            thinking=thinking,
            compact=compact,
        )
        for attempt in range(1, 3):
            try:
                parsed, finish_reason, content_length = request_once(session, url, headers, payload)
                if finish_reason == "length":
                    raise RuntimeError(
                        f"resposta interrompida por limite; caracteres={content_length}"
                    )
                return parsed
            except (requests.RequestException, RuntimeError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
                label = "compacta" if compact else "completa"
                errors.append(f"{label} tentativa {attempt}: {exc}")
                # Erros de JSON/truncamento devem migrar logo para o modo compacto.
                if isinstance(exc, json.JSONDecodeError) or "interrompida por limite" in str(exc):
                    break
                if attempt < 2:
                    time.sleep(4 * attempt)
        if not compact:
            print("AVISO: resposta completa inválida; repetindo em formato compacto.")

    raise RuntimeError("Falha ao gerar JSON completo no DeepSeek: " + " | ".join(errors[-4:]))


base.request_deepseek = request_deepseek_resilient


if __name__ == "__main__":
    base.main()
