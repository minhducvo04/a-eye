"""RAM-only event capture. No microphone, filesystem or transport in Armed."""
import asyncio
import base64
import time
from collections import deque
from urllib.parse import urlsplit, urlunsplit

import httpx

from device import hw
from device.trigger import Motion


class Capture:
    def __init__(self, device, clock=time.monotonic):
        self.device, self.clock = device, clock
        self.frames = deque(maxlen=11)
        self.state = 'Off'
        self.events = 0

    def signal(self, state):
        self.state = state
        self.device.indicator.set(state)

    def clear(self):
        for _, frame in self.frames:
            frame.close()
        self.frames.clear()

    async def send(self, frames):
        url = urlsplit(self.device.cfg['server']['url'])
        target = urlunsplit(('https' if url.scheme == 'wss' else 'http', url.netloc,
                             '/api/memory/event', '', ''))
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(target, headers=self.device.cfg.headers(), json={'frames': frames})
            response.raise_for_status()

    async def send_until_off(self, payload):
        sender = asyncio.create_task(self.send(payload))
        stopper = asyncio.create_task(self.device.stop.wait())
        button = asyncio.create_task(self.device.events.get())
        tasks = (sender, stopper, button)
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if button in done:
                kind, source = button.result()
                if kind == 'session':
                    self.device.events.put_nowait((kind, source))
            if stopper in done or button in done:
                return False
            await sender
            return True
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def event(self):
        self.signal('Event')
        payload = []
        try:
            end = self.clock() + 5
            while self.clock() < end and not self.device.stop.is_set():
                if not self.device.events.empty():
                    kind, source = self.device.events.get_nowait()
                    if kind in ('press', 'session'):
                        if kind == 'session':
                            self.device.events.put_nowait((kind, source))
                        return False
                image = self.device.camera.read()
                if image is not None:
                    image.thumbnail((640, 480))
                    self.frames.append((self.clock(), image))
                await asyncio.sleep(1)
            if self.device.stop.is_set():
                return False
            person = self.device.person
            # Unknown detector state is a refusal, never permission to transmit.
            if person is None or not person.available:
                return True
            safe = []
            for _, image in self.frames:
                # Tiny pre-roll cannot support a reliable HOG check: discard it.
                if image.width < 64 or image.height < 128 or person.has_person(image):
                    self.device.stats['frames_dropped_person'] += 1
                    continue
                safe.append(image)
            for image in safe[::max(1, len(safe) // 3)][:3]:
                jpeg, _, _ = hw.encode_jpeg(image)
                payload.append(base64.b64encode(jpeg).decode())
            if payload:
                if not await self.send_until_off(payload):
                    return False
                self.events += 1
            return True
        finally:
            payload.clear()
            self.clear()

    async def run(self, immediate=False):
        t = self.device.cfg['trigger']
        motion = Motion(min_share=t['motion_share'], zone=t['zone'])
        started = self.clock()
        self.device.mic.close()
        try:
            while not self.device.stop.is_set() and self.clock() - started < t['armed_cap_s']:
                self.signal('Armed')
                self.device.camera.open_low()
                trigger = immediate
                immediate = False
                while not trigger and not self.device.stop.is_set():
                    if self.clock() - started >= t['armed_cap_s']:
                        return
                    if not self.device.events.empty():
                        kind, source = self.device.events.get_nowait()
                        if kind in ('press', 'session'):
                            if kind == 'session':
                                self.device.events.put_nowait((kind, source))
                            return
                        trigger = kind == 'remember'
                    image = self.device.camera.read()
                    if image is not None:
                        thumb = image.convert('L').resize((64, 48))
                        image.close()
                        now = self.clock()
                        while self.frames and now - self.frames[0][0] >= 5:
                            self.frames.popleft()[1].close()
                        self.frames.append((now, thumb))
                        trigger = trigger or motion.changed(thumb)
                    if not trigger:
                        await asyncio.sleep(1)
                self.device.camera.close()
                if self.device.stop.is_set():
                    return
                self.device.camera.open()
                if not await self.event():
                    return
                self.device.camera.close()
                motion.reset()
        finally:
            self.device.camera.close()
            self.clear()
            self.signal('Off')
