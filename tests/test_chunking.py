import io
import json
import wave
import zipfile
import numpy as np
import pytest
from fastapi.testclient import TestClient
from stt.app import create_app
from stt.chunking import plan, silence_boundaries, sentence_offsets
from stt.domain import Conflict, edit
from stt.store import Store
from stt.transcripts import segment


def sample():
    return [segment(1, "Śutra je lijep dan. Čujem đecu! Ћирилица остаје.", 0, 12, status="verified"),
            segment(2, "Poslije pauze.", 14, 18)]


def test_default_keeps_dataset_unchanged():
    original = sample()
    result = plan(original, 20, {"mode":"default"})
    assert result["segments"] == original and not result["changes"]


def test_sentence_text_preserved_exactly_and_estimates_flagged():
    original = sample()
    result = plan(original, 20, {"mode":"sentence"})
    rows = result["segments"]
    assert len(rows) == 4
    assert "".join(s["text"] for s in rows[:3]) == original[0]["text"]
    assert all(s["status"] == "flagged" for s in rows[:3])
    assert rows[0]["id"] == "001" and rows[-1] == original[-1]
    assert len({s["id"] for s in rows}) == len(rows)
    assert rows[2]["end"] == 12 and rows[3]["start"] == 14
    assert all(s["source_ids"] == ["001"] for s in rows[:3])


def test_sentence_uses_word_time_instead_of_uniform_estimate():
    row = segment(1, "Prva. Druga.", 0, 10, status="verified", word_spans=[
        {"char_start":0,"char_end":5,"start":0,"end":2},
        {"char_start":6,"char_end":12,"start":3,"end":9}])
    result = plan([row], 10, {"mode":"sentence"})["segments"]
    assert len(result) == 2 and result[0]["end"] == 2.5
    assert result[1]["start"] == 2.5
    assert all(s["status"] == "unreviewed" and not s["chunking"]["estimated"] for s in result)


def test_common_abbreviations_and_decimals_not_split():
    text = 'Dr. Marko ima 3.14. Dobro! „Śutra?” Da.'
    offsets = sentence_offsets(text)
    assert [text[:n] for n in offsets][0].endswith('3.14. ')
    assert len(offsets) == 3


def test_duration_and_selected_scope():
    original = sample()
    result = plan(original, 20, {"mode":"duration","seconds":4,"scope":"selected","segment_id":"001"})["segments"]
    assert [(s["start"],s["end"]) for s in result] == [(0,4),(4,8),(8,12),(14,18)]
    assert "".join(s["text"] for s in result[:3]) == original[0]["text"]
    assert result[-1] == original[-1]


@pytest.mark.parametrize("opts", [
    {"mode":"duration","seconds":0}, {"mode":"pause","pause_seconds":float('nan')},
    {"mode":"split","segment_id":"001","time":0,"text_offset":10},
    {"mode":"split","segment_id":"001","time":12,"text_offset":10},
    {"mode":"split","segment_id":"001","time":6,"text_offset":0},
    {"mode":"split","segment_id":"001","time":6,"text_offset":1.5},
    {"mode":"merge","segment_id":"002"}, {"mode":"sentence","scope":"selected","segment_id":"unknown"}
])
def test_invalid_options_rejected(opts):
    before = sample()
    with pytest.raises(Conflict):
        plan(before,20,opts)
    assert before == sample()


def test_split_unicode_and_merge_lineage():
    row = segment(1,"Ćao 👋🏽! Śutra.  ",0,10,status="verified")
    opts={"mode":"split","segment_id":"001","time":4,"text_offset":8,"boundary_kind":"speaker_turn"}
    split=plan([row],10,opts)["segments"]
    assert "".join(s["text"] for s in split) == row["text"]
    assert split[0]["chunking"]["mode"] == "speaker_turn"
    merged=plan(split,10,{"mode":"merge","segment_id":"001"})["segments"]
    assert merged[0]["source_ids"] == ["001"]
    assert merged[0]["text"] == split[0]["text"]+"\n"+split[1]["text"]
    assert merged[0]["status"] == "unreviewed"


def test_merge_includes_gap_explicitly():
    result=plan(sample(),20,{"mode":"merge","segment_id":"001"})
    assert result["warnings"] and "2.000s gap" in result["warnings"][0]
    assert result["segments"][0]["source_ids"] == ["001","002"]
    assert result["changes"][1]["new"] is None


def test_timing_and_text_edits_discard_word_offsets():
    row=segment(1,"hello world",0,10,word_spans=[{"char_start":0,"char_end":5,"start":0,"end":2}])
    for patch in ({"text":"new text"},{"end":9}):
        result,_=edit([row],"001",patch,10)
        assert "word_spans" not in result[0]


def pause_audio(path):
    rate=16000
    tone=(np.sin(np.arange(rate)*2*np.pi*440/rate)*10000).astype('<i2')
    values=np.concatenate([np.zeros(rate//2,dtype='<i2'),tone,np.zeros(rate,dtype='<i2'),tone,np.zeros(rate//2,dtype='<i2')])
    with wave.open(str(path),'wb') as out:
        out.setparams((1,2,rate,0,'NONE','not compressed'))
        out.writeframes(values.tobytes())


def test_actual_pause_detection_and_threshold(tmp_path):
    path=tmp_path/'audio.wav'
    pause_audio(path)
    assert silence_boundaries(path,.6) == [2.0]
    assert silence_boundaries(path,1.2) == []
    result=plan([segment(1,"Prvo govori. Onda nastavlja.",0,4)],4,{"mode":"pause"},[2.0])
    assert result["after_count"] == 2
    assert result["segments"][0]["end"] == 2
    assert "not speaker identity" in ' '.join(result["warnings"])


def test_split_undo_redo_and_reload_record_added_removed_ids(tmp_path):
    store=Store(tmp_path)
    store.create({"id":"p","name":"test","duration":20,"settings":{},"segments":sample(),"media_name":"a.wav"})
    proposal=plan(sample(),20,{"mode":"sentence"})
    changed=store.apply_chunking('p',0,proposal)
    assert len(changed['segments']) == 4
    assert changed['original_segments'] == sample()
    undone=store.update('p',1,action='undo')
    assert undone['segments'] == sample()
    assert undone['chunking']['mode'] == 'default'
    redone=store.update('p',2,action='redo')
    assert redone['segments'] == changed['segments']
    assert Store(tmp_path).get('p')['segments'] == changed['segments']
    audit=store.audit('p')
    assert sum(c['old'] is None for c in audit[1]['changes']) == 2
    assert sum(c['new'] is None for c in audit[2]['changes']) == 2
    assert sum(c['old'] is None for c in audit[3]['changes']) == 2
    with pytest.raises(Conflict):
        store.apply_chunking('p',0,proposal)


def wait_job(client,jid):
    import time
    for _ in range(200):
        job=client.get('/api/jobs/'+jid).json()
        if job['status']!='processing':
            assert job['status']=='complete',job
            return job
        time.sleep(.02)
    raise AssertionError('Job timeout')


def test_chunking_api_preview_apply_and_consistent_zip(tmp_path):
    path=tmp_path/'fixture.wav'
    pause_audio(path)
    app=create_app(tmp_path/'data')
    with TestClient(app) as client:
        r=client.post('/api/import',files={'media':('a.wav',path.read_bytes()),'transcript':('a.json',json.dumps([{'id':'A','start':0,'end':4,'text':'Prvo govori. Śutra nastavlja.'}]).encode())})
        pid=wait_job(client,r.json()['id'])['project_id']
        before=client.get('/api/projects/'+pid).json()
        job=client.post(f'/api/projects/{pid}/chunking/preview',json={'revision':0,'options':{'mode':'pause','pause_seconds':.6}}).json()
        preview=wait_job(client,job['id'])['preview']
        assert preview['after_count']==2
        assert client.get('/api/projects/'+pid).json()['revision']==0
        applied=client.post(f'/api/projects/{pid}/chunking/apply',json={'revision':0,'proposal_id':preview['proposal_id']})
        assert applied.status_code==200,applied.text
        after=applied.json()
        assert after['original_segments']==before['original_segments']
        assert client.post(f'/api/projects/{pid}/chunking/apply',json={'revision':0,'proposal_id':preview['proposal_id']}).status_code==409
        response=client.get(f'/api/projects/{pid}/export/zip?revision=1').json()
        job=wait_job(client,response['id'])
        with zipfile.ZipFile(io.BytesIO(client.get(job['download']).content)) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            assert manifest['chunking']['mode']=='pause'
            assert len(manifest['segments'])==2
            for segment in manifest['segments']:
                with wave.open(io.BytesIO(archive.read(segment['audio_filename'])),'rb') as audio:
                    assert audio.getnframes()==round((segment['end']-segment['start'])*16000)
        # Undo shrinks topology; redo restores exactly the same stable IDs.
        assert len(client.post(f'/api/projects/{pid}/undo',json={'revision':1}).json()['segments'])==1
        assert client.post(f'/api/projects/{pid}/redo',json={'revision':2}).json()['segments']==after['segments']


def test_import_chunking_preserves_pre_chunking_original(tmp_path):
    path=tmp_path/'fixture.wav'
    pause_audio(path)
    with TestClient(create_app(tmp_path/'data')) as client:
        r=client.post('/api/import',files={'media':('a.wav',path.read_bytes()),'transcript':('a.json',json.dumps([{'id':'A','start':0,'end':4,'text':'Čujem đecu. Śutra dolaze.'}]).encode())},data={'chunk_mode':'sentence'})
        pid=wait_job(client,r.json()['id'])['project_id']
        p=client.get('/api/projects/'+pid).json()
        assert len(p['segments'])==2 and len(p['original_segments'])==1
        assert p['settings']['chunking']['mode']=='sentence'
        assert ''.join(s['text'] for s in p['segments'])==p['original_segments'][0]['text']
