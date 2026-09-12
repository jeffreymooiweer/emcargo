"""Browser regressions: ordinary prose must not yield an empty, exportable CMR.

The chairs scenario contained an unknown weight in a separate sentence. It
blocked intake, confused the payer and then lost the unweighed line in totals.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.services.assistant import orchestrator as assistant, runtime
from app.services.assistant.understanding import quantity_answer
from app.services.assistant.goods import open_questions_for_line
from app.services.pipeline import parse_and_calculate
from app.services.documents import get_document, validate_document


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(runtime, 'installed', lambda: False)
    with TestClient(app), SessionLocal() as session:
        yield session


def test_novice_intake_keeps_known_facts(db):
    result = assistant.step({'modality': 'road'},
        'Ik wil 6 gebruikte bureaustoelen van Breda naar Antwerpen sturen. Ze zijn niet verpakt. Het gewicht weet ik nog niet. Wat moet ik invullen?', None, db)
    assert len(result['state']['draft_lines']) == 1
    assert result['state']['draft_lines'][0]['quantity'] == 6
    assert result['state']['doc_values']['discharge_point'].startswith('Antwerpen')
    assert 'verpakt' not in result['state']['doc_values']['discharge_point']


def test_named_business_destination_keeps_counted_goods_and_separates_town(db):
    result = assistant.step({'modality': 'road'},
        'Ik moet morgen 4 pallets knakworsten vervoeren van de haven in Rotterdam naar supermarkt Plus in Wezep', None, db)
    state = result['state']
    assert state['draft_lines'][0]['quantity'] == 4
    assert state['draft_lines'][0]['unit'] == 'pallet'
    assert 'knakworsten' in state['draft_lines'][0]['description']
    assert state['doc_values']['consignee_name'] == 'supermarkt Plus'
    assert state['doc_values']['discharge_point'] == 'Wezep'
    assert 'consignee_address' not in state['doc_values']


def test_correction_uses_current_goods_noun():
    assert quantity_answer('Het zijn toch 8 stoelen.', 'pcs', 'gebruikte bureaustoelen') == 8
    assert quantity_answer('Het zijn toch 8 dozen.', 'pcs', 'gebruikte bureaustoelen') is None
    assert quantity_answer('Het zijn misschien 8 stoelen.', 'pcs', 'gebruikte bureaustoelen') is None
    assert quantity_answer('Het zijn toch 4 pallets.', 'pallet', 'boeken') == 4


@pytest.mark.parametrize('text, expected', [
    ('De klant in Antwerpen betaalt het vervoer.', 'collect'),
    ('Wij betalen het vervoer.', 'prepaid'),
    ('The receiver pays for transport.', 'collect'),
])
def test_payer_never_depends_on_model_guess(db, monkeypatch, text, expected):
    monkeypatch.setattr(assistant, '_model_choice', lambda *args: pytest.fail('Payment must be grounded'))
    events = assistant._apply_answer({}, {'scope': 'doc_question', 'field': 'payment_instruction',
        'options': ['prepaid', 'collect', 'agreement']}, text, 'nl')
    assert events[0]['suggested_choice'] == expected


def test_unweighed_goods_count_and_block_cmr(db):
    result = parse_and_calculate('gebruikte bureaustoelen | 8 | stuks', db)
    assert result['totals']['included_count'] == 1
    assert result['totals']['total_quantity'] == 8
    errors, _ = validate_document(get_document('cmr'), {}, result['lines'], [])
    assert any(isinstance(e, dict) and e.get('code') == 'documents.goods_incomplete' for e in errors)


def test_dimensions_without_material_still_have_loading_volume(db):
    result = parse_and_calculate('boeken | 4 | pallet', db, line_overrides=[{
        'line_id': 1, 'length_m': 1.2, 'width_m': .8, 'height_m': 1, 'weight_total_kg': 800}])
    assert result['totals']['total_transport_volume_m3'] == pytest.approx(3.84)


def test_dimensions_do_not_hide_missing_weight():
    assert open_questions_for_line({'quantity': 8, 'length_cm': 60, 'width_cm': 60, 'height_cm': 100})[0]['field'] == 'goods_weight_each'


@pytest.mark.parametrize('text', [
    'Ik wil 2 bureaus en 4 bureaustoelen van Eindhoven naar Gent sturen. Ik heb nog nooit een vrachtbrief gemaakt. Help je me stap voor stap?',
    '2 bureaus\n4 bureaustoelen\nVan Eindhoven naar Gent',
    '2 desks and 4 chairs from Eindhoven to Gent',
])
def test_counted_nouns_stay_separate_goods_not_parties(db, monkeypatch, text):
    monkeypatch.setattr(runtime, 'installed', lambda: True)
    monkeypatch.setattr(runtime, 'extract_json', lambda *args, **kwargs: pytest.fail('Counted rows need no model guess'))
    result = assistant.step({'modality': 'road'}, text, None, db)
    lines = result['state']['draft_lines']
    assert [line['quantity'] for line in lines] == [2, 4]
    assert [line['unit'] for line in lines] == ['pcs', 'pcs']
    assert not any(key.endswith('_name') for key in result['state']['doc_values'])
    assert result['state']['doc_values']['discharge_point'] == 'Gent'


def test_model_cannot_promote_counted_goods_or_route_towns_to_parties(monkeypatch):
    monkeypatch.setattr(runtime, 'installed', lambda: True)
    monkeypatch.setattr(runtime, 'extract_json', lambda *args, **kwargs: {
        'lines': [{'description': 'bureaustoelen', 'quantity': 4, 'unit': 'bureaustoelen'}],
        'fields': {'consignor_name': '2 bureaus', 'consignee_name': 'Gent', 'discharge_point': 'Gent'},
    })
    lines, fields = assistant._model_intake('2 bureaus; 4 bureaustoelen van Eindhoven naar Gent')
    assert fields == {'discharge_point': 'Gent'}
    assert assistant._intake_rows(lines, fields, '4 bureaustoelen') == ['bureaustoelen | 4 | pcs']


def test_explicit_split_repairs_legacy_merged_line(db):
    state = {'modality': 'road', 'draft_lines': [{'id': 1, 'description': 'bureaus en 4 bureaustoelen', 'quantity': 2, 'unit': 'pcs'}]}
    current = assistant.step(state, '', None, db)
    result = assistant.step(current['state'], 'Ik wil twee aparte goederenregels.', current['pending'], db)
    assert [(line['description'], line['quantity']) for line in result['state']['draft_lines']] == [('bureaus', 2), ('bureaustoelen', 4)]


def test_explicit_correction_moves_goods_out_of_sender(db):
    state = {'modality': 'road', 'doc_values': {'consignor_name': '2 bureaus'},
             'draft_lines': [{'id': 1, 'description': 'bureaustoelen', 'quantity': 4, 'unit': 'bureaustoelen'}]}
    current = assistant.step(state, '', None, db)
    result = assistant.step(current['state'], 'Dit klopt niet. De 2 bureaus zijn ook goederen, niet de afzender. Ik wil twee aparte goederenregels.', current['pending'], db)
    assert 'consignor_name' not in result['state']['doc_values']
    assert sorted((line['description'], line['quantity'], line['unit']) for line in result['state']['draft_lines']) == [('bureaus', 2, 'pcs'), ('bureaustoelen', 4, 'pcs')]


def test_split_does_not_guess_how_to_allocate_existing_weight(db):
    state = {'modality': 'road', 'draft_lines': [{'id': 1, 'description': 'bureaus en 4 bureaustoelen', 'quantity': 2, 'unit': 'pcs', 'stated_weight_kg': 120, 'weight_basis': 'total'}]}
    current = assistant.step(state, '', None, db)
    result = assistant.step(current['state'], 'Ik wil twee aparte goederenregels.', current['pending'], db)
    assert result['events'][0]['reason'] == 'split_goods'
    assert len(result['state']['draft_lines']) == 1
    assert result['state']['draft_lines'][0]['weight_total_kg'] == 120


def test_named_dimensions_preserve_explicit_total_mass(db):
    """A novice gave three named axes and a total; the old model path dropped mass."""
    current = assistant.step({'modality': 'road'}, '2 bureaus en 4 bureaustoelen van Eindhoven naar Gent', None, db)
    result = assistant.step(current['state'], 'Elk bureau is 160 cm lang, 80 cm breed en 75 cm hoog. Ze wegen samen 60 kilo.', current['pending'], db)
    desk, chair = result['state']['draft_lines']
    assert desk['weight_total_kg'] == 60
    assert desk['length_cm'] == 160
    assert desk['width_cm'] == 80
    assert desk['height_cm'] == 75
    assert not chair.get('stated_weight_kg')


def test_explicit_mass_correction_targets_previous_good(db):
    """An answer about desks must not be applied to the active chair question."""
    current = assistant.step({'modality': 'road'}, '2 bureaus en 4 bureaustoelen', None, db)
    result = assistant.step(current['state'], 'Wacht, die twee bureaus wegen samen 60 kilo, niet 480 kilo. De stoelen heb ik nog niet gewogen.', current['pending'], db)
    assert result['state']['draft_lines'][0]['weight_total_kg'] == 60
    assert not result['state']['draft_lines'][1].get('stated_weight_kg')


@pytest.mark.parametrize('text, expected', [
    ('Samen wegen de twee bureaus 60 kg, dus 30 kg per bureau.', 60),
    ('Together they weigh 60 kg, so 30 kg each.', 60),
    ('Samen 60.5 kg', 60.5),
])
def test_consistent_total_and_each_mass(text, expected):
    state = {'draft_lines': [{'id': 1, 'quantity': 2, 'unit': 'pcs'}]}
    events = assistant._apply_answer(state, {'scope': 'goods_question', 'field': 'goods_weight_each', 'line_id': 1}, text, 'nl')
    assert events[0]['kind'] == 'answered'
    assert state['draft_lines'][0]['stated_weight_kg'] == expected
    assert state['draft_lines'][0]['weight_basis'] == 'total'


def test_conflicting_total_and_each_mass_is_not_stored():
    """Consistency must be checked, not resolved by taking the first number."""
    state = {'draft_lines': [{'id': 1, 'quantity': 2}]}
    events = assistant._apply_answer(state, {'scope': 'goods_question', 'field': 'goods_weight_each', 'line_id': 1}, 'Samen 60 kg, dus 40 kg per bureau.', 'nl')
    assert events[0]['kind'] == 'clarify'
    assert 'stated_weight_kg' not in state['draft_lines'][0]


@pytest.mark.parametrize('text', [
    'Ik regel het vervoer namens Testkantoor Eindhoven.',
    'I arrange transport on behalf of Testkantoor Eindhoven.',
    'Ich organisiere den Transport für Testkantoor Eindhoven.',
    "J'organise le transport pour Testkantoor Eindhoven.",
])
def test_party_intro_does_not_become_the_company_name(text):
    state = {}
    events = assistant._apply_answer(state, {'scope': 'doc_question', 'field': 'consignor_name'}, text, 'nl')
    assert events[0]['kind'] == 'answered'
    assert state['doc_values']['consignor_name'] == 'Testkantoor Eindhoven'


def test_leaving_dimensions_for_later_still_asks_missing_weight(db):
    """Skipping optional dimensions must not silently bypass unknown cargo mass."""
    current = assistant.step({'modality': 'road'}, '2 bureaus', None, db)
    result = assistant.step(current['state'], 'Dat weet ik nog niet. Kan ik dat later invullen?', current['pending'], db)
    assert result['pending']['field'] == 'goods_weight_each'
    assert result['pending']['line_id'] == 1
    assert result['events'][0]['kind'] == 'skipped'


@pytest.mark.parametrize('text', ['Voor Testkantoor Gent.', 'For Testkantoor Gent.', 'Für Testkantoor Gent.', 'Pour Testkantoor Gent.'])
def test_recipient_intro_is_not_part_of_company_name(text):
    state = {}
    assistant._apply_answer(state, {'scope': 'doc_question', 'field': 'consignee_name'}, text, 'nl')
    assert state['doc_values']['consignee_name'] == 'Testkantoor Gent'


def test_local_model_reads_a_new_party_paraphrase(db, monkeypatch):
    monkeypatch.setattr(runtime, 'installed', lambda: True)
    monkeypatch.setattr(runtime, 'extract_json', lambda *args, **kwargs: {'name': 'Bureau Delta'})
    state = {}
    events = assistant._apply_answer(state, {'scope': 'doc_question', 'field': 'consignor_name'}, 'Voor deze zending is Bureau Delta onze opdrachtgever.', 'nl')
    assert events[0]['kind'] == 'answered'
    assert state['doc_values']['consignor_name'] == 'Bureau Delta'


@pytest.mark.parametrize('generated', ['Another Company', 'Voor deze zending is Bureau Delta onze opdrachtgever.', ''])
def test_model_cannot_invent_a_party_or_store_the_whole_sentence(db, monkeypatch, generated):
    monkeypatch.setattr(runtime, 'installed', lambda: True)
    monkeypatch.setattr(runtime, 'extract_json', lambda *args, **kwargs: {'name': generated})
    state = {}
    events = assistant._apply_answer(state, {'scope': 'doc_question', 'field': 'consignor_name'}, 'Voor deze zending is Bureau Delta onze opdrachtgever.', 'nl')
    assert events[0]['kind'] == 'clarify'
    assert not state.get('doc_values')


def test_prose_mass_without_clear_basis_requires_confirmation(db):
    current = assistant.step({'modality': 'road'}, '4 bureaustoelen', None, db)
    revised = assistant.step(current['state'], '', {'scope': 'goods_question', 'field': 'goods_weight_each', 'line_id': 1}, db, action='revise')
    result = assistant.step(revised['state'], 'Alles bij elkaar komt het op 48 kg.', revised['pending'], db)
    assert result['pending']['scope'] == 'goods_weight_basis'
    assert not result['state']['draft_lines'][0].get('stated_weight_kg')
    result = assistant.step(result['state'], 'total', result['pending'], db)
    assert result['state']['draft_lines'][0]['weight_total_kg'] == 48


def test_ambiguous_revision_survives_recalculation_of_previous_mass(db):
    """Reopening an already weighed line used to erase a new pending mass."""
    current = assistant.step({'modality': 'road', 'draft_lines': [
        {'id': 1, 'description': 'bureaustoelen', 'quantity': 4, 'unit': 'pcs', 'stated_weight_kg': 48, 'weight_basis': 'total'}]}, '', None, db)
    revised = assistant.step(current['state'], '', {'scope': 'goods_question', 'field': 'goods_weight_each', 'line_id': 1}, db, action='revise')
    result = assistant.step(revised['state'], 'Alles bij elkaar komt het op 52 kg.', revised['pending'], db)
    assert result['pending']['scope'] == 'goods_weight_basis'
    assert result['state']['draft_lines'][0]['unconfirmed_weight_kg'] == 52
    assert result['state']['draft_lines'][0]['weight_total_kg'] == 48
    result = assistant.step(result['state'], 'total', result['pending'], db)
    assert result['state']['draft_lines'][0]['weight_total_kg'] == 52


def test_weight_override_replaces_obsolete_missing_weight_message(db):
    result = parse_and_calculate('bureaustoelen | 4 | pcs', db, line_overrides=[{'line_id': 1, 'weight_each_kg': 14}])
    line = result['lines'][0]
    assert line['weight_total_kg'] == 56
    assert 'dimensions_missing' not in line['messages']
    assert 'transport_dimensions_missing' in line['messages']


def test_road_cities_are_not_turned_into_unrequested_terminals(db):
    """A new browser scenario converted Utrecht to Utrecht Centraal station."""
    result = assistant.step({'modality': 'road'}, 'Ik wil 3 dozen boeken van Utrecht naar Leuven sturen. Ik weet het gewicht nog niet. Kun je me helpen?', None, db)
    assert result['state']['doc_values']['loading_point'] == 'Utrecht'
    assert result['state']['doc_values']['discharge_point'] == 'Leuven'
    assert result['state']['draft_lines'][0]['quantity'] == 3


def test_answering_deferred_measurement_clears_later_reminder(db):
    state = {'modality':'road', 'draft_lines':[{'id':1,'description':'boeken','quantity':3,'unit':'box','stated_weight_kg':20,'weight_basis':'each'}], 'skipped_questions':['goods:1:goods_dimensions']}
    current = assistant.step(state, '', {'scope':'goods_question','field':'goods_dimensions','line_id':1}, db, action='revise')
    result = assistant.step(current['state'], 'Elke doos is 40 cm lang, 30 cm breed en 25 cm hoog.', current['pending'], db)
    assert 'goods:1:goods_dimensions' not in result['state']['skipped_questions']
    assert result['state']['draft_lines'][0]['weight_total_kg'] == 60
    assert result['state']['draft_lines'][0]['transport_volume_m3'] == pytest.approx(.09)


@pytest.mark.parametrize('lang, expected', [('nl','3 dozen boeken'),('en','3 boxes boeken'),('de','3 Kartons boeken'),('fr','3 cartons boeken')])
def test_cmr_preserves_the_packaging_unit_of_novice_goods(lang, expected):
    """The browser shipment said three boxes, but the PDF printed three books."""
    from app.services.documents.pdf_forms import fill_cmr
    fields = fill_cmr({}, [{'line_id':1,'description':'boeken','quantity':3,'unit':'box','weight_total_kg':60}], None, lang)
    assert fields['VakRood06Regel01Kolom06'] == expected
