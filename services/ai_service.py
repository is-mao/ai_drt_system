import os
import re
import time
import traceback
from models.system_config import SystemConfig
from services.failure_dict import lookup_failure
from services.historical_search import search_similar_failures

# Models to try in order (fallback if quota exhausted on one)
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

# Retry config (like stock_analysis)
MAX_RETRIES = 2
RETRY_DELAY = 30  # seconds


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
- Root Cause: 1-3 concise sentences.
- Action: numbered corrective steps. Only include steps for the actual cause category:
  * If operator issue: only operator-related steps
  * If test program issue: only test program-related steps
  * If test station/equipment issue: only station/equipment-related steps
  * May combine categories if multiple causes exist
  * Last step must always be: Retest and confirm PASS

Format your response EXACTLY as:
Root Cause: [plain text analysis]
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


def test_ai_connection(api_key):
    """Test if the Gemini API key is valid."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        for model_name in GEMINI_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents="Say 'connected' if you can read this.",
                )
                return True, f"[{model_name}] {response.text}"
            except Exception as e:
                if "quota" in str(e).lower() or "429" in str(e):
                    continue
                raise
        return False, "All models quota exhausted. Check billing at https://ai.google.dev"
    except ImportError:
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content("Say 'connected' if you can read this.")
            return True, response.text
        except Exception as e:
            return False, str(e)
    except Exception as e:
        return False, str(e)
