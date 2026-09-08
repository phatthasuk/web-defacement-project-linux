# Code Review by GPT-6 Astra

วันที่: 8 กันยายน 2026  
โครงการ: Website Defacement Monitoring System  
สถานะ: ดำเนินการแก้ไขเสร็จสมบูรณ์แล้ว — บันทึกประวัติที่ [`refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md`](../../refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md)

## 1. วัตถุประสงค์และขอบเขต

เอกสารนี้กำหนดแผนแก้ไขข้อค้นพบ 6 ประเด็นจากการ review backend และ frontend พร้อมหลักฐาน สาเหตุ ขั้นตอนดำเนินการ กรณีทดสอบ และเกณฑ์รับงาน เพื่อให้ดำเนินการแก้ไขได้โดยไม่สูญเสียความถูกต้องของการตรวจเว็บไซต์และประวัติการตรวจ

การจัดทำเอกสารครั้งนี้สร้างเฉพาะไฟล์แผนตามคำขอ ไม่แก้ไข source code, tests, configuration, dependencies, artifacts หรือฐานข้อมูลจริง การแก้ไขที่อธิบายต่อจากนี้เป็นงานในอนาคต และไม่ถือว่าดำเนินการแล้ว

เอกสารนี้เป็นแผน remediation ประกอบ `PROJECT_PLAN.md` ไม่แทนที่ roadmap หลัก ไม่ขยายระบบไปเป็นหลาย workers และไม่เปลี่ยนแนวทางตรวจแบบ deterministic หากข้อความใน roadmap ระบุว่า sandbox เปิดอยู่ ให้ถือเป็นความตั้งใจของระบบที่ implementation ยังทำไม่ได้ตามหลักฐานข้อ CR-01 และปรับเอกสารหลักเมื่อแก้ไขและตรวจสอบเสร็จ

ข้อจำกัดของการ review:

- ตรวจจาก source code และ source ของ Playwright ที่ติดตั้งในเครื่อง
- จำลอง CR-02, CR-03 และ CR-04 ด้วย SQLite ในหน่วยความจำ โดยใช้ session แบบ `autoflush=False` เช่นระบบจริง
- ไม่เปิดหรือเขียนฐานข้อมูลใช้งานจริง ไม่ส่งคำขอตรวจเว็บไซต์จริง
- ยังไม่ได้รัน regression suite ทั้งหมดหรือทดสอบผ่าน browser UI จริงในการ review รอบนี้
- รายการนี้ไม่ใช่การรับรองว่าไม่มีข้อผิดพลาดอื่น หรือเป็นผล security audit ที่ครอบคลุมทุก attack surface

## 2. สรุปข้อค้นพบและลำดับความสำคัญ

P1 หมายถึงควรแก้ก่อนการขยายการใช้งาน เนื่องจากกระทบการแยกความปลอดภัยหรือทำให้สถานะแจ้งเตือนผิด ส่วน P2 เป็นข้อผิดพลาดที่ควรแก้ในรอบ remediation เดียวกัน

| ID | ระดับ | ข้อค้นพบ | ผลกระทบหลัก | หลักฐาน |
| --- | --- | --- | --- | --- |
| CR-01 | P1 | Chromium sandbox ไม่เปิดตามคอนฟิก | เปิดหน้าเว็บโดยขาดการป้องกันที่ระบบระบุไว้ | ตรวจ launch call และ Playwright driver |
| CR-02 | P1 | อนุมัติ snapshot เก่าแล้ว target กลายเป็น OK | กลบสถานะเปลี่ยนแปลงล่าสุดที่ยังไม่ได้ review | จำลองได้: target=OK, latest check=Changed, acknowledged_at=None |
| CR-03 | P2 | จำนวน baseline เกินเพดานในระบบจริง | baseline ที่ UI แสดงกับชุดที่นำไปเปรียบเทียบอาจไม่ตรงกัน | ตั้งเพดาน 3 แต่ได้ active baseline 4 |
| CR-04 | P2 | เปลี่ยน URL ระหว่างตรวจได้ | บันทึกผลและ baseline ของ URL เก่าให้ target URL ใหม่ | จำลองได้: URL ใหม่มีสถานะ OK แต่ baseline เป็น URL เก่า |
| CR-05 | P2 | หน้ารายละเอียดไม่ติดตามงาน scheduler ขณะสถานะเดิมเป็น OK | ผู้ใช้เห็นสถานะหรือผลตรวจเก่าค้าง | ตรวจ query polling และ invalidation |
| CR-06 | P2 | หน้า target list ไม่มี pagination | แสดงเพียง 50 รายการแรกและจำนวนรวมไม่ครบ | Backend default limit=50 แต่ frontend ไม่ส่ง offset/limit |

## 3. หลักการที่ต้องรักษาระหว่างแก้ไข

1. การเพิ่ม baseline ไม่ใช่หลักฐานว่าปัญหาล่าสุดของเว็บไซต์ถูกแก้ไขแล้วเสมอไป
2. ผลตรวจหนึ่งงานต้องสัมพันธ์กับ URL ที่งานนั้นตรวจจริง
3. Baseline ที่ระบบบอกว่า active ต้องตรงกับ baseline ที่ detector มีสิทธิ์ใช้
4. ไม่ลบ snapshot, CheckResult หรือ artifact เพียงเพื่อให้การจำกัดจำนวน baseline ผ่าน
5. คงข้อห้าม demote baseline สุดท้าย และไม่เพิ่ม auto-rebaseline ที่รับหน้าเว็บปัจจุบันเป็น trusted baseline โดยไม่มี review
6. คง authentication, CSRF, SSRF guard, WebSocket blocking และ detector thresholds เดิม
7. ทดสอบ business logic ด้วย configuration ของ database session ที่สอดคล้องกับระบบจริง
8. คง single-worker deployment ตามสถาปัตยกรรมปัจจุบัน ไม่อ้างว่า process-local guard รองรับหลาย workers
9. ไม่ใช้ฐานข้อมูล production หรือการกดตรวจเว็บไซต์จริงเป็น regression test

## 4. CR-01 — เปิด Chromium sandbox ให้ตรงกับคอนฟิก

### 4.1 ตำแหน่งและสาเหตุ

- `backend/app/services/capture/capture.py`: `capture_snapshot()` และการเรียก `playwright.chromium.launch()` บริเวณบรรทัด 77 ณ วันที่ review
- `backend/app/core/config.py`: `BROWSER_DISABLE_SANDBOX=False`
- `docker-compose.yml`: runtime ของ browser และ user ที่ใช้รัน container
- `backend/tests/test_capture.py`: tests ของ capture และ launch configuration

โค้ดเพิ่ม `--no-sandbox` เฉพาะเมื่อ `BROWSER_DISABLE_SANDBOX=True` แต่ไม่ได้ส่ง `chromium_sandbox=True` เมื่อคอนฟิกเป็น False ขณะที่ driver ของ Playwright ที่ติดตั้งเพิ่ม `--no-sandbox` เองเมื่อ `chromiumSandbox` ไม่ใช่ True การไม่เพิ่ม flag ในโค้ดของแอปจึงไม่เท่ากับเปิด sandbox

### 4.2 พฤติกรรมเป้าหมาย

| คอนฟิก | พฤติกรรมที่ต้องได้ |
| --- | --- |
| `BROWSER_DISABLE_SANDBOX=False` | ส่ง `chromium_sandbox=True` อย่างชัดเจน ไม่มี launch args ที่ปิด sandbox |
| `BROWSER_DISABLE_SANDBOX=True` | ส่ง `chromium_sandbox=False` อย่างชัดเจน และบันทึก warning ตามที่มีอยู่ |
| runtime ไม่รองรับ sandbox แต่ตั้งให้เปิด | รายงานความล้มเหลว ไม่ fallback ไปปิด sandbox อัตโนมัติ |

### 4.3 ขั้นตอนดำเนินการ

1. ยืนยัน version ของ Python package และ browser runtime ก่อนแก้ไข โดยไม่อัปเกรด dependencies เป็นส่วนหนึ่งของงานนี้
2. เพิ่ม launch option ที่ผูกกับคอนฟิกโดยตรง และจัดการ args ที่ซ้ำซ้อนให้ไม่ขัดแย้งกับ option
3. รักษา host-resolver rules, service worker blocking, viewport และ WebSocket blocking เดิม
4. ตรวจ runtime ที่ใช้งานจริงแยก Windows และ Linux container เพราะการส่ง option ไม่ใช่หลักฐานว่านโยบายระดับ OS รองรับครบถ้วน
5. หาก container ใช้ root และเปิด sandbox ไม่ได้ ให้จัดทำ runtime ที่รองรับ เช่น user ที่ไม่ใช่ root และ permissions ที่เหมาะสม แล้ว smoke test ก่อนเลือกใช้ ไม่แก้ปัญหาด้วย silent fallback
6. ปรับคำอธิบายใน config, `.env.example` และเอกสารที่เกี่ยวข้องให้ตรงกับผลที่ทดสอบได้ รวมถึงข้อกำหนดของ container ถ้าจำเป็นต้องเปลี่ยน

### 4.4 กรณีทดสอบและเกณฑ์รับงาน

- Mock browser launch เพื่อตรวจ options ทั้งคอนฟิก True และ False
- จำลอง launch error และยืนยันว่าไม่มีการ retry แบบปิด sandbox
- Regression ของ redirect limit, private subresource, service worker และ WebSocket blocking ยังผ่าน
- Smoke test ด้วย fixture ที่ควบคุมได้ใน environment ที่จะใช้ deploy และตรวจ launch arguments ที่เกิดขึ้นจริง
- บันทึกผลการรองรับ sandbox ของแต่ละ environment อย่างชัดเจน ห้ามระบุว่าปลอดภัยครบทุก platform จาก mock test เพียงอย่างเดียว

## 5. CR-02 — แยกการอนุมัติ baseline ออกจากการล้างสถานะล่าสุด

### 5.1 ตำแหน่งและสาเหตุ

- `backend/app/services/review.py`: `approve_baseline()` บริเวณบรรทัด 47–73
- `backend/app/core/status.py`: state transitions
- `backend/tests/test_review.py` และ `backend/tests/test_api_routes.py`
- หน้า detail และ approve mutation ที่แสดงผลการอนุมัติ

ฟังก์ชันอนุมัติ snapshot ใดของ target ก็ได้ แล้วตั้ง `target.status=OK` และล้าง `last_error` เสมอ แม้ CheckResult ล่าสุดจะอ้างถึง snapshot คนละใบ หรือมี capture failure เกิดหลังจาก snapshot ที่กำลังอนุมัติ

หลักฐานที่จำลองได้: อนุมัติ baseline เก่าแล้ว target กลายเป็น OK ขณะที่ latest check ยังเป็น Changed และ `acknowledged_at=None`

### 5.2 กติกาที่เสนอ

| สถานการณ์ | ผลต่อ baseline | ผลต่อ target |
| --- | --- | --- |
| กำลัง Checking | ปฏิเสธตามข้อจำกัดเดิม | คงสถานะเดิม |
| อนุมัติ snapshot ของ latest Changed check และสถานะปัจจุบันเป็น Changed/Acknowledged/Defaced | อนุมัติและ acknowledge check ที่เกี่ยวข้อง | เปลี่ยนเป็น OK ได้ |
| อนุมัติ snapshot เก่าที่ไม่ใช่ current snapshot ของ latest check | เพิ่มเข้า baseline set ตามเพดาน | คงสถานะและ error ล่าสุด |
| ปัจจุบัน Failed หรือ Availability Issue | อนุมัติเป็น baseline ได้ถ้าเงื่อนไขอื่นผ่าน | คงสถานะและ last_error จนมี check ใหม่สำเร็จ |
| target เป็น OK อยู่แล้ว | อนุมัติได้ตามกติกา baseline | คง OK |
| อนุมัติซ้ำ snapshot ที่ active อยู่แล้ว | ทำงานแบบ idempotent | ไม่เปลี่ยนผลล่าสุดที่ไม่เกี่ยวข้อง |

เหตุผลที่รักษา Failed/Availability Issue: capture failure ไม่ได้สร้าง CheckResult ใหม่ในทุกกรณี จึงใช้เพียง latest CheckResult เพื่อสรุปว่าเหตุการณ์ล่าสุดได้รับการแก้ไขแล้วไม่ได้

### 5.3 ขั้นตอนดำเนินการ

1. อ่าน latest CheckResult ภายใน transaction ของการอนุมัติ และใช้ลำดับ `created_at DESC, id DESC` เหมือนส่วนอื่นของระบบ
2. แยกเงื่อนไขการเพิ่ม baseline, acknowledge check และเปลี่ยนสถานะ target ออกจากกัน
3. อนุญาตให้เปลี่ยนเป็น OK เฉพาะกรณีที่ตรงกับกติกาข้างต้น ไม่ทำ global assignment หลังอนุมัติทุกครั้ง
4. รักษาประวัติ `CheckResult.status` เดิมตาม semantics ปัจจุบัน และเปลี่ยนเฉพาะ acknowledgment ที่สัมพันธ์กับการอนุมัติ
5. ทำ approval และ baseline pruning ใน transaction เดียวกับ CR-03 หากขั้นตอนใดล้มเหลวต้อง rollback ทั้งชุด
6. ให้ข้อความ UI บอกว่าเพิ่ม baseline สำเร็จ โดยไม่สรุปว่าปัญหาล่าสุดถูกแก้ไขแล้วถ้า target ยังมีสถานะผิดปกติ
7. ปรับ test เดิมที่คาดหวังว่าอนุมัติจาก Failed แล้วต้องล้าง error เพราะ expectation เดิมเป็นส่วนหนึ่งของพฤติกรรมที่ต้องแก้

### 5.4 กรณีทดสอบและเกณฑ์รับงาน

- อนุมัติ snapshot เก่า ขณะ latest check เป็น Changed: target และ latest acknowledgment ต้องไม่ถูกล้าง
- อนุมัติ current snapshot ของ latest Changed check: target เป็น OK และ acknowledgment ถูกบันทึก
- Failed/Availability Issue ที่เกิดหลัง check ล่าสุด: อนุมัติ snapshot เก่าแล้ว error ยังคงอยู่
- อนุมัติจาก Defaced/Acknowledged: เปลี่ยนเป็น OK ได้เฉพาะ snapshot ที่สัมพันธ์กับผลล่าสุดตามกติกา
- Cross-target snapshot และ Checking ต้องยังถูกปฏิเสธ
- อนุมัติซ้ำต้องไม่ acknowledge check ที่ไม่เกี่ยวข้อง
- เพิ่ม API regression ที่ตรวจข้อมูลหลัง commit จาก session ใหม่ ไม่ตรวจเพียง object ในหน่วยความจำ

## 6. CR-03 — จำกัด baseline ให้ถูกต้องด้วย session ของระบบจริง

### 6.1 ตำแหน่งและสาเหตุ

- `backend/app/services/review.py`: ตั้ง `snapshot.is_baseline=True` แล้วเรียก prune
- `backend/app/services/checks.py`: `prune_baselines()` และ `get_baseline_snapshots()`
- `backend/app/db/session.py`: `SessionLocal(..., autoflush=False)`
- `backend/tests/test_review.py`: `sessionmaker(bind=engine)` ใช้ autoflush เริ่มต้น
- `backend/tests/conftest.py`: API test session มีความต่างเดียวกัน
- `frontend/src/components/BaselineManagerModal.tsx`: แสดงเพดาน 20 แบบ hardcoded

เมื่อ autoflush ปิด query ที่เลือก `is_baseline=True` ไม่เห็น snapshot ที่เพิ่งถูกเปลี่ยน flag จึง prune จากชุดเก่า ส่วน commit ภายหลังเพิ่ม candidate เข้าไปอีกหนึ่งรายการ

### 6.2 ขั้นตอนดำเนินการ

1. หลังตั้ง flag ให้ flush ภายใน transaction ก่อน query เพื่อ prune โดยไม่เพิ่ม intermediate commit
2. จำกัดเพดานให้เป็นจำนวนเต็มอย่างน้อย 1 เพื่อไม่ให้ configuration ลบ active baseline ทั้งชุด
3. รักษาการเรียงตาม `captured_at DESC, id DESC` และการ demote เฉพาะ flag ไม่ลบประวัติหรือ artifacts
4. กำหนดกรณี candidate เก่ากว่า baseline ทุกใบจนไม่ติดเพดาน: ตรวจล่วงหน้าและปฏิเสธพร้อมข้อความชัดเจน ไม่ตอบว่าอนุมัติสำเร็จทั้งที่ candidate ถูก demote ทันที ไม่เปลี่ยน retention policy ไปใช้เวลาอนุมัติโดยเงียบ ๆ
5. ทำ test factories ที่ครอบคลุม business logic และ API ให้ใช้ `autoflush=False` เช่น production ตรวจ failure ที่เกิดขึ้นแล้วแยก fixture setup ที่ต้อง flush อย่างชัดเจนจาก production bug
6. ถ้า UI ต้องแสดงเพดาน ให้ใช้ค่าจาก config API ที่ frontend อ่านได้ แทนตัวเลข 20 ที่เขียนตายตัว โดยเปิดเผยเฉพาะค่าที่จำเป็น ไม่ส่ง settings ทั้งชุด
7. เตรียมตรวจข้อมูลที่อาจมี baseline เกินเพดานจาก bug เดิมแบบอ่านอย่างเดียว แล้วสรุป target และ snapshot ที่จะถูก demote ให้ตรวจสอบก่อน repair

### 6.3 การจัดการข้อมูลเดิม

- ห้าม demote หรือ delete ข้อมูลจริงระหว่างการจัดทำหรือทดสอบแผน
- ขั้น repair ในอนาคตให้ใช้กติกาเดียวกับ detector: เก็บ N รายการใหม่สุดและ demote เฉพาะส่วนเกิน
- เก็บรายการ ID และ flag ก่อนแก้เพื่อย้อนกลับได้ ห้ามเปลี่ยนสถานะ target เป็น OK เป็นผลข้างเคียงของ repair
- หากข้อมูลไม่สอดคล้อง เช่น snapshot ขาด artifacts ให้แยกรายการตรวจสอบ ไม่ลบหรืออนุมัติใหม่อัตโนมัติ

### 6.4 กรณีทดสอบและเกณฑ์รับงาน

- เพดาน 3 มี active 3 ก่อนอนุมัติใบใหม่: หลัง commit ต้องเหลือ 3 และ demote ใบเก่าสุด
- เพดาน 1: baseline เดิมถูก demote และ candidate ที่ใหม่กว่าคง active
- ต่ำกว่าเพดาน: baseline เดิมและ candidate คง active ทั้งหมด
- Approve ซ้ำ: จำนวนไม่เพิ่มและไม่ demote ใบอื่นโดยไม่จำเป็น
- Candidate เก่าเกินเพดาน: ปฏิเสธอย่างชัดเจนและ rollback โดยสถานะ/acknowledgment ไม่เปลี่ยน
- วันที่ capture เท่ากัน: tie-break ด้วย ID ทำให้ผลแน่นอน
- ค่าเพดาน 0 หรือติดลบ: configuration validation ต้องปฏิเสธ
- API และ service tests ผ่านด้วย autoflush=False และตรวจข้อมูลจาก session ใหม่หลัง commit
- จำนวนที่ UI แสดง รายการ active และชุดที่ detector โหลดต้องตรงกัน

## 7. CR-04 — ป้องกันการเปลี่ยน URL ระหว่างงานตรวจ

### 7.1 ตำแหน่งและสาเหตุ

- `backend/app/api/routes/targets.py`: `update_target()` บริเวณบรรทัด 71–80
- `backend/app/services/concurrency.py`: `is_target_in_flight()` และ worker
- `backend/app/services/checks.py`: `run_target_check()`
- `frontend/src/components/EditTargetModal.tsx`
- `frontend/src/pages/TargetListPage.tsx` และ `TargetDetailPage.tsx`

PATCH URL ไม่มี guard ขณะ Checking งาน capture เริ่มด้วย URL เก่า แต่เมื่อเสร็จยังบันทึกผลให้ target ID เดิมที่ URL เปลี่ยนแล้ว

หลักฐานที่จำลองได้: target URL ใหม่แสดง OK แต่ baseline.final_url เป็น URL เก่า

### 7.2 แนวทางแก้ในสถาปัตยกรรมปัจจุบัน

1. ตรวจว่าค่า URL ที่ส่งมาต่างจากค่าปัจจุบันจริงหรือไม่ การส่งค่าเดิมซ้ำจาก modal ไม่ควรถูกนับเป็น URL change
2. ถ้า URL เปลี่ยนและ target เป็น Checking หรืออยู่ใน in-flight set รวมงานที่รอ semaphore ให้ปฏิเสธด้วย HTTP 409 พร้อมข้อความที่ frontend แสดงได้
3. ตรวจ guard และ commit โดยไม่เปิดช่องให้ worker เริ่มตรวจคั่นระหว่างขั้นตอนนั้น ภายใต้ single event loop/worker ปัจจุบัน หาก refactor เพิ่ม await ต้องทบทวน synchronization ใหม่
4. อนุญาตแก้ name ระหว่างตรวจได้ เพราะไม่เปลี่ยน input ของ detector
5. ใน modal ให้ปิดการแก้ URL เมื่อรู้ว่า target กำลังตรวจ พร้อมข้อความเหตุผล แต่ต้องคง backend guard เป็นตัวบังคับจริง เพราะ UI อาจมีข้อมูลเก่า
6. เมื่อได้ 409 ให้คงค่าที่ผู้ใช้พิมพ์ไว้ แสดง error และ refresh สถานะ target ไม่ปิด modal ราวกับบันทึกสำเร็จ
7. ทบทวนงาน queued: domain key ที่โหลดก่อนเข้าคิวต้องไม่ผิดจาก URL ที่ใช้ capture เมื่อเริ่มงาน หลังเพิ่ม guard แล้วเขียน test ยืนยันกรณีนี้

### 7.3 ขอบเขตของการเปลี่ยน URL ขณะ idle

การแก้ไข race นี้ไม่กำหนดให้ล้าง baseline หรือประวัติเมื่อเปลี่ยน URL ขณะ idle และไม่อนุญาตรับ URL ใหม่เป็น baseline อัตโนมัติ ให้รักษาพฤติกรรมการเก็บประวัติเดิม พร้อมข้อความว่าการเปลี่ยน URL ยังใช้ baseline ที่อนุมัติไว้ หากต้องการ workflow ย้ายเว็บไซต์และ baseline ใหม่ ให้แยกเป็นงานออกแบบเพิ่มเติม

### 7.4 กรณีทดสอบและเกณฑ์รับงาน

- ใช้ async events หยุด mock capture หลังเริ่มงาน แล้วส่ง PATCH เปลี่ยน URL: ต้องได้ 409 และ URL ไม่เปลี่ยน
- ปล่อยงานจบแล้วอ่านข้อมูลใหม่: target URL และ baseline ต้องตรงกับ URL ที่ capture
- งานรอ semaphore แต่ status ยังไม่เป็น Checking: เปลี่ยน URL ต้องถูกปฏิเสธด้วย in-flight guard
- เปลี่ยน name ระหว่างตรวจ: สำเร็จโดยไม่เปลี่ยน URL
- ส่ง URL ค่าเดิมพร้อม name ใหม่: สำเร็จ
- เปลี่ยน URL ตอน idle: ผ่าน SSRF validation เดิมและบันทึกได้
- คำขอที่เริ่มก่อน worker และ commit สำเร็จ: worker ต้อง capture URL ใหม่ ไม่ใช้ URL เก่าที่ cache ไว้
- Guard ต้องไม่กระทบ soft delete/inactive semantics เดิมโดยไม่ได้ตั้งใจ
- ยืนยันผลด้วย API tests ที่ใช้สอง sessions และการประสานเวลาด้วย events แทน sleep ที่ไม่แน่นอน

## 8. CR-05 — ทำให้หน้ารายละเอียดติดตามผล scheduler ได้

### 8.1 ตำแหน่งและสาเหตุ

- `frontend/src/hooks/useTargetDetail.ts`: `useTargetQuery()` และ queries ของ checks/snapshots/baselines
- `frontend/src/pages/TargetDetailPage.tsx`: effect ที่ refresh หลัง Checking เปลี่ยนเป็นสถานะอื่น
- `frontend/src/pages/TargetDetailPage.test.tsx`: tests ปัจจุบัน mock hooks จึงไม่ครอบคลุม polling จริง

เมื่อข้อมูลใน cache เป็น OK ค่า `refetchInterval` เป็น false หน้าเว็บจึงไม่เห็น scheduler เริ่มงานใหม่ นอกจากนี้การตรวจอาจเริ่มและจบระหว่างสอง polls ทำให้ UI ไม่เคยเห็น Checking และผลตรวจใหม่อาจมี status เดิม เช่น Changed → Changed

### 8.2 ขั้นตอนดำเนินการ

1. กำหนด polling ของ target metadata ขณะที่หน้ารายละเอียดเปิดอยู่ทุกสถานะ โดยใช้ช่วงเริ่มต้นประมาณ 4 วินาทีให้สอดคล้องหน้า list และลดเป็นประมาณ 3 วินาทีขณะ Checking ได้
2. ติดตามรายการ checks แบบ lightweight เป็นระยะด้วย เพื่อให้เห็น check ID ใหม่แม้ status ไม่เปลี่ยน ไม่ผูกการ refresh ทั้งหมดกับการผ่านสถานะ Checking เท่านั้น
3. ใช้ signature ของ latest check เช่น ID และ acknowledgment รวมกับข้อมูล target เช่น status/updated_at/last_error เพื่อตรวจความเปลี่ยนแปลงที่มีนัยสำคัญ
4. เมื่อ signature เปลี่ยน ให้ invalidate snapshots, baseline และ baselines ที่เกี่ยวข้อง รวมถึง check detail cache ถ้าการเปลี่ยน review action ทำให้ข้อมูลนั้นเก่า
5. รองรับ first capture ที่สร้าง baseline โดยไม่มี CheckResult: target จาก Never Checked เป็น OK ต้อง refresh baseline และ snapshots
6. Poll เฉพาะ metadata ไม่โหลด screenshot/text ซ้ำทุกช่วงเวลา; artifact queries ใช้ snapshot ID เป็น cache key ต่อไป
7. หยุด polling เมื่อ component unmount หรือ target ID ไม่พร้อม และใช้พฤติกรรม background/focus ของ query library อย่างชัดเจน
8. ตรวจ error states ให้สื่อว่าข้อมูลล่าสุดโหลดไม่ได้ ไม่แสดงค่าที่โหลดล้มเหลวว่าเป็นผลตรวจใหม่ที่สำเร็จ
9. ระวัง loop จาก effect invalidation: เก็บ signature ที่ประมวลผลแล้ว ไม่ invalidate ทุกครั้งเพียงเพราะ object reference ใหม่

### 8.3 กรณีทดสอบและเกณฑ์รับงาน

- เปิดหน้าตอน OK แล้ว mock scheduler เปลี่ยนเป็น Checking → Changed: badge และข้อมูลล่าสุดต้องอัปเดตโดยไม่ reload
- เปลี่ยน OK → Changed ระหว่าง polls โดยไม่เคยส่ง Checking ให้ UI: ต้องแสดง latest check และ snapshot ใหม่
- ผลสองรอบเป็น Changed เหมือนกัน แต่ check ID เปลี่ยน: ต้อง refresh ผลล่าสุด
- First capture: ไม่มี check record แต่ baseline ใหม่ต้องแสดงได้
- Capture ล้มเหลวโดยไม่มี check ใหม่: status และ error ต้องอัปเดต
- อนุมัติ/demote baseline: gallery และ baseline display ต้อง refresh ถูกชุด
- Metadata ไม่เปลี่ยน: ไม่สร้าง artifact requests ซ้ำอย่างไม่จำเป็น
- ออกจากหน้า: หยุด timer/requests และไม่มี update หลัง unmount
- ใช้ tests ที่มี QueryClient จริงและ mock API พร้อม fake timers เพื่อทดสอบ hook behavior; ไม่ใช้เฉพาะ mocked hooks แบบหน้าเดิม
- ใน foreground หน้าเว็บต้องสะท้อนการเปลี่ยนแปลงภายในรอบ polling ที่เกี่ยวข้อง บวกเวลาตอบสนอง API ไม่กำหนด SLA เดียวกันให้ background tab ที่ browser throttle

## 9. CR-06 — เพิ่ม pagination และจำนวน target ที่ถูกต้อง

### 9.1 ตำแหน่งและสาเหตุ

- `backend/app/api/routes/targets.py`: `list_targets()` default limit=50
- `backend/app/schemas/target.py` และ schema exports
- `frontend/src/api/targets.ts`: `listTargets()` ไม่รับ offset/limit
- `frontend/src/hooks/useTargets.ts`: query key และ polling
- `frontend/src/pages/TargetListPage.tsx`: แสดง targets.length เป็นจำนวนรวม
- API/page tests ที่เกี่ยวข้อง

### 9.2 API contract ที่เสนอ

เพิ่ม endpoint สำหรับ paginated response โดยคง `GET /targets` ที่ตอบ array เพื่อไม่ทำให้ consumer เดิมเสีย เช่น `GET /targets/page?limit=50&offset=0&include_inactive=false`

Response ที่เสนอ:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

- `total` นับจาก filter เดียวกับ items ก่อนใช้ limit/offset
- ใช้ validation limit ระหว่าง 1–200 และ offset อย่างน้อย 0 เช่น API เดิม
- ใช้ลำดับ `created_at DESC, id DESC` ให้ deterministic เมื่อเวลาเท่ากัน
- static route `/targets/page` ต้องประกาศก่อน dynamic route `/targets/{target_id}` และมี regression test ยืนยัน routing
- Endpoint ใหม่ต้องอยู่ภายใต้ authentication เดียวกับ target routes
- เป็น pagination แบบ offset: การเพิ่ม/ลบข้อมูลระหว่างการเปิดแต่ละหน้าอาจเลื่อนตำแหน่งได้ จึงไม่อ้างว่าเป็น snapshot consistency ข้ามหลาย requests

### 9.3 ขั้นตอนดำเนินการ

1. เพิ่ม response schema และ endpoint โดยใช้ filter เดียวกันในการ query items และ count ภายใน request เดียว
2. เพิ่ม type และ API function สำหรับ paginated targets; คง API function เดิมถ้ายังมี consumers
3. เพิ่ม page/offset state ในหน้า list และใส่ `limit`, `offset`, `includeInactive` ใน query key เพื่อไม่ใช้ข้อมูลผิดหน้า
4. เพิ่มปุ่มก่อนหน้า/ถัดไปและข้อความช่วงรายการ เช่น “51–100 จาก 126 รายการ” แทนการใช้ items.length เป็น total
5. ถ้าใช้ข้อมูลหน้าก่อนระหว่างโหลดหน้าใหม่ ต้องแสดง loading/placeholder state ให้ชัด และไม่แสดงว่าข้อมูลเก่าเป็นหน้าที่โหลดสำเร็จแล้ว
6. รักษา polling เฉพาะหน้าปัจจุบัน ไม่ดึงทุก target ทุก 4 วินาที
7. หลังสร้าง target ให้กลับหน้าแรกและ refresh เพื่อเห็นรายการใหม่; หลังแก้ไขให้คงหน้าปัจจุบันและ refresh; หลังลบรายการสุดท้ายของหน้าท้ายสุดให้เลื่อนกลับหน้าที่มีข้อมูล
8. ปรับ cache invalidation ของ create/update/delete/check mutations ให้ครอบคลุม query prefix ของ paginated list
9. แยกข้อความไม่มี target ทั้งระบบออกจากกรณีหน้าปัจจุบันว่างเพราะข้อมูลถูกลบหรือ offset เกินช่วง
10. จำนวนที่หัวตารางต้องใช้ total ส่วน items.length ใช้เฉพาะจำนวนรายการในหน้านั้น

### 9.4 กรณีทดสอบและเกณฑ์รับงาน

| จำนวน target | ผลที่คาดหวังเมื่อ page size=50 |
| --- | --- |
| 0 | Empty state และ total=0 ไม่มี next |
| 1 | แสดงหนึ่งรายการและ total=1 |
| 50 | หน้าเดียวเต็ม ไม่มี next |
| 51 | หน้าแรก 50 หน้า 2 หนึ่งรายการ total=51 |
| 126 | เข้าถึงครบ 3 หน้า: 50/50/26 |

- ทดสอบเวลาสร้างเท่ากันหลายรายการเพื่อยืนยันลำดับ tie-break
- กรณีข้อมูลไม่เปลี่ยนระหว่าง requests: เดินทุกหน้าต้องไม่ซ้ำและไม่ตกหล่น
- ทดสอบ include_inactive ให้ total และ items ใช้ filter ตรงกัน
- ทดสอบ limit/offset ไม่ถูกต้องและ authentication ของ endpoint ใหม่
- ลบรายการสุดท้ายของหน้าท้ายสุด: UI กลับหน้าที่ถูกต้อง ไม่ค้าง empty state ที่ทำให้เข้าใจว่าไม่มี targets
- เพิ่มรายการจากหน้าที่ไม่ใช่หน้าแรก: เห็นรายการใหม่หลังกลับหน้าแรก
- Polling ไม่ reset page และไม่ทำให้รายการจากคนละหน้าปะปนใน cache
- `GET /targets` และ `GET /targets/{target_id}` เดิมยังทำงานตาม contract เดิม

## 10. ลำดับดำเนินการและจุดตรวจ

| ช่วง | งาน | สิ่งที่ต้องได้ก่อนผ่านช่วง |
| --- | --- | --- |
| A | ยืนยัน source ปัจจุบันและเตรียม test environment แยก | ระบุ baseline ของ tests, runtime และ configuration ที่ใช้ |
| B | CR-01 | launch configuration tests และ smoke test ใน deployment environment ผ่าน |
| C | CR-03 แล้ว CR-02 | approval/pruning ถูกต้องด้วย autoflush=False และไม่กลบผลล่าสุด |
| D | CR-04 | API race tests ทั้ง Checking และ queued ผ่าน |
| E | CR-05 | หน้ารายละเอียดตามผล scheduler ได้แม้ไม่เห็น Checking |
| F | CR-06 | เข้าถึง targets เกิน 50 และนับ total ถูกต้อง |
| G | Regression รวมและตรวจเอกสาร | ไม่มี regression ใน auth, capture, scheduler, review และหน้าเว็บ |
| H | เตรียม rollout และประเมินข้อมูลเดิม | มีรายงานความผิดปกติเดิมและขั้น repair ที่ตรวจสอบได้ |

CR-03 ทำก่อน CR-02 ภายในชุดงาน approval เพราะต้องใช้ transaction และ fixtures เดียวกัน แต่ทั้งสองควรส่งมอบร่วมกันโดยไม่เลื่อน CR-02 ออกนอก remediation รอบนี้

## 11. แผนทดสอบรวม

### 11.1 Environment

- Backend ใช้ฐานข้อมูลทดสอบแยกหรือ SQLite in-memory พร้อม autoflush=False และกำหนดค่า environment ไม่ให้อ่านฐานข้อมูลจริง
- Artifact tests เขียนเฉพาะ temporary directory ของ test runner
- ไม่เปิด app lifespan กับ SessionLocal จริงใน test โดยไม่ override เพราะ startup มี recovery/reconciliation และเริ่ม scheduler
- Browser smoke tests ใช้หน้า fixture ที่ควบคุมได้ ไม่ใช้เว็บไซต์ภายนอกเป็น assertion ที่เปลี่ยนแปลงได้
- Frontend ใช้ QueryClient ใหม่ต่อ test และ cleanup timers/cache ทุกครั้ง

### 11.2 คำสั่งตัวอย่างสำหรับรอบ implementation

คำสั่งต่อไปนี้เป็นคำสั่งที่จะใช้หลังได้รับงานแก้ไขจริง ไม่ได้รันในขั้นจัดทำแผน บางคำสั่งสร้าง cache/build artifacts จึงต้องรันใน test workspace ที่เตรียมไว้

จากโฟลเดอร์ backend:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capture.py tests/test_review.py tests/test_api_routes.py tests/test_checks.py tests/test_concurrency.py tests/test_scheduler.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

จากโฟลเดอร์ frontend:

```powershell
npm run test
npm run lint
npm run typecheck
npm run build
```

หากเครื่องไม่มี tooling ที่กำหนด ให้ตรวจ dev dependencies และจัดเตรียม environment ก่อน ไม่ตีความว่า command ที่รันไม่ได้เท่ากับตรวจผ่าน

### 11.3 Acceptance scenario แบบ end-to-end

1. เตรียม target จำนวน 51 รายการในฐานข้อมูลทดสอบ และยืนยันว่าเข้าถึงรายการที่ 51 ได้จาก dashboard
2. เปิดหน้ารายละเอียด target ที่มี baseline และสถานะ OK ค้างไว้
3. ให้ scheduler ตรวจ fixture ที่เปลี่ยนเนื้อหา แล้วตรวจว่า UI แสดง Changed และผลล่าสุดโดยไม่ reload
4. อนุมัติ snapshot เก่าที่ไม่ใช่ latest current snapshot: target ต้องยัง Changed
5. อนุมัติ latest current snapshot: target เป็น OK และจำนวน baseline ไม่เกินเพดาน
6. เริ่มตรวจใหม่และหยุด mock capture ชั่วคราว จากนั้นแก้ URL ผ่าน API: ต้องได้ 409
7. ปล่อยงานจบและตรวจว่า snapshot สัมพันธ์กับ URL ที่เริ่ม capture
8. จำลอง availability failure แล้วอนุมัติ baseline เก่า: target ต้องยังแสดง availability error
9. ตรวจหลักฐาน sandbox launch ใน runtime ที่ใช้ทดสอบ โดยแยกผล mock และผล browser จริงในรายงาน

## 12. การนำขึ้นใช้งาน ข้อมูลเดิม และการย้อนกลับ

### 12.1 ก่อน rollout

- เก็บผล tests และรายการไฟล์ที่เปลี่ยนแยกตาม CR ID
- แผนหลักไม่จำเป็นต้องเปลี่ยน database schema; paginated response เป็น API schema หาก implementation พบว่าต้องเพิ่ม DB schema ให้จัดทำ migration plan แยกก่อนดำเนินการ
- สำรองฐานข้อมูลด้วยวิธีที่สอดคล้องกับ SQLite WAL เช่น backup API หรือหยุด service อย่างถูกต้อง ไม่คัดลอกเพียง app.db ขณะที่มี WAL writes แล้วถือว่าเป็น backup ครบ
- สำรอง artifacts ที่สัมพันธ์กับฐานข้อมูล และทดสอบว่า backup ใช้ได้ใน environment แยก
- ตรวจ sandbox support และ permissions ของ runtime ก่อนสลับใช้งาน

### 12.2 ประเมินผลจาก bug เดิม

- CR-03: ตรวจจำนวน active baselines ต่อ target และจัดทำรายการ demote ส่วนเกินแบบ dry run
- CR-02: สามารถหากรณี target=OK แต่ latest check=Changed และยังไม่ acknowledged เพื่อให้ operator ตรวจสอบ แต่ห้ามเปลี่ยนสถานะอัตโนมัติจากเงื่อนไขนี้เพียงอย่างเดียว เพราะต้องดูประวัติและการอนุมัติร่วมด้วย
- CR-04: final_url ต่างจาก target.url ไม่ใช่หลักฐาน race เสมอไป เพราะอาจเป็น redirect ปกติ ต้องตรวจลำดับเหตุการณ์หรือให้ operator review ก่อนตัดสินว่าผลผิด
- ไม่ลบ baseline เดิมหรือรับหน้าเว็บใหม่เป็น baseline อัตโนมัติเพื่อซ่อมข้อมูลที่น่าสงสัย
- การซ่อมข้อมูลจริงเป็นขั้นตอนแยกจากการ deploy code และต้องมีรายการเปลี่ยนแปลงที่ตรวจสอบได้

### 12.3 หลัง rollout

- ยืนยันว่ารัน single worker และมี scheduler เพียงชุดเดียวตามข้อจำกัดเดิม
- ตรวจ capture success/failure, sandbox errors, baseline counts และ API 409 ว่าเป็นไปตามกรณีที่ออกแบบ
- เปิดหน้ารายละเอียดค้างไว้จนผ่านรอบตรวจที่ควบคุมได้เพื่อยืนยัน UI refresh
- ตรวจ pagination และ total ด้วยข้อมูลที่มีจริงโดยไม่เพิ่ม target ทดสอบลง production โดยไม่จำเป็น

### 12.4 Rollback

- ย้อนกลับ code/config เป็นชุด version ที่เข้ากันได้ พร้อมบันทึกว่าข้อผิดพลาดใดจะกลับมา
- ห้ามปิด sandbox อัตโนมัติเป็นส่วนหนึ่งของ rollback; หาก browser ใช้งานไม่ได้ให้หยุดส่วน capture ที่ล้มเหลวและแก้ runtime ตามข้อมูล error
- หากมี baseline repair ให้ใช้รายการ ID/flag ที่สำรองไว้คืนค่า ไม่คืนฐานข้อมูลทั้งชุดทับผลตรวจใหม่ที่เกิดหลัง rollout โดยไม่ประเมินข้อมูลที่จะสูญเสีย
- คง snapshots และ CheckResult เพื่อให้ตรวจสอบเหตุการณ์ย้อนหลังได้

## 13. Definition of Done

- [ ] CR-01 ผ่าน launch-option regression และ browser smoke test ใน environment เป้าหมาย
- [ ] CR-02 การอนุมัติ snapshot เก่าไม่ล้างสถานะ/error ของเหตุการณ์ล่าสุด
- [ ] CR-03 จำนวน active baseline ไม่เกินเพดานด้วย autoflush=False และชุด UI ตรงกับชุด detector
- [ ] CR-04 ไม่สามารถเปลี่ยน URL ขณะ Checking หรือ queued/in-flight ได้
- [ ] CR-05 หน้า detail แสดงผลใหม่ได้แม้ไม่เคยเห็น Checking และไม่ poll artifacts โดยไม่จำเป็น
- [ ] CR-06 แสดง targets เกิน 50 รายการผ่าน pagination และ total ถูกต้อง
- [ ] Regression ของ auth/CSRF/SSRF, scheduler, capture, review และ soft delete ยังผ่าน
- [ ] Backend tests/static checks และ frontend tests/lint/typecheck/build มีผลตรวจบันทึกไว้
- [ ] แยก pre-existing failures ออกจาก regression ที่เกิดจากการแก้ไข พร้อมหลักฐาน ไม่อ้างว่าทั้งชุดผ่านหากยังมี failures
- [ ] เอกสารคอนฟิกและพฤติกรรมผู้ใช้ตรงกับ implementation หลังแก้ไข
- [ ] ข้อมูลเดิมที่อาจได้รับผลกระทบมีรายงานตรวจสอบ และไม่มีการ repair โดยเงียบ ๆ
- [ ] รายงานส่งมอบระบุไฟล์ที่เปลี่ยน ผลทดสอบ ข้อจำกัด runtime และงานค้างตามข้อเท็จจริง

## 14. สถานะงาน ณ วันที่จัดทำ

| รายการ | สถานะ |
| --- | --- |
| Review และสรุปข้อค้นพบ | เสร็จแล้ว |
| จำลอง CR-02/CR-03/CR-04 ในหน่วยความจำ | ยืนยันปัญหาได้แล้ว |
| จัดทำแผน remediation | เอกสารฉบับนี้ |
| แก้ไข source code/tests/configuration | ยังไม่ได้ดำเนินการ |
| รัน regression suite และ browser acceptance tests | ยังไม่ได้ดำเนินการ |
| ตรวจและ repair ข้อมูลจริง | ยังไม่ได้ดำเนินการ |
| Deploy | ยังไม่ได้ดำเนินการ |
