// The lexicon and its publish script (claude/tile-posts-plan.md, stage 1), against a stand-in account server.
import test from 'node:test';
import assert from 'node:assert/strict';
import { runPublish, readLexicons, ACCOUNT, SCHEMA } from '../scripts/publish-lexicons.mjs';

const PDS = 'https://fibercap.us-west.host.bsky.network';

test('the lexicon: cafe.thunderbird.tile.post as the plan has it', () => {
  const [l, ...more] = readLexicons();
  assert.equal(more.length, 0);
  assert.equal(l.id, 'cafe.thunderbird.tile.post');
  const m = l.defs.main;
  assert.equal(m.type, 'record');
  assert.equal(m.key, 'tid');
  assert.deepEqual(m.record.required, ['tile', 'createdAt']);
  const p = m.record.properties;
  assert.deepEqual(p.tile, { type: 'ref', ref: 'com.atproto.repo.strongRef', description: p.tile.description });
  assert.deepEqual([p.text.maxGraphemes, p.text.maxLength], [300, 3000]);
  assert.deepEqual([p.alt.maxGraphemes, p.alt.maxLength], [1000, 10000]);
  assert.deepEqual([p.langs.maxLength, p.langs.items.format], [3, 'language']);
  assert.equal(p.createdAt.format, 'datetime');
  assert.deepEqual(Object.keys(p).sort(), ['alt', 'createdAt', 'langs', 'text', 'tile']);
});

function server({ password = 'abcd-efgh-ijkl-mnop', sessionDid = ACCOUNT, mangle = false } = {}) {
  const repo = new Map();
  const calls = [];
  const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
  const fetchImpl = async (url, init = {}) => {
    const u = new URL(url);
    calls.push({ path: u.pathname, method: init.method || 'GET', body: init.body ? JSON.parse(init.body) : null, auth: init.headers?.Authorization });
    if (u.host === 'plc.directory') return json({ id: ACCOUNT, alsoKnownAs: ['at://thunderbird.cafe'], service: [{ id: '#atproto_pds', type: 'AtprotoPersonalDataServer', serviceEndpoint: PDS }] });
    if (u.pathname.endsWith('createSession')) {
      const b = JSON.parse(init.body);
      if (b.password !== password) return json({ error: 'AuthenticationRequired', message: 'Invalid identifier or password' }, 401);
      return json({ did: sessionDid, accessJwt: 'jwt' });
    }
    if (u.pathname.endsWith('putRecord')) {
      const b = JSON.parse(init.body);
      repo.set(`${b.collection}/${b.rkey}`, mangle ? { ...b.record, defs: {} } : b.record);
      return json({ uri: `at://${b.repo}/${b.collection}/${b.rkey}`, cid: 'bafyreilexicon' });
    }
    if (u.pathname.endsWith('getRecord')) {
      const v = repo.get(`${u.searchParams.get('collection')}/${u.searchParams.get('rkey')}`);
      if (!v) return json({ error: 'RecordNotFound' }, 400);
      // keys in another order, as a server may hand them back
      return json({ uri: 'x', cid: 'bafyreilexicon', value: Object.fromEntries(Object.entries(v).reverse()) });
    }
    return json({ error: 'NotFound' }, 404);
  };
  return { fetchImpl, calls, repo };
}
const quiet = () => {};

test('a dry run shows what would be published and writes nothing', async () => {
  const s = server();
  let wrote = false;
  const r = await runPublish({ fetchImpl: s.fetchImpl, log: quiet, dryRun: true, env: {}, readPublished: () => ({}), writePublished: () => { wrote = true; },
    ask: () => assert.fail('no questions in a dry run'), askHidden: () => assert.fail('no password in a dry run') });
  assert.deepEqual(r.due, ['cafe.thunderbird.tile.post']);
  assert.equal(wrote, false);
  assert.ok(!s.calls.some((c) => c.method === 'POST'));
});

test('publishing: the password from $env:BSKY_APP_PASSWORD, one record keyed by the NSID, read back, published.json written', async () => {
  const s = server();
  let saved = null;
  const lines = [];
  const r = await runPublish({ fetchImpl: s.fetchImpl, log: (l) => lines.push(l), env: { BSKY_APP_PASSWORD: 'abcd-efgh-ijkl-mnop' }, readPublished: () => ({}),
    writePublished: (o) => { saved = o; }, ask: async () => 'y', askHidden: () => assert.fail('the password came from the environment'), now: () => '2026-11-08T12:00:00.000Z' });
  assert.equal(r.changed, true);
  const put = s.calls.find((c) => c.path.endsWith('putRecord'));
  assert.equal(put.body.collection, SCHEMA);
  assert.equal(put.body.rkey, 'cafe.thunderbird.tile.post');
  assert.equal(put.body.repo, ACCOUNT);
  assert.equal(put.body.record.$type, SCHEMA);
  assert.equal(put.auth, 'Bearer jwt');
  const entry = saved.lexicons['cafe.thunderbird.tile.post'];
  assert.equal(entry.uri, `at://${ACCOUNT}/${SCHEMA}/cafe.thunderbird.tile.post`);
  assert.equal(entry.text, JSON.stringify(readLexicons()[0]));
  assert.ok(lines.some((l) => l.includes('_lexicon.tile')), 'it reminds about the TXT record');

  // again, unchanged: nothing to do, no password asked
  const s2 = server();
  const r2 = await runPublish({ fetchImpl: s2.fetchImpl, log: quiet, env: {}, readPublished: () => saved, writePublished: () => assert.fail('nothing to write'),
    ask: () => assert.fail('nothing to ask'), askHidden: () => assert.fail('nothing to ask') });
  assert.equal(r2.changed, false);
  // a changed text is published again
  const old = { lexicons: { 'cafe.thunderbird.tile.post': { ...entry, text: '{"old":1}' } } };
  const r3 = await runPublish({ fetchImpl: server().fetchImpl, log: quiet, dryRun: true, env: {}, readPublished: () => old, ask: quiet, askHidden: quiet });
  assert.deepEqual(r3.due, ['cafe.thunderbird.tile.post']);
});

test('the password asked for (hidden) when the environment has none; "no" stops before writing', async () => {
  const s = server();
  let asked = 0;
  const r = await runPublish({ fetchImpl: s.fetchImpl, log: quiet, env: {}, readPublished: () => ({}), writePublished: () => assert.fail('stopped'),
    askHidden: async () => { asked++; return 'abcd-efgh-ijkl-mnop'; }, ask: async () => 'n' });
  assert.equal(asked, 1);
  assert.equal(r.changed, false);
  assert.ok(!s.calls.some((c) => c.path.endsWith('putRecord')));
});

test("another account's app password, or a record that doesn't read back, stops it", async () => {
  await assert.rejects(runPublish({ fetchImpl: server({ sessionDid: 'did:plc:someoneelseaaaaaaaaaaaaa' }).fetchImpl, log: quiet, env: { BSKY_APP_PASSWORD: 'abcd-efgh-ijkl-mnop' },
    readPublished: () => ({}), writePublished: () => {}, ask: async () => 'y', askHidden: quiet }), /different account/);
  await assert.rejects(runPublish({ fetchImpl: server({ mangle: true }).fetchImpl, log: quiet, env: { BSKY_APP_PASSWORD: 'abcd-efgh-ijkl-mnop' },
    readPublished: () => ({}), writePublished: () => {}, ask: async () => 'y', askHidden: quiet }), /didn't read back/);
  await assert.rejects(runPublish({ fetchImpl: server().fetchImpl, log: quiet, env: { BSKY_APP_PASSWORD: 'wrong' },
    readPublished: () => ({}), writePublished: () => {}, ask: async () => 'y', askHidden: quiet }), /Invalid identifier or password/);
});
