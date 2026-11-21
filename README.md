# Tile posts

A **tile post** shares a web tile with a few words. It is a record of the kind `cafe.thunderbird.tile.post` in
its author's own atproto account, and [Raku](https://raku.lexicographer.space/) shows everyone's under
**Discover → Tile posts**. Bluesky doesn't show them.

This repo holds the tile family's lexicons (`cafe.thunderbird.tile.*`, published from thunderbird.cafe), the script
that publishes them, and a small Python script that writes, lists and deletes tile posts. Raku (reading) and, later,
the Web Tile Foundry (writing) both use it; neither owns it.

## The record: `cafe.thunderbird.tile.post`

`lexicons/cafe.thunderbird.tile.post.json`. Record keys are TIDs (time-based, like Bluesky posts).

| Field | | |
|---|---|---|
| `tile` | required | the tile, as a strongRef: its `ing.dasl.masl` record's address (`uri`, by DID) and exact version (`cid`), so a post shows the tile as it was when posted; with `record`, the renderer tile that shows that record |
| `record` | optional | since Nov 20 2026: the record the post is about when it isn't a tile (a song, later a place or a signpost), as a strongRef; shown by the renderer tile in `tile` |
| `createdAt` | required | when it was posted |
| `text` | optional | up to 300 characters; a post can be just the tile |
| `alt` | optional | what the tile (or the record) is and does, for screen readers and when only its card shows; empty means the tile's own description, or a line made from the record |
| `langs` | optional | up to three language tags |

An example:

```json
{
  "$type": "cafe.thunderbird.tile.post",
  "tile": {
    "uri": "at://did:plc:rqbqpaaluty5v47jwciowpik/ing.dasl.masl/3myyjuyr2ja2s",
    "cid": "bafyrei…"
  },
  "text": "An impossible maze you can walk around in.",
  "alt": "A small 3D maze you walk with the arrow keys.",
  "langs": ["en"],
  "createdAt": "2026-11-08T16:00:00.000Z"
}
```

**A song post** (claude/mixtape-3c-track-renderer-notes.md, R3c-11 and PB2): `record` is the song (a
`cafe.thunderbird.audio.track`, or an `fm.plyr.track` with its audio on its account's own server) and `tile` is
**Tracks**, the renderer tile that plays it. Raku shows a song card and plays that song with its currently pinned
Tracks; readers that don't know `record` show Tracks' card, which explains what it is when opened alone.

```json
{
  "$type": "cafe.thunderbird.tile.post",
  "tile": { "uri": "at://did:plc:6vxjigxrqizmbo56gojxico3/ing.dasl.masl/3n2sdwt2j6s2f", "cid": "bafyrei…" },
  "record": { "uri": "at://did:plc:rqbqpaaluty5v47jwciowpik/cafe.thunderbird.audio.track/3n2cz64eheg2v", "cid": "bafyrei…" },
  "text": "Ten minutes of No Expectations, from the Fillmore in 2002.",
  "createdAt": "2026-11-21T16:00:00.000Z"
}
```

Anyone can write one, with any tool. Later pieces of the family (comments, follows) will join under the same
`cafe.thunderbird.tile.` prefix; new fields on a post will all be optional. Raku's sign-in permission ("Raku",
`cafe.thunderbird.authRaku`, in the Raku repo) covers writing posts and hearts.

## The record: `cafe.thunderbird.tile.like` (a heart)

`lexicons/cafe.thunderbird.tile.like.json` (Nov 2026). Shaped like Bluesky's `app.bsky.feed.like`, in the hearting
account's own repo; record keys are TIDs. Raku shows them as hearts on tile posts and counts distinct accounts.
Deleting the record takes the heart back.

| Field | | |
|---|---|---|
| `subject` | required | what is hearted, as a strongRef (`uri`, `cid`): usually a `cafe.thunderbird.tile.post`; possibly a tile (`ing.dasl.masl`) later. Readers ignore subjects they don't show |
| `createdAt` | required | when it was given |

```json
{
  "$type": "cafe.thunderbird.tile.like",
  "subject": {
    "uri": "at://did:plc:6vxjigxrqizmbo56gojxico3/cafe.thunderbird.tile.post/3m…",
    "cid": "bafyrei…"
  },
  "createdAt": "2026-11-11T16:00:00.000Z"
}
```

## Publishing the lexicons

The names belong to thunderbird.cafe: a TXT record at `_lexicon.tile.thunderbird.cafe` with the value
`did=did:plc:6vxjigxrqizmbo56gojxico3` says so. Then, in this folder (Node 22, nothing to install):

```
node scripts/publish-lexicons.mjs --dry-run
node scripts/publish-lexicons.mjs
```

Each lexicon is written as a `com.atproto.lexicon.schema` record in thunderbird.cafe's repo (key: its NSID), only
when it is new or changed, and read back to check. The app password comes from `$env:BSKY_APP_PASSWORD`, or is asked
for. `published.json` records what was published: commit it.

## Writing a tile post (`scripts/tile_post.py`)

Python 3, standard library only. Writing and deleting need an app password in this terminal (one per task, deleted
after); listing and dry runs don't:

```
$env:BSKY_APP_PASSWORD = Read-Host "App password"
python scripts/tile_post.py post --tile at://pyxorium.com/ing.dasl.masl/3myyjuyr2ja2s --text "Walk the maze" --alt "A small 3D maze" --lang en --dry-run
python scripts/tile_post.py post --tile at://pyxorium.com/ing.dasl.masl/3myyjuyr2ja2s --text "Walk the maze" --alt "A small 3D maze" --lang en
python scripts/tile_post.py post --song at://pyxorium.com/cafe.thunderbird.audio.track/3n2cz64eheg2v --text "…" --handle pyxorium.com --dry-run
python scripts/tile_post.py list
python scripts/tile_post.py delete --rkey …
```

- `post` reads the tile's record from its own server (any account's) for its exact version, checks it really is an
  `ing.dasl.masl` record and that the text fits, writes one record, reads it back, and prints its address.
- `post --song` reads the song's record from its own server for its exact version (refusing another kind, or a plyr.fm
  song whose audio is only on plyr.fm's storage), puts it in `record`, and puts **Tracks** in `tile`: Tracks' address
  from `C:\thunderbird-cafe\renderer-tiles\published.json` (`track-renderer`) when that folder sits beside this one,
  its exact version read from its own server; `--renderer at://…` names it instead.
- `list` shows an account's tile posts (and a song post's `record`); `delete` removes one after "Really delete it?".
- `--handle pyxorium.com` (or a DID) works on another account; the default is thunderbird.cafe.
- Characters are counted as Python counts them, which is never fewer than a reader sees: a few emoji made of several
  parts count as more than one.

## Tests

```
npm test
python -m unittest discover -s test -v
```

`npm test` checks the lexicons and the publish script against a stand-in account server; the Python tests run
`tile_post.py` against stand-in servers on this computer (127.0.0.1).

## Files

| | |
|---|---|
| `lexicons/` | the lexicons, one file each, named by NSID |
| `scripts/publish-lexicons.mjs` | publishes them from thunderbird.cafe |
| `scripts/tile_post.py` | writes, lists and deletes tile posts |
| `published.json` | what was published (written by the publish script) |
| `test/` | `publish-lexicons.test.mjs` (Node), `test_tile_post.py` (Python) |
