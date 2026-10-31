# api-audit one-shot readings (2026-10-31)

Read once on the production machine from `logs/api-audit.jsonl`
(80,848 rows, 2026-06-25T23:13Z .. 2026-10-31T04:00Z). Counts of endpoint,
status and the whitelisted `content_status` scalars only; the log carries no
bodies. Not refreshed (ADR-0101: one reading, then removal).

## P1-07.4 — notifications missed outside the default window

The question assumed replies arrive through `get_notifications()`
(`client.py` `GET /notifications`, no `since`, default page). In production
that endpoint is never called:

| endpoint | rows |
|---|---|
| `GET /notifications` | 0 |
| `GET /home` | 4,896 (every month from 2026-06 to 2026-10) |
| `GET /posts/{id}/comments` | 5,787 |
| `POST /notifications/read-by-post/{id}` | 5,786 |

Every request goes through the one audited request path, so 0 rows means the
call was not made. The reply cycle uses `run_cycle_from_home`
(`agent.py` `_reply_step`): it takes `activity_on_your_posts` from `/home`, and
for each post with `new_notification_count > 0` fetches that post's comments
and marks its notifications read. `run_cycle` (the `get_notifications` path) is
only the fallback for an empty `/home` refresh, which did not occur in the
window.

Reading: missed notifications through the default `/notifications` window = 0
over 2026-06-25 .. 2026-10-31, because that window is never used.

Decision: no paging for `get_notifications`, and no regime-table row (nothing
changes). What the reading cannot answer: whether `/home`'s
`activity_on_your_posts` list is itself capped. The audit records only its
top-level keys, not its length, and the platform's page size is unconfirmed;
that question belongs to the platform-spec reading (P1-07.19), not to paging
`/notifications`.

## P1-07.5 — `content_status` non-null count

The census error rule for this log is already `200 <= status < 300`
(`scripts/_census_registry.py`, commit `83f588e0`). The one count the item asked
for:

| count | rows |
|---|---|
| `content_status` non-null | 15,110 (`POST /posts/{id}/comments` 9,239, `GET /posts/{id}` 5,215, `POST /posts` 656) |
| of which a moderation flag is true | 21, all on `GET /posts/{id}` (a post the agent fetched, own or not; the row does not say whose): `is_spam` 20, `is_deleted` 1, `is_locked` 0 |
| flag true on the agent's own `POST` rows | 0 |
| `verification_status` | pending 10,040 / verified 5,052 / failed 18 |
| rows the new error rule counts (non-2xx or null status) | 838 (400: 520, 404: 285, 403: 12, 503: 10, 410: 9, null: 2) |

None of the 21 is on a row where the agent published (its `POST` rows carry
no true flag), so no deferred row is raised from this count; the owner can
revisit if `is_spam` on fetched posts should be read as a platform signal.
