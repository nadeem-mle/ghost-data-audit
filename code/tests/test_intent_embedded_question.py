import pytest
from audit.engine import intent, Unresolved

def test_spanish_si_whether_is_not_a_condition():
    assert intent('¿Pueden comprobar si todavía queda algún dato y completar la eliminación si hace falta?')=='YES'

def test_english_check_if_is_not_a_condition():
    assert intent('Please check if any data remains and delete my account.')=='YES'

def test_real_conditional_still_unresolved():
    with pytest.raises(Unresolved):
        intent('Delete my account if my order has shipped.')
