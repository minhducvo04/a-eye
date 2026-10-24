"""Local Ollama vision. Images exist only in memory; confidence is heuristic."""
import base64
from difflib import SequenceMatcher
from io import BytesIO
import json
import re
import math
import os
from pathlib import Path

import httpx
from PIL import Image


BOARDS = Path(__file__).resolve().parents[1] / "data" / "boards"


def parse_json(text):
    """Read the first JSON array/object, including fenced answers with prose."""
    if not isinstance(text, str):
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "[{":
            try:
                return decoder.raw_decode(text[index:])[0]
            except ValueError:
                continue
    return None


_LABEL_BOX = re.compile(r'"label"\s*:\s*"([^"]+)"\s*,\s*"bbox_2d"\s*:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)')
_CAPTION = re.compile(r'"caption"\s*:\s*"([^"]*)"')


def salvage_scene(text):
    """Qwen2.5-VL sometimes emits broken JSON (seen live: a box closed with '}' instead of ']').
    Pull caption and label/box pairs out with regexes instead of losing the whole answer."""
    if not isinstance(text, str):
        return None
    rows = [{"label": m[0], "bbox_2d": [float(v) for v in m[1:]]} for m in _LABEL_BOX.findall(text)]
    caption = _CAPTION.search(text)
    if not rows and not caption:
        return None
    return {"caption": caption.group(1) if caption else "", "objects": rows}


def normalized(text):
    return "".join(text.casefold().replace("_", "").split())


def headers_for(board_id):
    # Board IDs are filenames, never paths supplied by the caller.
    if not board_id or Path(board_id).name != board_id:
        return []
    try:
        return json.loads((BOARDS / (board_id + ".json")).read_text())["headers"]
    except FileNotFoundError:
        return []


def match_header(label, headers, fuzzy=False):
    if not isinstance(label, str) or not normalized(label):
        return None, 0
    label = normalized(label)
    scores = []
    for header in headers:
        aliases = {normalized(header["name"]), normalized(header.get("silkscreen", header["name"]))}
        if label in aliases:
            return header, .7
        scores.append((max(SequenceMatcher(None, label, alias).ratio() for alias in aliases), header))
    scores.sort(key=lambda entry: entry[0], reverse=True)
    if fuzzy and scores and scores[0][0] >= .8:
        if len(scores) == 1 or scores[0][0] > scores[1][0]:
            return scores[0][1], .5
    return None, 0


def box_normalized(box, width, height):
    if not isinstance(box, list) or len(box) != 4:
        return None
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in box):
        return None
    x1, y1, x2, y2 = [max(0, min(1, value / size))
                      for value, size in zip(box, (width, height, width, height))]
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2 - x1, y2 - y1]


class OllamaBackend:
    def __init__(self, *, url=None, model=None, transport=None, client=None):
        self.url = (url or os.environ.get("OLLAMA_URL", "http://100.93.176.7:11434")).rstrip("/")
        self.model = model or os.environ.get("VISION_MODEL", "qwen2.5vl:7b-q4_K_M")
        self.client = client if client is not None else httpx.Client(transport=transport)

    def _chat(self, body, prompt):
        with Image.open(BytesIO(base64.b64decode(body["image_b64"]))) as original:
            width, height = original.size
            scale = 1280 / max(width, height)
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            resized = original.convert("RGB").resize(size, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            resized.save(buffer, format="JPEG")
        response = self.client.post(self.url + "/api/chat", timeout=20, json={
            "model": self.model, "stream": False, "options": {"temperature": 0},
            "messages": [{"role": "user", "content": prompt,
                          "images": [base64.b64encode(buffer.getvalue()).decode("ascii")]}],
        })
        response.raise_for_status()
        try:
            self.last_text = response.json()["message"]["content"]
            answer = parse_json(self.last_text)
        except (ValueError, KeyError, TypeError):
            self.last_text, answer = "", None
        return answer, size

    def health(self):
        responses = []
        for endpoint in ("ps", "tags"):
            response = self.client.get(self.url + "/api/" + endpoint, timeout=2)
            response.raise_for_status()
            responses.append(response.json().get("models", []))
        loaded, available = responses
        def is_model(row):
            return self.model in (row.get("name"), row.get("model"))
        current = next((row for row in loaded if is_model(row)), None)
        gpu = "not_loaded"
        if current is not None:
            vram, size = current.get("size_vram", 0), current.get("size", 0)
            gpu = "cpu" if vram == 0 else "gpu" if vram == size else "partial"
        return {"ok": any(is_model(row) for row in available), "models": [self.model],
                "gpu": gpu, "fake": False}

    def scene(self, body, scenario):
        queries = body.get("queries", [])
        limit = body.get("max_objects", 8)
        answer, (width, height) = self._chat(body,
            'Describe the frame in one short sentence and locate objects. First try these queries '
            'in order: ' + json.dumps(queries) + '. For each visible query match, use the exact '
            'query text as its label. Omit queries that are not visible. Then add other salient '
            f'objects, returning at most {limit} objects total. Return JSON '
            '{"caption": str, "objects": [{"label": str, "bbox_2d": [x1,y1,x2,y2]}]} '
            'with boxes in this image\'s own pixel coordinates.')
        result = {"caption": "Could not describe the frame.", "objects": [], "source": "ollama"}
        if not (isinstance(answer, dict) and isinstance(answer.get("objects"), list)):
            answer = salvage_scene(getattr(self, "last_text", ""))
        if not isinstance(answer, dict):
            return result
        if isinstance(answer.get("caption"), str) and answer["caption"].strip():
            result["caption"] = answer["caption"].strip()
        rows = answer.get("objects")
        if not isinstance(rows, list):
            return result
        query_order = {}
        for index, query in enumerate(queries):
            query_order.setdefault(normalized(query), index)
        found = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("label"), str):
                continue
            label = row["label"].strip()
            box = box_normalized(row.get("bbox_2d"), width, height)
            if not label or box is None:
                continue
            priority = query_order.get(normalized(label), len(queries))
            # Heuristic scores, not calibrated VLM probabilities.
            found.append((priority, {"label": label, "bbox": box,
                                     "conf": .7 if priority < len(queries) else .5}))
        found.sort(key=lambda entry: entry[0])
        result["objects"] = [{"id": f"o{index + 1}", **row}
                             for index, (_, row) in enumerate(found[:limit])]
        return result

    def identify(self, body, scenario):
        candidates = body["candidates"]
        choices = ", ".join(f'{item} ({item.replace("_", " ")})' for item in candidates)
        answer, _ = self._chat(body, 'Identify the held PC part. Candidates: ' + choices +
                               '. Return JSON {"item": one candidate ID or "unknown", "confidence": 0..1}.')
        if not isinstance(answer, dict):
            return {"item": "unknown", "conf": .3}
        item = answer.get("item")
        conf = answer.get("confidence", .3)
        if type(conf) not in (int, float) or not math.isfinite(conf):
            conf = .3
        return {"item": item if item in candidates else "unknown", "conf": max(0, min(.85, conf))}

    def locate(self, body, scenario):
        headers = headers_for(body["board_id"])
        target, _ = match_header(body["header"], headers)
        if target is None:
            return {"found": False, "conf": 0}
        labels = [header.get("silkscreen", header["name"]) for header in headers]
        answer, (width, height) = self._chat(body,
            'Find the printed silkscreen label text for ' + target.get("silkscreen", target["name"]) +
            ' and all these board headers: ' + json.dumps(labels) +
            '. Return [{"label": str, "bbox_2d": [x1,y1,x2,y2]}] in this image\'s own pixel coordinates. '
            'Boxes must surround the printed text, not connectors. Omit labels that are not visible.')
        rows = answer if isinstance(answer, list) else [answer]
        found = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            header, conf = match_header(row.get("label"), headers, fuzzy=True)
            box = box_normalized(row.get("bbox_2d"), width, height)
            if header and box:
                name = header["name"]
                if name not in found or conf > found[name]["conf"]:
                    found[name] = {"header": name, "bbox": box, "conf": conf}
        requested = found.pop(target["name"], None)
        result = {"found": requested is not None, "conf": requested["conf"] if requested else 0,
                  "others": list(found.values())}
        if requested:
            result.update(bbox=requested["bbox"], source="ocr")
        return result

    def verify(self, body, scenario):
        headers = headers_for(body["board_id"])
        target, _ = match_header(body["header"], headers)
        label = target.get("silkscreen", target["name"]) if target else body["header"]
        answer, _ = self._chat(body, 'Is a connector plugged into the header labeled ' + label +
                               '? Which printed label is it next to? Return JSON {"plugged": bool, "label": str}.')
        if (not isinstance(answer, dict) or type(answer.get("plugged")) is not bool
                or not isinstance(answer.get("label"), str)):
            return {"pass": False, "abstain": True, "conf": .3,
                    "reason": "Could not interpret the connection; hold still and move closer."}
        seen, _ = match_header(answer["label"], headers)
        passed = bool(answer["plugged"] and target and seen and target["name"] == seen["name"])
        result = {"pass": passed, "conf": .75,
                  "reason": "Connection appears matched." if passed else "Connection not confirmed at the requested header."}
        result["reason"] += " VLM confidence is below the 0.8 green gate; independent verification is required."
        if seen:
            result["seen_header"] = seen["name"]
        return result


class AutoBackend:
    """Try the PC for every request; only connection failures/timeouts use demo data."""
    def __init__(self, ollama, fake):
        self.ollama, self.fake = ollama, fake

    def _call(self, operation, *args):
        try:
            return getattr(self.ollama, operation)(*args)
        except (httpx.ConnectError, httpx.TimeoutException):
            import logging
            logging.getLogger(__name__).warning("ollama unreachable, using fake")
            return getattr(self.fake, operation)(*args)

    def health(self):
        return self._call("health")

    def identify(self, body, scenario):
        return self._call("identify", body, scenario)

    def scene(self, body, scenario):
        return self._call("scene", body, scenario)

    def locate(self, body, scenario):
        return self._call("locate", body, scenario)

    def verify(self, body, scenario):
        return self._call("verify", body, scenario)
