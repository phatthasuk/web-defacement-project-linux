# Website Defacement Monitoring System - Revised Project Plan

## 1. Executive Summary

ระบบ Website Defacement Monitoring เป็นระบบตรวจจับการเปลี่ยนแปลงของเว็บไซต์โดยใช้วิธี deterministic diffing ไม่ใช้ AI โดยระบบจะเก็บ snapshot ของหน้าเว็บ เช่น HTML, rendered text, screenshot, metadata และเปรียบเทียบกับ baseline ที่ถือว่าเป็น known-good state

แนวทางหลักของระบบถูกต้องและเหมาะสำหรับ production แต่ควรปรับแผนให้เน้น false-positive control, baseline governance, retry verification, security threat model และ operational readiness ตั้งแต่ phase แรก ๆ เพราะประเด็นเหล่านี้เป็นตัวกำหนดว่าระบบจะใช้งานจริงได้หรือกลายเป็นระบบแจ้งเตือน noise จำนวนมาก

## 2. Review Summary

### จุดแข็งของแผนเดิม

- แยก architecture เป็น Scheduler, Snapshotter, Diff Engine, Alerting, Storage และ Dashboard ได้ชัดเจน
- เลือกใช้ Playwright สำหรับ snapshot หลัง render ซึ่งเหมาะกับเว็บยุคใหม่และ SPA
- ใช้ DOM diff, text diff, visual diff, hash diff และ security-signal rules ครอบคลุมหลายรูปแบบของ defacement
- แยก object storage สำหรับ screenshot/raw HTML ออกจาก relational database ได้ถูกต้อง
- มีแนวคิดเรื่อง baseline drift, dynamic content และ scaling headless browser ตั้งแต่ต้น

### ประเด็นที่ควรแก้ไข

- ไฟล์ต้นฉบับมีปัญหา encoding ทำให้ diagram และสัญลักษณ์บางส่วนแสดงผิด เช่น dash, arrow และ box drawing characters
- Normalization, ignore selectors และ visual masking ไม่ควรถูกเลื่อนไป Phase 7 เพราะเป็น core requirement สำหรับลด false positive
- ควรเพิ่ม SSRF protection และ sandboxing เพราะระบบต้องเปิด URL ที่อาจมาจาก user input
- ควรแยกสถานะ Down, Changed, Unstable และ Defacement Suspected ออกจากกัน
- ควรมี double-check/retry verification ก่อนส่ง alert severity สูง
- ควรกำหนด baseline update policy ชัดเจน เพื่อป้องกัน slow defacement หรือ malicious drift
- ควรเพิ่ม data retention, storage lifecycle และ operational metrics

## 3. Revised High-Level Architecture

```text
Target Management
       |
       v
Scheduler / Job Queue
       |
       v
Crawler / Snapshotter (Playwright Workers)
       |
       +--> Snapshot Storage (S3 / MinIO)
       |
       +--> Metadata DB (PostgreSQL)
       |
       v
Normalization + Masking Layer
       |
       v
Diff / Comparator Engine
       |
       v
Rules Engine + Severity Scoring
       |
       v
Verification Queue / Retry Check
       |
       v
Alerting Engine + Dashboard
```

หลักสำคัญของ architecture ฉบับปรับปรุงคือให้ Normalization/Masking และ Verification Queue เป็นส่วนหลักของ pipeline ไม่ใช่ feature เสริมท้ายโครงการ

## 4. Core Components

### 4.1 Target Management

ผู้ใช้สามารถลงทะเบียน URL ที่ต้องการ monitor พร้อม config ราย target:

- URL, name, owner/team
- check interval
- viewport size
- sensitivity thresholds
- detection modes: hash, DOM, text, visual, link/resource, security rules
- ignore selectors และ ignore regions
- allowlist external domains
- authentication profile ถ้าเป็นหน้า login-gated
- baseline approval policy
- alert channels

### 4.2 Scheduler / Job Queue

ควรใช้ Celery + Redis หรือ Celery + RabbitMQ โดยมีความสามารถ:

- schedule targets ตาม interval ที่ต่างกัน
- jitter เพื่อลด thundering herd
- retry with exponential backoff
- separate queue สำหรับ normal checks, retry verification และ high-priority incidents
- per-domain concurrency limit เพื่อไม่ยิง request ถี่เกินไป

### 4.3 Snapshotter

ใช้ Playwright เพื่อเปิดหน้าเว็บและเก็บ artifact หลัง render:

- raw rendered HTML
- visible text content
- full-page screenshot
- page title และ meta tags
- HTTP status
- response headers
- redirect chain
- favicon hash
- external script/link/iframe domains
- response time และ browser timing

ควรมี configurable wait strategy:

- network idle
- wait for selector
- fixed delay
- custom readiness selector ต่อ target

### 4.4 Normalization and Visual Masking

ควรทำตั้งแต่ phase แรกที่เริ่ม diff จริง เพราะเป็นตัวลด false positive หลัก

HTML normalization:

- remove volatile attributes เช่น CSRF token, nonce, session id
- normalize timestamps
- remove tracking query parameters
- strip known ad widgets หรือ dynamic containers
- canonicalize whitespace และ attribute ordering

Visual masking:

- ซ่อน element จาก `ignore_selectors` ก่อน screenshot
- หรือ mask region หลัง screenshot ด้วย bounding boxes
- รองรับ dynamic widgets เช่น ad banner, carousel, timestamp, weather, stock ticker

### 4.5 Diff / Comparator Engine

แต่ละ detector ควรให้ผลลัพธ์เป็น score, evidence และ explanation

| Detector | Method | Purpose |
|---|---|---|
| Hash diff | SHA-256 ของ normalized content | ตรวจเปลี่ยนแปลงแบบเร็ว |
| DOM diff | normalized DOM tree comparison | ตรวจ injected elements, script, iframe |
| Text diff | word/line diff | ตรวจข้อความ defacement |
| Visual diff | pHash, SSIM, pixel diff | ตรวจ image/CSS/visual defacement |
| Link/resource diff | set diff ของ links/scripts/iframes/forms | ตรวจ redirect, phishing, malicious resource |
| Security-signal rules | rule-based heuristics | ตรวจสัญญาณเสี่ยงแบบ explainable |

### 4.6 Security-Signal Rules

ควรเพิ่ม rule ต่อไปนี้ใน severity model:

- new external script domain outside allowlist
- new iframe outside allowlist
- CSP header removed or weakened
- new inline script block
- Subresource Integrity attribute removed
- suspicious `eval`, `atob`, long base64 blob หรือ obfuscated JavaScript
- unexpected meta refresh
- unexpected form action domain
- redirect chain changed to untrusted domain
- favicon changed together with title/text change
- HTTP 200 เปลี่ยนเป็น 403/500/timeout ให้จัดเป็น availability issue ก่อน ไม่ถือว่า defaced ทันที

## 5. Status Model

ควรแยกสถานะของ target ให้ชัดเจน:

- `OK`: ไม่พบการเปลี่ยนแปลงสำคัญ
- `Changed`: พบการเปลี่ยนแปลง แต่ยังไม่เข้าเงื่อนไข defacement
- `Availability Issue`: timeout, DNS error, 4xx/5xx หรือ asset load failure
- `Unstable`: ผลตรวจไม่เสถียร เช่น retry แล้วผลไม่ตรงกัน
- `Verification Pending`: พบความเสี่ยงและกำลังตรวจซ้ำ
- `Defacement Suspected`: ตรวจซ้ำแล้วยังพบความเสี่ยง
- `Acknowledged`: ผู้ใช้รับทราบแล้ว
- `Resolved`: baseline หรือ website ถูกแก้กลับแล้ว

## 6. Baseline Policy

Baseline update ต้องมีกฎชัดเจน:

- Low severity: อนุญาต auto-update baseline ได้ ถ้าผ่าน rule ที่กำหนด
- Medium severity: ต้องมี human review ก่อน update baseline
- High severity: freeze baseline และส่ง alert ทันทีหลัง verification
- Repeated low-risk changes: ใช้ learning window เพื่อระบุ normal variance
- Manual override: admin สามารถ mark snapshot เป็น known-good ได้

เหตุผลคือถ้า auto-update baseline มากเกินไป ระบบอาจพลาด slow defacement หรือ malicious change ที่ค่อย ๆ แทรกทีละน้อย

## 7. Retry and Verification Policy

ก่อนส่ง alert severity สูง ควรมี verification step:

- retry หลัง 1-2 นาที
- ใช้ worker คนละตัวหรือ browser instance คนละตัว
- ถ้าเป็นไปได้ ใช้ network path หรือ region คนละชุด
- ยืนยัน alert เฉพาะเมื่อ diff ยังเกิน threshold
- ถ้า retry ให้ผลต่างกัน ให้ mark เป็น `Unstable` แทน `Defacement Suspected`

นโยบายนี้ลด false positive จาก CDN, asset loading, browser timeout, transient network issue และ CMS slowness

## 8. Security and Threat Model

เพราะระบบนี้ต้อง fetch URL ที่อาจมาจากผู้ใช้ จึงต้องป้องกัน SSRF และ browser abuse:

- อนุญาตเฉพาะ `http` และ `https`
- block private IP ranges เช่น `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- block link-local และ cloud metadata address เช่น `169.254.169.254`
- validate DNS resolution ก่อน fetch และระหว่าง redirect
- จำกัด redirect count
- จำกัด response size
- จำกัด page load timeout
- run browser workers ใน sandboxed container
- ไม่ให้ browser access internal network โดยไม่จำเป็น
- encrypt credentials, cookies และ Playwright storage state
- audit log การเข้าถึง snapshot, credential และ baseline approval

## 9. Storage and Retention

### Recommended storage split

- PostgreSQL: targets, users, configs, check results, diff metadata, alert state
- S3/MinIO: screenshots, raw HTML, rendered text, large diff artifacts
- Time-series store หรือ PostgreSQL partitioning: metrics และ check history

### Retention policy

- เก็บ full screenshot/raw HTML 30-90 วัน
- เก็บ metadata และ alert history นานกว่า เช่น 1-2 ปี
- เก็บ incident snapshots ถาวรหรือจนกว่าจะ archive
- ใช้ S3 lifecycle policy เพื่อลด storage cost
- compression สำหรับ HTML/text artifacts

## 10. Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Browser automation | Playwright Python async API | reliable rendering, screenshot, DOM extraction |
| Backend API | FastAPI | async-friendly, OpenAPI support |
| Queue | Celery + Redis/RabbitMQ | retries, scheduling, horizontal scale |
| Database | PostgreSQL | structured target/config/diff metadata |
| Object storage | S3 or MinIO | large artifacts outside DB |
| Visual diff | Pillow, imagehash, scikit-image | pHash, SSIM, pixel comparison |
| DOM/text diff | lxml, difflib, diff-match-patch | deterministic diffing |
| Frontend | React or htmx | dashboard and diff viewers |
| Auth | session auth or JWT | team/user access |
| Notifications | SMTP, Slack, Discord, webhook, SMS | alert delivery |
| Observability | Prometheus, Grafana, Loki/ELK | monitor the monitor |
| Deployment | Docker Compose for dev, Kubernetes for scale | consistent Playwright environment |

## 11. Operational Metrics

ควร monitor metric ต่อไปนี้:

- checks per minute
- queue depth
- average render time
- browser crash count
- timeout rate
- diff processing latency
- alert count by severity
- retry confirmation rate
- false positive rate
- storage growth rate
- per-domain failure rate
- worker memory usage

สำหรับ Playwright workers ควรกำหนด:

- `worker_max_tasks_per_child`
- max browser contexts per worker
- browser restart every N jobs
- memory limit per container
- graceful shutdown เพื่อไม่ทิ้ง partial snapshots

## 12. Revised Build Phases

### Phase 1: Core Snapshot Loop

- single target
- Playwright capture HTML, text, screenshot และ metadata
- store artifacts to local disk หรือ object storage
- hash diff แบบง่าย
- basic status: OK, Changed, Availability Issue

### Phase 2: Normalization and Noise Control

- HTML normalization
- ignore selectors
- visual masking
- viewport config
- basic allowlist for external domains
- initial baseline policy

### Phase 3: Multi-Detector Diffing

- text diff
- DOM diff
- visual diff with pHash/SSIM
- link/resource diff
- structured diff result JSON

### Phase 4: Scheduler and Multi-Target Support

- Celery + Redis/RabbitMQ
- Postgres-backed targets
- worker pool
- retries with backoff
- per-domain concurrency limit

### Phase 5: Rules Engine and Verification Queue

- weighted severity scoring
- security-signal checks
- double-check/retry verification
- status model refinement
- baseline approval workflow

### Phase 6: Alerting

- email/webhook/Slack/Discord integrations
- alert deduplication
- escalation policy
- include screenshot diff, HTML diff, severity and evidence

### Phase 7: Dashboard

- target list and current status
- timeline per site
- visual diff viewer
- HTML/text diff viewer
- alert acknowledgment
- baseline approval UI
- target config management

### Phase 8: Hardening and Scale

- SSRF protection
- credential encryption
- container sandboxing
- object storage lifecycle
- observability dashboards
- load testing
- worker memory recycling

## 13. Final Recommendation

โครงการนี้มีพื้นฐานที่ดีและควรเดินหน้าต่อได้ แต่ควรปรับจากแผนเดิมให้ treat false-positive suppression, verification retry, baseline governance และ SSRF protection เป็น core requirements ตั้งแต่ต้น ไม่ใช่งาน hardening ตอนท้าย

ลำดับการทำงานที่เหมาะสมคือสร้าง snapshot loop ให้ได้ก่อน จากนั้นรีบใส่ normalization/masking แล้วค่อยเพิ่ม diff detectors และ rules engine การทำตามลำดับนี้จะทำให้ระบบทดสอบง่ายขึ้น ลด alert noise และช่วยให้ผลลัพธ์มีความน่าเชื่อถือเมื่อใช้กับเว็บไซต์จริง
