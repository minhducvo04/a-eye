"""Incremental STT: the last partial stands in for the final only when the tail after it is quiet."""
from array import array

from server.ws2 import quiet_tail


def pcm(level, ms):
    return array('h', [level if i % 2 else -level for i in range(16 * ms)]).tobytes()


def test_quiet_tail_reuses_partial_after_silence_only():
    speech = pcm(3000, 1000)
    assert quiet_tail(speech + pcm(50, 400), len(speech))
    assert not quiet_tail(speech + pcm(3000, 400), len(speech))  # words after the partial
    assert not quiet_tail(speech + pcm(0, 1200), len(speech))     # tail too long to trust
    assert not quiet_tail(speech, 0)
