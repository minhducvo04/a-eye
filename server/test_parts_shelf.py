"""Parts shelf: card loading, the step note in the background context, the tool switch and the upload allowlist."""
import asyncio
import json

import pytest

from server import context_agent, gemini_live, parts_shelf, privacy
from server.agent import Session
from server.packs.electronics import TASKS as EE
from server.packs.home import TASKS as HOME
from server.parts_shelf import FIELDS, Shelf, check_card
from scripts import kb_upload

STEPS = {**HOME, **EE}


def test_checked_in_cards_load_and_link_real_steps_and_products():
    shelf = Shelf.load()
    assert shelf.cards and all(set(c['task_ids'].split(',')) <= parts_shelf.TASKS for c in shelf.cards)
    for card in shelf.cards:
        assert set(card) == set(FIELDS)
        for key in filter(None, card['step_keys'].split(',')):
            task, step = key.split(':')
            assert 1 <= int(step) <= len(STEPS[task])
        for pid in filter(None, card['product_ids'].split(',')):
            row = shelf.products[pid]
            assert row['url'].startswith('https://www.amazon.com/') and row['name']
            assert 'price' not in row  # the export has no prices; never invent one
    # Every guide step that has a card target in the plan is covered.
    assert shelf.for_step('ee_led', 3) and shelf.for_step('ee_multimeter', 3)
    assert not any(shelf.for_step(task, 1) for task in ('sink', 'hinge', 'breaker', 'tie'))


def test_missing_or_bad_files_give_an_empty_shelf(tmp_path):
    assert Shelf.load(tmp_path).cards == []
    card = json.loads((parts_shelf.DIR / 'cards.json').read_text())[0]
    (tmp_path / 'cards.json').write_text(json.dumps([dict(card, owner_note='x')]))
    (tmp_path / 'products.json').write_text('{}')
    assert Shelf.load(tmp_path).cards == []
    assert Shelf().note('sink', 6) == ''


def test_step_note_puts_the_named_part_first_and_stays_short():
    shelf = parts_shelf.shelf()
    note = shelf.note('ee_led', 3, line=parts_shelf.step_text('ee_led', 3))
    assert note.startswith('220 ohm resistor:') and 'in series' in note
    assert len(note) <= parts_shelf.NOTE_MAX
    meter = shelf.note('ee_multimeter', 3, line=parts_shelf.step_text('ee_multimeter', 3))
    assert 'multimeter' in meter and 'powered circuit' in meter


def test_dialogue_warms_only_cards_for_the_current_step():
    shelf = parts_shelf.shelf()
    assert 'adjustable wrench' not in shelf.note('ee_led', 2, ['do I need a wrench?'])
    assert 'multimeter' not in shelf.note('ee_resistor', 1, ['which multimeter should I use'])
    assert 'multimeter' in shelf.note(texts=['which multimeter should I use'])
    assert shelf.note(texts=['where is my adjustable wrench']) == ''
    assert shelf.note(texts=['light an LED']).startswith('LED:')


def test_look_up_part_answers_from_memory_or_says_no_card():
    shelf = parts_shelf.shelf()
    text = shelf.look_up('a multimeter')
    assert text.startswith('multimeter') and 'ohms' in text and len(text) <= parts_shelf.TOOL_MAX
    for name in ('sink shutoff valve', 'faucet cartridge', 'cabinet hinge', 'breaker panel'):
        assert shelf.look_up(name) == parts_shelf.NO_CARD
    assert shelf.look_up('a flux capacitor') == parts_shelf.NO_CARD


def test_tool_is_offered_only_with_kb_tool(monkeypatch):
    monkeypatch.delenv('KB_TOOL', raising=False)
    assert 'look_up_part' not in [d['name'] for d in gemini_live.declarations(False)]
    monkeypatch.setenv('KB_TOOL', '1')
    tool = next(d for d in gemini_live.declarations(False) if d['name'] == 'look_up_part')
    assert tool['behavior'] == 'NON_BLOCKING'


def test_background_block_carries_the_parts_note(monkeypatch):
    async def trial():
        privacy.set_call({'google': True, 'claude': False})
        session = Session('parts', camera=False)
        session.live_guide_note = dict(task='ee_led', step=3, line='Connect the resistor.', completed=False)
        seen, published = [], []

        async def assess(session, evidence):
            seen.append(json.loads(evidence))
            return {'context': 'User is wiring the resistor.', 'hazard': ''}

        async def publish(block):
            published.append(block)
            return True

        async def stop(line):
            raise AssertionError(line)
        monkeypatch.setattr(context_agent, 'assess_live_context', assess)
        builder = context_agent.LiveContextBuilder(session, publish, stop, lambda text: None)
        await builder.build()
        assert seen[0]['parts'].startswith('Parts for this step')
        assert '220 ohm resistor' in published[0] and 'never quote a price' in published[0]
        session.live_guide_note = dict(task='ee_led', step=7, line='', completed=True)
        assert parts_shelf.step_note(session) == ''
    asyncio.run(trial())


def test_upload_sends_only_allowlisted_fields_in_order(tmp_path):
    sent = []

    class Store:
        def _request(self, path, *, args=None, query=None):
            sent.append((path, args))
    assert kb_upload.upload(parts_shelf.DIR / 'cards.json', Store()) == len(parts_shelf.shelf().cards)
    assert all(path == '/call/upsert_kb_card' and len(args) == len(FIELDS) for path, args in sent)
    card = json.loads((parts_shelf.DIR / 'cards.json').read_text())[0]
    assert sent[0][1] == [card[key] for key in FIELDS]
    sent.clear()
    bad = tmp_path / 'cards.json'
    bad.write_text(json.dumps([card, dict(card, id='sink.extra', home_address='private')]))
    with pytest.raises(ValueError):
        kb_upload.upload(bad, Store())
    assert sent == []  # nothing leaves when any card fails the allowlist


@pytest.mark.parametrize('change', [dict(task_ids='kitchen'), dict(step_keys='sink:0'), dict(kind='secret'),
                                    dict(what='x' * 201), dict(product_ids='a,b,c'), dict(updated='today')])
def test_card_check_rejects_unsafe_values(change):
    card = json.loads((parts_shelf.DIR / 'cards.json').read_text())[0]
    with pytest.raises(ValueError):
        check_card(dict(card, **change))
