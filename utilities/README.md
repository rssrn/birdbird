# Utilities

One-off and maintenance scripts for managing birdbird data and R2 storage.
Run from the project root with the venv active:

```bash
source ../.venv/bin/activate   # if not already active
python utilities/<script>.py [args]
```

---

## remove_batch.py

Remove a batch entry from `latest.json` in R2.

Use this after manually deleting batch files from R2 storage. Only updates
the `latest.json` index; does not delete any objects from R2.

```bash
# Interactive: lists batches and prompts for selection
python utilities/remove_batch.py

# Remove a specific batch
python utilities/remove_batch.py 20260205_01

# Preview without writing anything
python utilities/remove_batch.py 20260205_01 --dry-run
```

---

## update_metadata.py

Backfill `start_date` / `end_date` fields into existing batch `metadata.json`
files in R2. Only needed for batches uploaded before these fields were added.

```bash
python utilities/update_metadata.py [/path/to/BIRDS]
```

Defaults to `/home/ross/BIRDS` if no path is given. Skips batches that
already have the fields. Updates `latest.json` with the new values.
