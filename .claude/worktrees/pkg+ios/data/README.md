# data/

Hand-checked tables only. Public manuals, never personal data.

- `boards/<board_id>.json`: header table per board, shape `header_table` in `contracts/schema.json`.
  Every header needs `checked_by` (initials of the person who checked it against the manual page).
- `demo-b650.json` is a made-up fixture (`"fixture": true`) so the skeleton runs. Replace it with the real board.
- Never put video, frames, clips or audio here. Clips live outside the repo (see AGENTS.md, Privacy).
