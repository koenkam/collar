# Collar — how agents work here

## Task tracking (read this first, every session)

- `todo/todo_collar.md` is the single list of open work. Read it at the start of every session before doing anything else.
- Work only on items listed there (or on what the user asks for directly). If the user asks for something not in the list, add it as an item first, then do it.
- `todo/done_YYYYMM.md` (current month, UTC) holds completed items. Nothing is ever deleted from the repo's task history; it is moved.
- Never infer status from a file's location or from notes in other documents; only `todo/` carries status.

## Item format

One item per line, checkbox at column 0, stable ID, short title, and the source the item came from:

```markdown
- [ ] T012 Short title of the task — see path/to/context.md or a one-line why
```

- IDs are `T` + zero-padded number, assigned sequentially, never reused. Take the next number after the highest ID in `todo_collar.md` and all `done_*.md`.
- Keep lines in `todo_collar.md` ordered by priority (top = do first). Never reword or merge an existing line; add a new item instead.
- Sub-steps, notes and findings go indented under the item, not in other files.
- Every new item names its source after the title (`— …`): the user request, the parent item (`follow-up to T012`), the checkup or analysis date, the log line or file, or whatever surfaced it. An item without a source cannot be judged later, so do not add one without it.

## Completing an item

When an item is finished (code changed, tests passing where applicable, and verified):

1. Remove the line from `todo/todo_collar.md`.
2. Append it to `todo/done_YYYYMM.md` for the current month as:

   ```markdown
   - [x] T012 Short title of the task — 2026-10-27 3f2a1c0
   ```

   Date = completion date (UTC), followed by the short commit sha. If not yet committed, write `uncommitted` and let the commit step fix it.
3. Mention the item ID in the commit message (`T012: short title`).

Partial progress stays in `todo_collar.md` with notes under the item. Do not move an item to done because it is "mostly" finished.

## Finding new work

If you find a bug, drift or risk while working on something else, add it to `todo/todo_collar.md` as a new item (with a one-line why) and continue the current task. Do not fix it silently, and do not write findings into separate plan files.

## The list shrinks

- Todo lists are there to be closed, not maintained. A session must end with fewer open items in `todo/todo_collar.md` than it started with; never more.
- When new todos emerge from an existing task (follow-ups, sub-steps, bugs found on the way), they are part of that task: add them as items so they are tracked, then finish and close them in the same session, after the current task. Do not park them for later.
- An item may stay open only when it genuinely cannot be done now (waiting on a live window, external data or a decision only the user can take). Write the blocker and the exact close condition under the item; the moment the blocker clears, close it.
- Before ending a session, go through `todo/todo_collar.md` top to bottom and close everything that can be closed. Finishing the asked-for change is not the end of the session; an emptier list is.

## One-off scripts

One-off scripts live in `botscripts/`. New one-off scripts go in `botscripts/`.

## Code quality

To maximize code quality and efficiency, always omit conversational filler and output complete, copy-pasteable code without placeholders like `// TODO` or leftover debug prints. Before writing new logic, search the codebase to prevent duplication, verify function signatures, and strictly use only existing dependencies rather than hallucinating new ones. Favor composition, pure functions, and readability over premature optimization or clever one-liners. Apply the "Fail Fast" principle using guard clauses, catch specific exceptions with descriptive errors rather than failing silently, and if a request is ambiguous or requires multi-file changes, stop to provide a brief plan or ask a clarifying question instead of guessing. Remember YAGNI and KISS. The simplest solution is the best.
