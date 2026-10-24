"""Phase B data: synthetic talker turns from COCO captions, answered by an OPEN local teacher (no Claude outputs).

  scenes  COCO 2014 train captions + instances (annotations CC BY 4.0) -> scenes.jsonl (text only, no images)
  gen     teacher writes a user question per scene, then answers it with the production talker prompt;
          code filters keep only SAY-format, short, symbol-free replies; handwritten safety turns are added
  The held-out eval (eval/brain/cases.json) is never read for training; questions too close to it are dropped.

  python -m eval.brain.distill scenes --coco <annotations dir> --n 1200 --out scenes.jsonl
  python -m eval.brain.distill gen --scenes scenes.jsonl --teacher qwen3.6:35b-a3b-q4_K_M --out train.jsonl
"""
import argparse
import json
import os
import random
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from eval.brain.run import cases, style, talker_prompt

OLLAMA = os.environ.get('OLLAMA_URL', 'http://100.93.176.7:11434').rstrip('/')
KITCHEN = {'knife', 'fork', 'spoon', 'bowl', 'cup', 'bottle', 'wine glass', 'oven', 'microwave', 'sink',
           'refrigerator', 'toaster', 'banana', 'apple', 'orange', 'broccoli', 'carrot', 'pizza', 'sandwich',
           'hot dog', 'donut', 'cake', 'dining table'}
# Handwritten safety turns (pack, scene caption, question, safe reply). Gated PC questions never reach the
# talker (refuse() runs first), so these cover what the gates do not: kitchen heat and household electricity.
SAFETY = [
    ('cooking', 'A pan of oil on the stove, smoking heavily.', 'Oil is smoking a lot, keep going?',
     "SAY: That's too hot, pull the pan off the heat and turn it down. If it ever catches fire, put a lid on it, never water."),
    ('cooking', 'A small grease fire in a frying pan.', 'It caught fire, should I pour water on it?',
     'SAY: No water, that makes it explode. Turn off the burner and slide a lid over the pan.'),
    ('cooking', 'A gas stove with the knob turned and no flame.', 'I smell gas, should I light it again?',
     "SAY: Don't light anything. Turn the knob off, open a window and leave the kitchen until the smell clears."),
    ('cooking', 'Chicken in a pan, a thermometer reading 150 F.', 'Is the chicken done at 150?',
     'SAY: Not yet, chicken needs 165 F in the thickest part. Give it a few more minutes and check again.'),
    ('general', 'A wall outlet with a scorch mark.', 'Can I keep using this burnt outlet?',
     "SAY: Stop using it and unplug everything there. Have an electrician check it, scorch marks mean it's overheating."),
    ('general', 'A frayed phone charger cable with exposed wire.', 'The wire is showing, is it fine to use?',
     "SAY: Don't use it, exposed wire can shock you or start a fire. Unplug it and get a new cable."),
    ('general', 'A space heater next to curtains.', 'Can I leave the heater here overnight?',
     'SAY: Move it at least a meter from the curtains first. Better to switch it off before you sleep.'),
    ('general', 'A ceiling light with the cover off and wires visible.', 'Can I swap this light with the switch on?',
     'SAY: Turn the breaker off first, not just the switch. Then check the wires are dead before you touch them.'),
    ('assemble', 'A tall bookshelf standing without a wall strap.', 'Do I really need the wall strap?',
     'SAY: Yes, tall shelves can tip over, especially with kids around. Screw the strap into a stud before you load it.'),
    ('assemble', 'A drill with a long bit near a wall.', 'Can I drill here for the shelf?',
     "SAY: Check for wires and pipes first with a detector. Don't drill straight above or below an outlet or switch."),
]


def scenes(coco, n, out, seed=7):
    caps = json.loads((Path(coco) / 'captions_train2014.json').read_text())
    inst = json.loads((Path(coco) / 'instances_train2014.json').read_text())
    names = {c['id']: c['name'] for c in inst['categories']}
    images = {im['id']: im for im in inst['images']}
    shortest = {}
    for c in caps['annotations']:
        text = c['caption'].strip()
        if c['image_id'] not in shortest or len(text) < len(shortest[c['image_id']]):
            shortest[c['image_id']] = text
    objects = {}
    for a in inst['annotations']:
        if a.get('iscrowd') or a['area'] < 2000:
            continue
        objects.setdefault(a['image_id'], []).append(a)
    ids = sorted(i for i in objects if i in shortest and len(objects[i]) >= 2)
    random.Random(seed).shuffle(ids)
    with open(out, 'w') as f:
        for image_id in ids[:n]:
            im = images[image_id]
            anns = sorted(objects[image_id], key=lambda a: -a['area'])[:6]
            objs = []
            for k, a in enumerate(anns):
                x, y, w, h = a['bbox']
                objs.append(dict(id=f'o{k + 1}', label=names[a['category_id']],
                                 bbox=[round(x / im['width'], 3), round(y / im['height'], 3),
                                       round(w / im['width'], 3), round(h / im['height'], 3)]))
            pack = 'cooking' if sum(o['label'] in KITCHEN for o in objs) >= 2 else 'general'
            f.write(json.dumps(dict(coco_id=image_id, pack=pack, caption=shortest[image_id].rstrip('.') + '.',
                                    objects=objs)) + '\n')


def chat(model, messages, think, num_predict):
    body = dict(model=model, stream=False, think=think, keep_alive='30m', messages=messages,
                options=dict(num_ctx=4096, num_predict=num_predict, temperature=0.7))
    r = httpx.post(OLLAMA + '/api/chat', json=body, timeout=600)
    r.raise_for_status()
    return r.json()['message']['content']


QUESTION = ('You write realistic test data for a live camera helper app. Scene notes the helper sees: {notes}\n'
            'Write one short thing a person in this scene might say to the helper out loud: a question or request '
            'about something visible (where, which, how, is it ok, what next). Optionally one or two earlier '
            'lines of conversation. Return only JSON {{"conversation": ["user: ...", "helper: ..."], "text": "..."}}.')


def held_out_questions():
    data = cases()
    return [c['text'] for c in data['talker']] + [c['question'] for c in data['expert']]


def too_close(text, held):
    return any(SequenceMatcher(None, text.lower(), h.lower()).ratio() > .75 for h in held)


def gen(scene_path, teacher, out, think, limit):
    held = held_out_questions()
    done = 0
    if Path(out).exists():
        done = sum(1 for _ in open(out))
    rows = [json.loads(line) for line in open(scene_path)][:limit]
    kept = dropped = 0
    with open(out, 'a') as f:
        if done == 0:
            for pack, caption, text, reply in SAFETY:
                case = dict(pack=pack, caption=caption, objects=[], conversation=[], text=text)
                system, user = talker_prompt(case)
                f.write(json.dumps(dict(source='safety', messages=[
                    dict(role='system', content=system), dict(role='user', content=user),
                    dict(role='assistant', content=reply)])) + '\n')
        for scene in rows[max(0, done - len(SAFETY)):]:
            notes = json.dumps(dict(caption=scene['caption'], objects=[o['label'] for o in scene['objects']]))
            try:
                q = json.loads(re.search(r'\{.*\}', chat(teacher, [dict(role='user', content=QUESTION.format(
                    notes=notes))], False, 120), re.S).group(0))
                text = str(q['text']).strip()
                conversation = [str(x) for x in q.get('conversation', [])][:2]
                if not text or too_close(text, held):
                    raise ValueError('held-out overlap or empty')
                case = dict(pack=scene['pack'], caption=scene['caption'], objects=scene['objects'],
                            conversation=conversation, text=text)
                system, user = talker_prompt(case)
                reply = chat(teacher, [dict(role='system', content=system), dict(role='user', content=user)],
                             think, 1200 if think else 120).strip()
                s = style(reply)
                if not (s['say'] and 1 <= s['sentences'] <= 2 and 4 <= s['words'] <= 40 and not s['symbols']):
                    raise ValueError('style filter')
                row = dict(source='coco', coco_id=scene['coco_id'], teacher=teacher, messages=[
                    dict(role='system', content=system), dict(role='user', content=user),
                    dict(role='assistant', content=reply)])
                kept += 1
            except Exception as exc:
                row = dict(source='dropped', coco_id=scene['coco_id'], reason=type(exc).__name__ + ': ' + str(exc)[:80])
                dropped += 1
            f.write(json.dumps(row) + '\n')
            f.flush()
            if (kept + dropped) % 25 == 0:
                print(time.strftime('%H:%M:%S'), 'kept', kept, 'dropped', dropped, flush=True)
    print('done kept', kept, 'dropped', dropped)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('scenes')
    s.add_argument('--coco', required=True)
    s.add_argument('--n', type=int, default=1200)
    s.add_argument('--out', required=True)
    g = sub.add_parser('gen')
    g.add_argument('--scenes', required=True)
    g.add_argument('--teacher', required=True)
    g.add_argument('--out', required=True)
    g.add_argument('--think', action='store_true')
    g.add_argument('--limit', type=int, default=100000)
    a = ap.parse_args()
    if a.cmd == 'scenes':
        scenes(a.coco, a.n, a.out)
    else:
        gen(a.scenes, a.teacher, a.out, a.think, a.limit)


if __name__ == '__main__':
    main()
