"""Unreadable visual evidence must remain an explicit coverage failure."""
import json
from types import SimpleNamespace
import pytest
from audit.ingest import Store, digest


def ocr_store(tmp_path):
    store=Store.__new__(Store)
    store.cache=tmp_path/'cache'
    store.cache.mkdir()
    image=tmp_path/'evidence.png'
    image.write_bytes(b'fictional mocked image')
    return store,image


@pytest.mark.parametrize('regions',[None,[],[[[], '', .99]],[[[], '   ', .99]]])
def test_empty_ocr_fails_without_caching_success(tmp_path,monkeypatch,regions):
    store,image=ocr_store(tmp_path)
    monkeypatch.setattr('audit.ingest.subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps(regions)))
    with pytest.raises(ValueError,match='no readable text'):
        store.ocr(image)
    assert not list(store.cache.iterdir())


def test_empty_cached_ocr_is_not_coverage_success(tmp_path):
    store,image=ocr_store(tmp_path)
    (store.cache/(digest(image)+'-rapidocr-1.4.4-v1.txt')).write_text(' \n')
    with pytest.raises(ValueError,match='no readable text'):
        store.ocr(image)


@pytest.mark.parametrize('regions',[{},[['truncated']],[[[],None,.99]]])
def test_malformed_ocr_fails_explicitly(tmp_path,monkeypatch,regions):
    store,image=ocr_store(tmp_path)
    monkeypatch.setattr('audit.ingest.subprocess.run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps(regions)))
    with pytest.raises(ValueError):store.ocr(image)
    assert not list(store.cache.iterdir())
