# แผนแก้ไขเพิ่มเติมจากการ Review CR10

วันที่: 17 กันยายน 2026  
สถานะ: เสนอแผน — ยังไม่ได้ดำเนินการแก้ไขโค้ด

อ้างอิง: [แผน CR10](Code-Review-and-Remediation-Plan-CR10-17-9-2026.md), [แผนหลัก](PROJECT_PLAN.md) และเอกสาร [Phase 1](../refinement/17-9-2026/Code-Review-Remediation-CR10-Phase1-17-9-2026.md), [Phase 2](../refinement/17-9-2026/Code-Review-Remediation-CR10-Phase2-17-9-2026.md), [Phase 3](../refinement/17-9-2026/Code-Review-Remediation-CR10-Phase3-17-9-2026.md)

## ขอบเขตและข้อจำกัด

- เอกสารนี้บันทึกรายการแก้ไขจากการ review เท่านั้น การสร้างเอกสารไม่ได้รวมการดำเนินการแก้ไขโค้ด
- รักษาฐานข้อมูลจริง ประวัติการตรวจ baseline และ monitoring targets เดิมทั้งหมด ห้าม reset หรือลบข้อมูลเพื่อให้เทสต์ผ่าน
- รักษา single API worker, authentication, CSRF, SSRF protections และ detector thresholds เดิม
- การทดสอบต้องใช้ฐานข้อมูลและ artifacts แยกจากข้อมูลจริง และไม่ติดต่อ monitoring targets จริง
- การ review ตรวจโค้ดปัจจุบันเทียบเอกสาร ไม่สามารถยืนยัน diff ก่อน–หลังได้เนื่องจาก Git metadata ไม่สมบูรณ์ ไม่พบ `walkthrough.md` และไม่ได้รันชุดเทสต์เต็ม

## 1. [P1] แก้การบันทึกผล Changed เมื่อเปิด Foreign Key

ไฟล์เกี่ยวข้อง: `backend/app/services/checks.py`, `backend/app/models/snapshot.py`, `backend/app/models/check_result.py`

**ข้อพบ:** เส้นทางตรวจพบความเปลี่ยนแปลงเพิ่ม Snapshot และ CheckResult ใน transaction เดียวกัน โดยไม่มี ORM relationship ที่กำหนดลำดับ insert การจำลองด้วยโมเดลจริงบน SQLite in-memory ที่เปิด foreign key พบ `FOREIGN KEY constraint failed` จากการ insert CheckResult ก่อน snapshot ที่อ้างถึง

**งานที่ต้องทำ**

- flush Snapshot ก่อนเพิ่ม CheckResult ที่อ้างถึง หรือกำหนด ORM relationship ให้จัดลำดับ insert ถูกต้อง โดยรักษาความเป็น transaction เดียวกัน
- rollback transaction ก่อนจัดการข้อผิดพลาดจาก flush/commit เพื่อไม่ใช้งาน session ที่อยู่ในสถานะ failed transaction
- ตรวจเส้นทาง artifacts ที่ promote แล้วแต่ transaction ล้มเหลว และกำหนด cleanup ให้ไม่ทิ้งไฟล์ที่ไม่มี record อ้างอิง โดยไม่กระทบ artifacts ที่บันทึกสำเร็จ

**เกณฑ์ตรวจรับ**

- เมื่อมี baseline แล้วและตรวจพบการเปลี่ยนแปลง สามารถบันทึก Snapshot และ CheckResult พร้อมสถานะ Changed ได้ครบเมื่อเปิด foreign key
- ไม่มี IntegrityError หรือ PendingRollbackError ในเส้นทางสำเร็จ
- เมื่อจำลอง commit failure ระบบ rollback และจัดการสถานะ/ไฟล์ได้โดยไม่ทำลายข้อมูลเดิม

## 2. [P1] ปรับเทสต์ให้ใช้ Foreign Key เหมือนระบบจริง

ไฟล์เกี่ยวข้อง: `backend/tests/conftest.py`, `backend/tests/test_checks.py` และ fixtures ที่สร้าง SQLite engine แยก

**ข้อพบ:** engine ในเทสต์หลักไม่ได้เปิด foreign key ขณะที่ engine ของแอปเปิดแล้ว การตรวจค่า PRAGMA ของ app engine เพียงอย่างเดียวไม่ครอบคลุมพฤติกรรมการบันทึกข้อมูลใน fixtures

**งานที่ต้องทำ**

- เปิด `PRAGMA foreign_keys=ON` ทุก connection ของ test engines ที่ใช้ตรวจพฤติกรรมฐานข้อมูล
- เพิ่ม regression test สำหรับ baseline → ตรวจพบการเปลี่ยนแปลง → บันทึก Changed
- เพิ่มเทสต์การอ้างถึง target/snapshot ที่ไม่มีอยู่ และการลบ record ที่ยังมี foreign key อ้างถึงตามข้อกำหนด CR10-06
- ให้เทสต์ตรวจ PRAGMA ใช้ฐานข้อมูลแยก ไม่เชื่อมต่อฐานข้อมูลจริงผ่าน app engine

**เกณฑ์ตรวจรับ**

- regression test สามารถจับปัญหาข้อ 1 ก่อนแก้ และผ่านหลังแก้
- การอ้างอิง record ที่ไม่มีอยู่ถูกปฏิเสธด้วย IntegrityError
- ชุดเทสต์ฐานข้อมูลผ่านโดยเปิด foreign key และไม่อ่านเขียนฐานข้อมูลจริง

## 3. [P2] ครอบคลุม cleanup ตลอดช่วง capture

ไฟล์เกี่ยวข้อง: `backend/app/services/capture/capture.py`, `backend/app/services/checks.py`, เทสต์ capture/checks/concurrency

**ข้อพบ:** cleanup finally ใน run_target_check เริ่มหลัง capture คืนค่า หาก cancellation เกิดหลังเขียน staging แต่ระหว่าง await browser.close() จะยังไม่มี CaptureResult ส่งกลับให้ caller cleanup เทสต์ที่เพิ่มใน Phase 2 จำลองการยกเลิกหลัง capture คืนค่าแล้วเท่านั้น

**งานที่ต้องทำ**

- ให้ผู้สร้าง staging รับผิดชอบ cleanup เมื่อ capture ล้มเหลวหรือถูก cancel ก่อนส่งผลลัพธ์กลับ
- ครอบคลุม timeout/cancellation ระหว่างปิด browser และออกจาก async context managers
- รักษาการส่งต่อ CancelledError และการปล่อย in-flight reservation
- เพิ่มเทสต์ยกเลิกงานหลังเขียน artifacts แต่ก่อน capture คืนค่า รวมถึงเทสต์หลัง capture คืนค่า

**เกณฑ์ตรวจรับ**

- ไม่เหลือ staging ของงานที่ถูกยกเลิกทันทีหลัง coroutine จบ โดยไม่ต้องรอ periodic cleanup
- reservation ถูกปล่อยและงานถัดไปไม่ถูกกีดกันด้วย reservation ค้าง
- การ capture/promote สำเร็จยังเก็บ artifacts ที่ต้องใช้ได้ครบ

## 4. [P3] จัด configuration สำหรับ production ตามแผน

ไฟล์เกี่ยวข้อง: `docker-compose.yml`, production frontend build/server configuration, development compose configuration, `README.md`

**ข้อพบ:** compose ปัจจุบันยังรัน frontend ด้วย npm run dev และ backend ด้วย --reload --reload-dir app ซึ่งเป็นทางเลือก development ไม่ใช่ configuration สำหรับ production/Stage 2 ที่แผน CR10 ระบุ

**งานที่ต้องทำ**

- จัด frontend build stage และเสิร์ฟ dist ผ่าน production static server พร้อม caching headers ที่เหมาะสม
- ถอด --reload จาก backend สำหรับ production/Stage 2 และคง --workers 1
- แยก development configuration และอธิบายวิธีเลือกใช้งานใน README
- ตรวจ API routing, frontend routes และ runtime configuration ในรูปแบบ deployment ที่เลือก

**เกณฑ์ตรวจรับ**

- frontend deployment เสิร์ฟ precompiled/minified assets แทน Vite development server
- ตรวจ caching headers, เปิดหน้าโดยตรง และการเรียก API ได้ตามปกติ
- backend ไม่ restart จากการเขียน capture artifacts และใช้ single worker
- production build ผ่าน พร้อมคำแนะนำ deployment ที่ตรงกับ configuration จริง

## 5. [P2] แก้เอกสาร Phase 3 ให้ตรงกับแผน

ไฟล์เกี่ยวข้อง: เอกสาร refinement Phase 3, `UPDATE_SUMMARY.md`, `README.md`

**งานที่ต้องทำ**

- แก้การจับคู่หมายเลขให้ตรงกับแผนเดิม:

| หมายเลข | งานตามแผน CR10 |
|---|---|
| CR10-08 | Alembic migration alignment |
| CR10-09 | Triage guards และ error banner |
| CR10-10 | ปุ่ม Run Check ใน Target Detail |
| CR10-12 | Production frontend deployment |

- บันทึก query cache invalidation เป็นงานประกอบ ไม่ใช้แทนรายการที่กำหนดในแผน
- แก้ชื่อ migration ที่อ้างผิดเป็น `d2b3c4e5f6a7_structural_detector.py` และไม่อ้างว่า migration นี้เพิ่ม status index
- บันทึกขั้นตอนตรวจ schema และ stamping ใน UPDATE_SUMMARY โดยการแก้เอกสารไม่ต้อง stamp ฐานข้อมูลจริงซ้ำ
- ปรับข้อความ “100% completed” ให้ตรงกับรายการที่ทำและตรวจรับจริง แยกสิ่งที่ยังไม่ทำหรือยังไม่ได้ยืนยัน

**เกณฑ์ตรวจรับ**

- ทั้ง 12 รายการในแผนมีสถานะและหลักฐานตรงกับงานจริง ไม่มีรายการหายจากการเปลี่ยนหมายเลข
- ชื่อไฟล์ migration และคำอธิบายตรงกับ source ที่มีอยู่
- ไม่ใช้ผล build หรือผลเทสต์เดิมแทนหลักฐานตรวจรับหลังแก้ไข

## 6. การตรวจรับรวมหลังแก้ไข

1. แก้ข้อ 1 พร้อม regression tests ในข้อ 2 ก่อนรับรองเส้นทางตรวจจับ Changed
2. ตรวจ cancellation/timeout และ cleanup ตามข้อ 3 ด้วย mocks และ artifacts แยก
3. รัน backend tests, frontend tests, type checking, lint และ production build ที่เกี่ยวข้อง
4. ตรวจ production configuration ตามข้อ 4 ในสภาพแวดล้อมแยกจากระบบจริง
5. อัปเดตเอกสารตามข้อ 5 พร้อมผลจริง ข้อจำกัด และรายการที่ยังค้าง

ผลตรวจรับต้องระบุคำสั่ง สภาพแวดล้อม และผลลัพธ์ โดยไม่เปิดเผย secrets และต้องรักษาฐานข้อมูลจริง ประวัติ และ baseline เดิมทั้งหมด
