# Review Security — 14-10-2026

วันที่ตรวจ: 14 ตุลาคม 2026 (Asia/Bangkok)  
โปรเจกต์: Web Defacement Monitoring System  
สถานะ: รายงาน audit และข้อเสนอแก้ไข — **แก้ใน source แล้วบางส่วน (ดูหัวข้อ 7) แต่ยังไม่ deploy และยังไม่ได้ทดสอบบน Linux/container จริง จึงยังไม่ถือว่าปิด finding ใดทั้งสิ้น**  
อัปเดตสถานะการแก้ไขล่าสุด: 14 ตุลาคม 2026 (Asia/Bangkok)

> เนื้อหาหัวข้อ 1–6 คือรายงานต้นฉบับ ณ เวลาที่ตรวจ ไม่ได้ถูกแก้ไข หัวข้อ 7 เพิ่มเข้ามาเพื่อบันทึกสิ่งที่ทำไปแล้ว สิ่งที่ยังไม่ได้ทำ และเหตุผล

## 1. ขอบเขตและข้อจำกัด

ตรวจไฟล์ปัจจุบันของ backend, frontend และ deployment configuration โดยเน้น authentication, authorization, CSRF, SSRF, capture pipeline, structural detector และการบันทึกการตัดสินใจด้าน security พร้อมตรวจ advisory ภายนอกสำหรับ dependencies ที่เกี่ยวข้อง

- โฟลเดอร์นี้ไม่มี Git metadata จึงตรวจจากไฟล์ปัจจุบัน ไม่ใช่ diff ระหว่าง commits
- ตรวจเวอร์ชัน Python packages จาก project `.venv`; เวอร์ชันที่ใช้งานใน Linux production จริงยังไม่ได้ตรวจ
- Chromium 130.0.6723.31 เป็นเวอร์ชันที่ระบุใน browser manifest ของ Playwright 1.48.0; production Dockerfile ใช้ image รุ่นเดียวกัน แต่ยังไม่ได้ตรวจ binary ใน container ที่ deploy จริง
- ไม่ได้ทดสอบโจมตี production, exploit browser, ทำให้ระบบ OOM หรือยิงโหลด DoS
- ไม่ได้ทำ vulnerability scan ของ Python dependencies ทั้งหมด, OS packages หรือ container images ทั้งหมด
- Findings ของ detector เป็นช่องว่างการตรวจพบพฤติกรรมอันตราย ไม่ใช่หลักฐานว่า monitoring application ถูกเจาะหรือ SSRF ถูก bypass
- การจัดระดับด้านล่างเป็นการประเมินความเสี่ยงของโปรเจกต์ ไม่ใช่การคัดลอก CVSS ของ advisory โดยตรง

## 2. สรุปผล

พบ 2 ประเด็นความเสี่ยงสูง และ 5 ประเด็นปานกลางที่ควรแก้

| ID | ระดับ | ประเด็น | หลักฐาน/สถานะ |
| --- | --- | --- | --- |
| SEC-01 | สูง | Browser สำหรับ capture เก่า | ตรวจ version manifest และ Dockerfile; เทียบ security release ของ Chromium |
| SEC-02 | สูง | Starlette FileResponse มีช่องโหว่ DoS ผ่าน Range | เวอร์ชันอยู่ในช่วง affected; screenshot routes ใช้ FileResponse; ทดลอง parser แบบจำกัดขนาด |
| SEC-03 | ปานกลาง | ไม่ตรวจ HTTP/HTTPS formaction | ยืนยันด้วย offline Chromium probe |
| SEC-04 | ปานกลาง | javascript: ที่มี tab แทรกหลุด detector | ยืนยันด้วย offline Chromium probe |
| SEC-05 | ปานกลาง | เปลี่ยน script type จาก inert เป็น executable แล้ว facts เดิม | ยืนยันด้วย offline Chromium probe |
| SEC-06 | ปานกลาง | จำกัด artifact หลัง allocation และไม่มี container resource limits | พบจากโค้ด/config; ยังไม่ได้ทดสอบ OOM |
| SEC-07 | ปานกลาง | Review/baseline mutations ไม่มี actor audit trail | พบจาก routes และ service code |

ลำดับแก้ไขแนะนำ: browser → FastAPI/Starlette → resource limits → detector → audit trail

## 3. Findings

### SEC-01 — Chromium สำหรับจับหน้าเว็บเก่า

**ตำแหน่ง:** `backend/Dockerfile:1`, `backend/requirements.txt:7`

Dockerfile ใช้ `mcr.microsoft.com/playwright/python:v1.48.0-noble` และ requirements pin `playwright==1.48.0` ขณะที่ browser manifest ของ package ระบุ Chromium `130.0.6723.31` ระบบเปิดและรัน JavaScript ของหน้าเว็บที่อาจถูกโจมตี จึงมี attack surface โดยตรงต่อ browser engine

รุ่นที่กำหนดมาก่อน security releases หลายรอบ ตัวอย่างเช่น Chrome 131.0.6778.108 แก้ High CVE-2024-12053 (Type Confusion in V8) การเทียบนี้สนับสนุนความจำเป็นในการอัปเดต browser; ไม่ใช่การพิสูจน์ว่า exploit ดังกล่าวสำเร็จกับ capture runtime นี้

**ผลกระทบ:** หน้าเว็บอันตรายอาจโจมตี browser engine ที่ไม่ได้รับแพตช์ ความสามารถในการกระทบ API, ข้อมูลหรือ host ต่อไปขึ้นกับ sandbox และ container isolation; ยังไม่ได้ยืนยันการ escape หรือ code execution ในโปรเจกต์นี้

**เสนอแก้ไข:**

- [ ] อัปเดต Playwright package และ browser image เป็นรุ่นที่เข้ากันได้และได้รับ security fixes
- [ ] ตรวจ version ของ browser binary ใน container ที่ deploy จริง
- [ ] รักษา Chromium sandbox และ non-root runtime; ไม่ใช้ development Compose กับ production
- [ ] แยก capture worker จาก API และฐานข้อมูล เพื่อลดผลกระทบหาก browser ถูก compromise
- [ ] ทดสอบ capture, SSRF proxy, redirects, WebSocket blocking และ sandbox บน Linux หลังอัปเดต

**เกณฑ์ตรวจรับ:** Package/image/browser binary สอดคล้องกันและไม่มี advisory ที่เกี่ยวข้องค้างอยู่; capture และ SSRF regression checks ผ่านบน deployment environment

**แหล่งอ้างอิง:** [Chrome security update วันที่ 3 ธันวาคม 2024](https://chromereleases.googleblog.com/2024/12/stable-channel-update-for-desktop.html)

### SEC-02 — Starlette FileResponse มีช่องโหว่ DoS ผ่าน Range header

**ตำแหน่ง:** `backend/requirements.txt:1`, `backend/app/api/routes/snapshots.py:61`, `backend/app/api/routes/snapshots.py:77`

Project `.venv` ใช้ FastAPI 0.115.5 และ Starlette 0.41.3 โดย FastAPI รุ่นนี้กำหนด `starlette>=0.40.0,<0.42.0` จึงต้องอัปเดตคู่กันหรือเลือกรุ่นที่เข้ากันได้ ไม่ควร force upgrade Starlette ข้าม constraint โดยไม่ตรวจ compatibility

Starlette 0.41.3 อยู่ในช่วง affected ของ CVE-2025-62727 / GHSA-7f5h-v6xp-fcq8 ซึ่งเกิด quadratic processing ใน `FileResponse` Range parsing/merging เส้นทาง screenshot/raw screenshot ของโปรเจกต์ใช้ `FileResponse` จึงมี code path ที่เกี่ยวข้อง

**เงื่อนไขของโปรเจกต์:** ผู้โจมตีต้องมี session ที่ผ่าน authentication และมีสิทธิ์อ่าน snapshot ของ target นั้นก่อน ต่างจากคำอธิบายทั่วไปใน advisory ที่กล่าวถึง file-serving endpoint แบบ unauthenticated

ทดลองเรียก parser ใน process แยกแบบ offline ด้วย ranges จำนวนจำกัด ไม่ได้ส่งโหลดไปยัง API:

| จำนวน ranges | ขนาด header | เวลาประมวลผลที่วัดได้ |
| --- | --- | --- |
| 500 | 3,895 bytes | 5.56 ms |
| 1,000 | 8,895 bytes | 20.34 ms |
| 2,000 | 18,895 bytes | 82.95 ms |

เวลาที่เพิ่มขึ้นใกล้เคียงกำลังสองสนับสนุนพฤติกรรมตาม advisory แต่ไม่ใช่การวัด production throughput ทั้งนี้ Nginx อาจปฏิเสธ header ที่ใหญ่เกินค่าจำกัดของมัน จึงต้องพิจารณาขนาดที่ proxy ยอมรับด้วย

**ผลกระทบ:** ผู้ใช้ที่มีสิทธิ์สามารถใช้ crafted Range requests เพื่อเพิ่ม CPU load และกระทบ availability ของ backend ซึ่ง deploy ด้วย worker เดียว

**เสนอแก้ไข:**

- [ ] อัปเดต FastAPI/Starlette ที่เข้ากันได้และรวมแพตช์ของ advisory แล้ว; แพตช์ของ advisory นี้เริ่มที่ Starlette 0.49.1 แต่ไม่ควรถือว่าเป็นรุ่นเป้าหมายที่ปลอดภัยครบทุก advisory ในปัจจุบัน
- [ ] ระหว่างรออัปเดต จำกัดหรือปฏิเสธ multi-range ที่ reverse proxy หาก application ไม่จำเป็นต้องใช้
- [ ] ตรวจ behavior ของ screenshot endpoints สำหรับ single range, multi-range และ malformed range หลังแก้

**เกณฑ์ตรวจรับ:** Runtime พ้นช่วง affected, dependency constraints ถูกต้อง และ crafted ranges ไม่ทำให้ parser ใช้เวลาประมวลผลแบบเดิม

**แหล่งอ้างอิง:** [Starlette security advisory GHSA-7f5h-v6xp-fcq8](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8)

### SEC-03 — เปลี่ยนปลายทางส่งฟอร์มผ่าน formaction โดยไม่แจ้งเตือน

**ตำแหน่ง:** `backend/app/services/diff/structure.py:114`, `backend/app/services/diff/structure.py:142`

Parser เก็บ `form.action` แต่ไม่ได้เก็บ HTTP/HTTPS `button.formaction` หรือ `input.formaction` ซึ่ง override ปลายทางส่งฟอร์มได้ การมี `formaction` ใน executable URL attribute list ครอบคลุมเฉพาะค่าที่ถูกจำแนกเป็น `javascript:`

**หลักฐาน:** Offline Chromium probe เปลี่ยน effective submission destination จาก `https://example.com/save` เป็น `https://collector.example/save` โดยภาพและข้อความเหมือนเดิม และ structure score = 0.0 ไม่มีการส่งฟอร์มหรือเชื่อมต่อปลายทาง

**ผลกระทบ:** การเปลี่ยนปลายทางรับข้อมูลของหน้าเว็บอาจไม่ถูกแจ้งเตือน เมื่อไม่มี text/pixel changes อื่น

**เสนอแก้ไข:**

- [ ] เก็บ facts ของ `formaction` สำหรับ button/input รวม relative URLs และ effective base URL
- [ ] กำหนด policy ของ allowed domains สำหรับปลายทางส่งข้อมูลให้ชัดเจน
- [ ] เพิ่ม regression cases สำหรับ addition, modification และ removal

**เกณฑ์ตรวจรับ:** การเปลี่ยน effective submission destination ที่ไม่ได้รับอนุญาตทำให้ detector รายงาน Changed แม้ภาพ/ข้อความเหมือนเดิม

### SEC-04 — JavaScript URL ที่แทรก tab หลุดการตรวจ

**ตำแหน่ง:** `backend/app/services/diff/structure.py:114`

การตรวจ `value.lstrip().lower().startswith('javascript:')` ไม่ normalize ASCII tab/newline ภายใน scheme ตามพฤติกรรม browser เช่น `href="java&#9;script:void(window.auditProbe=1)"` ซึ่งผ่าน HTML entity decoding แล้วมี tab คั่น

**หลักฐาน:** Offline Chromium probe คลิก link แล้ว `window.auditProbe` เปลี่ยนจาก 0 เป็น 1 แต่ text/PNG เหมือนเดิมและ structure score = 0.0

**ผลกระทบ:** Executable URL ที่เพิ่มลงในหน้าเว็บอาจหลุดการแจ้งเตือน

**เสนอแก้ไข:**

- [ ] Normalize ASCII tab, LF และ CR ก่อนจำแนก URL scheme ให้ตรงกับ browser
- [ ] รักษาความหมายของ script body หลังจำแนก scheme
- [ ] เพิ่ม cases สำหรับ literal control characters, HTML entities และ mixed casing
- [ ] ไม่ใช้ domain allowlist ละเลย executable URLs

**เกณฑ์ตรวจรับ:** URL ที่ browser จำแนกเป็น JavaScript ถูกเก็บเป็น executable fact และการเพิ่ม/เปลี่ยนค่าทำให้เกิด alert

### SEC-05 — เปลี่ยน script จาก inert เป็น executable แล้ว facts ไม่เปลี่ยน

**ตำแหน่ง:** `backend/app/services/diff/structure.py:124`, `backend/app/services/diff/structure.py:252`

Parser เก็บ inline script body hash แต่ไม่เก็บ `type` หรือ executable/inert classification เมื่อเปลี่ยน `<script type="text/plain">` เป็น `<script type="text/javascript">` โดย body เดิม hash จึงเหมือนเดิม External script facts ก็ไม่บันทึก type จึงควรตรวจเส้นทางนั้นควบคู่กัน

**หลักฐาน:** Offline Chromium probe ยืนยันว่า baseline ไม่รัน body แต่ current รันจน `window.auditProbe = 1` โดย text/PNG เหมือนเดิมและ structure score = 0.0

**ผลกระทบ:** การเปิดใช้โค้ดที่เดิม inert อาจไม่ถูกแจ้งเตือน

**เสนอแก้ไข:**

- [ ] เก็บ normalized script type และ executable classification ทั้ง inline/external scripts
- [ ] เพิ่ม cases สำหรับ inert → classic/module และ reverse transitions
- [ ] ไม่ละเลย inert content โดยไม่ตรวจการเปลี่ยน classification

**เกณฑ์ตรวจรับ:** การเปลี่ยนสถานะ executable ทำให้ facts เปลี่ยน แม้ URL หรือ script body เดิม

SEC-03 ถึง SEC-05 เป็นการยืนยันซ้ำของ R2-01 ถึง R2-03 ใน `Review Round 2 By GPT 6.1 Sol 14-10-2026.md`; ไม่ใช่ findings ใหม่คนละชุด

### SEC-06 — ขีดจำกัด artifact ไม่ครอบคลุม allocation และ runtime resources

**ตำแหน่ง:** `backend/app/services/capture/capture.py:281`, `backend/app/services/capture/capture.py:433`, `backend/app/services/capture/capture.py:446`, `docker-compose.yml`

Capture ใช้ `route.fetch(max_redirects=0)` ก่อนตรวจขนาด artifact จาก DOM และสร้าง full-page screenshot ก่อนตรวจขนาด encoded PNG ค่า `MAX_ARTIFACT_SIZE_MB` จึงไม่ใช่เพดาน network response bytes หรือ decoded pixel allocation

Playwright response body อยู่ใน memory จน dispose/context close; capture ไม่กำหนด byte budget ของแต่ละ response หรือ aggregate resources ต่อหน้า ขณะที่ production Compose ไม่มี memory, CPU หรือ PID limits แม้มี concurrency limits และ check timeout แล้ว

**ผลกระทบ:** หน้าเว็บที่ผู้โจมตีควบคุมอาจใช้ทรัพยากรมากจาก response, DOM หรือ screenshot dimensions ก่อนถูก reject ทำให้ capture/backend หรือ host มี availability ลดลง เป็นความเสี่ยงจาก design/config ที่ตรวจพบ ยังไม่ได้ทดลองให้ระบบ OOM

**เสนอแก้ไข:**

- [ ] กำหนด response byte limits และ aggregate resource budget โดยตรวจระหว่างรับข้อมูล ไม่พึ่ง Content-Length อย่างเดียว
- [ ] กำหนดเพดาน screenshot dimensions/pixel count และความสูงของ full-page capture
- [ ] กำหนด container memory, CPU และ PID limits พร้อมตรวจการจัดการ failure
- [ ] แยก capture worker จาก API เพื่อให้ resource exhaustion ไม่กระทบ API โดยตรง
- [ ] คง timeout และ cleanup ของ browser/staging artifacts เมื่อถูกยกเลิก

**เกณฑ์ตรวจรับ:** หน้าเว็บทดสอบที่เกิน byte/pixel budget ถูก reject ภายใน resource budget และไม่ทำให้ API สูญเสีย availability

### SEC-07 — การตัดสินใจด้าน review/baseline ไม่มี audit trail ระบุผู้ทำ

**ตำแหน่ง:** `backend/app/api/routes/review.py:19`, `backend/app/services/review.py:25`, `backend/app/api/routes/targets.py` (`demote_target_baseline`)

Routes ตรวจ session และ target access แล้ว แต่ approve baseline, acknowledge check, confirm defacement และ demote baseline ไม่สร้าง audit event ที่ระบุ actor การส่งต่อไปยัง review service ก็ไม่ได้ส่งตัวผู้ทำไปด้วย

ปัจจุบันบางข้อมูลมี timestamp เช่น `acknowledged_at` และสถานะ baseline แต่ข้อมูลเหล่านี้ไม่ระบุว่าใครเป็นผู้เปลี่ยน ต่างจาก member/website/tag mutations ที่มี `MemberAuditEvent`

**ผลกระทบ:** เมื่อ baseline ที่เป็นอันตรายได้รับการอนุมัติหรือสถานะ incident ถูกเปลี่ยน จะสืบย้อนผู้ทำและเจตนาของการตัดสินใจได้ไม่ครบ เป็นช่องว่างด้าน accountability ไม่ใช่การยืนยันว่า Operator มีสิทธิ์เกิน policy ที่ออกแบบไว้

**เสนอแก้ไข:**

- [ ] ส่ง actor ไปยัง mutation service หรือบันทึก audit event ใน route ภายใต้ transaction เดียวกัน
- [ ] เก็บ actor, timestamp, action, target/snapshot/check IDs และค่าก่อน–หลัง
- [ ] บันทึก baseline ที่ถูก demote อัตโนมัติจาก cap เมื่อ approve baseline ด้วย
- [ ] กำหนด retention และสิทธิ์อ่าน audit events ตามความต้องการด้าน incident investigation

**เกณฑ์ตรวจรับ:** ทุก review/baseline mutation ที่สำเร็จมี audit event ที่เชื่อมโยงผู้ทำและรายการที่เปลี่ยนได้; transaction ที่ rollback ไม่ทิ้ง success event

## 4. มาตรการที่มีอยู่แล้ว

จากการตรวจโค้ด พบมาตรการหลักดังต่อไปนี้:

- Password hashing ใช้ Argon2 และมี account lockout logic
- Session token สุ่มใหม่เมื่อ login และเก็บ token hash ในฐานข้อมูล
- Session cookies เป็น HttpOnly; production Compose เปิด Secure และ SameSite strict
- ใช้ synchronizer CSRF token สำหรับ authenticated mutations
- Authorization แยก Admin/Operator และจำกัด Operator ตาม target assignments
- Snapshot artifact paths ตรวจว่าอยู่ภายใน data directory
- SSRF proxy resolve/check IP และเชื่อมต่อไปยัง IP ที่ตรวจแล้ว ลด DNS rebinding validation-to-connection gap
- Capture block service workers และเปิด WebSocket blocking เป็นค่าเริ่มต้น
- Production Compose ใช้ non-root backend, read-only filesystem, cap_drop และ seccomp profile
- Production backend ไม่ publish port บน host และกำหนด trusted proxy IP
- Initial snapshot/URL revision ต้องผ่าน baseline approval ก่อนเป็น reference

รายการนี้เป็นหลักฐานว่ามี controls ในโค้ด/config ไม่ใช่การรับรองว่าทุก control ทำงานครบใน production จริง

## 5. ผลการตรวจสอบในรอบนี้

| การตรวจ | ผล |
| --- | --- |
| Backend security/API regression subset | 71 passed, 105 warnings, 43.61 วินาที |
| Offline Chromium detector probe | ยืนยัน SEC-03, SEC-04 และ SEC-05 |
| Bounded Starlette Range parser probe | เวลาเพิ่มใกล้เคียงกำลังสอง ตามตาราง SEC-02 |
| Frontend npm audit | 0 vulnerabilities; dependency metadata รวม 411 |
| Python/container vulnerability scan ครบทั้งหมด | ยังไม่ได้ทำ |
| Linux production verification / load test | ยังไม่ได้ทำ |

Regression subset ครอบคลุม `test_auth.py`, `test_member_management.py`, `test_ssrf_guard.py`, `test_ssrf_proxy.py` และ `test_api_routes.py` โดยใช้ฐานข้อมูลทดสอบแยกจาก production

**ข้อจำกัดของผล tests:** `backend/tests/conftest.py:43` ปิด SlowAPI limiter ผ่าน fixture ดังนั้นผล 71 passed ไม่ได้ยืนยันประสิทธิผลของ per-IP rate limiting ภายใต้โหลดจริง

การรัน pytest และ Playwright ครั้งแรกใน sandbox พบ Windows Access Denied ต่อ temporary directories/subprocess pipes จึงรันซ้ำด้วยสิทธิ์ที่ผ่าน approval review แล้วและได้ผลสำเร็จ ไม่ใช่ application test failure

### วิธีพิสูจน์ซ้ำ

รันจากโฟลเดอร์ `backend` บน PowerShell โดยใช้ชื่อ basetemp ใหม่ที่ยังไม่มีข้อมูลสำคัญ:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_member_management.py tests/test_ssrf_guard.py tests/test_ssrf_proxy.py tests/test_api_routes.py -q --basetemp=.security-audit-rerun -p no:cacheprovider

$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/audit_round2_probe.py
```

Probe ใช้ local HTML ใน browser ด้วย `set_content` และ harmless variable assignments ไม่มี navigation ไปเว็บไซต์ภายนอกหรือส่งข้อมูลไปยัง collector

ผลที่ยืนยันในรอบนี้:

```text
formaction:     structure_score=0.0, same_text=true, same_png=true, destination changed
script-type:   structure_score=0.0, same_text=true, same_png=true, behavior 0 → 1
javascript-tab: structure_score=0.0, same_text=true, same_png=true, behavior 0 → 1
```

รันจากโฟลเดอร์ `frontend`:

```powershell
npm.cmd audit --json
```

ผล npm audit ขึ้นกับ advisory database ณ เวลาที่รัน และไม่ครอบคลุม Python, Chromium หรือ OS packages

## 6. เอกสารที่เกี่ยวข้อง

- [Audit รอบ 2 — 14 ตุลาคม 2026](./Review%20Round%202%20By%20GPT%206.1%20Sol%2014-10-2026.md)
- [Code review — 14 ตุลาคม 2026](./Review%20By%20GPT%206.1%20Sol%2014-10-2026.md)
- [Project plan](./PROJECT_PLAN.md)
- [Member management plan](./MEMBER_MANAGEMENT_PLAN.md)

## 7. สถานะการแก้ไข (อัปเดต 14-10-2026)

หัวข้อนี้บันทึกสิ่งที่ลงมือแก้หลังรายงานฉบับนี้ ตัวเลขและผลทดสอบทั้งหมดมาจากเครื่อง Windows ที่ใช้พัฒนา ไม่ใช่ Linux production

**ข้อสรุป:** แก้ใน source ครบทั้ง 7 ข้อในระดับที่ทำได้โดยไม่ต้องใช้ Linux/Docker แต่ยังไม่มีข้อใดผ่านเกณฑ์ตรวจรับครบ เพราะเกณฑ์ของ SEC-01 และ SEC-06 ต้องยืนยันบน deployment จริง และ SEC-02 ใช้มาตรการเสริมแทนการแก้ที่ต้นเหตุ

### 7.1 สรุปสถานะรายข้อ

| ID | สถานะ | ที่ทำแล้ว | ที่ยังเหลือ |
| --- | --- | --- | --- |
| SEC-01 | แก้ใน source แล้ว ยังไม่ปิด | อัปเดต Playwright และ image | ยืนยัน browser binary ใน container, sandbox/seccomp, SSRF regression บน Linux; แยก capture worker |
| SEC-02 | แก้บางส่วน ใช้มาตรการเสริม | อัปเดต FastAPI/Starlette และตัด `Range` ที่ route screenshot | ยังมี merge หลายช่วงแบบ O(n²); ต้องยืนยันรายละเอียด advisory และพฤติกรรมใน Linux |
| SEC-03 | แก้ใน source แล้ว | เก็บ `formaction` บน submit-capable button/input รวมค่าว่างที่ชี้กลับ URL เอกสาร | policy allowed domains แยกสำหรับ `formaction`; form owner association ยังไม่ตรวจ |
| SEC-04 | แก้ใน source แล้ว | normalize tab/LF/CR และ control characters ตามที่ Chromium ทำ | — |
| SEC-05 | แก้ใน source แล้ว | จำแนก classic/module/importmap/speculationrules/inert และ MIME type แบบตรงตาม HTML | — |
| SEC-06 | แก้ส่วนโค้ด ส่วน runtime ยังไม่ทำ | งบไบต์รวม, เพดาน pixel/ความสูง, เพดาน DOM nodes | container memory/CPU/PID limits; แยก capture worker |
| SEC-07 | แก้ใน source แล้ว | audit event ของ approve/ack/confirm/demote พร้อม actor | retention, หน้า frontend สำหรับอ่าน |

### 7.2 สิ่งที่ทำไปแล้ว

**SEC-01 และ SEC-02 (dependencies และ route)**

- `backend/requirements.txt`: FastAPI 0.115.5 → 0.128.8, เพิ่มการ pin Starlette 0.52.1 (เดิม 0.41.3), Playwright 1.48.0 → 1.63.0 ซึ่ง manifest ระบุ Chromium 153.0.8010.12 (เดิม 130.0.6723.31)
- `backend/Dockerfile` และ `docker-compose.dev.yml`: image เป็น `mcr.microsoft.com/playwright/python:v1.63.0-noble` (ตรวจแล้วว่า tag นี้มีบน MCR; v1.64.0 ยังไม่มี image)
- `backend/app/api/routes/snapshots.py`: เพิ่ม `WholeFileResponse` ที่ตัด `Range`/`If-Range` และส่ง `Accept-Ranges: none` ใช้กับ screenshot ทั้ง 3 จุดที่เดิมใช้ `FileResponse`
- `backend/tests/test_api_routes.py`: เพิ่ม test ส่ง Range 3 แบบ (ช่วงเดียว, 2,000 ช่วง, header เสีย) ต้องได้ 200 และไฟล์เต็ม

**SEC-03 ถึง SEC-05 (`backend/app/services/diff/structure.py`)**

- เก็บ fact `formaction:<URL>` เฉพาะ submit-capable `<button>`/`<input>` โดย resolve URL แบบ relative ตาม base และใช้ `allowed_hosts` ชุดเดิม; แยกกรณีไม่มี attribute ออกจาก `formaction=""` ซึ่งส่งไปยัง URL ของเอกสารปัจจุบัน (แม้มี `<base>`)
- normalize URL ก่อนจำแนก `javascript:` โดยตัด tab/LF/CR ทุกตำแหน่งและ control characters/ช่องว่างหัวท้าย รองรับ literal, HTML entity และตัวพิมพ์ผสม
- จำแนก `<script>` ตามกติกา HTML: MIME type แบบมี parameter ไม่ถือเป็น classic JavaScript, token อย่าง `module` ต้องตรงโดยไม่ trim ช่องว่าง; บันทึกชนิดที่ไม่ใช่ classic รวม `module`, `importmap`, `speculationrules` และ `inert` ใน facts ส่วน script ปกติยังคงรูปแบบ fact เดิม
- `backend/tests/test_structure.py`: เพิ่ม 12 test ซึ่ง 8 ตัวล้มเมื่อรันกับโค้ดเดิม
- ไม่ต้อง migration: `diff.py` คำนวณ facts ใหม่จาก HTML ที่เก็บไว้ทั้งสองฝั่งทุกครั้ง baseline เดิมจึงไม่ถูกมองว่า Changed เพราะ format ของ fact

**SEC-06 (เฉพาะส่วนโค้ด)**

- `ssrf_proxy.py`: proxy นับไบต์ที่ relay ให้ browser ระหว่างรับข้อมูล (ไม่พึ่ง `Content-Length`) เมื่อเกินงบจะตัด connection และปฏิเสธทุก response ที่ตามมา ทำให้ capture ล้มเหลวทั้งชุด
- `capture.py`: ตรวจเพดานความสูง, pixel และจำนวน DOM nodes ผ่าน CDP (`Page.getLayoutMetrics`, `Memory.getDOMCounters`) ก่อนเรียก `page.content()` และก่อนถ่าย full-page ค่ามาจากฝั่ง browser หน้าเว็บโกหกผ่าน JavaScript ไม่ได้ (มี test ยืนยัน)
- `config.py` และ `backend/.env.example`: `MAX_CAPTURE_TRANSFER_MB=100`, `MAX_SCREENSHOT_HEIGHT_PX=30000`, `MAX_SCREENSHOT_PIXELS=64000000`, `MAX_DOM_NODES=300000`
- `errors.py`: เพิ่ม `CaptureBudgetExceeded` (สืบทอดจาก `CaptureError` จึงสถานะ check เป็น Failed เหมือนเดิม)
- `backend/tests/test_capture_budgets.py`: เพิ่ม 7 test ใช้ Chromium จริง; แก้ mock ของ test เดิม 4 ตัวใน `test_capture.py` ให้ตอบ CDP ได้

**SEC-07 (audit trail)**

- `backend/app/services/audit.py` (ใหม่): บันทึกเข้าตาราง `member_audit_events` ที่มีอยู่แล้ว จึงไม่ต้องทำ Alembic migration ใหม่
- บันทึก `baseline.approved`, `check.acknowledged`, `check.defacement_confirmed`, `baseline.demoted` พร้อม actor, target_id และสถานะก่อน–หลัง ทั้งหมดอยู่ใน transaction เดียวกับการเปลี่ยนแปลง (commit ล้มเหลวแล้ว rollback จะไม่เหลือ event)
- baseline ที่ถูก demote อัตโนมัติจาก cap บันทึกเป็น `baseline.demoted` ที่ `source="baseline_cap"` พร้อม `caused_by_snapshot_id`
- เก็บเฉพาะ ID และสถานะ ไม่เก็บ URL หรือเนื้อหา; acknowledge ซ้ำไม่สร้าง event ซ้ำ
- เพิ่ม `GET /audit-events` เฉพาะ Admin (operator ได้ 403, ไม่ login ได้ 401) กรองตาม target/actor/action และแบ่งหน้าได้ ซึ่งเดิมไม่มี endpoint อ่าน audit เลย
- ไฟล์ที่แก้: `services/review.py`, `api/routes/review.py`, `api/routes/targets.py` (demote), `api/routes/audit.py` (ใหม่), `schemas/audit.py` (ใหม่), `main.py`; test: `tests/test_review_audit.py` (7 ตัว)

### 7.3 ผลตรวจหลังแก้

| การตรวจ | ผล |
| --- | --- |
| Test ก่อนแก้ (dependency เดิม) | 218 passed |
| Test หลังอัปเดต dependency + route Range | 219 passed |
| Test หลังแก้ detector | 230 passed |
| Test หลังแก้ SEC-06 และ SEC-07 | **244 passed** |
| ruff / mypy (`app`) | ผ่าน (mypy ตรวจ 58 ไฟล์) |
| Offline Chromium probe (Chromium 153) | `scripts/audit_round2_probe.py`: โค้ดเดิมได้ structure_score 0.0 ทั้ง 3 กรณี โค้ดใหม่ได้ formaction 0.5, script-type 1.0, javascript-tab 1.0 โดยภาพและข้อความเหมือนเดิม |

ผลการวัด Range parser ของ Starlette ด้วย disjoint ranges (ต่างจากตัวเลขในหัวข้อ SEC-02 ซึ่งวัดคนละรูปแบบ header):

| จำนวน ranges | Starlette 0.41.3 | Starlette 0.52.1 |
| --- | --- | --- |
| 2,000 | 76 ms | 98 ms |
| 4,000 | 335 ms | 407 ms |

Test ทั้งหมดรันบน Windows ด้วย venv แยก (Python 3.13.7) และ Chromium 153 ที่ติดตั้งในเครื่อง ไม่ใช่ใน Linux container

### 7.4 สิ่งที่ยังไม่ได้ทำ และเหตุผล

| รายการ | เหตุผลที่ยังไม่ทำ |
| --- | --- |
| Build image และรัน capture ใน Linux container จริง (Chromium sandbox, seccomp, read-only filesystem, non-root) | ยังยืนยันไม่ได้: Docker client 29.8.0 ติดตั้งอยู่ แต่การเข้าถึง Docker API ถูกปฏิเสธ (`permission denied` สำหรับ `/var/run/docker.sock`); `docker compose ps --all` จึงอ่าน running containers ไม่ได้ |
| ตรวจ version ของ Chromium binary ใน container ที่ deploy จริง | Project pin/manifest และ Chromium binary ที่ติดตั้งแยกใน venv Linux สอดคล้องกันที่ Playwright 1.63.0 / Chromium 153.0.8010.12 (revision 1243); binary ใน image/container ที่ deploy ยังตรวจไม่ได้เพราะ Docker API เข้าไม่ถึง |
| เทียบ `deploy/playwright-seccomp.json` กับโปรไฟล์ของ Playwright 1.63 และแก้ README บรรทัดที่อ้าง v1.48.0 | เทียบกับไฟล์ทางการของ tag v1.63.0 แล้ว แต่ JSON ไม่ตรงกัน: ไฟล์ project เพิ่ม syscall `chroot` ในกฎ allow สำหรับ user namespaces และมี comment เก่า; ยังไม่แก้ไฟล์หรือ README จนกว่าจะตรวจ profile ที่ใช้จริงใน container |
| ทดสอบ SSRF proxy, redirects, WebSocket blocking และ CDP session บน Linux | Redirect/SSRF guard และ capture tests ได้รันบน Linux host เมื่อ sandbox ปิดเฉพาะ test process; ผลไม่ครอบคลุม sandbox/seccomp ของ image. WebSocket block และ CDP behavior ยังไม่ได้ทดสอบ end-to-end บน container |
| Rebuild `backend/.venv` เดิม | ไม่แตะ `.venv` ใน project; สร้าง `/tmp/web-defacement-linux-audit` แยกสำหรับ Linux checks. Chromium 153 ถูกติดตั้งลง browser path แยกใน `/tmp` |
| Re-baseline ทุก target | เป็นขั้นตอนปฏิบัติการหลัง deploy ที่ต้องมีคนตรวจและ approve ทีละ target ไม่ใช่งานโค้ด; ยังไม่ได้เทียบภาพ Chromium 130 กับ 153 เพราะ binary 130 ถูกลบไปแล้ว จึงยังไม่ทราบขนาดของ false positive จริง |
| Container memory/CPU/PID limits ใน `docker-compose.yml` | ตรวจแล้วว่าไม่มี limit ดังกล่าวใน production Compose; cgroup ของ shell ปัจจุบันแสดง `cpu.max=max 100000`, `memory.max=max`, `pids.max=max`. ไม่มี container runtime ให้ตรวจหรือทดสอบ limit; ไม่ได้ทำ load/OOM test |
| แยก capture worker ออกจาก API และฐานข้อมูล (SEC-01, SEC-06) | เป็นงานโครงสร้างใหญ่ (queue, IPC, การเข้าถึง secret/DB, deployment, health check) เสี่ยงสร้าง bug ใหม่ จึงเลื่อนไปทำหลังยืนยัน Linux ด้วยรอบที่เล็กกว่า |
| แก้ Range parser ของ Starlette ที่ต้นเหตุ (SEC-02) | Starlette 0.52.1 มี parser ที่อัปเดตจากรุ่นเดิม แต่การ merge หลายช่วงยังมี loop O(n²); route screenshot ตัด `Range`/`If-Range` ที่ระดับแอปแล้ว แต่ยังไม่ได้เทียบ advisory ต้นฉบับเพื่อยืนยันขอบเขตแพตช์ CVE-2025-62727 หรือเพิ่มการจำกัด multi-range ที่ Nginx เป็น defense in depth |
| Policy allowed domains แยกสำหรับ `formaction` (SEC-03) | ต้องให้เจ้าของระบบตัดสินใจ ตอนนี้ใช้ `allowed_hosts` ชุดเดียวกับ form ถ้าเข้มเกินไป เว็บที่ใช้ฟอร์มของบุคคลที่สามจะแจ้งเตือนซ้ำจนคนเลิกใส่ใจ |
| ครอบคลุม attribute URL อื่นใน detector (เช่น `object data`, `embed src`) และตรวจว่า submit control มี form owner จริงหรือเชื่อมด้วย `form=` หรือไม่ | อยู่นอก scope SEC-03 รอบนี้; หากพบ control ที่ไม่มีฟอร์มรองรับ อาจเกิด false positive ควรพิจารณาเป็น follow-up |
| Retention ของ audit log และหน้า frontend สำหรับอ่าน (SEC-07) | ใช้ค่าเริ่มต้นที่เสนอ คือไม่ลบอัตโนมัติและอ่านผ่าน API เฉพาะ Admin; นโยบาย retention และ UX ของหน้าอ่านต้องให้เจ้าของระบบตัดสินใจ |
| Vulnerability scan ของ Python, OS packages และ container image ทั้งหมด | รายงานต้นฉบับระบุว่านอกขอบเขตและยังไม่ได้ทำ ต้องใช้เครื่องมือสแกนและ image ที่ build แล้ว |
| Load test บน Linux production | ไม่ได้ทำ; ต้องมี environment ที่ deploy แล้วและต้องได้รับอนุญาตก่อนยิงโหลด; ผล test ปัจจุบันปิด limiter ใน fixture ยกเว้น `test_auth.py:415` ซึ่งเปิด limiter จริงและผ่าน |

### 7.5 ข้อจำกัดของสิ่งที่แก้แล้ว

- งบไบต์ของ proxy นับไบต์บนสาย (ที่ถูกบีบอัดแล้ว) ไม่ใช่ขนาดหลังแตกไฟล์ จึงยังไม่กันกรณี gzip bomb
- Playwright ยัง buffer response ทั้งก้อนใน driver ก่อนส่งต่อ หน่วยความจำต่อ capture อาจสูงถึงงบ 100 MB และมีได้ 4 capture พร้อมกัน
- เพดาน pixel/DOM ตรวจหลังหน้าโหลดและ settle แล้ว หน้าที่กินทรัพยากรหนักระหว่างโหลดก่อนถึงจุดตรวจยังไม่ถูกกั้นด้วยเพดานนี้
- ค่าเริ่มต้นของเพดานทั้งหมดตั้งโดยยังไม่ได้วัดกับเว็บจริง เว็บที่ยาวหรือหนักมากอาจถูกปฏิเสธ ควรตรวจบน staging
- Audit log ไม่มี actor สำหรับการเปลี่ยนแปลงก่อนวันที่แก้ และตาราง `member_audit_events` ใช้ร่วมกับ event ของ member/website/tag
- ยังไม่มี Git history: `.git` ของโปรเจกต์เป็นโฟลเดอร์ว่าง ใช้ branch/tag ไม่ได้ จึงสำรองซอร์สก่อนแก้ไว้ที่ `backup-pre-security-fix-2026-10-14/` ควรลบเมื่อยืนยันผลบน Linux แล้ว

### 7.6 ข้อกำหนดก่อน deploy

1. ก่อน deploy ให้ทบทวน screenshot ที่เปลี่ยนจาก Chromium 153 และตรวจ alert ของ detector บน staging เป็นราย target; facts คำนวณใหม่จาก HTML ของทั้ง baseline และ snapshot ปัจจุบัน จึงไม่บังคับให้ re-baseline ทุก target ห้าม bulk-approve โดยไม่ตรวจ เพราะ baseline ที่ถูกเจาะอยู่แล้วจะกลายเป็น reference
2. ต้องผ่านข้อ "Build image และรัน capture ใน Linux container จริง", การเทียบ seccomp และการทดสอบ SSRF/WebSocket บน Linux ก่อน
3. ตั้ง container memory/CPU/PID limits หลังวัดบน Linux ก่อนเปิดใช้งานจริง

รายงานนี้ไม่เปลี่ยนสถานะ roadmap และ **ยังไม่ถือว่า findings ได้รับการแก้ไขครบ** การแก้ใน source ตามหัวข้อ 7 ยังต้องผ่านเกณฑ์ตรวจรับของแต่ละ finding บน deployment จริงก่อน

### 7.7 ผลตรวจหลังปรับแก้รอบนี้ (14-10-2026)

- Test backend ทั้งหมด ณ รอบตรวจเดิม: **246 passed** (รวม `tests/test_structure.py` 34 passed); รอบทบทวนล่าสุดเพิ่มการตรวจชนิด submit control และผลยืนยันอัปเดตไว้ในข้อ 7.8; มี deprecation warnings จาก dependencies/tests
- Ruff: ผ่าน (`app`, `tests`, `scripts`, `alembic`)
- Mypy: ผ่าน ตรวจ 58 source files ด้วย Python 3.11; ข้าม type-check ของ upstream `deprecated.*` เนื่องจาก package รุ่นล่าสุดใช้ syntax Python 3.12 แม้แอปรองรับ Python 3.11
- Offline Chromium 153 probe: ตรวจพบการเปลี่ยน `formaction` ปกติและค่าว่าง (structure score 0.5), script type ปกติและ MIME parameters รวมถึง javascript URL ที่มี tab (1.0); ทุกกรณีภาพและข้อความเหมือนเดิม
- การตรวจ Linux container, sandbox/seccomp, SSRF/WebSocket และ resource limits ยังเป็นงานค้างตามข้อ 7.4–7.6; ผลผ่านบน Windows ไม่ใช้แทนเกณฑ์ตรวจรับ Linux

### 7.8 ผลทบทวนความสมบูรณ์เพิ่มเติม

- พบและแก้ false positive ใน SEC-03: `formaction` จะถูกเก็บเฉพาะบน `<button>` ที่มีสถานะ submit (รวม missing/invalid type) และ `<input type="submit|image">`; เพิ่ม test ยืนยันว่า button/reset/text inputs ไม่สร้าง fact ดังกล่าว
- ยังไม่ได้ตรวจความสัมพันธ์กับ form owner หรือ `form=` attribute ของ control นอกฟอร์ม; รายงาน alert จาก control ที่ไม่มี form owner ได้ และจัดเป็น follow-up ที่ระบุไว้ในข้อ 7.4
- รอบยืนยันหลังแก้ submit-control filter: backend **247 passed** (รวม `tests/test_structure.py` 35 passed), Ruff ผ่าน, mypy ผ่าน 58 ไฟล์ และ Offline Chromium 153 probe ทั้ง 5 กรณีผ่าน; ภาพ/ข้อความคงเดิมในทุกกรณี

### 7.9 ผลตรวจ Linux เพิ่มเติม (15-10-2026, Asia/Bangkok)

ตรวจจาก Linux host ด้วย temporary venv แยก ไม่ใช่ container ที่ build/deploy อยู่จริง: kernel `7.0.0-30-generic` x86_64, Python `3.12.3`, shell UID/GID `1003:1003`. Docker client `29.8.0` มีอยู่ แต่ทุกคำสั่งที่ต้องคุยกับ daemon ถูกปฏิเสธด้วย `permission denied` ที่ `/var/run/docker.sock`; จึงยืนยัน running container, image digest, mount flags, capabilities, seccomp ที่ attach จริง หรือ network namespace จริงไม่ได้ และไม่ได้ดึง/build production image.

| รายการตรวจ | หลักฐานและผลจริง |
| --- | --- |
| Project/browser versions | `backend/Dockerfile` ใช้ `mcr.microsoft.com/playwright/python:v1.63.0-noble`; `backend/requirements.txt` pin `playwright==1.63.0`. Package manifest ระบุ Chromium `153.0.8010.12`, revision `1243`. ติดตั้ง browser แยกใน `/tmp`; `chrome --version` รายงาน `Google Chrome for Testing 153.0.8010.12`. ตรงกันใน Linux test environment แต่ยังไม่ใช่หลักฐานของ image/container ที่ deploy |
| Compose isolation ที่คาดหวัง | Source config ระบุ `${APP_UID:-1000}:${APP_GID:-1000}`, `read_only: true`, `cap_drop: ALL`, `no-new-privileges:true`, custom `seccomp:./deploy/playwright-seccomp.json`, `/tmp` แบบ tmpfs และไม่มี `ports` บน backend. Backend กับ frontend อยู่บน bridge network เดียวกัน (`172.30.0.0/24`); Compose ไม่ได้ประกาศ `internal: true` หรือ egress ACL จึงไม่มี egress block ใน config. เป็นการอ่าน config เท่านั้น ไม่ยืนยันค่าที่ runtime ใช้อยู่ |
| Runtime sandbox/capabilities | Shell ปัจจุบัน UID 1003; `/proc/self/status` ให้ `CapEff=0`, `NoNewPrivs=0`, `Seccomp=0`. ค่านี้เป็นของ shell บน host ไม่ใช่ capture container. Chromium sandbox เปิดไว้ตาม default แล้ว launch ไม่สำเร็จ โดย log ระบุ `Chromium sandboxing failed`; จึงยังยืนยัน sandbox ใน deployment ไม่ได้และไม่ปิด SEC-01 |
| Seccomp profile | เทียบ JSON กับ [ไฟล์ทางการ Playwright v1.63.0](https://github.com/microsoft/playwright/blob/v1.63.0/utils/docker/seccomp_profile.json). Project file ไม่ตรง: เพิ่ม `chroot` ในกฎ allow สำหรับ user namespaces และคง comment เดิม; upstream rule อนุญาต `clone`, `setns`, `unshare`. ยังไม่ได้แก้ profile หรือทดลอง attach ใน container เพราะ runtime ใช้ไม่ได้ |
| SSRF/redirects | ใน test run แบบ sandbox ปิด มี automated local tests สำหรับ redirect ไป blocked destination และ private-IP rebinding ผ่าน. `tests/test_ssrf_guard.py` ผ่าน 7 tests. เป็นผลจาก test environment เท่านั้น ยังไม่ยืนยัน network policy หรือ seccomp ใน container |
| WebSocket/CDP | Config เปิด `BLOCK_WEBSOCKETS=True` และ capture ลงทะเบียน `context.route_web_socket("**/*", ...)`; CDP session ถูกสร้างภายในเพื่ออ่าน page metrics และไม่พบ remote CDP endpoint ใน launch config. ยังไม่มี end-to-end test ยืนยันว่า WebSocket ถูกบล็อกหรือ CDP ไม่ถูก expose ใน running container; runtime ยังไม่ได้ตรวจ |
| Screenshot Range | `tests/test_api_routes.py::test_raw_screenshot_ignores_range_headers` ผ่านใน full run. Single range, 2,000 ranges และ malformed range ตอบ HTTP 200 พร้อม full body เดิม, `Accept-Ranges: none` และไม่มี `Content-Range` |
| Capture budgets | ทั้ง 7 tests ใน `tests/test_capture_budgets.py` ผ่านใน test run ที่ปิด Chromium sandbox: in-budget, ขนาด height/pixels/DOM เกิน limit, JavaScript ซ่อน scroll height, transfer เกิน/ไม่เกินงบ. นี่ทดสอบ capture budgets ไม่ใช่ CPU/memory/PID cgroup limits |
| CPU/memory/PID | Production `docker-compose.yml` ไม่มี `cpus`, memory limit หรือ `pids_limit`. cgroup ของ shell รายงาน `cpu.max=max 100000`, `memory.max=max`, `pids.max=max` (ไม่จำกัด). ไม่มี limit ที่ตั้งไว้ให้ทดสอบใน environment นี้; ไม่ได้ทำ load/OOM test |

**คำสั่งและผล backend บน Linux** (รันจาก `backend/`; ใช้ temporary venv `/tmp/web-defacement-linux-audit`):

- `python3 -m venv /tmp/web-defacement-linux-audit && /tmp/web-defacement-linux-audit/bin/python -m pip install -r requirements-dev.txt` — ผ่าน; ติดตั้ง requirements ที่ pin ไว้ รวม pytest, Ruff, mypy และ Playwright
- `PLAYWRIGHT_BROWSERS_PATH=/tmp/web-defacement-linux-audit/pw-browsers /tmp/web-defacement-linux-audit/bin/python -m pytest` — **207 passed, 40 failed**. Capture/browser tests เปิด sandbox ตาม default แล้ว Chromium ปฏิเสธการ launch บน host นี้ (`Chromium sandboxing failed`); จึงไม่ใช่ผลยืนยัน production container
- `BROWSER_DISABLE_SANDBOX=true PLAYWRIGHT_BROWSERS_PATH=/tmp/web-defacement-linux-audit/pw-browsers /tmp/web-defacement-linux-audit/bin/python -m pytest -k 'not test_capture_snapshot_sandbox_configuration'` — **243 passed, 3 failed, 1 deselected**. Tests ของ Range, capture budgets, redirect/SSRF และ detector ทำงานใน test environment นี้. Failure ที่เหลือ: `test_capture_snapshot_routes_all_requests_through_loopback_proxy` ได้ค่า sandbox ปิดจาก environment override; `test_proxy_closes_tunnel_when_upstream_stalls` และ `test_proxy_records_reset_before_response` พบ `ConnectionResetError` ในการอ่าน socket ที่ test คาดว่าจะปิดตามปกติ
- `/tmp/web-defacement-linux-audit/bin/ruff check app tests scripts alembic` — ผ่าน (`All checks passed!`)
- `/tmp/web-defacement-linux-audit/bin/mypy app` — ผ่าน (`Success: no issues found in 58 source files`)

**สถานะหลังรอบนี้:** ยังไม่ปิด finding ใดเพิ่ม. SEC-01 acceptance ยังต้องมี running target container ที่ Chromium sandbox/seccomp ทำงานภายใต้ non-root, read-only filesystem, capabilities และ network configuration จริง; SEC-06 ยังไม่มี CPU/memory/PID limits หรือการทดสอบ staging ที่พิสูจน์ budgets ภายใต้ resource limit. SEC-02 ยังคงเป็น mitigation ที่ route screenshot ไม่รับ Range; ยังไม่ได้ปิดประเด็น parser ที่ต้นเหตุ. ต้องแก้/ตรวจความต่างของ seccomp profile ก่อนถือว่า config สอดคล้องกับ Playwright 1.63.
