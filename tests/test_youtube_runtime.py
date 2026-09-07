"""Native mpv smoke checks using localhost VTT, a generated image and silent WAV.
No YouTube service, GPU, audio device, desktop GUI or user configuration is used.
"""
import collections
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
VTT = b'WEBVTT\n\n00:00:00.000 --> 00:00:19.000\nA test caption.\n'

class CaptionPlayback(unittest.TestCase):
    def setUp(self):
        binary = shutil.which('mpv')
        if not binary or not hasattr(socket, 'AF_UNIX'):
            if os.environ.get('NATIVE_MPV_REQUIRED') == '1':
                self.fail('Native mpv and Unix IPC are required for this CI job')
            self.skipTest('Native mpv/Unix IPC unavailable; run the dedicated Linux CI job')
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        config = self.root / 'config'
        module = config / 'scripts/modules/stream_policy.lua'
        module.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / 'scripts/modules/stream_policy.lua', module)
        # --no-config would also disable find_config_file for this isolated directory.
        (config / 'mpv.conf').write_text('# Isolated native caption test\n')
        self.image = self.root / 'clip.ppm'
        self.image.write_bytes(b'P6\n16 16\n255\n' + b'\0' * 768)
        self.hits = collections.Counter()
        self.started = threading.Event()
        hits, started = self.hits, self.started
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits[self.path] += 1
                if self.path == '/slow.vtt':
                    started.set()
                    time.sleep(1.5)
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/vtt; charset=utf-8')
                    self.send_header('Content-Length', str(len(VTT)))
                    self.end_headers()
                    self.wfile.write(VTT)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.url = 'http://127.0.0.1:' + str(server.server_port)
        ipc = self.root / 'ipc'
        self.process = subprocess.Popen([
            binary, '--config-dir=' + str(config), '--load-scripts=no',
            '--script=' + str(ROOT / 'scripts/ytdl-sub-menu.lua'),
            '--script=' + str(ROOT / 'scripts/player-toolbar.lua'), '--ytdl=no',
            '--vo=null', '--ao=null', '--force-window=no', '--idle=yes', '--keep-open=yes',
            '--image-display-duration=20', '--input-ipc-server=' + str(ipc),
            '--log-file=' + str(self.root / 'mpv.log')],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dump_script_log)
        self.addCleanup(self.stop_player)
        self.wait(lambda: ipc.exists())
        self.connection = socket.socket(socket.AF_UNIX)
        self.connection.settimeout(5)
        self.connection.connect(str(ipc))
        self.addCleanup(self.connection.close)
        self.reader = self.connection.makefile('rb')
        self.addCleanup(self.reader.close)
        self.request_id = 0
        self.command('loadfile', str(self.image))
        self.wait(lambda: self.get('time-pos') is not None)
        self.command('set_property', 'sub-visibility', False)

    def dump_script_log(self):
        path = self.root / 'mpv.log'
        if path.exists():
            lines = path.read_text(errors='replace').splitlines()
            relevant = [line for line in lines if any(word in line for word in
                        ('ytdl_sub_menu', 'ytdl-sub-menu', 'stream_policy', 'player_toolbar', 'Lua error'))]
            print('MPV caption-script log:\n' + '\n'.join(relevant)[-12000:])

    def stop_player(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        log = (self.root / 'mpv.log').read_text(errors='replace') if (self.root / 'mpv.log').exists() else ''
        self.fail('Timed out waiting for mpv state\n' + log[-6000:])

    def command(self, *args, allow_missing=False):
        self.request_id += 1
        rid = self.request_id
        self.connection.sendall((json.dumps({'command': args, 'request_id': rid}) + '\n').encode())
        while True:
            line = self.reader.readline()
            if not line:
                self.fail('mpv closed IPC')
            reply = json.loads(line)
            if reply.get('request_id') == rid:
                if reply.get('error') != 'success' and not allow_missing:
                    self.fail(str(reply))
                return reply.get('data')

    def get(self, name):
        return self.command('get_property', name, allow_missing=True)

    def prepare_captions(self, path):
        metadata = {'automatic_captions': {'en': [{'ext': 'vtt', 'name': 'English', 'url': self.url + path}]}}
        self.command('set_property', 'user-data/mpv/ytdl/source-url', 'https://youtu.be/fixture')
        self.command('set_property', 'user-data/mpv/ytdl/json-subprocess-result',
                     {'status': 0, 'stdout': json.dumps(metadata)})

    def subtitles(self):
        return [t for t in self.get('track-list') or [] if t['type'] == 'sub']

    def test_load_and_reuse(self):
        self.prepare_captions('/caption.vtt')
        self.assertEqual(sum(self.hits.values()), 0)
        before = self.get('time-pos')
        self.command('script-message-to', 'ytdl_sub_menu', 'fetch-sub', 'en')
        self.wait(lambda: any(t.get('selected') for t in self.subtitles())
                  and self.get('sub-visibility') is True)
        self.assertTrue(self.get('sub-visibility'))
        self.assertGreaterEqual(self.get('time-pos'), before)
        self.assertEqual(self.hits['/caption.vtt'], 1)
        self.command('script-message-to', 'ytdl_sub_menu', 'fetch-sub', 'en')
        time.sleep(0.3)
        self.assertEqual(self.hits['/caption.vtt'], 1)
        self.assertEqual(len(self.subtitles()), 1)

    def test_cancel_on_file_change(self):
        self.prepare_captions('/slow.vtt')
        self.command('script-message-to', 'ytdl_sub_menu', 'fetch-sub', 'en')
        self.assertTrue(self.started.wait(5), 'Caption request did not start')
        self.command('loadfile', str(self.image))
        time.sleep(2)
        self.assertEqual(self.subtitles(), [], 'Old captions leaked into the new file')
        self.assertEqual(self.hits['/slow.vtt'], 1)

    def test_stable_volume_preserves_filters(self):
        audio = self.root / 'audio.wav'
        with wave.open(str(audio), 'wb') as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(48000)
            out.writeframes(b'\0' * (48000 * 4 * 30))
        self.command('loadfile', str(audio))
        self.wait(lambda: self.get('audio-params') is not None)
        custom = {'name': 'lavfi', 'label': 'user_filter', 'params': {'graph': 'volume=0.5'}}
        self.command('set_property', 'af', [custom])
        before = self.get('af')
        label = 'mpv_config_stable_volume'
        self.command('script-message-to', 'player_toolbar', 'toggle-stable-volume')
        self.wait(lambda: any(f.get('label') == label for f in self.get('af') or []))
        self.assertEqual([f for f in self.get('af') if f.get('label') != label], before)
        self.command('script-message-to', 'player_toolbar', 'toggle-stable-volume')
        self.wait(lambda: self.get('af') == before)
        legacy = before + [
            {'name': 'lavfi', 'params': {'graph': 'dynaudnorm=f=500:g=15:p=0.95:m=10'}},
            {'name': 'lavfi', 'params': {'graph': 'alimiter=limit=0.9:level=false'}},
        ]
        self.command('set_property', 'af', legacy)
        self.command('script-message-to', 'player_toolbar', 'toggle-stable-volume')
        self.wait(lambda: self.get('af') == before)
        self.assertEqual(self.get('path'), str(audio))

if __name__ == '__main__':
    unittest.main()
