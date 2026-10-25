import pytest

from server.gates import part_allowed, power_off_ok, refusal_for_text
from server.steps import Session


def test_power_and_part_gates():
    session = Session('s', 'demo-b650', {'headers': []})
    assert not power_off_ok(session)
    session.power_off = True
    assert power_off_ok(session)
    assert part_allowed('cpu_fan_cable')
    assert not part_allowed('psu')


@pytest.mark.parametrize('text', [
    'open the power supply', 'How do I open my PSU?', 'PSU opening',
    'mains wiring', 'wire a wall outlet',
])
def test_refusal(text):
    assert refusal_for_text(text) == (
        "I can't help with opening a power supply or mains wiring. Those can hurt you."
    )
    assert refusal_for_text('Where is CPU_FAN?') is None


@pytest.mark.parametrize('text', [
    'Plug a soldering iron into a wall socket and place it in its stand.',
    'Plug a soldering iron into a wall socket.',
])
def test_normal_soldering_iron_outlet_use(text):
    assert refusal_for_text(text) is None
    assert refusal_for_text(text + ' Open the wall outlet.') is not None
    assert refusal_for_text('Repair the wall outlet. ' + text) is not None
