# แผนแก้ไขเพิ่มเติม CR10 หลังการ Review รอบที่สอง

วันที่: 17 กันยายน 2026  
สถานะ: ดำเนินการด้านโค้ดและ automated verification แล้ว — ตรวจ runtime เมื่อ deploy บน Linux  
ขอบเขต: Production security, test isolation, capture cleanup และความถูกต้องของเอกสาร

เอกสารอ้างอิง:

- [แผน CR10 หลัก](Code-Review-and-Remediation-Plan-CR10-17-9-2026.md)
- [แผน Follow-up รอบแรก](CR10-Follow-up-Remediation-Plan-17-9-2026.md)
- [บันทึกการดำเนินการ Follow-up](../refinement/17-9-2026/Code-Review-Remediation-CR10-FollowUp-17-9-2026.md)
- [แผนโครงการ](PROJECT_PLAN.md)

## 1. วัตถุประสงค์

แผนนี้จัดการประเด็นที่พบจากการ review ซ้ำหลังดำเนินการ CR10 Follow-up รอบแรก โดยเน้นให้ production configuration บังคับใช้นโยบายความปลอดภัยจริง แยกการทดสอบออกจากฐานข้อมูล production ครอบคลุม cleanup ตลอดอายุของ capture coroutine และทำให้สถานะในเอกสารตรงกับหลักฐานที่ตรวจรับได้

ผลการดำเนินการและข้อจำกัดล่าสุดบันทึกไว้ใน
[`Code-Review-Remediation-CR10-SecondFollowUp-17-9-2026.md`](../refinement/17-9-2026/Code-Review-Remediation-CR10-SecondFollowUp-17-9-2026.md)
โดยข้อ 3.1–3.5 ดำเนินการด้าน source/configuration แล้ว การทดสอบ Docker runtime
บน Windows ถูกยกเว้นเนื่องจากระบบเป้าหมายคือ Linux ส่วน image, TLS,
routed-authentication และ sandbox smoke checks ให้ดำเนินการในขั้นตอน deploy บน Linux

## 2. ข้อกำหนดที่ต้องรักษา

- ห้ามลบ reset stamp ซ้ำ หรือเปลี่ยนข้อมูลใน `backend/data/app.db` ระหว่างการพัฒนาและทดสอบ
- ต้องรักษา monitoring targets, snapshots, baselines และ check history เดิมทั้งหมด
- ต้องรักษา single API worker (`--workers 1`), SSRF guard, CSRF verification, authentication และ detector thresholds เดิม
- Regression tests ต้องใช้ฐานข้อมูล ไดเรกทอรี และ network fixtures ที่แยกจาก production
- ห้ามติดต่อ monitoring targets จริงจากชุดทดสอบ
- ห้ามระบุว่า production พร้อมใช้งานหรือ verified จนกว่า runtime integration checks ที่เกี่ยวข้องจะผ่าน

## 3. รายการแก้ไข

### 3.1 [P1] บังคับใช้ Production Environment และ Secure Session Cookies

ไฟล์เกี่ยวข้อง:

- `docker-compose.yml`
- `backend/.env.example`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `README.md`
- TLS/reverse-proxy configuration ที่เลือกใช้

**ข้อพบ**

`docker-compose.yml` ระบุว่าเป็น production environment แต่ไม่ได้กำหนด `ENVIRONMENT=production` และ `SESSION_COOKIE_SECURE=true` ค่าเริ่มต้นจึงยังเป็น development และ cookie แบบไม่ secure ทำให้ production startup guard ไม่ถูกเรียกใช้ตามเจตนา

**งานที่ต้องทำ**

1. กำหนด `ENVIRONMENT=production` ใน production deployment อย่างชัดเจน
2. เปิด `SESSION_COOKIE_SECURE=true` สำหรับ production
3. เพิ่ม HTTPS/TLS endpoint ก่อนเปิด secure cookie โดยเลือก reverse proxy หรือ ingress ที่เหมาะกับสภาพแวดล้อมจริง
4. กำหนด trusted origins ให้ตรงกับ HTTPS origin ที่ผู้ปฏิบัติงานใช้จริง
5. แยก development defaults ออกจาก production defaults ให้ชัดเจน
6. ปรับ README ให้ระบุ URL, certificate, cookie และ startup requirements ตาม configuration จริง

**เกณฑ์ตรวจรับ**

- Production backend ปฏิเสธการเริ่มทำงานเมื่อ secure cookie ถูกปิด
- Dashboard เปิดผ่าน HTTPS และ login, `/auth/me`, mutation และ logout ทำงานผ่าน same-origin `/api`
- Session cookie มี `Secure`, `HttpOnly`, `SameSite` และ `Path` ตาม configuration
- HTTP endpoint redirect ไป HTTPS หรือไม่เปิดให้เข้าถึงตาม deployment design
- Development workflow ยังใช้งานได้ผ่าน configuration แยก

### 3.2 [P1] เปิด Browser Sandbox หรือเพิ่มมาตรการ Isolation ที่เพียงพอ

ไฟล์เกี่ยวข้อง:

- `docker-compose.yml`
- backend container image/build configuration
- `backend/app/services/capture/capture.py`
- deployment documentation

**ข้อพบ**

Production Compose กำหนด `BROWSER_DISABLE_SANDBOX=true` และ `seccomp:unconfined` แต่ไม่ได้กำหนด non-root user, read-only filesystem หรือ network isolation ตามมาตรการชดเชยที่ source code ระบุไว้ เว็บที่ถูก capture อาจเป็นเนื้อหาที่เป็นอันตราย จึงไม่ควรใช้งาน configuration นี้ใน production โดยไม่มี isolation เพิ่มเติม

**งานที่ต้องทำ**

1. พยายามเปิด Chromium sandbox ใน production เป็นตัวเลือกหลัก
2. ใช้ non-root user และลด Linux capabilities เท่าที่ runtime รองรับ
3. หลีกเลี่ยง `seccomp:unconfined`; หากจำเป็นต้องใช้ ให้บันทึกเหตุผลและเพิ่มมาตรการชดเชยที่ตรวจสอบได้
4. จำกัด filesystem access โดยใช้ read-only root filesystem และ writable mounts เฉพาะตำแหน่งที่ต้องเขียน
5. จำกัด network reachability ของ capture runtime ไม่ให้เข้าถึง internal networks นอกเส้นทางที่ SSRF proxy ควบคุม
6. ตรวจว่า Playwright/Chromium ยัง capture ได้ภายใต้ข้อจำกัดใหม่

**เกณฑ์ตรวจรับ**

- Chromium เปิดด้วย sandbox หรือมีชุดมาตรการชดเชยที่ระบุและทดสอบครบ
- Container ไม่รันด้วยสิทธิ์เกินความจำเป็น
- ไม่มี unrestricted host/internal network access จาก browser process
- Capture tests, SSRF proxy tests และ smoke capture ผ่านใน production container
- การเขียน artifacts และ SQLite ทำได้เฉพาะ writable paths ที่กำหนด

### 3.3 [P1] แยก Foreign-Key Test ออกจาก Production Database

ไฟล์เกี่ยวข้อง:

- `backend/tests/test_checks.py`
- `backend/tests/conftest.py`
- test database fixtures
- `backend/app/db/session.py` หากต้องแยก helper สำหรับติดตั้ง PRAGMA

**ข้อพบ**

`test_sqlite_foreign_keys_pragma` เชื่อมต่อ `app.db.session.engine` ซึ่งใช้ `DATABASE_URL` ของแอปและอาจชี้ไป `backend/data/app.db` เมื่อ connection เปิดขึ้น event listener ยังสั่ง `PRAGMA journal_mode=WAL` จึงขัดกับข้อกำหนด test isolation

**งานที่ต้องทำ**

1. เปลี่ยนเทสต์ PRAGMA ให้สร้าง SQLite engine ใน temporary directory หรือ in-memory database
2. ใช้กลไกติดตั้ง PRAGMA เดียวกับ production engine เพื่อให้เทสต์ตรวจ implementation จริงโดยไม่เชื่อมต่อ app engine
3. ห้าม import หรือ connect `SessionLocal`/`engine` ที่ชี้ production database ใน database unit tests
4. เพิ่ม guard ใน test setup เพื่อปฏิเสธ `DATABASE_URL` ที่ resolve ไปยัง `backend/data/app.db`
5. เพิ่ม regression tests สำหรับ invalid target/snapshot foreign keys และ restricted delete ตาม acceptance criteria เดิม

**เกณฑ์ตรวจรับ**

- การรัน backend test suite ไม่เปิดหรือเปลี่ยน `backend/data/app.db`, `app.db-wal` หรือ `app.db-shm`
- Test engine ทุกตัวที่จำลอง production SQLite มี `PRAGMA foreign_keys=1`
- Invalid foreign-key insert และการลบ parent ที่ยังถูกอ้างถึงล้มเหลวด้วย `IntegrityError`
- Test suite ผ่านเมื่อ production database ไม่มีอยู่หรือถูกทำให้ read-only

### 3.4 [P2] ครอบคลุม Staging Cleanup จน CaptureResult ถูกส่งกลับสำเร็จ

ไฟล์เกี่ยวข้อง:

- `backend/app/services/capture/capture.py`
- `backend/app/services/capture/ssrf_proxy.py`
- `backend/tests/test_capture.py`
- `backend/tests/test_concurrency.py`

**ข้อพบ**

cleanup ปัจจุบันครอบคลุม write failure และ cancellation ใน `browser.close()` แต่หลัง browser ปิดแล้วยังต้องออกจาก Playwright และ `SsrfProxy` async context managers หาก cancellation หรือ shutdown failure เกิดในช่วงนี้ coroutine จะไม่คืน `CaptureResult` แต่ staging อาจค้างอยู่

**งานที่ต้องทำ**

1. ครอบ capture lifecycle ทั้งฟังก์ชันด้วย outer `try/finally` หรือ ownership guard ที่ทำงานจนถึงจุดคืน `CaptureResult`
2. กำหนดสถานะสำเร็จหลังออกจาก async context managers ครบแล้วเท่านั้น
3. ลบ staging เมื่อ exception หรือ `CancelledError` เกิดก่อน caller ได้รับผลลัพธ์
4. ส่งต่อ cancellation เดิมโดยไม่เปลี่ยนเป็น business error
5. ตรวจว่าการปล่อย in-flight reservation และการเปลี่ยน target status ยังทำงานถูกต้องเมื่อ timeout/cancel

**เกณฑ์ตรวจรับ**

- Cancellation ระหว่าง artifact write, `browser.close()`, Playwright shutdown และ `SsrfProxy.__aexit__()` ไม่ทิ้ง staging
- Capture ที่สำเร็จเก็บ staging ไว้ให้ `run_target_check` promote หรือ discard ตามผลเปรียบเทียบ
- `CancelledError` ยังถูกส่งต่อ และ reservation ถูกปล่อยใน worker `finally`
- เพิ่ม regression test แยกสำหรับ cancellation ระหว่างออกจากแต่ละ async context ที่สำคัญ

### 3.5 [P3] ทำให้สถานะในเอกสารตรงกับผลตรวจรับ

ไฟล์เกี่ยวข้อง:

- `refinement/17-9-2026/Code-Review-Remediation-CR10-FollowUp-17-9-2026.md`
- `refinement/17-9-2026/Code-Review-Remediation-CR10-Phase3-17-9-2026.md`
- `UPDATE_SUMMARY.md`
- `README.md`

**ข้อพบ**

Follow-up ระบุว่า Docker runtime validation ยังรอดำเนินการ แต่ Phase 3 ยังระบุว่า CR10 เสร็จและ verified 100% อีกทั้ง Follow-up Items 2–3 ยังเป็น Completed & Verified ทั้งที่ test isolation และ full capture cleanup ยังไม่ครบ

**งานที่ต้องทำ**

1. ปรับสถานะ Items 2–4 และสถานะรวมให้ตรงกับงานที่ยังค้าง
2. ลบหรือแก้ข้อความว่า production database “untouched” จนกว่าชุดเทสต์จะแยกจาก app engine และมีหลักฐานยืนยัน
3. แยกสถานะ implementation, automated verification และ runtime deployment verification
4. บันทึก Docker/TLS/Nginx/backend integration results หลังทดสอบจริง
5. ปรับข้อความ “100% completed” หลังเกณฑ์ตรวจรับทั้งหมดผ่านเท่านั้น

**เกณฑ์ตรวจรับ**

- เอกสารทุกฉบับแสดงสถานะเดียวกันสำหรับแต่ละ CR10 item
- ไม่มีข้อความ fully verified หากยังขาด Docker runtime, HTTPS หรือ capture lifecycle test
- ผลทดสอบทุกตัวระบุคำสั่ง สภาพแวดล้อม วันที่ และข้อจำกัดที่เกี่ยวข้อง

## 4. ลำดับดำเนินการ

1. แยก test database ตามข้อ 3.3 ก่อนรัน backend suite ครั้งถัดไป
2. แก้ capture lifecycle และ regression tests ตามข้อ 3.4
3. ออกแบบ production HTTPS/session configuration ตามข้อ 3.1
4. ปรับ browser/container isolation ตามข้อ 3.2
5. รัน automated verification ทั้งหมดใน isolated environment
6. ทดสอบ Docker Compose, HTTPS, Nginx-to-FastAPI, login และ smoke capture บน deployment host
7. ปรับเอกสารตามข้อ 3.5 ด้วยผลตรวจรับจริง

## 5. Verification Matrix

| พื้นที่ | การตรวจที่ต้องผ่าน |
|---|---|
| Database isolation | Full backend suite โดย production DB เป็น read-only หรือไม่อยู่ใน workspace test path |
| Foreign keys | PRAGMA, invalid insert และ restricted delete บน temporary SQLite engine |
| Capture cleanup | Write failure, browser-close cancellation, Playwright-exit cancellation, proxy-exit cancellation และ timeout |
| Backend quality | Pytest, Ruff และ Mypy |
| Frontend quality | Vitest, TypeScript และ production build |
| Container | Image build, non-root/isolation inspection, health checks และ smoke capture |
| HTTPS/Auth | Secure cookie attributes, login, `/auth/me`, CSRF mutation และ logout ผ่าน `/api` |
| Routing | SPA fallback, static caching และ Nginx `/api` path stripping |
| Data preservation | Target, snapshot, baseline และ check-result counts/checksums ก่อนและหลัง deployment validation |

## 6. เงื่อนไขการปิดแผน

แผนนี้ปิดได้เมื่อ P1 และ P2 ทุกข้อผ่านเกณฑ์ตรวจรับ ไม่มีการเขียนจากชุดเทสต์ไปยัง production database, Docker runtime integration ผ่านบน host เป้าหมาย และเอกสาร CR10 ทุกฉบับแสดงสถานะตรงกับหลักฐานล่าสุด
