"""Executa a análise contextual com recuperação de respostas vazias ou truncadas.

O V4 Pro pode consumir o orçamento com raciocínio e retornar ``content`` vazio,
ou pode encerrar o JSON no meio de uma string. Este wrapper mantém o V4 Pro como
modelo da análise final e tenta variantes progressivamente mais simples antes de
considerar a execução perdida.
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

FIRST_ANALYSIS_PROMPT_SUFFIX = """

Regra de primeira execução:
- quando o campo `anterior` for nulo, `mudancas_desde_anterior.texto` deve apenas
  informar que esta é a primeira análise disponível;
- nesse caso específico, `mudancas_desde_anterior.evidencias` pode ser uma lista
  vazia, pois a inexistência de análise anterior é metadado do sistema, não uma
  afirmação fundamentalista sobre a companhia.
"""

# A regra vale para a resposta completa e para as tentativas compactas.
base.SYSTEM_PROMPT += FIRST_ANALYSIS_PROMPT_SUFFIX
_ORIGINAL_VALIDATE_CLAIM = base.validate_claim


def _is_first_analysis_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    phrases = (
        "primeira análise",
        "primeira analise",
        "não há análise anterior",
        "nao ha analise anterior",
        "sem análise anterior",
        "sem analise anterior",
        "ainda não existe análise anterior",
        "ainda nao existe analise anterior",
    )
    return any(phrase in normalized for phrase in phrases)


def validate_claim_resilient(
    value: Any,
    field: str,
    evidence_keys: set[str],
) -> dict[str, Any]:
    """Permite evidência vazia somente para o marco inicial da primeira análise.

    As demais afirmações continuam passando pelo validador original e exigem uma
    ou mais chaves existentes em ``fatos.evidencias``.
    """
    if field == "mudancas_desde_anterior" and isinstance(value, dict):
        text = base.require_text(value.get("texto"), f"{field}.texto", 500)
        evidence = value.get("evidencias")
        if evidence in (None, []) and _is_first_analysis_text(text):
            return {"texto": text, "evidencias": []}
    return _ORIGINAL_VALIDATE_CLAIM(value, field, evidence_keys)


base.validate_claim = validate_claim_resilient


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
    return f"DeepSeek HTTP {response.status_code}: {body[:800]}"


def content_text(value: Any) -> str:
    """Normaliza os formatos textuais observados em APIs compatíveis com OpenAI."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("output_text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def response_diagnostics(body: dict[str, Any], choice: dict[str, Any]) -> str:
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = content_text(message.get("content"))
    reasoning = content_text(message.get("reasoning_content"))
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return (
        f"finish_reason={choice.get('finish_reason')}; content_chars={len(content)}; "
        f"reasoning_chars={len(reasoning)}; prompt_tokens={usage.get('prompt_tokens')}; "
        f"completion_tokens={usage.get('completion_tokens')}; total_tokens={usage.get('total_tokens')}"
    )


def make_payload(
    facts: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    model: str,
    thinking: str,
    mode: str,
) -> dict[str, Any]:
    compact = mode != "full"
    system = base.SYSTEM_PROMPT + (COMPACT_SYSTEM_SUFFIX if compact else "")
    user_prompt = base.prompt_for(facts, previous)
    if compact:
        user_prompt = (
            "A tentativa anterior não produziu conteúdo final utilizável. Gere novamente uma versão curta, "
            "obedecendo exatamente ao esquema e usando somente as evidências fornecidas. "
            "Não descreva seu raciocínio; entregue diretamente o JSON final.\n\n"
            + user_prompt
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 7000 if compact else 6500,
        "stream": False,
    }

    if mode == "full":
        payload["response_format"] = {"type": "json_object"}
        payload["thinking"] = {"type": thinking}
        payload["reasoning_effort"] = "low"
    elif mode == "compact_json":
        payload["response_format"] = {"type": "json_object"}
        payload["thinking"] = {"type": "disabled"}
    elif mode == "compact_compat":
        # Compatibilidade máxima: alguns gateways retornam conteúdo vazio quando
        # recebem campos opcionais, mesmo respondendo HTTP 200.
        pass
    else:  # pragma: no cover - proteção contra erro de programação
        raise ValueError(f"Modo desconhecido: {mode}")
    return payload


def request_once(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str | None, int, str]:
    response = session.post(url, headers=headers, json=payload, timeout=(20, 360))
    if response.status_code >= 400:
        raise RuntimeError(response_error(response))
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(f"DeepSeek retornou resposta não JSON: {response.text[:800]}") from exc
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"DeepSeek retornou resposta sem choices; chaves={sorted(body.keys())}")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = content_text(message.get("content"))
    # Alguns gateways usam output_text em vez de content.
    if not content:
        content = content_text(message.get("output_text")) or content_text(body.get("output_text"))
    finish_reason = choice.get("finish_reason")
    diagnostics = response_diagnostics(body, choice)
    if not content:
        raise RuntimeError("DeepSeek retornou conteúdo vazio; " + diagnostics)
    parsed = extract_json(content)
    return parsed, finish_reason, len(content), diagnostics


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

    modes = ("full", "compact_json", "compact_compat")
    for mode in modes:
        payload = make_payload(
            facts,
            previous,
            model=model,
            thinking=thinking,
            mode=mode,
        )
        attempts = 1 if mode == "full" else 2
        for attempt in range(1, attempts + 1):
            try:
                parsed, finish_reason, content_length, diagnostics = request_once(
                    session, url, headers, payload
                )
                if finish_reason == "length":
                    raise RuntimeError(
                        f"resposta interrompida por limite; caracteres={content_length}; {diagnostics}"
                    )
                if mode != "full":
                    print(f"Análise recuperada no modo {mode}.")
                return parsed
            except (
                requests.RequestException,
                RuntimeError,
                KeyError,
                IndexError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                errors.append(f"{mode} tentativa {attempt}: {exc}")
                # Resposta vazia, JSON inválido ou corte por limite pedem mudança
                # imediata de formato, não repetição da mesma chamada completa.
                text = str(exc).lower()
                if mode == "full" or "conteúdo vazio" in text or "interrompida por limite" in text:
                    break
                if attempt < attempts:
                    time.sleep(4 * attempt)
        if mode == "full":
            print("AVISO: resposta completa indisponível; tentando V4 Pro sem raciocínio.")
        elif mode == "compact_json":
            print("AVISO: JSON compacto indisponível; tentando modo de compatibilidade.")

    raise RuntimeError("Falha ao gerar JSON completo no DeepSeek: " + " | ".join(errors[-6:]))


base.request_deepseek = request_deepseek_resilient


if __name__ == "__main__":
    base.main()
