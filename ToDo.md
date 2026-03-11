# ToDo for EXE Packaging

Goal: prepare this project so it can be packaged as a single Windows executable with stable runtime behavior.

## Hard Requirements

- `LtpaToken2` must only exist during runtime.
- `LtpaToken2` must never be written to disk.
- Do not use `.env` anymore for runtime operation.
- Do not rely on browser `localStorage` as the only source of truth for connection state.
- Persistent app data must live in a local user-writable app folder on Windows, not in temp and not inside bundled code.
- Keep current cleanup rules.

## Runtime Storage Rules

Use a persistent local app folder, for example:

- `%LOCALAPPDATA%\\MaximoAssetScanUI\\`

Store persistent non-secret files there:

- `cache\\queue.json`
- `cache\\templates.json`
- `cache\\projects.json`
- `cache\\users.json`
- `cache\\locations_raw.json`
- `cache\\locations_tree.json`
- optional later: `logs\\app.log`

Do not store `LtpaToken2` there.

## Queue and Cache Rules

- `queue.json` must be persistent and must never be placed in temp.
- Downloaded JSON cache files must be persistent and must never be placed in temp.
- `queue.json` must not be deleted automatically.
- Cache JSON files should be overwritten only after a successful refresh.
- If `Hole Daten` fails, keep the previous cache files.
- No automatic cleanup on startup.
- If cleanup is wanted later, add an explicit manual action such as `Cache leeren`.

## Connection Rules

- `SERVER` may be persisted if needed.
- `LtpaToken2` must remain runtime-only.
- After app restart, the user may need to re-enter `LtpaToken2`.
- Web UI should pass `SERVER` and `LtpaToken2` into the running backend session directly.
- `Hole Daten` should also receive `SERVER` and `LtpaToken2` directly from the running app state.

## Refactor Needed Before Packaging

1. Introduce one runtime app-data directory helper in `maximo/config/settings.py`.
2. Move all cache and queue paths to that runtime app-data directory.
3. Decide whether `SERVER` should be persisted in a small non-secret config file.
4. Do not persist `LtpaToken2`.
5. Refactor the current `python -m maximo.main` flow so data refresh runs in-process instead of spawning a Python module subprocess.
6. Keep the web routes working with the refactored in-process refresh flow.
7. Make sure first start without cache files is handled cleanly in the UI.
8. Verify that queue persistence still works after restart.

## Packaging Notes

- Target is a single Windows `.exe`.
- Bundled app code may be unpacked to a temp location by the packager; writable runtime data must not go there.
- Static web assets must still be served correctly from the packaged app.
- Path handling must work both in normal Python execution and in the packaged EXE.

## Non-Goals

- Do not change current cleanup rules.
- Do not store `LtpaToken2` anywhere on disk.
- Do not move queue/cache data into temp.

## Suggested Validation After Refactor

- Start app with no existing cache directory.
- Enter `SERVER` and `LtpaToken2` in UI.
- Run `Hole Daten`.
- Confirm cache JSON files are created in the persistent app-data folder.
- Add queue entries and confirm `queue.json` is created in the persistent app-data folder.
- Restart app and confirm queue persists.
- Confirm `LtpaToken2` is not present in any written file.
- Confirm upload still works with a freshly entered runtime token.
