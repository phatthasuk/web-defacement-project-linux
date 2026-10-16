# Stage 2 audit

**Verdict: the exit criteria are not met on the available evidence. There isn’t enough reliable per-target data to design Stage 3 notification policy yet.**

This was a read-only audit. I read `Check.md`, the project plan, the README, and the Stage 2 restart records. I did not change configuration or monitoring data, restart services, trigger checks, or deploy code.

## Evidence boundary

I could not verify the live Linux server. SSH to the documented host, `10.117.10.68`, failed host-key verification; there was no trusted key entry to confirm its identity, so I stopped. Local Docker access also failed with a permission error.

The findings below come from the workspace’s `backend/data/app.db` and artifacts. They describe that local dataset; they **do not establish the current server process state**.

## Targets and coverage

The plan names seven expected sites. The local database has four active targets with checks, plus an inactive, never-checked Google target. The expected Kasemrad Ari, Kasemrad Vientiane, and BCH Sustainability targets are absent.

Each active target has records spanning about 38 days, from **September 8 to October 16, 2026**—longer than two weeks. But the records don’t establish continuous hourly coverage:

| Active target | Results | OK / Changed | Longest gap between results | Gaps over 75 min |
|---|---:|---:|---:|---:|
| Bangkok Chain Hospital TH | 915 | 0 / 915 | 3.0 h | 2 |
| Kasemrad Hospital TH | 899 | 28 / 871 | 15.8 h | 4 |
| Kasemrad Inter Hospital TH | 913 | 5 / 908 | 4.4 h | 4 |
| World Medical Hospital TH | 893 | 0 / 893 | 3.1 h | 15 |

The recorded completion interval’s median is about **1.03 hours** for each target. That supports near-hourly checking for much of the period, but the gaps and missing targets prevent confirming that every configured target ran continuously.

The database has 3,620 results total: 3,587 `Changed` and 33 `OK`. Its `next_check_at` fields for the four active targets were in the future, and recent scheduled completions were recorded. Those are signs consistent with a running scheduler in this dataset, but they don’t verify the live server or its effective configuration.

## Detector results

The firing counts below use the thresholds documented in the project plan: text `> 0.02`, visual `> 0.01`, and structural `> 0`. The server’s effective thresholds were not verified.

| Active target | Text fired | Visual fired | Structural fired | Unchanged (`OK`) visual scores |
|---|---:|---:|---:|---|
| Bangkok Chain Hospital TH | 333 / 915 | 915 / 915 | 901 / 915 | No `OK` checks |
| Kasemrad Hospital TH | 826 / 899 | 827 / 899 | 870 / 899 | 28 checks; median 0, p95 0, max 0.000211 |
| Kasemrad Inter Hospital TH | 890 / 913 | 908 / 913 | 890 / 913 | 5 checks; median 0.003009, p95/max 0.006104 |
| World Medical Hospital TH | 681 / 893 | 703 / 893 | 893 / 893 | No `OK` checks |

Text and structural scores were zero on the 33 `OK` records. Visual scores were low on those records, but unchanged observations are sparse and exist for only two targets. The high firing counts, especially for visual and structural detection, need investigation before they can guide notification policy.

## Failures, duration, and overlap

Detailed attempt history is available only from **October 15 06:23 UTC through October 16 07:00 UTC**. In that period, it records:

- Three manual attempts with `internal_error`: one each for Bangkok Chain Hospital, Kasemrad Inter Hospital, and World Medical Hospital.
- One Kasemrad Hospital manual attempt marked `Availability Issue` / `process_interrupted`, lasting about 2 hours 32 minutes.
- Six attempts still recorded as `Checking` with no finish time: four manual Kasemrad Hospital attempts and two scheduled Kasemrad Inter attempts.

There are no recorded DNS, timeout, or HTTP error causes in this attempt history. Earlier failure history is unavailable in the local database, so a full-period failure rate by cause cannot be established.

For completed scheduled attempts in this short history, average durations were about 12–33 seconds by target, with a maximum of 44 seconds. Two scheduled checks overlapped at peak across targets. No same-target overlap is evident in the result intervals, but the attempt records are too recent to assess overlap over the full observation period.

## Storage

The current local database contains 3,591 retained screenshot, HTML, and text artifact sets dated September 8–October 16. They total about **11.3 GB**: 9.64 GB of screenshots, 1.59 GB of HTML, and 60 MB of text. That corresponds to roughly **300 MB/day** across the four active targets during full days. This estimates retained artifact accumulation from current file timestamps; it is not a server disk-growth measurement, and there is no start-of-run disk snapshot for comparison.

A separate local `raw_screenshots` directory holds about 1.9 GB of files dated October 8–16. I excluded it from the estimate above because its relationship to production storage isn’t established.

## Commands, queries, and logs

I queried `backend/data/app.db` in SQLite read-only mode (`mode=ro`, `PRAGMA query_only=ON`), examining:

- `targets` for active status and next-check times
- `check_results` grouped by target, date, status, and detector scores
- `check_attempts` grouped by target, source, status, error code, and duration
- `snapshots` for record dates and artifact counts

I also inventoried artifact file sizes and modification times with `du` and filesystem metadata. The database result and snapshot date ranges were September 8 09:59–October 16 07:00 UTC; attempt history starts October 15 06:23 UTC.

The host checks attempted were `ssh -o BatchMode=yes -o ConnectTimeout=7 10.117.10.68 ...` and `docker ps --format ...`; neither provided live server evidence. No application logs were available locally. The README’s operational log source is Docker stdout via `docker compose logs backend`, but I could not access the server to read it.

## Next read-only checks

1. Verify the server’s SSH host-key fingerprint through a trusted channel, then inspect `docker compose ps` and backend logs on that host.
2. Query the server’s SQLite database read-only and confirm its target list, result and attempt date ranges, effective scheduler settings, and unfinished attempts.
3. Check hourly coverage and detector scores for the three missing expected targets, and investigate the high firing rates on the four targets present.
4. Compare server storage now with any recorded start-of-run measurement, if one exists.

Until those checks confirm target coverage and yield reliable unchanged-score data for every target, the evidence is insufficient to proceed with Stage 3 notification policy design.
