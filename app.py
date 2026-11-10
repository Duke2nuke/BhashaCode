"""BhashaCode — explain code in Indian languages.

Flask web app for the BharatCode Build League (solo entry by
Aarambh Maan Shrestha). Paste a code snippet, pick a language, get a
plain-language explanation plus a line-by-line breakdown, powered by
the BharatCode model API (qwen-3.8-27b). Without a
``BHARATCODE_API_KEY`` the app runs in clearly labelled MOCK mode.

Run:  pip install -r requirements.txt
       python app.py          # http://127.0.0.1:5000
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from bharatcode_client import SUPPORTED_LANGUAGES, BharatCodeError, explain_code

app = Flask(__name__)

EXAMPLE_CODE = (
    "def total(prices):\n"
    "    total = 0\n"
    "    for price in prices:\n"
    "        total = total + price\n"
    "    return total\n"
    "\n"
    "print(total([10, 20, 30]))\n"
)


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        languages=SUPPORTED_LANGUAGES,
        example=EXAMPLE_CODE,
        mock_mode=not bool(os.environ.get("BHARATCODE_API_KEY")),
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "mode": "mock" if not os.environ.get("BHARATCODE_API_KEY") else "live",
        }
    )


@app.route("/explain", methods=["POST"])
def explain():
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        code = payload.get("code", "")
        lang = payload.get("language", "en")
    else:
        code = request.form.get("code", "")
        lang = request.form.get("language", "en")

    try:
        result = explain_code(code, lang)
    except ValueError as exc:
        # Bad input: empty code, unknown language, too long.
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        return render_template(
            "index.html",
            languages=SUPPORTED_LANGUAGES,
            example=EXAMPLE_CODE,
            mock_mode=not bool(os.environ.get("BHARATCODE_API_KEY")),
            error=str(exc),
            code=code,
            language=lang,
        ), 400
    except BharatCodeError as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 502
        return render_template(
            "index.html",
            languages=SUPPORTED_LANGUAGES,
            example=EXAMPLE_CODE,
            mock_mode=not bool(os.environ.get("BHARATCODE_API_KEY")),
            error=f"BharatCode API error: {exc}",
            code=code,
            language=lang,
        ), 502

    if request.is_json:
        return jsonify(result)
    return render_template(
        "index.html",
        languages=SUPPORTED_LANGUAGES,
        example=EXAMPLE_CODE,
        mock_mode=result["mode"] == "mock",
        result=result,
        code=code,
        language=lang,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
