# Collar — how agents work here

## Task tracking (read this first, every session)

- `todo/todo.md` is the single list of open work. Read it at the start of every session before doing anything else.
- Work only on items listed there (or on what the user asks for directly). If the user asks for something not in the list, add it as an item first, then do it.
- `todo/done_YYYYMM.md` (current month, UTC) holds completed items. Nothing is ever deleted from the repo's task history; it is moved.
- Never infer status from a file's location or from notes in other documents; only `todo/` carries status.

## Item format

One item per line, checkbox at column 0, stable ID, short title, optional pointer to context:

```markdown
- [ ] T012 Short title of the task — see path/to/context.md or a one-line why
```

- IDs are `T` + zero-padded number, assigned sequentially, never reused. Take the next number after the highest ID in `todo.md` and all `done_*.md`.
- Keep lines in `todo.md` ordered by priority (top = do first). Never reword or merge an existing line; add a new item instead.
- Sub-steps, notes and findings go indented under the item, not in other files.

## Completing an item

When an item is finished (code changed, tests passing where applicable, and verified):

1. Remove the line from `todo/todo.md`.
2. Append it to `todo/done_YYYYMM.md` for the current month as:

   ```markdown
   - [x] T012 Short title of the task — 2026-10-27 3f2a1c0
   ```

   Date = completion date (UTC), followed by the short commit sha. If not yet committed, write `uncommitted` and let the commit step fix it.
3. Mention the item ID in the commit message (`T012: short title`).

Partial progress stays in `todo.md` with notes under the item. Do not move an item to done because it is "mostly" finished.

## Finding new work

If you find a bug, drift or risk while working on something else, add it to `todo/todo.md` as a new item (with a one-line why) and continue the current task. Do not fix it silently, and do not write findings into separate plan files.
