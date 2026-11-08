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
| `tile` | required | the tile, as a strongRef: its `ing.dasl.masl` record's address (`uri`, by DID) and exact version (`cid`), so a post shows the tile as it was when posted |
| `createdAt` | required | when it was posted |
| `text` | optional | up to 300 characters; a post can be just the tile |
| `alt` | optional | what the tile is and does, for screen readers and when only its card shows; empty means the tile's own description |
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

Anyone can write one, with any tool. Later pieces of the family (likes, comments, follows, and a permission set
covering them) will join under the same `cafe.thunderbird.tile.` prefix; new fields on a post will all be optional.

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
python scripts/tile_post.py list
python scripts/tile_post.py delete --rkey …
```

- `post` reads the tile's record from its own server (any account's) for its exact version, checks it really is an
  `ing.dasl.masl` record and that the text fits, writes one record, reads it back, and prints its address.
- `list` shows an account's tile posts; `delete` removes one after "Really delete it?".
- `--handle pyxorium.com` (or a DID) works on another account; the default is thunderbird.cafe.
- Characters are counted as Python counts them, which is never fewer than a reader sees: a few emoji made of several
  parts count as more than one.

## Tests

```
npm test
python -m unittest discover -s test -v
```

`npm test` checks the lexicon and the publish script against a stand-in account server; the Python tests run
`tile_post.py` against stand-in servers on this computer (127.0.0.1).

## Files

| | |
|---|---|
| `lexicons/` | the lexicons, one file each, named by NSID |
| `scripts/publish-lexicons.mjs` | publishes them from thunderbird.cafe |
| `scripts/tile_post.py` | writes, lists and deletes tile posts |
| `published.json` | what was published (written by the publish script) |
| `test/` | `publish-lexicons.test.mjs` (Node), `test_tile_post.py` (Python) |
