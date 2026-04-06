import os
import re
import json
import time
import traceback
import urllib.parse
import urllib.request
import urllib.error
from models.system_config import SystemConfig
from services.failure_dict import lookup_failure
from services.historical_search import search_similar_failures

# Models to try in order (fallback if quota exhausted on one)
GEMINI_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash"]

# Retry config (like stock_analysis)
MAX_RETRIES = 2
RETRY_DELAY = 30  # seconds

TRANSLATE_PROVIDER_GEMINI = "Gemini Flash"
TRANSLATE_PROVIDER_GLM = "GLM-4.7-Flash"
TRANSLATE_PROVIDER_GOOGLE = "Google Translate"

_LANG_LABELS = {"zh": "Chinese (Simplified)", "vi": "Vietnamese", "en": "English"}
_GOOGLE_LANGS = {"auto": "auto", "zh": "zh-CN", "vi": "vi", "en": "en"}
_GOOGLE_CHUNK_SIZE = 1800


def _get_api_keys():
    """Get all Gemini API keys: database config first, then env var fallback.
    Supports comma-separated keys for quota rotation."""
    keys = []
    db_key = SystemConfig.get_value("gemini_api_key")
    if db_key:
        keys.extend([k.strip() for k in db_key.split(",") if k.strip()])
    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key:
        for k in env_key.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


def _get_glm_api_key():
    return SystemConfig.get_value("glm_api_key") or os.environ.get("GLM_API_KEY", "")


def _get_google_translate_api_key():
    return SystemConfig.get_value("google_translate_api_key") or os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")


def _http_json_request(url, method="GET", headers=None, body=None, timeout=30):
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        return json.loads(payload) if payload else {}


def _extract_gemini_text(payload):
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join([text for text in texts if text]).strip()


def _build_plain_translation_prompt(text, target_lang):
    lang_name = _LANG_LABELS.get(target_lang, target_lang)
    return (
        "You are a professional technical translator for manufacturing and defect analysis text.\n"
        f"Translate the following text into {lang_name}.\n"
        "Rules:\n"
        "- Keep technical abbreviations unchanged.\n"
        "- Preserve line breaks and numbering.\n"
        "- Return plain text only.\n"
        "- Do not add explanation.\n\n"
        f"Text:\n{text}"
    )


def _translate_with_gemini_flash(text, target_lang):
    api_keys = _get_api_keys()
    if not api_keys:
        raise RuntimeError("Gemini Flash API key is not configured. Add it in Settings.")

    prompt = _build_plain_translation_prompt(text, target_lang)
    for api_key in api_keys:
        for model_name in GEMINI_MODELS:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                + model_name
                + ":generateContent?key="
                + urllib.parse.quote(api_key)
            )
            body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            try:
                payload = _http_json_request(
                    url, method="POST", headers={"Content-Type": "application/json"}, body=body
                )
                result = _extract_gemini_text(payload)
                if result:
                    return result
            except urllib.error.HTTPError as exc:
                err = exc.read().decode("utf-8", errors="ignore")
                if exc.code in (429, 503) or "quota" in err.lower():
                    continue
                raise RuntimeError(err or f"Gemini request failed with HTTP {exc.code}")
            except Exception as exc:
                raise RuntimeError(str(exc))

    raise RuntimeError("Gemini Flash request failed or quota exhausted.")


def _translate_with_glm_flash(text, target_lang):
    api_key = _get_glm_api_key()
    if not api_key:
        raise RuntimeError("GLM-4.7-Flash API key is not configured. Add it in Settings.")

    prompt = _build_plain_translation_prompt(text, target_lang)
    body = json.dumps(
        {
            "model": "glm-4.7-flash",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        payload = _http_json_request(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            method="POST",
            headers=headers,
            body=body,
        )
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(err or f"GLM request failed with HTTP {exc.code}")
    except Exception as exc:
        raise RuntimeError(str(exc))

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("GLM returned empty response.")
    message = (choices[0] or {}).get("message") or {}
    return (message.get("content") or "").strip()


def _translate_with_google_public(text, source_lang, target_lang):
    def _split_keep_newlines(raw_text, chunk_size):
        parts = []
        current = ""
        for line in raw_text.splitlines(keepends=True):
            if len(current) + len(line) <= chunk_size:
                current += line
            else:
                if current:
                    parts.append(current)
                if len(line) <= chunk_size:
                    current = line
                else:
                    for i in range(0, len(line), chunk_size):
                        parts.append(line[i : i + chunk_size])
                    current = ""
        if current:
            parts.append(current)
        return parts or [""]

    def _translate_chunk(chunk):
        params = {
            "client": "gtx",
            "sl": _GOOGLE_LANGS.get(source_lang, "auto"),
            "tl": _GOOGLE_LANGS.get(target_lang, target_lang),
            "dt": "t",
            "ie": "UTF-8",
            "oe": "UTF-8",
            "q": chunk,
        }
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
        payload = _http_json_request(url)
        if not payload or not isinstance(payload, list) or not payload[0]:
            raise RuntimeError("Google Translate returned empty response.")
        return "".join([segment[0] for segment in payload[0] if segment and segment[0]])

    try:
        chunks = _split_keep_newlines(text, _GOOGLE_CHUNK_SIZE)
        translated = [_translate_chunk(chunk) for chunk in chunks]
        return "".join(translated).strip()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(err or f"Google Translate request failed with HTTP {exc.code}")
    except Exception as exc:
        raise RuntimeError(str(exc))


def _translate_with_google_official(text, source_lang, target_lang):
    api_key = _get_google_translate_api_key()
    if not api_key:
        raise RuntimeError("Google Cloud Translation API key is not configured.")

    payload = {
        "q": text,
        "target": _GOOGLE_LANGS.get(target_lang, target_lang),
        "format": "text",
        "model": "nmt",
    }
    mapped_source = _GOOGLE_LANGS.get(source_lang, "auto")
    if mapped_source != "auto":
        payload["source"] = mapped_source

    body = json.dumps(payload).encode("utf-8")
    url = "https://translation.googleapis.com/language/translate/v2?key=" + urllib.parse.quote(api_key)
    resp = _http_json_request(url, method="POST", headers={"Content-Type": "application/json"}, body=body)

    data = (resp or {}).get("data") or {}
    translations = data.get("translations") or []
    if not translations:
        raise RuntimeError("Google Cloud Translation returned empty response.")
    return (translations[0] or {}).get("translatedText", "").strip()


def _translate_text_by_provider(text, provider, target_lang, source_lang="auto"):
    if not text:
        return ""

    if provider == TRANSLATE_PROVIDER_GOOGLE:
        # Prefer official Cloud Translation for better quality when configured,
        # then gracefully fallback to public endpoint.
        try:
            return _translate_with_google_official(text, source_lang, target_lang)
        except Exception:
            return _translate_with_google_public(text, source_lang, target_lang)
    if provider == TRANSLATE_PROVIDER_GLM:
        return _translate_with_glm_flash(text, target_lang)
    return _translate_with_gemini_flash(text, target_lang)


def analyze_log_with_ai(log_content, failure="", defect_class="", station="", bu="", keywords="", exclude_id=None):
    """Analyze log content using Google Gemini AI.

    Returns: {'success': bool, 'source': str, 'root_cause': str, 'action': str, 'details': list|None}
    """
    # Tier 1: Try Google Gemini AI (with multiple key rotation)
    api_keys = _get_api_keys()
    ai_error = None
    for api_key in api_keys:
        try:
            result = _call_gemini(api_key, log_content, failure, defect_class, station, bu, keywords)
            if result:
                root_cause, action = _parse_ai_response(result)
                return {
                    "success": True,
                    "source": "ai",
                    "root_cause": root_cause,
                    "action": action,
                    "suggestion": result,
                    "details": None,
                }
        except Exception as e:
            ai_error = str(e)
            err_str = ai_error.lower()
            if "quota" in err_str or "resource_exhausted" in err_str or "429" in err_str:
                print(f"API key ...{api_key[-6:]} quota exhausted, trying next key...")
                continue
            print(f"Gemini API error: {e}")
            traceback.print_exc()
            break

    # Tier 2: Search historical data
    if failure:
        similar = search_similar_failures(failure, station=station, bu=bu, exclude_id=exclude_id)
        if similar:
            return {
                "success": True,
                "source": "history",
                "root_cause": similar[0].get("root_cause", ""),
                "action": similar[0].get("action", ""),
                "suggestion": similar[0].get("root_cause", ""),
                "details": similar,
                "ai_error": ai_error,
            }

    # Tier 3: Static failure dictionary
    if failure and bu:
        dict_result = lookup_failure(bu, failure)
        if dict_result:
            defect_cls, defect_val, root_cause = dict_result
            return {
                "success": True,
                "source": "dict",
                "root_cause": root_cause,
                "action": "",
                "suggestion": root_cause,
                "details": [{"defect_class": defect_cls, "defect_value": defect_val, "root_cause": root_cause}],
                "ai_error": ai_error,
            }

    # Tier 4: No suggestion available
    return {
        "success": False,
        "source": "none",
        "root_cause": None,
        "action": None,
        "suggestion": None,
        "details": None,
        "ai_error": ai_error
        or ("No API key configured. Set GEMINI_API_KEY in .env or Settings page." if not api_keys else None),
    }


def _parse_ai_response(text):
    """Parse AI response to extract Root Cause and Action separately."""
    root_cause = ""
    action = ""

    # Try to parse structured response
    rc_match = re.search(
        r"Root\s*Cause[:\s]*(.+?)(?=(?:Recommended\s+)?Action[:\s]|$)", text, re.IGNORECASE | re.DOTALL
    )
    action_match = re.search(r"(?:Recommended\s+)?Action[:\s]*(.+?)$", text, re.IGNORECASE | re.DOTALL)

    if rc_match:
        root_cause = rc_match.group(1).strip()
    if action_match:
        raw_action = action_match.group(1).strip()
        # Ensure numbered lines are on separate lines
        raw_action = re.sub(r"(?<!\n)(\d+\.\s)", r"\n\1", raw_action)
        action = raw_action.strip()

    # Fallback: if parsing failed, put everything in root_cause
    if not root_cause and not action:
        root_cause = text.strip()

    # Strip all markdown formatting: **bold**, *italic*, `code`
    root_cause = _strip_markdown(root_cause)
    action = _strip_markdown(action)

    return root_cause, action


def _strip_markdown(text):
    """Remove markdown formatting from text."""
    if not text:
        return text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold**
    text = re.sub(r"\*(.+?)\*", r"\1", text)  # *italic*
    text = re.sub(r"`(.+?)`", r"\1", text)  # `code`
    return text.strip()


def beautify_root_cause_action(root_cause, action):
    """Use Gemini AI to beautify/improve Root Cause and Action text.

    Returns: {'success': bool, 'root_cause': str, 'action': str, 'error': str|None}
    """
    api_keys = _get_api_keys()
    if not api_keys:
        return {"success": False, "error": "No API key configured. Set GEMINI_API_KEY in .env or Settings page."}

    prompt = f"""You are a technical writing expert for manufacturing defect reports.
Your task is to improve the clarity and readability of the following Root Cause and Action text.

Rules:
- Keep the original technical meaning and facts UNCHANGED.
- Improve grammar, sentence structure, and clarity.
- Use concise professional language suitable for engineering reports.
- Plain text ONLY. No markdown, no bold (**), no asterisks, no bullet symbols.
- Root Cause: 1-3 clear, concise sentences.
- Action: numbered steps. Keep the same number of steps, just improve wording.
- If the original text is already good, return it with only minor improvements.
- Do NOT add new information or diagnosis that isn't in the original text.

Original Root Cause:
{root_cause}

Original Action:
{action}

Format your response EXACTLY as:
Root Cause: [improved text]
Action:
1. [improved step]
2. [improved step]
..."""

    for api_key in api_keys:
        try:
            try:
                from google import genai

                client = genai.Client(api_key=api_key)
                for model_name in GEMINI_MODELS:
                    try:
                        response = client.models.generate_content(model=model_name, contents=prompt)
                        result_text = response.text
                        new_rc, new_action = _parse_ai_response(result_text)
                        return {
                            "success": True,
                            "root_cause": new_rc or root_cause,
                            "action": new_action or action,
                        }
                    except Exception as e:
                        err_str = str(e).lower()
                        if "quota" in err_str or "429" in err_str:
                            continue
                        raise
            except ImportError:
                result_text = _call_gemini_legacy(api_key, prompt, "", "", "", "", "")
                if result_text:
                    new_rc, new_action = _parse_ai_response(result_text)
                    return {
                        "success": True,
                        "root_cause": new_rc or root_cause,
                        "action": new_action or action,
                    }
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str:
                continue
            return {"success": False, "error": str(e)}

    return {"success": False, "error": "All API keys exhausted (quota). Please try again later."}


def translate_root_cause_action(
    root_cause, action, target_lang, provider=TRANSLATE_PROVIDER_GEMINI, source_lang="auto"
):
    """Translate Root Cause and Action text using the selected provider.

    Args:
        root_cause: Root Cause text to translate
        action: Action text to translate
        target_lang: Target language code ('zh' for Chinese, 'vi' for Vietnamese, 'en' for English)
        provider: Translation provider name
        source_lang: Source language code or 'auto'

    Returns: {'success': bool, 'root_cause': str, 'action': str, 'error': str|None}
    """
    try:
        translated_root_cause = _translate_text_by_provider(root_cause, provider, target_lang, source_lang)
        translated_action = _translate_text_by_provider(action, provider, target_lang, source_lang)
        return {
            "success": True,
            "provider": provider,
            "root_cause": translated_root_cause or root_cause,
            "action": translated_action or action,
        }
    except Exception as e:
        return {"success": False, "provider": provider, "error": str(e)}


def _build_prompt(bu, station, failure, defect_class, log_content, keywords=""):
    """Build the shared AI analysis prompt."""
    keywords_section = ""
    if keywords:
        keywords_section = f"\nUser-provided Keywords/Hints: {keywords}\nIMPORTANT: Pay special attention to the keywords above. They indicate the engineer's suspected direction for root cause analysis. Use them to guide your diagnosis.\n"

    return f"""You are a manufacturing defect analysis expert for Cisco networking equipment.
Analyze the following test logs (sequence log and buffer log) and diagnose the root cause.

BU: {bu}
Station: {station}
Failure Step: {failure}
Defect Class: {defect_class}
{keywords_section}
{log_content[:8000]}

IMPORTANT formatting rules:
- Plain text ONLY. No markdown, no bold (**), no asterisks, no special formatting.
- Root Cause: 1-2 SHORT sentences MAXIMUM. Be extremely concise — state ONLY the direct cause and the specific component/signal involved. No background explanation, no log quoting, no context repetition. Example good format: "DIMM slot A1 memory module defective, causing memory test failure."
- Action: numbered corrective steps (2-4 steps max). Only include steps for the actual cause category:
  * If operator issue: only operator-related steps
  * If test program issue: only test program-related steps
  * If test station/equipment issue: only station/equipment-related steps
  * May combine categories if multiple causes exist
  * Each step should be one short sentence
  * Last step must always be: Retest and confirm PASS

Format your response EXACTLY as:
Root Cause: [1-2 short sentences only]
Action:
1. [step]
2. [step]
3. Retest and confirm PASS"""


def _call_gemini(api_key, log_content, failure, defect_class, station, bu, keywords=""):
    """Call Google Gemini API with retry-on-rate-limit (like stock_analysis)."""
    try:
        from google import genai
    except ImportError:
        return _call_gemini_legacy(api_key, log_content, failure, defect_class, station, bu, keywords)

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(bu, station, failure, defect_class, log_content, keywords)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        for model_name in GEMINI_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "quota" in err_str or "resource_exhausted" in err_str or "429" in err_str:
                    print(f"Quota exhausted for {model_name}, trying next model...")
                    continue
                raise

        # All models exhausted for this attempt — parse retry delay from error or use default
        if attempt < MAX_RETRIES:
            delay = _parse_retry_delay(str(last_error)) or RETRY_DELAY
            print(f"All models rate-limited. Waiting {delay}s before retry {attempt + 2}/{MAX_RETRIES + 1}...")
            time.sleep(delay)

    raise last_error


def _parse_retry_delay(error_str):
    """Extract retry delay from Gemini error message (e.g. 'Please retry in 57.2s')."""
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
    if match:
        return min(int(float(match.group(1))) + 2, 90)  # cap at 90s, add 2s buffer
    return None


def _call_gemini_legacy(api_key, log_content, failure, defect_class, station, bu, keywords=""):
    """Fallback: Call Gemini using deprecated google.generativeai SDK."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    prompt = _build_prompt(bu, station, failure, defect_class, log_content, keywords)

    last_error = None
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "quota" in err_str or "resource_exhausted" in err_str or "429" in err_str:
                print(f"Quota exhausted for {model_name}, trying next model...")
                continue
            raise

    raise last_error


def test_ai_connection(provider, api_key, **kwargs):
    """Test whether the requested provider credentials are valid."""
    provider = (provider or "gemini").lower()

    if provider == "glm":
        try:
            body = json.dumps(
                {
                    "model": "glm-4-flash",
                    "messages": [{"role": "user", "content": "Reply with connected."}],
                    "temperature": 0,
                }
            ).encode("utf-8")
            payload = _http_json_request(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                body=body,
            )
            choices = payload.get("choices") or []
            msg = ((choices[0] or {}).get("message") or {}).get("content", "connected") if choices else "connected"
            return True, msg
        except Exception as e:
            return False, str(e)

    keys = [k.strip() for k in api_key.split(",") if k.strip()]
    if not keys:
        return False, "No API key provided."

    if provider == "gemini":
        last_error = ""
        for key in keys:
            for model_name in GEMINI_MODELS:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models/"
                    + model_name
                    + ":generateContent?key="
                    + urllib.parse.quote(key)
                )
                body = json.dumps({"contents": [{"parts": [{"text": "Reply with connected."}]}]}).encode("utf-8")
                try:
                    payload = _http_json_request(
                        url, method="POST", headers={"Content-Type": "application/json"}, body=body
                    )
                    text = _extract_gemini_text(payload) or "connected"
                    key_hint = f"...{key[-4:]}" if len(key) > 4 else "****"
                    return True, f"[{model_name}] {text} (key {key_hint})"
                except Exception as e:
                    last_error = str(e)
                    if "quota" in last_error.lower() or "429" in last_error:
                        continue
        return False, last_error or "All keys failed"

    return False, f"Unsupported provider: {provider}"
