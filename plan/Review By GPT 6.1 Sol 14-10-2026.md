# Review By GPT 6.1 Sol 14-10-2026

วันที่ตรวจ: 14 ตุลาคม 2026 (Asia/Bangkok)  
โปรเจกต์: Web Defacement Monitoring System  
สถานะ: รายการเสนอแก้ไขจาก audit — ยังไม่ได้แก้ source code

## 1. ขอบเขตและข้อจำกัด

ตรวจโค้ด backend, เส้นทาง capture/baseline/review, authentication และ authorization, frontend ที่เกี่ยวข้อง และ configuration สำหรับ deployment พร้อมรันชุดทดสอบและ static checks บน Windows จากไฟล์ปัจจุบัน โฟลเดอร์นี้ไม่มี Git metadata จึงไม่ได้เปรียบเทียบกับ commit หรือ branch ใด

ยังไม่ได้ทดสอบ deployment บน Linux production จริง และไม่ได้ตรวจ vulnerability ของ dependencies กับฐานข้อมูล advisory ภายนอก ผลนี้จึงไม่ใช่การรับรองความปลอดภัยทั้งหมดของระบบ

เอกสารนี้เป็นรายการงานจาก review ให้ใช้ร่วมกับ `PROJECT_PLAN.md` และ `MEMBER_MANAGEMENT_PLAN.md` ไม่ได้เปลี่ยนสถานะ roadmap หรือประกาศว่าการแก้ไขเสร็จแล้ว

## 2. รายการที่ต้องแก้ไข

P1 = ควรแก้ก่อนเชื่อถือผล monitoring ใน production; P2 = ควรแก้ในรอบถัดไปเพื่อเพิ่มความถูกต้องและความมั่นใจ; P3 = ความสม่ำเสมอและคุณภาพของโค้ด/เอกสาร

| ID | ระดับ | งาน | สถานะ |
| --- | --- | --- | --- |
| RV-01 | P1 | เปลี่ยน baseline แรกให้รอ operator อนุมัติ | ยังไม่แก้ |
| RV-02 | P2 | เพิ่มการตรวจ event handler และ JavaScript URL ใน structural detector | ยังไม่แก้ |
| RV-03 | P2 | ตรวจ navigation errors ซ้ำหลังรอหน้าและก่อนส่งคืน capture | ยังไม่แก้ |
| RV-04 | P2 | เปรียบเทียบ origin ให้ครบ scheme, hostname และ port | ยังไม่แก้ |
| RV-05 | P3 | ทำ Target response ให้สม่ำเสมอทุก endpoint | ยังไม่แก้ |
| RV-06 | P2 | แก้ frontend test setup ให้รองรับ authentication context | ยังไม่แก้ |
| RV-07 | P3 | แก้ Ruff findings ใน environment ของโปรเจกต์ | ยังไม่แก้ |
| RV-08 | P3 | ปรับ test temporary path บน Windows และข้อมูล verification ใน README | ยังไม่แก้ |

### RV-01 — Baseline แรกถูกเชื่อถืออัตโนมัติ

**หลักฐาน:** `backend/app/services/checks.py:257` กำหนด `is_baseline=target.url_revision == 1` และบรรทัด 261 กำหนดสถานะ `OK` สำหรับ revision แรก

**ผลกระทบ:** หากเว็บไซต์ถูก deface ก่อนเพิ่ม target ระบบจะเก็บเนื้อหานั้นเป็น baseline และรายงาน `OK` โดยไม่มีการอนุมัติ เป็นความเสี่ยงเชิงออกแบบของการเริ่ม monitoring แม้พฤติกรรมนี้ถูกเขียนไว้โดยตั้งใจ

**สิ่งที่ต้องแก้:**

- [ ] เก็บ capture แรกเป็น candidate (`is_baseline=False`) และกำหนดสถานะ `Awaiting Baseline`
- [ ] ปรับ approval ให้รองรับ revision แรกที่ยังไม่มี baseline แล้วเปลี่ยนเป็น `OK` หลังอนุมัติสำเร็จ
- [ ] ปรับ scheduler ให้ใช้เงื่อนไขรอ candidate review กับทุก revision ไม่เฉพาะ `url_revision > 1`
- [ ] ตรวจ UI ให้แสดง candidate และ action อนุมัติได้เมื่อยังไม่มี baseline/check result
- [ ] รักษา candidate ไว้จน review และกำหนดพฤติกรรม manual recapture ให้ชัดเจน

**เกณฑ์ตรวจรับ:** Target ใหม่ที่ capture สำเร็จต้องไม่ขึ้น `OK` ก่อนอนุมัติ; scheduler ไม่สร้าง candidate ซ้ำทุก interval ระหว่างรอ review; หลังอนุมัติ การตรวจครั้งถัดไปเปรียบเทียบกับ baseline ได้; workflow หลังเปลี่ยน URL และสิทธิ์ Operator ที่ได้รับ assignment ยังทำงานถูกต้อง

### RV-02 — Structural detector ไม่ตรวจ event handler

**หลักฐาน:** `backend/app/services/diff/structure.py:104` เลือกเก็บ facts ของ elements บางประเภท แต่ไม่เก็บ event attributes ของ elements ทั่วไป การทดลองเพิ่ม `onclick="console.log(1)"` ในปุ่มที่มีข้อความเดิมให้ structural score เท่ากับ `0.0`

**ผลกระทบ:** โค้ดที่รันเมื่อผู้ใช้โต้ตอบกับหน้าอาจถูกเพิ่มโดยไม่เปลี่ยนภาพหรือข้อความ ทำให้ detectors ทั้งสามไม่รายงานการเปลี่ยนแปลงในกรณีนี้

**สิ่งที่ต้องแก้:**

- [ ] เก็บ facts สำหรับ event-handler attributes เช่น `onclick`, `onerror`, `onload` โดย hash เนื้อหาแทนการใส่โค้ดเต็มใน summary
- [ ] ตรวจ JavaScript URL ใน attributes ที่เกี่ยวข้อง เช่น `href="javascript:..."` และกำหนด normalization ให้ชัดเจน
- [ ] เพิ่มกรณีทดสอบ addition, modification และ removal ของ event handler โดย text/pixel ไม่เปลี่ยน
- [ ] ตรวจผลกระทบต่อ false positives และข้อมูลที่แสดงใน summary ก่อนเปิดใช้

**เกณฑ์ตรวจรับ:** เพิ่มหรือแก้ executable attribute แล้ว structure score ต้องมากกว่า `0`; ค่าเดิมต้องไม่สร้าง false change; allowlist ของ external domains ต้องไม่ทำให้ event handler ถูกละเลยโดยอัตโนมัติ

### RV-03 — Capture คืนผลสำเร็จหลัง late navigation ถูกบล็อก

**หลักฐาน:** `backend/app/services/capture/capture.py:388` ตรวจ guard errors หลัง `page.goto` แต่หลัง `wait_page_ready` ที่บรรทัด 407 ไม่มีการตรวจซ้ำ การทดลองแบบ mocked navigation ระหว่าง readiness ยืนยันว่า `route.abort()` ถูกเรียกหนึ่งครั้ง แต่ capture ยังคืน HTTP status `200`

**ผลกระทบ:** Navigation ที่ถูกบล็อกหรือผิดพลาดหลังการโหลดแรกอาจถูกกลบด้วย artifacts/status ของหน้าเดิม ทำให้ผล check สื่อว่าจับหน้าได้สำเร็จ การทดลองนี้ยืนยันข้อผิดพลาดในการส่งต่อ error ไม่ได้ยืนยันการ bypass SSRF ที่ socket

**สิ่งที่ต้องแก้:**

- [ ] รวมการตรวจ `blocked_error`, `availability_error` และ `capture_error` เป็น helper ที่ใช้ได้หลายจุด
- [ ] ตรวจ error หลัง readiness และก่อนส่งคืนผล capture
- [ ] ทำให้ final URL, HTTP status และ artifacts อ้างถึง navigation เดียวกัน หากมี navigation ระหว่างจับ artifacts ให้ retry หรือ reject อย่างชัดเจน
- [ ] เพิ่ม regression tests สำหรับ late main-frame navigation ที่เกิด SSRF block, DNS failure และ upstream failure
- [ ] ยืนยันว่า capture ที่ถูก reject ไม่เหลือ staging artifacts

**เกณฑ์ตรวจรับ:** Late main-frame navigation ที่ถูกบล็อกต้องไม่คืนผลสำเร็จจากหน้าเดิม; errors ถูกจัดประเภทถูกต้อง; การบล็อก subresource/popup ไม่เปลี่ยนความหมายเป็น main-document failure โดยไม่ตั้งใจ

### RV-04 — Origin validation ไม่เปรียบเทียบ port

**หลักฐาน:** `backend/app/main.py:135` ตัด port ออกจาก Host และเปรียบเทียบเพียง hostname/scheme การเรียก `_is_trusted_origin` ด้วย origin `https://monitor.example:9999` และ Host `monitor.example:3030` โดยไม่มี origin ใน allowlist คืน `True`

**ผลกระทบ:** Origin บน hostname เดียวกันแต่คนละ port ถูกจัดเป็น trusted เกินขอบเขต same-origin ที่ควรเป็น ยังไม่ได้ยืนยันการโจมตีผ่าน CORS preflight หรือ synchronizer CSRF token จึงไม่ควรตีความว่าเป็นการ bypass mutation authorization ทั้งระบบ

**สิ่งที่ต้องแก้:**

- [ ] เปรียบเทียบ scheme, hostname และ effective port ครบ โดย normalize default HTTP/HTTPS ports
- [ ] รองรับ IPv6 host โดยไม่ใช้ `split(':')[0]`
- [ ] รักษา external host/port ที่ถูกต้องจาก reverse proxy; ปัจจุบัน Nginx ส่ง `$host` ซึ่งไม่มี public port จึงต้องปรับ proxy headers ควบคู่กับ validation
- [ ] ใช้ forwarding headers เฉพาะภายใต้ proxy trust policy และรักษาการ overwrite headers จาก client
- [ ] เพิ่ม tests สำหรับ port ต่างกัน, default port, explicit allowlist, IPv6 และ production reverse proxy

**เกณฑ์ตรวจรับ:** Origin คนละ port ถูกปฏิเสธถ้าไม่ได้อยู่ใน allowlist; origin ที่ operator ใช้จริงผ่าน; CSRF token enforcement และ production login/logout ยังทำงาน

### RV-05 — Target response ไม่สม่ำเสมอ

**หลักฐาน:** `backend/app/api/routes/targets.py:242` คืน ORM Target โดยตรงจาก PATCH ขณะที่ GET ใช้ `_target_read` ที่บรรทัด 293 ผล test `test_target_patch_rejects_null_required_fields_and_allows_omission` พบว่า GET คืน `assignees: []` แต่ PATCH body ว่างคืน `assignees: null`

**ผลกระทบ:** Response contract แตกต่างตาม endpoint และอาจทำให้ frontend สูญเสียข้อมูล assignees เมื่อใช้ mutation response อัปเดต cache

**สิ่งที่ต้องแก้:**

- [ ] ใช้ serializer ของ Target ที่สม่ำเสมอใน create/update/delete และ read endpoints ตามสิทธิ์ผู้ใช้
- [ ] ตรวจ return type/response model ให้ตรงกับผล serialization
- [ ] เพิ่ม assertion สำหรับ target ที่มี assignment จริง และป้องกันการเปิดเผย assignees ให้ role ที่ไม่ควรเห็น

**เกณฑ์ตรวจรับ:** PATCH body ว่างให้ข้อมูลเท่ากับ GET สำหรับผู้ใช้เดียวกัน; mutation response ไม่ล้าง assignees โดยไม่ตั้งใจ; backend test ที่ล้มผ่าน

### RV-06 — Frontend test setup ขาด authentication context

**หลักฐาน:** Frontend tests ผ่าน 47 และไม่ผ่าน 25 จากทั้งหมด 72 tests ใน 11 files; 3 files ล้ม ได้แก่ `TargetListPage.test.tsx`, `TargetDetailPage.test.tsx` และ `TargetDetailPage.cache.test.tsx` หลายรายการแจ้ง `useAuth must be used within an AuthProvider` ตัวอย่าง setup อยู่ที่ `frontend/src/pages/TargetDetailPage.test.tsx:190`

**ผลกระทบ:** Tests ไม่ได้เข้าถึง assertions ของ page behavior จึงยังใช้ยืนยัน workflow/cache หลังเพิ่ม member management ไม่ได้ การล้มนี้ไม่ได้พิสูจน์ว่าหน้า production ขาด AuthProvider เพราะ app มี provider อยู่แล้ว

**สิ่งที่ต้องแก้:**

- [ ] สร้าง test render helper ที่ให้ authentication context และ QueryClient/Router ตามที่ component ต้องใช้
- [ ] ใช้ role fixtures ของ Admin และ Operator ที่ตรงกับสถานการณ์ทดสอบ
- [ ] ปรับ mocks/expectations ที่ไม่ตรงกับ hooks และ UI ปัจจุบันหลังแก้ context
- [ ] ตรวจการล้าง cache เมื่อ logout/เปลี่ยนผู้ใช้ และการเปลี่ยนสิทธิ์/assignment

**เกณฑ์ตรวจรับ:** Frontend suite ผ่านทั้งหมด; tests ตรวจพฤติกรรมจริงของแต่ละ role; ไม่มี unhandled context errors หรือการข้าม tests เพื่อทำให้ผลผ่าน

### RV-07 — Ruff findings

**หลักฐาน:** Ruff ใน virtual environment ของโปรเจกต์พบ 5 errors จากการตรวจ `app tests scripts alembic`:

| ไฟล์ | สิ่งที่ต้องแก้ |
| --- | --- |
| `backend/alembic/env.py` | I001: import order |
| `backend/alembic/versions/a5b6c7d8e9f0_tags.py` | I001: import order |
| `backend/alembic/versions/b7c8d9e0f1a2_nested_tags.py` | I001: import order |
| `backend/app/models/__init__.py` | I001: import order และ E501: line length |

**สิ่งที่ต้องแก้:**

- [ ] จัด imports และแบ่ง `__all__` ตาม configuration โดยไม่เปลี่ยน migration semantics
- [ ] รัน Ruff ด้วย environment/version เดียวกันใน local และ CI

**เกณฑ์ตรวจรับ:** Ruff ผ่าน; mypy ใน environment ของโปรเจกต์ยังผ่าน; model registration และ migration imports ยังทำงาน

### RV-08 — Windows test paths และ README verification

**หลักฐาน:** Backend รอบเต็มได้ 199 passed / 8 failed จาก 207 tests; 7 capture failures เกิดขณะเขียน artifact ใน temporary paths ยาวบน Windows เมื่อรันเฉพาะ 7 รายการด้วย `--basetemp=.audit-t` ทั้งหมดผ่าน เหลือ failure ของ response contract ใน RV-05 ส่วน README ยังระบุจำนวน backend/frontend tests เป็น 123/61

**สิ่งที่ต้องแก้:**

- [ ] กำหนด temporary path สั้นสำหรับ Windows verification หรือปรับ fixture ให้ลดความยาว path
- [ ] แยก environment failures ออกจาก application failures ในผลทดสอบ
- [ ] ปรับ README ให้ใช้คำสั่งจาก environment ของโปรเจกต์ และแก้/นำจำนวน tests ที่ล้าสมัยออก
- [ ] รัน verification บน Linux ตาม deployment target และบันทึกผลใหม่เมื่อ remediation เสร็จ

**เกณฑ์ตรวจรับ:** Tests ไม่ล้มเพราะ temporary path; เอกสารระบุคำสั่งและผลตรวจตามจริง โดยไม่ประกาศว่า Linux production ผ่านจากผล Windows

## 3. ผล verification ณ วันที่ review

| รายการ | ผลที่ยืนยันได้ |
| --- | --- |
| Backend pytest รอบเต็ม | 199 passed / 8 failed / 207 tests |
| Retry เฉพาะ capture failures ด้วย short path | 7 passed / 11 deselected |
| Backend failure ที่เหลือ | Target GET/PATCH response: `assignees []` กับ `null` |
| Frontend Vitest | 47 passed / 25 failed / 72 tests; 8 files passed / 3 failed |
| Backend mypy ใน `.venv` | ผ่าน 55 source files |
| Backend Ruff ใน `.venv` | 5 errors |
| Frontend ESLint | ผ่าน |
| Frontend production build | ผ่าน |
| Linux deployment verification | ยังไม่ได้รัน |

ผล backend ข้างต้นเป็นรอบเต็มหนึ่งรอบและการ retry เฉพาะรายการ ไม่ใช่ผลรอบเต็มใหม่ที่ผ่าน 206 tests ระบบ Python นอก `.venv` มี dependency ไม่ครบ และ mypy ให้ผลต่างกัน จึงใช้ผลของ environment โปรเจกต์เป็นหลัก

## 4. ลำดับดำเนินการและการตรวจรับรวม

1. RV-01: ทำ baseline approval ให้ครอบคลุมการเริ่ม monitoring
2. RV-02 และ RV-03: ปิดช่องว่างของ detector และความถูกต้องของ capture
3. RV-04: แก้ origin validation พร้อม configuration ของ reverse proxy
4. RV-05 และ RV-06: แก้ API contract และทำ functional tests ให้กลับมาครอบคลุม workflows
5. RV-07 และ RV-08: ทำ static checks และ verification workflow ให้สม่ำเสมอ

- [ ] เพิ่ม regression tests สำหรับ RV-01 ถึง RV-05 ตามเกณฑ์ของแต่ละรายการ
- [ ] รัน backend suite รอบเต็มใน environment ของโปรเจกต์
- [ ] รัน frontend suite, lint, type-check/production build และ backend Ruff/mypy
- [ ] ตรวจ Linux deployment: HTTPS login, baseline approval, scheduled capture, error classification และสิทธิ์ Admin/Operator
- [ ] บันทึกผลจริงและข้อจำกัดที่เหลือก่อนปรับ roadmap ว่างานเสร็จ

## 5. สิ่งที่มีอยู่แล้วและต้องรักษาไว้

จากโค้ดที่ตรวจพบการป้องกัน session/CSRF, authorization ของ Admin–Operator, SSRF proxy ที่ตรวจ connection-time IP และ artifact path containment การ remediation ต้องรักษาพฤติกรรมเหล่านี้ รวมถึงการเก็บ raw screenshot เพื่อใช้เป็นหลักฐาน และการไม่ซ่อน overlay ระหว่าง capture
