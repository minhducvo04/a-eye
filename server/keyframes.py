"""Small in-memory scene signatures, scan selection and caption history."""
import base64
from collections import deque
import io
import os

from PIL import Image


def signature(jpeg_b64):
    with Image.open(io.BytesIO(base64.b64decode(jpeg_b64, validate=True))) as image:
        return image.convert('L').resize((32, 32), Image.Resampling.BILINEAR).tobytes()


def difference(a, b):
    if len(a) != 1024 or len(b) != 1024:
        raise ValueError('Expected 32x32 grayscale signatures')
    return sum(abs(x - y) for x, y in zip(a, b)) / 1024


class KeyframeGate:
    def __init__(self, threshold=34.5, heartbeat_s=10.0, min_gap_s=0.5):
        self.threshold = float(os.environ.get('KEYFRAME_THRESHOLD', threshold))
        self.heartbeat_s = float(os.environ.get('KEYFRAME_HEARTBEAT_S', heartbeat_s))
        self.min_gap_s = min_gap_s
        self.previous = None
        self.scanned_at = None

    def should_scan(self, signature, now):
        reason = 'skip'
        if self.previous is None:
            reason = 'first'
        elif now - self.scanned_at >= self.min_gap_s:
            if difference(signature, self.previous) >= self.threshold:
                reason = 'change'
            elif now - self.scanned_at >= self.heartbeat_s:
                reason = 'heartbeat'
        if reason != 'skip':
            self.previous = signature
            self.scanned_at = now
        return reason != 'skip', reason


class SceneMemory:
    """Keep observation times internally so ages stay correct between turns."""
    def __init__(self):
        self.entries = deque(maxlen=8)

    def add(self, scene, observed_at):
        entry = dict(caption=scene['caption'], labels=[o['label'] for o in scene['objects']],
                     observed_at=observed_at)
        if self.entries and self.entries[0]['caption'] == entry['caption']:
            self.entries.popleft()
        self.entries.appendleft(entry)

    def snapshot(self, now, current=True):
        return [dict(caption=e['caption'], labels=list(e['labels']),
                     age_s=round(max(0, now - e['observed_at'])),
                     **({'now': True} if current and i == 0 else {}))
                for i, e in enumerate(self.entries)]
