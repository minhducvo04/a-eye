"""Run from the repo root: .venv/bin/python -m vision.probe_ollama."""
import argparse
import base64
from io import BytesIO
import json
import sys
from time import perf_counter

from PIL import Image, ImageDraw, ImageFont

from contracts import validate
from vision.ollama import OllamaBackend


def synthetic_board():
    image = Image.new("RGB", (1280, 960), (15, 65, 40))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    target = None
    for label, position in [("CPU_FAN", (160, 140)), ("SYS_FAN1", (850, 360)),
                            ("F_PANEL", (600, 780))]:
        bounds = draw.textbbox(position, label, font=font)
        draw.text(position, label, font=font, fill="white")
        if label == "CPU_FAN":
            x1, y1, x2, y2 = bounds
            target = [x1 / 1280, y1 / 960, (x2 - x1) / 1280, (y2 - y1) / 960]
    stream = BytesIO()
    image.save(stream, format="JPEG")
    return base64.b64encode(stream.getvalue()).decode("ascii"), target


def iou(box, target):
    x, y, w, h = box
    tx, ty, tw, th = target
    overlap = max(0, min(x + w, tx + tw) - max(x, tx)) * max(0, min(y + h, ty + th) - max(y, ty))
    union = w * h + tw * th - overlap
    return overlap / union if union else 0


def synthetic_scene():
    image = Image.new("RGB", (1280, 960), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=36)
    draw.rectangle((100, 100, 300, 300), fill="red")
    draw.ellipse((700, 100, 950, 350), fill="blue")
    draw.polygon([(450, 550), (300, 800), (600, 800)], fill="green")
    for label, position in [("red square", (100, 320)), ("blue circle", (700, 370)),
                            ("green triangle", (300, 820))]:
        draw.text(position, label, font=font, fill="black")
    stream = BytesIO()
    image.save(stream, format="JPEG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def main(argv=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", action="store_true", help="Ground labelled synthetic shapes")
    args = parser.parse_args(argv)
    image, target = (synthetic_scene(), None) if args.scene else synthetic_board()
    backend = OllamaBackend()
    try:
        health = backend.health()
        validate("health_response", health)
        print("health:", json.dumps(health), flush=True)
        start = perf_counter()
        if args.scene:
            result = backend.scene({"image_b64": image, "queries": ["red square"]}, "ok")
            result["ms"] = (perf_counter() - start) * 1000
            validate("scene_response", result)
            print(json.dumps(result))
            return
        result = backend.locate({"image_b64": image, "board_id": "demo-b650", "header": "CPU_FAN"}, "ok")
        result["ms"] = (perf_counter() - start) * 1000
        validate("locate_response", result)
        score = iou(result["bbox"], target) if result["found"] else 0
        print(f'CPU_FAN found={result["found"]} IoU={score:.4f} ms={result["ms"]:.1f}')
    finally:
        backend.client.close()


if __name__ == "__main__":
    main(sys.argv[1:])
