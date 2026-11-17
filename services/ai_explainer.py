import json, logging, os, urllib.request

log = logging.getLogger("inspector")
SEV_TEXT = {"None": "no material severity", "Low": "low severity - cosmetic or marginal deviation",
            "Medium": "medium severity - may affect quality grade", "High": "high severity - likely functional or critical-to-quality impact"}
ACTIONS = {"PASS": "Release the component through the normal flow. Keep the record for traceability.",
           "REVIEW REQUIRED": "Hold the component for a manual visual check of the highlighted region before release.",
           "FAIL": "Reject or quarantine the component, route it for secondary inspection and review the upstream process step."}
DISCLAIMER = ("Generated from the inspection engine's outputs; the explanation does not independently verify a physical defect.")


def region(d, w, h):
    cx, cy = (d["x"] + d["width"] / 2) / w, (d["y"] + d["height"] / 2) / h
    return f"{'upper' if cy < .33 else 'lower' if cy > .66 else 'central'}-{'left' if cx < .33 else 'right' if cx > .66 else 'middle'}".replace("central-middle", "centre")


def local_explain(c):
    w, h, ds = c.get("width") or 1, c.get("height") or 1, c.get("defects", [])
    lines = [f"**Inspection Summary**",
             f"The inspected {c['category']} item scored {c['anomaly_score']:.2f} on the anomaly scale and was classified **{c['status']}**."]
    if ds:
        top = max(ds, key=lambda d: d["confidence"])
        lines[-1] += f" The strongest candidate region is in the {region(top, w, h)} area."
        lines += ["", "**Detected anomalies**"] + [
            f"- {d['defect_type']} ({d['severity']}) in the {region(d, w, h)} region, box {d['width']}x{d['height']} px at ({d['x']}, {d['y']})" for d in ds]
    else:
        lines += ["", "**Detected anomalies**", "- No localised anomalous regions above the configured threshold."]
    lines += ["", f"**Severity:** {c['severity']} - {SEV_TEXT.get(c['severity'], '')}", "",
              f"**Recommended action:** {ACTIONS[c['status']]}", "",
              f"_Method: {c['inference_mode']}. {DISCLAIMER}_"]
    return "\n".join(lines)


def gemini_call(prompt, config, system=None):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or config.get("LLM_PROVIDER", "gemini") != "gemini":
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.get('GEMINI_MODEL')}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log.warning("Gemini call failed, using local engine: %s", e)
        return None


SYSTEM = ("You explain results of an automated visual inspection engine. Use only the supplied JSON. Do not claim you verified a "
          "physical defect; detections are model/heuristic outputs. Be concise and use the headings: Inspection Summary, "
          "Detected anomalies, Severity, Recommended action.")


def explain(ctx, config):
    out = gemini_call("Inspection record:\n" + json.dumps(ctx), config, SYSTEM)
    if out:
        return out, "gemini"
    return local_explain(ctx), "local-template"


def llm_status(config):
    has = bool(os.getenv("GEMINI_API_KEY", "").strip())
    return {"provider": config.get("LLM_PROVIDER", "gemini"), "api_key_configured": has,
            "active": "gemini" if has else "local-template"}


def assistant_reply(question, rec, prev, config):
    """rec/prev are dicts (inspection to_dict) or None."""
    if rec is None:
        return "Select or run an inspection first - I answer using saved inspection records.", "local-template"
    ctx = {"current": rec, "previous": prev}
    out = gemini_call(f"Question: {question}\n\nRecords:\n{json.dumps(ctx)}", config, SYSTEM +
                      " Answer the user's question about these records; 'previous' may be null.")
    if out:
        return out, "gemini"
    q, w, h, ds = question.lower(), rec["width"] or 1, rec["height"] or 1, rec["defects"]
    if "compare" in q or "previous" in q:
        if not prev:
            return "There is no earlier inspection to compare against.", "local-template"
        return (f"Current {rec['inspection_code']}: {rec['status']}, score {rec['anomaly_score']}, {rec['defect_count']} defect(s), severity {rec['severity']}.\n"
                f"Previous {prev['inspection_code']}: {prev['status']}, score {prev['anomaly_score']}, {prev['defect_count']} defect(s), severity {prev['severity']}.\n"
                f"Score change: {rec['anomaly_score'] - prev['anomaly_score']:+.2f}."), "local-template"
    if "heatmap" in q:
        return ("The heatmap shows per-pixel anomaly evidence from the selected detector: warm colours (red/yellow) mean stronger deviation "
                f"from what the detector considers normal. Method used: {rec['inference_mode']}."), "local-template"
    if "region" in q or "suspicious" in q or "where" in q:
        if not ds:
            return "No region exceeded the threshold, so there is no suspicious region to point to.", "local-template"
        t = max(ds, key=lambda d: d["confidence"])
        return f"The most suspicious region is the {t['defect_type']} in the {region(t, w, h)} area, at ({t['x']}, {t['y']}), {t['width']}x{t['height']} px, strength {t['confidence']:.2f}.", "local-template"
    if "next" in q or "inspect" in q and "should" in q:
        return ACTIONS[rec["status"]], "local-template"
    if "why" in q or "fail" in q:
        return (f"The result is {rec['status']} because the anomaly score {rec['anomaly_score']} was compared with the configured threshold, "
                f"with {rec['defect_count']} localised region(s). " + (", ".join(d['defect_type'] for d in ds) if ds else "No regions were localised.")), "local-template"
    if "defect" in q or "detect" in q or "what" in q:
        return ("Detected: " + "; ".join(f"{d['defect_type']} ({d['severity']}) at ({d['x']}, {d['y']})" for d in ds)) if ds else "No defects were localised in this inspection.", "local-template"
    return "I can explain defects, why a part failed, the suspicious region, the heatmap, next steps, or compare with the previous inspection.", "local-template"
