"""Write, list and delete tile posts (cafe.thunderbird.tile.post records) in your own atproto account.

claude/tile-posts-plan.md, stage 2. Standard library only: nothing to install. Run it from VS Code's terminal in
C:\\thunderbird-cafe\\tile-posts:

    python scripts/tile_post.py post --tile at://... --text "..." [--alt "..."] [--lang en] [--dry-run]
    python scripts/tile_post.py list
    python scripts/tile_post.py delete --rkey ... [--dry-run]

Add --handle pyxorium.com (or a DID) to any of them for another account; the default is thunderbird.cafe.

Writing and deleting need an app password, taken from $env:BSKY_APP_PASSWORD (one per task, deleted after):

    $env:BSKY_APP_PASSWORD = Read-Host "App password"

Listing and dry runs need none. A post names its tile by address and exact version (a strongRef: the tile record's
CID, read from the tile's own server), so Raku shows the tile as it was when posted. The tile can be anyone's.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

COLLECTION = 'cafe.thunderbird.tile.post'
TILE_COLLECTION = 'ing.dasl.masl'
DEFAULT_HANDLE = 'thunderbird.cafe'
HANDLE_RESOLVER = 'https://public.api.bsky.app'
PLC_DIRECTORY = 'https://plc.directory'
RAKU_POSTS = 'https://raku.lexicographer.space/#t=raku%3Adiscover%2Fposts&a=0'
TEXT_MAX, TEXT_MAX_BYTES = 300, 3000           # the lexicon's maxGraphemes and maxLength
ALT_MAX, ALT_MAX_BYTES = 1000, 10000
TIMEOUT = 20
USER_AGENT = 'tile_post.py (github.com/pyxorium/tile-posts)'

DID_RE = re.compile(r'^did:(plc:[a-z2-7]{24}|web:[a-zA-Z0-9.%:-]+)$')
HANDLE_RE = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$')
RKEY_RE = re.compile(r'^[A-Za-z0-9._~:-]{1,512}$')
LANG_RE = re.compile(r'^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$')


class Stop(Exception):
    """Something to tell the person, then stop (no traceback)."""


# ---------- the network ----------

def _check_url(url):
    u = urllib.parse.urlparse(url)
    # https only; plain http just for a stand-in server on this computer (the tests)
    if u.scheme == 'https' or (u.scheme == 'http' and u.hostname == '127.0.0.1'):
        return
    raise Stop(f'Refusing to talk to {url}: https only.')


def http_json(url, data=None, token=None, method=None):
    """GET (or POST when data is given) a JSON answer. Raises Stop with the server's message on an error."""
    _check_url(url)
    headers = {'Accept': 'application/json', 'User-Agent': USER_AGENT}
    body = None
    if data is not None:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=body, headers=headers, method=method or ('POST' if body is not None else 'GET'))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            text = res.read().decode('utf-8')
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as err:
        try:
            answer = json.loads(err.read().decode('utf-8'))
        except Exception:
            answer = {}
        finally:
            err.close()
        e = Stop(answer.get('message') or answer.get('error') or f'{err.code} {err.reason}')
        e.status, e.error = err.code, answer.get('error')
        raise e
    except urllib.error.URLError as err:
        raise Stop(f"Couldn't reach {urllib.parse.urlparse(url).hostname}: {err.reason}")


def xrpc(base, nsid, params=None, data=None, token=None):
    url = f'{base}/xrpc/{nsid}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    return http_json(url, data=data, token=token)


# ---------- accounts and tiles ----------

def resolve_did(actor):
    """A handle (or a DID) -> its DID."""
    actor = actor.strip().lstrip('@').lower() if not actor.startswith('did:') else actor.strip()
    if DID_RE.match(actor):
        return actor
    if not HANDLE_RE.match(actor):
        raise Stop(f'"{actor}" is neither a handle nor a DID.')
    try:
        did = xrpc(HANDLE_RESOLVER, 'com.atproto.identity.resolveHandle', {'handle': actor}).get('did')
    except Stop as err:
        raise Stop(f"Couldn't find the account @{actor} ({err}).")
    if not isinstance(did, str) or not DID_RE.match(did):
        raise Stop(f"Couldn't find the account @{actor}.")
    return did


def account(did):
    """A DID -> {'did', 'handle', 'pds'} from its DID document."""
    if did.startswith('did:plc:'):
        doc = http_json(f'{PLC_DIRECTORY}/{did}')
    else:
        host = urllib.parse.unquote(did[len('did:web:'):])
        doc = http_json(f'https://{host}/.well-known/did.json')
    if doc.get('id') != did:
        raise Stop(f"The account document for {did} doesn't match it.")
    pds = next((s.get('serviceEndpoint') for s in doc.get('service', [])
                if s.get('id') in ('#atproto_pds', f'{did}#atproto_pds') or s.get('type') == 'AtprotoPersonalDataServer'), None)
    if not isinstance(pds, str):
        raise Stop(f'The account {did} names no server.')
    handle = next((a[5:] for a in doc.get('alsoKnownAs', []) if isinstance(a, str) and a.startswith('at://')), did)
    return {'did': did, 'handle': handle, 'pds': pds.rstrip('/')}


def parse_tile_address(text):
    """at://<handle or DID>/ing.dasl.masl/<rkey> -> (actor, rkey)."""
    m = re.match(r'^at://([^/]+)/([^/]+)/([^/?#]+)$', text.strip())
    if not m:
        raise Stop(f'"{text}" is not a tile address (at://<account>/{TILE_COLLECTION}/<key>).')
    if m.group(2) != TILE_COLLECTION:
        raise Stop(f'{text} is a {m.group(2)} record, not a tile ({TILE_COLLECTION}).')
    if not RKEY_RE.match(m.group(3)):
        raise Stop(f'"{m.group(3)}" is not a record key.')
    return m.group(1), m.group(3)


def read_tile(address):
    """The tile's record from its own server -> {'uri' (by DID), 'cid', 'name', 'by'}. Stops when it isn't a tile."""
    actor, rkey = parse_tile_address(address)
    did = resolve_did(actor)
    acct = account(did)
    try:
        got = xrpc(acct['pds'], 'com.atproto.repo.getRecord', {'repo': did, 'collection': TILE_COLLECTION, 'rkey': rkey})
    except Stop as err:
        if getattr(err, 'status', None) in (400, 404):
            raise Stop(f"There's no tile at {address} (it may have been deleted).")
        raise
    value, cid = got.get('value'), got.get('cid')
    if not isinstance(value, dict) or value.get('$type') != TILE_COLLECTION or not isinstance(cid, str):
        raise Stop(f'{address} is not a tile record ({TILE_COLLECTION}).')
    tile = value.get('tile') if isinstance(value.get('tile'), dict) else value
    name = tile.get('name') if isinstance(tile.get('name'), str) else ''
    return {'uri': f'at://{did}/{TILE_COLLECTION}/{rkey}', 'cid': cid, 'name': name or 'Untitled tile', 'by': acct['handle']}


# ---------- the post ----------

def check_text(text, most, most_bytes, what):
    """Characters as Python counts them (code points): never more than a reader sees, so a text that passes here also
    passes the lexicon's grapheme limit. A few emoji made of several code points count as more than one here."""
    if len(text) > most:
        raise Stop(f'The {what} is {len(text)} characters; at most {most}.')
    if len(text.encode('utf-8')) > most_bytes:
        raise Stop(f'The {what} is too long ({len(text.encode("utf-8"))} bytes; at most {most_bytes}).')


def now_iso():
    """The time now as atproto writes it: 2026-11-08T15:04:05.123Z."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def make_record(tile, text=None, alt=None, langs=(), created_at=None):
    rec = {'$type': COLLECTION, 'tile': {'uri': tile['uri'], 'cid': tile['cid']}}
    if text:
        check_text(text, TEXT_MAX, TEXT_MAX_BYTES, 'text')
        rec['text'] = text
    if alt:
        check_text(alt, ALT_MAX, ALT_MAX_BYTES, 'alt text')
        rec['alt'] = alt
    langs = [l for l in langs if l]
    if len(langs) > 3:
        raise Stop('At most three languages.')
    for l in langs:
        if not LANG_RE.match(l):
            raise Stop(f'"{l}" is not a language tag (en, fr, pt-BR …).')
    if langs:
        rec['langs'] = langs
    rec['createdAt'] = created_at or now_iso()
    return rec


def sign_in(acct, env=os.environ):
    password = (env.get('BSKY_APP_PASSWORD') or '').strip()
    if not password:
        raise Stop('No app password: in this terminal, run\n    $env:BSKY_APP_PASSWORD = Read-Host "App password"\nthen try again.')
    try:
        session = xrpc(acct['pds'], 'com.atproto.server.createSession', data={'identifier': acct['did'], 'password': password})
    except Stop as err:
        raise Stop(f'Signing in as @{acct["handle"]} failed: {err}')
    if session.get('did') != acct['did']:
        raise Stop('That app password belongs to a different account.')
    return session['accessJwt']


def post(args, out=print, env=os.environ):
    acct = account(resolve_did(args.handle))
    tile = read_tile(args.tile)
    record = make_record(tile, text=args.text, alt=args.alt, langs=args.lang or [])
    out(f'Account: @{acct["handle"]} ({acct["did"]})')
    out(f'Tile: "{tile["name"]}" by @{tile["by"]}, {tile["uri"]}')
    out(f'      version {tile["cid"]}')
    out('The record:')
    out(json.dumps(record, indent=2, ensure_ascii=False))
    if args.dry_run:
        out('\nDry run: nothing was written.')
        return None
    token = sign_in(acct, env)
    made = xrpc(acct['pds'], 'com.atproto.repo.createRecord', data={'repo': acct['did'], 'collection': COLLECTION, 'record': record}, token=token)
    uri = made.get('uri', '')
    rkey = uri.rsplit('/', 1)[-1]
    back = xrpc(acct['pds'], 'com.atproto.repo.getRecord', {'repo': acct['did'], 'collection': COLLECTION, 'rkey': rkey})
    if back.get('value', {}).get('tile') != record['tile']:
        raise Stop(f'The post {uri} did not read back as written: look at it in PDSls.')
    out(f'\nPosted, and read back: {uri}')
    out(f'  key: {rkey}')
    out(f'  see it in Raku: {RAKU_POSTS}')
    out(f'  the record: https://pdsls.dev/{uri}')
    return uri


def list_posts(acct):
    posts, cursor = [], None
    while True:
        params = {'repo': acct['did'], 'collection': COLLECTION, 'limit': 100}
        if cursor:
            params['cursor'] = cursor
        page = xrpc(acct['pds'], 'com.atproto.repo.listRecords', params)
        records = page.get('records') or []
        posts += records
        cursor = page.get('cursor')
        if not cursor or not records or len(posts) >= 1000:
            return posts


def show_list(args, out=print, env=os.environ):
    acct = account(resolve_did(args.handle))
    posts = list_posts(acct)
    out(f'Tile posts by @{acct["handle"]} ({acct["did"]}): {len(posts)}')
    for p in posts:
        v = p.get('value') or {}
        text = (v.get('text') or '').replace('\n', ' ')
        out(f'\n  {p.get("uri", "").rsplit("/", 1)[-1]}  {v.get("createdAt", "")}')
        out(f'    {text[:70] + ("…" if len(text) > 70 else "") if text else "(no text)"}')
        out(f'    tile: {(v.get("tile") or {}).get("uri", "?")}')
    return posts


def delete(args, out=print, env=os.environ, ask=input):
    if not RKEY_RE.match(args.rkey):
        raise Stop(f'"{args.rkey}" is not a record key.')
    acct = account(resolve_did(args.handle))
    try:
        got = xrpc(acct['pds'], 'com.atproto.repo.getRecord', {'repo': acct['did'], 'collection': COLLECTION, 'rkey': args.rkey})
    except Stop as err:
        if getattr(err, 'status', None) in (400, 404):
            raise Stop(f'@{acct["handle"]} has no tile post with the key {args.rkey}.')
        raise
    v = got.get('value') or {}
    out(f'The tile post {got.get("uri")}')
    out(f'  {v.get("createdAt", "")}: {v.get("text") or "(no text)"}')
    out(f'  tile: {(v.get("tile") or {}).get("uri", "?")}')
    if args.dry_run:
        out('\nDry run: nothing was deleted.')
        return False
    token = sign_in(acct, env)
    if ask('Really delete it? [y/N] ').strip().lower() not in ('y', 'yes'):
        out('Stopped; nothing was deleted.')
        return False
    xrpc(acct['pds'], 'com.atproto.repo.deleteRecord', data={'repo': acct['did'], 'collection': COLLECTION, 'rkey': args.rkey}, token=token)
    try:
        xrpc(acct['pds'], 'com.atproto.repo.getRecord', {'repo': acct['did'], 'collection': COLLECTION, 'rkey': args.rkey})
    except Stop as err:
        if getattr(err, 'status', None) in (400, 404):
            out('Deleted (it no longer reads back).')
            return True
        raise
    raise Stop('The server said it deleted the post, but it still reads back: look at it in PDSls.')


def parser():
    p = argparse.ArgumentParser(prog='tile_post.py', description='Write, list and delete tile posts (cafe.thunderbird.tile.post).')
    sub = p.add_subparsers(dest='command', required=True)
    def common(s):
        s.add_argument('--handle', default=DEFAULT_HANDLE, help=f'the account (a handle or DID; default {DEFAULT_HANDLE})')
    s = sub.add_parser('post', help='write one tile post')
    s.add_argument('--tile', required=True, help='the tile: at://<account>/ing.dasl.masl/<key>')
    s.add_argument('--text', default=None, help=f'some words, at most {TEXT_MAX} characters (optional)')
    s.add_argument('--alt', default=None, help="what the tile is and does, for screen readers (optional; empty: the tile's own description)")
    s.add_argument('--lang', action='append', help='a language tag, e.g. en (repeat for up to three)')
    s.add_argument('--dry-run', action='store_true', help='show the record without writing it')
    common(s)
    s = sub.add_parser('list', help='list your tile posts')
    common(s)
    s = sub.add_parser('delete', help='delete one tile post, after asking')
    s.add_argument('--rkey', required=True, help='its key (the last part of its address; see list)')
    s.add_argument('--dry-run', action='store_true', help='show what would be deleted, delete nothing')
    common(s)
    return p


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors='replace')
    except Exception:
        pass
    args = parser().parse_args(argv)
    try:
        {'post': post, 'list': show_list, 'delete': delete}[args.command](args)
        return 0
    except Stop as err:
        print(f'\n{err}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nStopped.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
