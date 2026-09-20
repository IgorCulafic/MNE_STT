import io
import json
import math
import struct
import time
import wave
import zipfile
import pytest
from fastapi.testclient import TestClient
from stt.app import create_app


def wav_bytes(duration=3):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"".join(struct.pack('<h', int(15000 * math.sin(i * 2 * math.pi * 440 / 16000))) for i in range(int(duration * 16000))))
    return output.getvalue()


def wait_job(client, jid):
    for _ in range(500):
        job = client.get('/api/jobs/' + jid).json()
        if job['status'] != 'processing':
            return job
        time.sleep(.02)
    raise AssertionError('Job did not finish')


def import_sample(client):
    transcript = '1\n00:00:00,000 --> 00:00:01,000\nŚutra.\n\n2\n00:00:01,000 --> 00:00:02,000\nČujem đecu.\n\n3\n00:00:02,000 --> 00:00:03,000\nŹenica.\n'
    response = client.post('/api/import', files={'media': ('recording.wav', wav_bytes(), 'audio/wav'), 'transcript': ('transcript.srt', transcript.encode('utf-8'), 'text/plain')}, data={'language':'sr','model':'base'})
    assert response.status_code == 200
    job = wait_job(client, response.json()['id'])
    assert job['status'] == 'complete', job
    return job['project_id']


def test_end_to_end_matching_exports_and_chunks(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        pid = import_sample(client)
        original = (tmp_path / pid / 'original-media').read_bytes()
        change = client.patch(f'/api/projects/{pid}/segments/002', json={'revision':0,'patch':{'start':1.2,'end':2.2}})
        assert change.status_code == 200, change.text
        state = change.json()
        assert [(s['start'], s['end']) for s in state['segments']] == [(0,1.2),(1.2,2.2),(2.2,3)]
        export = client.get(f'/api/projects/{pid}/export/zip?revision=1').json()
        # Edit while exporting: the bundle must remain entirely revision 1.
        client.patch(f'/api/projects/{pid}/segments/002', json={'revision':1,'patch':{'text':'Edited after snapshot'}})
        job = wait_job(client, export['id'])
        assert job['status'] == 'complete', job
        blob = client.get(job['download']).content
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            manifest = json.loads(z.read('manifest.json'))
            transcript = json.loads(z.read('transcript.json'))
            assert manifest['revision'] == transcript['revision'] == 1
            assert manifest['segments'][1]['text'] == 'Čujem đecu.'
            assert '00:00:01,200 --> 00:00:02,200' in z.read('transcript.srt').decode()
            assert '00:00:01.200 --> 00:00:02.200' in z.read('transcript.vtt').decode()
            assert len(json.loads(z.read('audit.json'))) >= 3
            with wave.open(str(tmp_path / pid / 'audio.wav'), 'rb') as full:
                for s in manifest['segments']:
                    with wave.open(io.BytesIO(z.read(s['audio_filename'])), 'rb') as part:
                        assert part.getnframes() == round((s['end'] - s['start']) * 16000)
                        full.setpos(round(s['start'] * 16000))
                        assert part.readframes(part.getnframes()) == full.readframes(part.getnframes())
        assert (tmp_path / pid / 'original-media').read_bytes() == original
        assert client.get(f'/api/projects/{pid}/chunks/002?revision=1').status_code == 409
        assert client.get(f'/api/projects/{pid}/audio', headers={'Range':'bytes=0-99'}).status_code == 206
    with TestClient(create_app(tmp_path)) as reopened:
        saved = reopened.get(f'/api/projects/{pid}').json()
        assert saved['revision'] == 2
        assert saved['segments'][1]['text'] == 'Edited after snapshot'


def test_bad_media_reports_readability_error(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/import', files={'media':('fake.mp4', b'not media')})
        job = wait_job(client, response.json()['id'])
        assert job['status'] == 'failed'
        assert 'audio' in job['message'].lower() or 'decode' in job['message'].lower()
        assert (tmp_path / job['id'] / 'original-media').exists()


def test_invalid_import_retained_and_exports_blocked(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        rows = [{'id':'A','text':'keep ś','start':0,'end':2},{'id':'B','text':'keep ź','start':1,'end':3}]
        response = client.post('/api/import', files={'media':('a.wav',wav_bytes()),'transcript':('a.json',json.dumps(rows).encode())})
        job = wait_job(client, response.json()['id'])
        assert job['status'] == 'complete'
        pid = job['project_id']
        state = client.get('/api/projects/'+pid).json()
        assert state['issues']
        assert state['segments'][1]['start'] == 1
        assert client.get(f'/api/projects/{pid}/export/zip?revision=0').status_code == 409


def test_cross_origin_write_rejected(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/import', headers={'Origin':'https://other.example'},files={'media':('a.wav',wav_bytes())}).status_code == 403


def test_media_only_and_untimed_workflows_with_controlled_speech_backend(tmp_path, monkeypatch):
    # Deterministic contract test. Real model inference requires downloaded weights.
    import stt.app as module
    def fake_speech(path, settings, report):
        assert settings['language'] == 'bs' and settings['task'] == 'transcribe'
        return ([{'id':'001','text':'Whisper words','start':0,'end':3,'status':'unreviewed','modified':False}],
                [{'text':'Śutra','start':.5,'end':2}])
    monkeypatch.setattr(module, 'transcribe', fake_speech)
    with TestClient(create_app(tmp_path)) as client:
        for text in (None, '  Śutra!  '):
            files={'media':('a.wav', wav_bytes())}
            if text: files['transcript']=('a.txt',text.encode('utf-8'))
            response=client.post('/api/import',files=files,data={'language':'bs'})
            job=wait_job(client,response.json()['id'])
            assert job['status']=='complete',job
            state=client.get('/api/projects/'+job['project_id']).json()
            assert state['segments'][0]['text'] == (text or 'Whisper words')
            assert state['segments'][0]['status'] == ('flagged' if text else 'unreviewed')
