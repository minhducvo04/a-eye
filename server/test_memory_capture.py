import asyncio
import base64

from PIL import Image

from device.hw import encode_jpeg
from device.test_capture import assert_no_images
from server.memory import Store, find
from server.memory_capture import capture


def test_text_only_note_findable_and_buffers_deleted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store('capture-test', base=tmp_path)
    store.save_settings({'consent': {'person': True, 'caregiver': True}, 'remembering': True})
    frames = [base64.b64encode(encode_jpeg(Image.new('RGB', (320, 240)))[0]).decode()]

    async def judge(images):
        assert images
        return {'worth': True, 'note': 'Keys placed on the table.'}

    assert asyncio.run(capture(store, frames, judge)) == {'noted': True}
    assert not frames and len(store.records()) == 1
    assert asyncio.run(find(store, 'keys'))['found']
    assert_no_images(tmp_path)


def test_consent_refusal_and_failure_clear(tmp_path):
    store = Store('capture-test', base=tmp_path)
    frames = ['unused']
    assert asyncio.run(capture(store, frames))['reason'] == 'consent_required'
    assert frames == [] and store.records() == []


def test_model_failure_releases_frames_without_note(tmp_path):
    import pytest
    store = Store('capture-test', base=tmp_path)
    store.save_settings({'consent': {'person': True, 'caregiver': True}, 'remembering': True})
    frames = [base64.b64encode(encode_jpeg(Image.new('RGB', (320, 240)))[0]).decode()]

    async def fail(images):
        raise OSError('local model down')

    with pytest.raises(OSError):
        asyncio.run(capture(store, frames, fail))
    assert not frames and not store.records()
    assert_no_images(tmp_path)
