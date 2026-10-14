# Audit รอบ 2 — 14 ตุลาคม 2026

ตรวจไฟล์ปัจจุบันต่อจาก `Review By GPT 6.1 Sol 14-10-2026.md` โดยตรวจ backend, frontend, capture/review workflow, authorization และ deployment configuration ไม่มี Git metadata จึงไม่ใช่การ review diff ระหว่าง commits ไม่ได้แก้ application code ในรอบนี้ เพิ่มเพียงรายงานและสคริปต์พิสูจน์ findings แบบ offline

## Findings ใหม่

ทั้งสามรายการเป็น **P2**: ช่องว่างการตรวจพฤติกรรมที่ไม่เปลี่ยนภาพหรือข้อความ ไม่ใช่การยืนยันว่าระบบ monitoring ถูกเจาะหรือ SSRF ถูก bypass

### R2-01 — ไม่ตรวจปลายทาง HTTPS ใน `formaction`

ตำแหน่ง: `backend/app/services/diff/structure.py:114` และ `:141–146`

`formaction` อยู่ใน executable URL attributes แต่ถูกเก็บเฉพาะเมื่อขึ้นต้นด้วย `javascript:` ขณะที่ปลายทาง HTTP/HTTPS ถูกเก็บเฉพาะ `form.action` จึงเพิ่มหรือแก้ `button/input.formaction` ให้ส่งฟอร์มไปอีก host ได้โดย facts ไม่เปลี่ยน

พิสูจน์ด้วย `<form action="https://example.com/save"><button>Save</button></form>` แล้วเพิ่ม `formaction="https://collector.example/save"` ที่ปุ่ม: Chromium อ่าน effective submission destination เปลี่ยนจาก example.com เป็น collector.example แต่ text/PNG เหมือนกันและ structure score = 0.0 สคริปต์ไม่ได้ส่งฟอร์มหรือเชื่อมต่อปลายทาง

ผลกระทบ: การเปลี่ยนปลายทางส่งข้อมูลอาจไม่ถูกแจ้งเตือนเมื่อ detectors อื่นไม่เปลี่ยน

เสนอแก้: เก็บ facts ของ `formaction` สำหรับ button/input รวม relative URLs และ base URL พร้อม tests addition/modification/removal และ policy สำหรับ allowed domains

### R2-02 — JavaScript URL ที่มี tab แทรกไม่ถูกตรวจ

ตำแหน่ง: `backend/app/services/diff/structure.py:114–120`

การตรวจ `value.lstrip().lower().startswith('javascript:')` ไม่ normalize tab/newline ภายใน scheme ตามพฤติกรรม browser เช่น `href="java&#9;script:void(window.auditProbe=1)"` ผ่าน HTML entity decoding แล้วมี tab คั่นใน scheme จึงไม่ถูกเก็บเป็น JavaScript fact และไม่เกิด link-host fact

พิสูจน์ด้วย Chromium: ก่อนเปลี่ยน link ใช้ `href="#"`; หลังเปลี่ยนและคลิก link ค่า `window.auditProbe` เปลี่ยนจากไม่มีค่าเป็น 1 โดย text/PNG เหมือนเดิมและ structure score = 0.0

ผลกระทบ: JavaScript ที่เพิ่มใน link แบบนี้อาจไม่ถูกแจ้งเตือน แม้ RV-02 เดิมเพิ่มการตรวจ JavaScript URL แล้ว

เสนอแก้: normalize ASCII tab, LF และ CR ตาม browser URL handling ก่อนจำแนก scheme พร้อม tests literal control characters, entities และ mixed casing โดยไม่ใช้ domain allowlist ละเลย executable URLs

### R2-03 — เปลี่ยนชนิด script จาก inert เป็น executable แล้ว facts เหมือนเดิม

ตำแหน่ง: `backend/app/services/diff/structure.py:124–132` และ `:252–254`

Parser เก็บ inline script body hash แต่ไม่เก็บ `type` หรือ executable/inert classification การเปลี่ยน `<script type="text/plain">window.auditProbe = 1</script>` เป็น `type="text/javascript"` โดย body เดิมจึงได้ hash เดิม

พิสูจน์ด้วย Chromium: baseline ไม่รัน body; current รันจน `window.auditProbe = 1` โดย text/PNG เหมือนกันและ structure score = 0.0

ผลกระทบ: การเปิดใช้โค้ดที่อยู่ใน inert script เดิมอาจไม่ถูกแจ้งเตือน เช่นเดียวกัน external script facts ไม่บันทึก type จึงควรตรวจเส้นทางนั้นควบคู่กัน

เสนอแก้: เก็บ executable classification/type ที่ normalize แล้วทั้ง inline และ external scripts พร้อม tests inert→classic/module และ reverse transition ต้องไม่ละเลย inert content โดยไม่ตรวจการเปลี่ยน classification

## วิธีพิสูจน์ซ้ำ

จากโฟลเดอร์ backend บน PowerShell:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/audit_round2_probe.py
```

สคริปต์สร้างหน้าใน Chromium ด้วย `set_content` ไม่มี navigation ไปเว็บภายนอก ใช้เพียง harmless variable assignment และตรวจ DOM, visible text และ screenshot bytes ของ baseline/current ที่ browser serializes จริง ผลทั้งสามรายการ: `structure_score=0.0`, `same_text=true`, `same_png=true` แต่ `before_behavior` และ `after_behavior` ต่างกัน

เมื่อใช้ artifacts ที่ text/pixels/facts เหมือนกันนี้กับ comparison pipeline คะแนนทั้งสามเป็นศูนย์; `run_target_check` มีเส้นทางรายงาน OK และ discard current artifacts สำหรับผล unchanged ไม่ได้รัน full API exploit สำหรับแต่ละกรณี

## Verification ล่าสุด

| Check | ผล |
| --- | --- |
| Backend pytest ทั้ง suite ใน project .venv, `--basetemp=.audit-r2-full -q` | **218 passed**, 113 warnings, 125.96 วินาที |
| Frontend Vitest | **76 passed**, 12 files |
| Backend Ruff: `app tests scripts alembic` | ผ่าน; สคริปต์ probe ที่เพิ่มตรวจ Ruff แยกแล้วผ่าน |
| Backend mypy: `app` | ผ่าน 55 source files |
| Frontend ESLint | ผ่าน |
| Frontend production build รวม TypeScript | ผ่าน |
| Offline Chromium probes | ยืนยันทั้ง 3 findings |

ผลของ suite เดิมที่ผ่านไม่ได้ครอบคลุมสามกรณีใหม่ Frontend ยังมี React `act(...)` warnings; backend มี dependency/model datetime deprecation warnings เก็บ log ที่ `backend/audit-r2-pytest.log`, `frontend/audit-r2-vitest.log`, `frontend/audit-r2-build.log`

การรันครั้งแรกใน sandbox ติด Windows temp-directory permissions และ `spawn EPERM` จากนั้นรัน suite/build ใหม่โดยได้รับอนุญาตจาก execution approval reviewer และผ่าน ใช้ผลรอบใหม่ข้างต้นเป็นหลัก

## สถานะรายการเดิม

RV-01: code รอ baseline approval ทุก revision; scheduler ข้าม pending candidates และมี UI สำหรับ approval แล้ว

RV-02: code ตรวจ event handlers และ JavaScript URL ปกติแล้ว แต่ยังมี R2-01/R2-02/R2-03 ต้องเพิ่ม coverage

RV-03: code ตรวจ navigation errors หลัง readiness และก่อนคืน artifacts พร้อม generation/final URL consistency checks; tests late-navigation ผ่าน

RV-04: origin validation เปรียบเทียบ effective port และรองรับ parsed host; Nginx ใช้ `$http_host` และ backend จำกัด trusted proxy แล้ว ยังต้องยืนยัน live Linux deployment

RV-05/RV-06/RV-07: serializer ถูกใช้อย่างสม่ำเสมอ และ suites/static checks ปัจจุบันผ่าน

RV-08: README ใช้ short basetemp และเลิกอ้างจำนวน tests เดิมแล้ว; verification Windows รอบนี้ผ่าน แต่ Linux production verification ยังไม่ได้รัน

## ข้อจำกัด

ยังไม่ได้ทดสอบ deployment จริงบน Linux, certificate/proxy behavior ใน production หรือ dependency advisory audit ภายนอก การตรวจรอบนี้ยืนยันเฉพาะ source และการทดสอบ local ที่ระบุ ไม่ใช่การรับรองความปลอดภัยทั้งหมด การแก้ findings ใหม่ยังไม่ได้ทำ
