"""tile_post.py against a stand-in account directory, handle resolver and account server (http://127.0.0.1).

Run from C:\\thunderbird-cafe\\tile-posts:  python -m unittest discover -s test -v
"""
import importlib.util
import io
import json
import threading
import types
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

spec = importlib.util.spec_from_file_location('tile_post', Path(__file__).resolve().parents[1] / 'scripts' / 'tile_post.py')
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)

ME = 'did:plc:6vxjigxrqizmbo56gojxico3'          # thunderbird.cafe
OTHER = 'did:plc:rqbqpaaluty5v47jwciowpik'       # pyxorium.com (the maze's account)
PASSWORD = 'abcd-efgh-ijkl-mnop'
TILE_CID = 'bafyreigawujq3a4qtir6mepbu3yk4owndjwkb7xd6xuwyoi53nkyknsloe'


class World:
    """The stand-in network: one server answering for plc.directory, the handle resolver and both accounts' servers."""
    def __init__(self):
        self.records = {
            (OTHER, 'ing.dasl.masl', '3mzmaze'): {'cid': TILE_CID, 'value': {'$type': 'ing.dasl.masl', 'tile': {'name': 'The Escher maze'}}},
            (OTHER, 'app.bsky.feed.post', 'notatile'): {'cid': 'bafyreipost', 'value': {'$type': 'app.bsky.feed.post', 'text': 'hi'}},
            (OTHER, 'ing.dasl.masl', 'fake'): {'cid': 'bafyreifake', 'value': {'$type': 'something.else'}},
        }
        self.calls = []
        self.next = 0
        self.keep_after_delete = False
        world = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def answer(self, obj, status=200):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.handle_any(None)

            def do_POST(self):
                n = int(self.headers.get('content-length') or 0)
                self.handle_any(json.loads(self.rfile.read(n) or b'{}'))

            def handle_any(self, data):
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                world.calls.append((self.command, u.path, q, data, self.headers.get('Authorization')))
                base = f'http://127.0.0.1:{world.port}'
                if u.path.startswith('/plc/'):
                    did = u.path[len('/plc/'):]
                    hd = {ME: 'thunderbird.cafe', OTHER: 'pyxorium.com'}.get(did)
                    if not hd:
                        return self.answer({'message': 'DID not registered'}, 404)
                    return self.answer({'id': did, 'alsoKnownAs': [f'at://{hd}'], 'service': [{'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': f'{base}/pds'}]})
                name = u.path.rsplit('/', 1)[-1]
                if name == 'com.atproto.identity.resolveHandle':
                    did = {'thunderbird.cafe': ME, 'pyxorium.com': OTHER}.get(q.get('handle'))
                    return self.answer({'did': did}) if did else self.answer({'error': 'InvalidRequest', 'message': 'Unable to resolve handle'}, 400)
                if name == 'com.atproto.server.createSession':
                    if data.get('password') != PASSWORD:
                        return self.answer({'error': 'AuthenticationRequired', 'message': 'Invalid identifier or password'}, 401)
                    return self.answer({'did': data['identifier'], 'accessJwt': 'jwt-' + data['identifier']})
                if name == 'com.atproto.repo.getRecord':
                    r = world.records.get((q['repo'], q['collection'], q['rkey']))
                    if not r:
                        return self.answer({'error': 'RecordNotFound', 'message': 'Could not locate record'}, 400)
                    return self.answer({'uri': f"at://{q['repo']}/{q['collection']}/{q['rkey']}", **r})
                if name == 'com.atproto.repo.listRecords':
                    keys = sorted([k for k in world.records if k[0] == q['repo'] and k[1] == q['collection']], key=lambda k: k[2], reverse=True)
                    return self.answer({'records': [{'uri': f'at://{k[0]}/{k[1]}/{k[2]}', **world.records[k]} for k in keys]})
                if name == 'com.atproto.repo.createRecord':
                    if self.headers.get('Authorization') != f"Bearer jwt-{data['repo']}":
                        return self.answer({'error': 'AuthRequired'}, 401)
                    world.next += 1
                    rkey = f'3mztest{world.next:06d}'.replace('0', 'a').replace('1', 'b')
                    world.records[(data['repo'], data['collection'], rkey)] = {'cid': 'bafyreinew', 'value': data['record']}
                    return self.answer({'uri': f"at://{data['repo']}/{data['collection']}/{rkey}", 'cid': 'bafyreinew'})
                if name == 'com.atproto.repo.deleteRecord':
                    if self.headers.get('Authorization') != f"Bearer jwt-{data['repo']}":
                        return self.answer({'error': 'AuthRequired'}, 401)
                    if not world.keep_after_delete:
                        world.records.pop((data['repo'], data['collection'], data['rkey']), None)
                    return self.answer({})
                return self.answer({'error': 'NotFound'}, 404)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TilePostTest(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.saved = (tp.PLC_DIRECTORY, tp.HANDLE_RESOLVER)
        tp.PLC_DIRECTORY = f'http://127.0.0.1:{self.w.port}/plc'
        tp.HANDLE_RESOLVER = f'http://127.0.0.1:{self.w.port}'
        self.env = {'BSKY_APP_PASSWORD': PASSWORD}

    def tearDown(self):
        tp.PLC_DIRECTORY, tp.HANDLE_RESOLVER = self.saved
        self.w.close()

    def args(self, argv):
        return tp.parser().parse_args(argv)

    def run_quiet(self, fn, *a, **kw):
        lines = []
        result = fn(*a, out=lambda s='': lines.append(str(s)), **kw)
        return result, '\n'.join(lines)

    def mine(self):
        return {k: v for k, v in self.w.records.items() if k[0] == ME and k[1] == tp.COLLECTION}

    def test_post_writes_one_record_with_the_tiles_exact_version(self):
        uri, said = self.run_quiet(tp.post, self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze', '--text', 'Walk the maze',
                                                       '--alt', 'A small 3D maze', '--lang', 'en']), env=self.env)
        posts = self.mine()
        self.assertEqual(len(posts), 1)
        (_, _, rkey), r = next(iter(posts.items()))
        rec = r['value']
        self.assertEqual(rec['$type'], tp.COLLECTION)
        self.assertEqual(rec['tile'], {'uri': f'at://{OTHER}/ing.dasl.masl/3mzmaze', 'cid': TILE_CID}, 'the tile by DID and exact version')
        self.assertEqual((rec['text'], rec['alt'], rec['langs']), ('Walk the maze', 'A small 3D maze', ['en']))
        self.assertRegex(rec['createdAt'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')
        self.assertEqual(uri, f'at://{ME}/{tp.COLLECTION}/{rkey}')
        self.assertIn(uri, said)
        self.assertIn('raku.lexicographer.space', said)
        self.assertIn('"The Escher maze" by @pyxorium.com', said)

    def test_a_post_can_be_just_the_tile(self):
        self.run_quiet(tp.post, self.args(['post', '--tile', f'at://{OTHER}/ing.dasl.masl/3mzmaze']), env=self.env)
        rec = next(iter(self.mine().values()))['value']
        self.assertEqual(sorted(rec), ['$type', 'createdAt', 'tile'])

    def test_dry_run_writes_nothing_and_needs_no_password(self):
        _, said = self.run_quiet(tp.post, self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze', '--text', 'hi', '--dry-run']), env={})
        self.assertIn('Dry run: nothing was written.', said)
        self.assertIn('"cid": "' + TILE_CID, said)
        self.assertEqual(self.mine(), {})
        self.assertFalse(any(c[1].endswith('createSession') or c[1].endswith('createRecord') for c in self.w.calls))

    def test_text_limits(self):
        with self.assertRaisesRegex(tp.Stop, '301 characters; at most 300'):
            self.run_quiet(tp.post, self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze', '--text', 'x' * 301]), env=self.env)
        self.run_quiet(tp.post, self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze', '--text', 'é' * 300]), env=self.env)
        with self.assertRaisesRegex(tp.Stop, 'alt text'):
            tp.make_record({'uri': 'u', 'cid': 'c'}, alt='a' * 1001)
        with self.assertRaisesRegex(tp.Stop, 'language tag'):
            tp.make_record({'uri': 'u', 'cid': 'c'}, langs=['english please'])
        with self.assertRaisesRegex(tp.Stop, 'three'):
            tp.make_record({'uri': 'u', 'cid': 'c'}, langs=['en', 'fr', 'de', 'it'])
        self.assertEqual(len(self.mine()), 1)

    def test_the_tile_must_really_be_a_tile(self):
        cases = [
            ('at://pyxorium.com/app.bsky.feed.post/notatile', 'not a tile'),
            ('at://pyxorium.com/ing.dasl.masl/missing', "There's no tile"),
            ('at://pyxorium.com/ing.dasl.masl/fake', 'not a tile record'),
            ('https://example.org/x', 'not a tile address'),
            ('at://nobody.example.org/ing.dasl.masl/3mzmaze', "Couldn't find the account"),
        ]
        for address, words in cases:
            with self.subTest(address), self.assertRaisesRegex(tp.Stop, words):
                self.run_quiet(tp.post, self.args(['post', '--tile', address, '--dry-run']), env=self.env)
        self.assertEqual(self.mine(), {})

    def test_password_needed_and_checked(self):
        a = self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze'])
        with self.assertRaisesRegex(tp.Stop, 'Read-Host'):
            self.run_quiet(tp.post, a, env={})
        with self.assertRaisesRegex(tp.Stop, 'Invalid identifier or password'):
            self.run_quiet(tp.post, a, env={'BSKY_APP_PASSWORD': 'wrong'})
        self.assertEqual(self.mine(), {})

    def test_another_account_with_handle(self):
        self.run_quiet(tp.post, self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze', '--handle', 'pyxorium.com']), env=self.env)
        self.assertEqual(len([k for k in self.w.records if k[0] == OTHER and k[1] == tp.COLLECTION]), 1)
        self.assertEqual(self.mine(), {})

    def test_list_and_delete(self):
        for t in ('one', 'two'):
            self.run_quiet(tp.post, self.args(['post', '--tile', 'at://pyxorium.com/ing.dasl.masl/3mzmaze', '--text', t]), env=self.env)
        posts, said = self.run_quiet(tp.show_list, self.args(['list']), env={})
        self.assertEqual(len(posts), 2)
        self.assertIn('Tile posts by @thunderbird.cafe', said)
        self.assertIn(f'tile: at://{OTHER}/ing.dasl.masl/3mzmaze', said)
        rkey = posts[0]['uri'].rsplit('/', 1)[-1]
        # a dry run and a "no" leave it
        done, said = self.run_quiet(tp.delete, self.args(['delete', '--rkey', rkey, '--dry-run']), env={})
        self.assertFalse(done)
        self.assertIn('nothing was deleted', said)
        done, _ = self.run_quiet(tp.delete, self.args(['delete', '--rkey', rkey]), env=self.env, ask=lambda q: 'n')
        self.assertFalse(done)
        self.assertEqual(len(self.mine()), 2)
        # yes: gone, and checked
        asked = []
        done, said = self.run_quiet(tp.delete, self.args(['delete', '--rkey', rkey]), env=self.env, ask=lambda q: asked.append(q) or 'y')
        self.assertTrue(done)
        self.assertEqual(asked, ['Really delete it? [y/N] '])
        self.assertEqual(len(self.mine()), 1)
        self.assertIn('Deleted', said)
        with self.assertRaisesRegex(tp.Stop, 'has no tile post with the key'):
            self.run_quiet(tp.delete, self.args(['delete', '--rkey', rkey]), env=self.env, ask=lambda q: 'y')
        # a server that says it deleted but didn't
        other = self.mine()
        self.w.keep_after_delete = True
        with self.assertRaisesRegex(tp.Stop, 'still reads back'):
            self.run_quiet(tp.delete, self.args(['delete', '--rkey', next(iter(other))[2]]), env=self.env, ask=lambda q: 'y')

    def test_https_only(self):
        with self.assertRaisesRegex(tp.Stop, 'https only'):
            tp.http_json('http://example.org/x')

    def test_main_prints_problems_without_a_traceback(self):
        err = io.StringIO()
        import contextlib
        with contextlib.redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = tp.main(['post', '--tile', 'nonsense', '--dry-run'])
        self.assertEqual(code, 1)
        self.assertIn('not a tile address', err.getvalue())
        self.assertNotIn('Traceback', err.getvalue())


if __name__ == '__main__':
    unittest.main()
