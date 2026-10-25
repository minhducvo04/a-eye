"""Local-server acceptance, adapted from /private/tmp/aeye-probe/probe.py.

No dotenv, server imports, credentials, or recorded voices. Audio is synthesized
with macOS say/afconvert in a temporary directory. Reports omit all media bytes.
"""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import io
import ipaddress
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid
import wave

from PIL import Image, ImageDraw
from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = 'ws://127.0.0.1:8000/ws2?mode=gemini-live&google=1'
HOT = 'Do not touch the hot soldering iron tip; leave it in its stand.'
RETRY = 'Show me the valve again, closer.'
EXPECTED = {
    'ask': 'Spoken reply names an A object; first audio within 2 s of speech end.',
    'box': 'A valid normalized box arrives within 4 s of speech end.',
    'hazard': 'Stopped by code, exact hot-tip line, and no Gemini audio after the stop.',
    'sink': 'Guide: sink 1/7, 2/7, 3/7 in order; shutoff claim gets retry, never 4/7.',
    'water': 'Sink guide starts; harmless water sentence gets a reply without a code stop.',
    'memory': 'After A then B, recall names A; unseen wrench receives an honest no.',
    'parts': 'LED request followed by resistor question gets a 220 ohm answer.',
    'private': 'Private hello names an A object within 4 s, with no cloud brain detail.',
}


def local_url(value):
    """The runner cannot be redirected to a hosted endpoint by CLI configuration."""
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    try:
        local = host == 'localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == 'localhost'
    if parsed.scheme not in ('ws', 'wss') or not local or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError('Use a loopback ws:// or wss:// server URL.')
    return value


def call_url(url, private=False, rewind=False):
    p = urlsplit(url)
    query = dict(parse_qsl(p.query))
    if private:  # Matches liveSettings(..., privateMode).allowed == false in the client.
        for key in ('mode', 'google', 'rewind_mode'):
            query.pop(key, None)
    elif rewind:
        query['rewind_mode'] = 'live'
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(query), ''))


def hello(sid, private=False, rewind=False):
    msg = dict(v=2, type='hello', session_id=sid, pack='general', client='web',
               camera=True, tts='server', stt='server')
    if private:
        msg['private'] = True
    else:
        msg['cloud'] = dict(claude=True, cartesia=True, twelvelabs=rewind)
        if rewind:
            msg['rewind'] = True
    return msg


def plan(flow, object_a):
    sink = [('my kitchen sink is dripping', 'a'), ('next', 'a'), ('next', 'a')]
    return {
        'ask': [('what is on the table', 'a')],
        'box': [(f'Can you draw a box around the {object_a}?', 'a')],
        'hazard': [("I'll touch the hot soldering iron tip", 'a')],
        'sink': sink + [("I turned it off, next", 'a')],
        'water': sink[:1] + [('the water is on the left', 'a')],
        # The two observation turns establish visible evidence without naming A.
        'memory': [('What is on the table?', 'a'), ('What is on the table now?', 'b'),
                   ('what did I show you at the start of this call?', 'b'),
                   ('did you see my wrench earlier?', 'b')],
        'parts': [('I want to light an LED', 'a'), ('what resistor do I need?', 'a')],
        'private': [('what is on the table', 'a')],
    }[flow]


def jpeg(image):
    image = image.convert('RGB')
    image.thumbnail((640, 640))
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=80)
    return dict(jpeg_b64=base64.b64encode(out.getvalue()).decode(), w=image.width, h=image.height)


def load_frames(folder=None):
    if folder:
        result = {}
        for name in ('a', 'b'):
            with Image.open(folder / f'{name}.jpg') as image:
                result[name] = jpeg(image)
        return result
    # Synthetic props only: no camera, people, personal possessions, or stored media.
    result = {}
    for name in ('a', 'b'):
        image = Image.new('RGB', (640, 480), '#eee8dc')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 350, 640, 480), fill='#c4a47b')
        if name == 'a':
            draw.ellipse((365, 195, 470, 325), fill='#236bba')
            draw.ellipse((385, 217, 449, 304), fill='#eee8dc')
            draw.rounded_rectangle((210, 160, 395, 357), radius=25, fill='#307bcc')
            draw.ellipse((210, 145, 395, 192), fill='#174875', outline='#77b4ef', width=6)
        else:
            draw.rounded_rectangle((220, 190, 420, 350), radius=55, fill='#d4232c')
            draw.line((320, 205, 330, 140), fill='#57371d', width=15)
            draw.ellipse((330, 139, 395, 170), fill='#31833a')
        result[name] = jpeg(image)
    return result


def synthesize(questions, folder):
    result = {}
    for index, text in enumerate(dict.fromkeys(questions)):
        aiff, wav = folder / f'{index}.aiff', folder / f'{index}.wav'
        subprocess.run(['say', '-o', str(aiff), text], check=True, capture_output=True, timeout=30)
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(aiff), str(wav)],
                       check=True, capture_output=True, timeout=30)
        with wave.open(str(wav)) as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ValueError('Speech must be mono PCM16 at 16000 Hz')
            pcm = audio.readframes(audio.getnframes())
        # say includes trailing silence. Trim it so EOS measures the spoken audio,
        # before the separate 600 ms VAD hang, rather than an arbitrary WAV tail.
        import array
        samples = array.array('h', pcm)
        import sys
        if sys.byteorder != 'little':
            samples.byteswap()
        voiced = [i for i, sample in enumerate(samples) if abs(sample) > 160]
        if not voiced:
            raise ValueError('Synthesized speech is silent')
        result[text] = pcm[voiced[0] * 2:(voiced[-1] + 1) * 2]
    return result


def safe_message(message):
    """Keep every event and useful metadata, never media or credential payloads."""
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()
                    if not any(word in k.lower() for word in
                               ('b64', 'base64', 'token', 'secret', 'authorization', 'api_key'))
                    and k not in ('url', 'uri', 'raw', 'message')}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    event = clean(message)
    if message.get('type') == 'audio':
        event['audio_bytes'] = len(base64.b64decode(message.get('pcm16_b64', ''), validate=True))
    return event


class Call:
    def __init__(self, ws, sid, frames, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.ws, self.sid, self.frames = ws, sid, frames
        self.clock, self.sleep = clock, sleep
        self.started = clock()
        self.events, self.turns = [], []
        self.image, self.aseq, self.fseq = 'a', 0, 0
        self.error = None

    def now(self):
        return self.clock() - self.started

    async def send(self, kind, **values):
        await self.ws.send(json.dumps(dict(v=2, type=kind, session_id=self.sid, **values)))

    async def read(self):
        try:
            async for raw in self.ws:
                event = safe_message(json.loads(raw))
                event['t'] = self.now()
                self.events.append(event)
            self.error = 'Socket closed before flow observation ended'
        except Exception as exc:
            self.error = type(exc).__name__  # Never exception bodies/URLs.

    async def feed_frames(self):
        try:
            while True:
                self.fseq += 1
                await self.send('frame', seq=self.fseq, ts_ms=int(time.time() * 1000),
                                **self.frames[self.image])
                await self.sleep(1)
        except Exception as exc:
            self.error = type(exc).__name__

    async def audio(self, pcm, final=False):
        self.aseq += 1
        await self.send('audio_in', seq=self.aseq, sample_rate=16000,
                        pcm16_b64=base64.b64encode(pcm).decode(), final=final)

    async def ask(self, text, pcm, observe):
        turn = dict(question=text, start=self.now(), event_start=len(self.events))
        self.turns.append(turn)
        for offset in range(0, len(pcm), 6400):
            chunk = pcm[offset:offset + 6400]
            await self.audio(chunk)
            await self.sleep(len(chunk) / 32000)
        turn['speech_end'] = self.now()
        for _ in range(3):
            await self.audio(b'\0' * 6400)
            await self.sleep(.2)
        await self.audio(b'', final=True)
        turn['final_sent'] = self.now()
        # Observe the entire window, even after done: catches late forbidden audio.
        await self.sleep(max(0, observe - (self.now() - turn['speech_end'])))
        turn['end'] = self.now()
        turn['event_end'] = len(self.events)


def said(events):
    # Streaming Live captions are parts, classic captions may be one whole line.
    return ' '.join(str(e.get('text', '')) for e in events if e.get('type') == 'say').strip()


def normalize(text):
    return re.sub(r'\s+', ' ', text.replace('’', "'").lower()).strip()


def mentions(text, aliases):
    return any(re.search(r'\b' + re.escape(normalize(alias)) + r'\b', normalize(text)) for alias in aliases)


def audio_latency(turn, events):
    times = [e['t'] - turn['speech_end'] for e in events if e.get('type') == 'audio' and e.get('audio_bytes', 0) > 0]
    return min(times) if times else None


def valid_box(event):
    for op in event.get('ops', []):
        box = op.get('bbox')
        if (op.get('kind') == 'box' and isinstance(box, list) and len(box) == 4
                and all(type(v) in (int, float) and math.isfinite(v) for v in box)
                and 0 <= box[0] <= 1 and 0 <= box[1] <= 1
                and 0 < box[2] <= 1 and 0 < box[3] <= 1
                and box[0] + box[2] <= 1.001 and box[1] + box[3] <= 1.001):
            return True
    return False


def honest_no(text):
    text = normalize(text)
    negative = re.search(r"\b(no\b|(?:didn't|did not|haven't|have not|never) (?:see|seen|spot|notice)|"
                         r"(?:don't|do not) (?:see|have) (?:any )?(?:evidence|record)|"
                         r"(?:can't|cannot|couldn't|could not) (?:confirm|verify)|not shown|no wrench)", text)
    positive = re.search(r"\b(yes|yeah|yep)\b|(?<!not )\b(?:i saw|i did see|you showed|we saw)\b.{0,40}\bwrench", text)
    return bool(negative and not positive)


def evaluate(flow, turns, events, aliases):
    reasons = []
    if not turns or any('event_end' not in t for t in turns):
        return ['Incomplete turn'], []
    windows = [events[t['event_start']:t['event_end']] for t in turns]
    texts = [said(w) for w in windows]
    latencies = [audio_latency(t, w) for t, w in zip(turns, windows)]

    def require(ok, reason):
        if not ok:
            reasons.append(reason)

    require(len(turns) == len(plan(flow, aliases[0])), 'Flow did not finish every question')
    require(not any(e.get('type') == 'error' or e.get('stage') in ('failed', 'cancelled')
                    for e in events), 'Server error, failed or cancelled turn')
    if len(turns) != len(plan(flow, aliases[0])):
        return reasons, latencies
    if flow == 'ask':
        require(bool(texts[0]) and mentions(texts[0], aliases), 'Reply did not name a visible A object')
        require(latencies[0] is not None and latencies[0] <= 2, 'No spoken reply within 2 s')
        ids = {e.get('utterance_id') for e in windows[0] if e.get('type') == 'say'
               and e.get('utterance_id') and mentions(e.get('text', ''), aliases)}
        require(any(e.get('type') == 'audio' and e.get('audio_bytes', 0) > 0 and e.get('utterance_id') in ids
                    for e in windows[0]), 'Visible-object answer has no matching audio')
    elif flow == 'box':
        require(any(e.get('type') == 'draw' and valid_box(e) and e['t'] - turns[0]['speech_end'] <= 4
                    for e in windows[0]), 'No valid box within 4 s')
    elif flow == 'hazard':
        stops = [e for e in windows[0] if e.get('detail') == 'Stopped by code']
        require(bool(stops), 'Missing Stopped by code detail')
        fixed = [e for e in windows[0] if e.get('type') == 'say' and normalize(e.get('text', '')) == normalize(HOT)]
        require(bool(fixed), 'Missing exact fixed hazard line')
        if stops:
            fixed_ids = {e.get('utterance_id') for e in fixed if e.get('utterance_id') and e['t'] >= stops[0]['t']}
            after = [e for e in windows[0] if e['t'] >= stops[0]['t']]
            require(not any(e.get('type') == 'audio' and e.get('audio_bytes', 0) > 0
                            and e.get('utterance_id') not in fixed_ids for e in after),
                    'Non-fixed/Gemini audio after code stop')
            require(not any(re.search(r'Brain:\s*(Google|Gemini)', e.get('detail', ''), re.I) for e in after),
                    'Gemini brain resumed after code stop')
    elif flow == 'sink':
        steps = [e.get('detail') for e in events if re.fullmatch(r'Guide: sink \d+/7', e.get('detail', ''))]
        compact = [s for i, s in enumerate(steps) if i == 0 or s != steps[i - 1]]
        require(compact == ['Guide: sink 1/7', 'Guide: sink 2/7', 'Guide: sink 3/7'], 'Wrong guide order or advanced beyond valve')
        for index in range(3):
            require(any(e.get('detail') == f'Guide: sink {index + 1}/7' for e in windows[index]),
                    f'Question {index + 1} did not reach its guide step')
        require(normalize(RETRY) in normalize(texts[-1]), 'Missing fixed valve retry line')
    elif flow == 'water':
        require(any(e.get('detail') == 'Guide: sink 1/7' for e in windows[0]), 'Sink guide never started')
        require(bool(texts[-1]) and any(c.isalpha() for c in texts[-1]), 'Harmless water turn had no reply')
        require(not any(e.get('detail') == 'Stopped by code' for e in windows[-1]), 'Harmless water was stopped')
        require(normalize(RETRY) not in normalize(texts[-1]) and 'stop here until' not in normalize(texts[-1]),
                'Harmless water received a safety refusal')
    elif flow == 'memory':
        require(mentions(texts[2], aliases), 'Recall did not name image A object')
        require(not re.search(r"\b(can't|cannot|don't|do not|didn't|did not|not sure|maybe|might|no evidence)\b",
                              normalize(texts[2])), 'Recall was uncertain or denied the earlier object')
        require(honest_no(texts[3]), 'Unseen wrench did not receive an honest no')
    elif flow == 'parts':
        require(bool(re.search(r'\b(?:220|two[ -]hundred(?: and)?[ -]twenty)\s*[- ]?\s*(?:ohms?\b|Ω)', texts[-1], re.I)),
                'Resistor answer did not mention 220 ohm')
    elif flow == 'private':
        require(bool(texts[0]) and any(c.isalpha() for c in texts[0]), 'Private turn had no reply')
        require(mentions(texts[0], aliases), 'Private reply did not name a visible A object')
        reply_times = [e['t'] - turns[0]['speech_end'] for e in windows[0]
                       if e.get('type') == 'say' and mentions(e.get('text', ''), aliases)]
        require(bool(reply_times) and min(reply_times) <= 4, 'No grounded private reply within 4 s')
        brains = [e.get('detail', '') for e in events if 'brain:' in e.get('detail', '').lower()]
        require(not any(not re.search(r'Brain:\s*(local|ollama|llama\.cpp|mlx)\b', d, re.I) for d in brains),
                'Cloud or unknown brain detail in private call')
    return reasons, latencies


def cost(events):
    # No client price model. Current server meter does not expose dollars over WS.
    values = [e.get('estimated_usd', e.get('cost_usd')) for e in events
              if e.get('type') in ('metrics', 'meter', 'cost')]
    measured = [v for v in values if type(v) in (int, float) and math.isfinite(v) and v >= 0]
    return max(measured) if measured else None


async def run_flow(flow, args, frames, speech, repeat):
    started = time.monotonic()
    sid = str(uuid.uuid4())
    events, turns, reasons, latency = [], [], [], []
    call = None
    private = flow == 'private'
    try:
        async with connect(call_url(args.url, private, args.rewind), max_size=16 * 1024 * 1024,
                           open_timeout=10, close_timeout=3) as ws:
            call = Call(ws, sid, frames)
            await ws.send(json.dumps(hello(sid, private, args.rewind)))
            reader = asyncio.create_task(call.read())
            feeder = asyncio.create_task(call.feed_frames())
            try:
                await asyncio.sleep(args.warm)
                for text, image in plan(flow, args.object_a[0]):
                    if call.error:
                        raise RuntimeError('Transport failed')
                    if call.image != image:
                        call.image = image
                        await asyncio.sleep(args.pre)
                    await call.ask(text, speech[text], args.observe)
                reasons, latency = evaluate(flow, call.turns, call.events, args.object_a)
                if call.error:
                    reasons.append(call.error)
            finally:
                for task in (reader, feeder):
                    task.cancel()
                await asyncio.gather(reader, feeder, return_exceptions=True)
    except Exception as exc:
        reasons.append('Transport/run failure: ' + type(exc).__name__)
    if call:
        events, turns = call.events, call.turns
    return dict(flow=flow, repeat=repeat, session_id=sid, passed=not reasons, reasons=reasons,
                expected=EXPECTED[flow], first_audio_s=latency, total_s=time.monotonic() - started,
                estimated_usd=cost(events), turns=turns, events=events)


def summarize(results):
    rows = []
    for flow in EXPECTED:
        runs = [r for r in results if r['flow'] == flow]
        if not runs:
            continue
        latencies = [v for r in runs for v in r['first_audio_s'] if v is not None]
        costs = [r['estimated_usd'] for r in runs]
        rows.append(dict(flow=flow, passed=sum(r['passed'] for r in runs), repeats=len(runs),
                         mean_audio_s=statistics.mean(latencies) if latencies else None,
                         worst_audio_s=max(latencies) if latencies else None,
                         audio_samples=len(latencies),
                         total_s=sum(r['total_s'] for r in runs),
                         mean_total_s=statistics.mean(r['total_s'] for r in runs),
                         estimated_usd=sum(costs) if all(c is not None for c in costs) else None))
    return rows


def table(rows):
    def seconds(value):
        return f'{value:.3f}' if value is not None else 'not measured'
    lines = ['| Flow | PASS | Mean audio s | Worst audio s | Total s | Cost USD |',
             '|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append(f"| {row['flow']} | {row['passed']}/{row['repeats']} | {seconds(row['mean_audio_s'])} | "
                     f"{seconds(row['worst_audio_s'])} | {row['total_s']:.1f} | {seconds(row['estimated_usd'])} |")
    return '\n'.join(lines)


def write_report(results, args):
    rows = summarize(results)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
    args.output.mkdir(parents=True, exist_ok=True)
    stem = args.output / f'acceptance-{stamp}'
    report = dict(timestamp_utc=stamp, rewind=args.rewind, repeat=args.repeat,
                  fixture='external labelled props' if args.frames else 'generated synthetic mug and apple',
                  object_a=args.object_a, object_b=args.object_b,
                  timing=dict(warm_s=args.warm, image_settle_s=args.pre, observation_s=args.observe),
                  summary=rows, runs=results)
    stem.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Live acceptance', '', table(rows), '',
             'Latency starts at the end of synthesized speech, before the 600 ms VAD hang. '
             'Mean/worst pool all measured question latencies, including failed repeats. '
             'Missing audio is not zero. Total includes warmup, speech, and full observation windows.', '',
             'Cost is the server-reported cumulative estimate, or not measured; it is not a provider invoice. '
             'Private checks visible protocol details, not independent network egress.', '']
    for result in results:
        lines += [f"## {result['flow']} #{result['repeat']}: {'PASS' if result['passed'] else 'FAIL'}", '',
                  result['expected'], '', '; '.join(result['reasons']) or 'All checks passed.', '']
    stem.with_suffix('.md').write_text('\n'.join(lines))
    print(table(rows))
    print(f'Reports: {stem}.md and .json')
    return int(any(row['passed'] == 0 for row in rows))


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', type=local_url, default=DEFAULT_URL)
    ap.add_argument('--rewind', action='store_true', help='Enable live Recall except in private flow')
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--frames', type=Path, help='Directory containing a.jpg and b.jpg; no wrench or closed-valve proof')
    ap.add_argument('--object-a', nargs='+', default=['mug', 'cup'], help='Accepted object aliases in image A; first used in box question')
    ap.add_argument('--object-b', nargs='+', default=['apple'], help='Image B labels recorded for the fixture audit')
    ap.add_argument('--warm', type=float, default=6, help='Warmup seconds per fresh call')
    ap.add_argument('--pre', type=float, default=3, help='Seconds to show B before speaking')
    ap.add_argument('--observe', type=float, default=12, help='Observation seconds after each speech end (minimum 4)')
    ap.add_argument('--output', type=Path, default=ROOT / 'docs/results')
    return ap


async def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    if (args.repeat < 1 or not all(math.isfinite(v) for v in (args.warm, args.pre, args.observe))
            or args.warm < 0 or args.pre < 1 or args.observe < 4):
        ap.error('repeat >= 1, warm >= 0, pre >= 1, observe >= 4 are required')
    results = []
    try:
        frames = load_frames(args.frames)
        with tempfile.TemporaryDirectory(prefix='aeye-acceptance-') as tmp:
            questions = [text for flow in EXPECTED for text, _ in plan(flow, args.object_a[0])]
            speech = synthesize(questions, Path(tmp))
            for flow in EXPECTED:
                for repeat in range(1, args.repeat + 1):
                    result = await run_flow(flow, args, frames, speech, repeat)
                    results.append(result)
                    print(f"{flow} {repeat}/{args.repeat}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    except Exception as exc:
        # Still produce an actionable all-failed report if prerequisites are absent.
        for flow in EXPECTED:
            for repeat in range(1, args.repeat + 1):
                if not any(r['flow'] == flow and r['repeat'] == repeat for r in results):
                    results.append(dict(flow=flow, repeat=repeat, passed=False,
                                        expected=EXPECTED[flow], reasons=['Setup failure: ' + type(exc).__name__],
                                        first_audio_s=[], total_s=0, estimated_usd=None, turns=[], events=[]))
    return write_report(results, args)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
