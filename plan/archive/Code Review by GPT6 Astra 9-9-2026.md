# Code Review by GPT6 Astra 9-9-2026

วันที่: 9 กันยายน 2026  
โครงการ: Website Defacement Monitoring System  
สถานะ ณ 10 กันยายน 2026: **แก้โค้ด CR09-01 ถึง CR09-07 ครบตามขอบเขตระบบและผ่านการตรวจบน Windows แล้ว** การตรวจ isolated Linux runtime และ effective Chromium sandbox ยังเปิดอยู่เพราะ Docker daemon ไม่ทำงานในเครื่องตรวจ

แผนดำเนินการต่อ: [Code Review Completion Plan — CR09 — 10-9-2026](Code-Review-Completion-Plan-CR09-10-9-2026.md)  
ผลดำเนินการล่าสุด: [Code Review Completion CR09 — 10-9-2026](../refinement/10-9-2026/Code-Review-Completion-CR09-10-9-2026.md)  
บันทึกการแก้ไขรอบก่อน: [`refinement/10-9-2026/Code-Review-Remediation-CR09-01-to-CR09-07-10-9-2026.md`](../refinement/10-9-2026/Code-Review-Remediation-CR09-01-to-CR09-07-10-9-2026.md) เป็นประวัติการ implementation รอบแรกและถูกแทนสถานะล่าสุดด้วยบันทึกด้านบน

## 1. วัตถุประสงค์และขอบเขต

แผนนี้รวบรวมข้อค้นพบ 7 ข้อจากการตรวจ backend, frontend และ Docker configuration พร้อมแนวทางแก้ไข กรณีทดสอบ และเกณฑ์รับงาน โดยรวมคำชี้แจงของผู้ใช้ว่าการเปิด Chromium sandbox เคยทำให้ระบบบน Linux มีปัญหา

ผู้ใช้อนุมัติให้ดำเนินการตามแผนแล้วในวันที่ 10 กันยายน 2026 งานรอบนี้แก้ source code และชุดทดสอบ พร้อมตรวจบน Windows โดยไม่เปลี่ยน production configuration, deployment, database, snapshot history, baseline หรือ thresholds

เอกสารนี้เป็นแผนประกอบ [PROJECT_PLAN.md](PROJECT_PLAN.md) ไม่เปลี่ยนสถานะ Stage 2 ไม่รีเซ็ต soak test และไม่แทนที่ master plan ส่วนข้อค้นพบที่ใช้รหัส CR09 ด้านล่างเป็นคนละชุดกับ CR-01 ถึง CR-06 ของวันที่ 8 กันยายน

## 2. หลักฐานและข้อจำกัดของการรีวิว

รายการในหัวข้อนี้เป็นหลักฐานของการรีวิววันที่ 9 กันยายน ก่อน remediation ส่วนสถานะโค้ดและผลตรวจซ้ำวันที่ 10 กันยายนอยู่ในแผนดำเนินการต่อที่ลิงก์ด้านบน

- ตรวจ source code และชุดทดสอบที่มีอยู่ รวมถึงบันทึก remediation วันที่ 8 กันยายน
- ยืนยันด้วย mock ว่าเมื่อตั้ง `BROWSER_DISABLE_SANDBOX=False` แล้ว launch เกิด error `Target closed` โค้ดลองเปิด browser ด้วยค่า sandbox `True → False`
- จำลองด้วยฐานข้อมูล SQLite ในหน่วยความจำและควบคุมจังหวะ diff: demote baseline ระหว่างตรวจสำเร็จ แต่ผลตรวจยังเป็น `OK` และอ้าง baseline ที่ถูก demote
- จำลองกรณีไม่มี HTML สำหรับ structural comparison: score เป็น `0.0` และ summary ระบุว่าไม่พบการเปลี่ยนแปลงทั้งสาม detector
- จำลอง DNS resolution failure: ได้ `SsrfBlockedError` และ `is_availability_error()` คืน `False`
- ข้อ SSRF อ้างอิงตำแหน่ง routing ในโค้ดและข้อจำกัดที่ระบุในเอกสาร Playwright รวมถึงเอกสารของ package ที่ติดตั้ง ยังไม่ได้ทดสอบส่ง request ไปยังเครือข่ายภายในจริง
- TypeScript ผ่านทั้ง `tsconfig.app.json` และ `tsconfig.node.json`; ESLint ไม่มี error มี 1 warning ใน `useAuth.tsx`
- Ruff พบ `I001` เรื่อง import ordering ใน `backend/scripts/create_user.py` จำนวน 1 จุด ยังไม่ได้แก้ไข
- Pytest รันทั้งชุดไม่สำเร็จ เนื่องจากสิทธิ์เข้าถึง temporary directory บน Windows ไม่ใช่หลักฐานว่า application tests ไม่ผ่าน
- Vitest เริ่มทำงานไม่ได้ เนื่องจากขาด native dependency `@rolldown/binding-win32-x64-msvc` ยังไม่ได้ติดตั้งหรือเปลี่ยน lockfile
- ยังไม่ได้ตรวจ runtime, logs หรือ isolation ของเครื่อง Linux ปัจจุบันโดยตรง ข้อมูลเหตุขัดข้องบน Linux มาจากบันทึกโครงการ

## 3. สรุปข้อค้นพบ

P1: ควรจัดการก่อนขยายการใช้งาน เนื่องจากกระทบความปลอดภัยของ capture หรือความน่าเชื่อถือของผล `OK`  
P2: ควรแก้ในรอบ remediation เพื่อให้สถานะ ข้อมูล และการใช้งานถูกต้อง

| ID | ระดับ | ข้อค้นพบ | ผลลัพธ์ที่ต้องได้ |
| --- | --- | --- | --- |
| CR09-01 | P1 | SSRF guard ไม่ครอบคลุม redirect และ popup | ปลายทางที่ถูกห้ามต้องไม่ได้รับ request รวมถึงเส้นทาง redirect และ popup |
| CR09-02 | P1 | Sandbox fallback ฝืน configuration | การเปิดหรือปิด sandbox ต้องตรงกับค่าที่กำหนด และ Linux ต้องผ่านการตรวจ runtime ก่อนเปลี่ยนโหมด |
| CR09-03 | P1 | Structural comparison ใช้งานไม่ได้แต่ให้คะแนนเหมือนไม่เปลี่ยนแปลง | การตรวจไม่ครบต้องไม่ถูกแปลเป็นผล `OK` |
| CR09-04 | P2 | Demote baseline ระหว่าง check ได้ | ชุด baseline ต้องคงที่ตลอดงานตรวจ |
| CR09-05 | P2 | Target Detail แสดงคู่ภาพไม่ตรงกับ latest check | ภาพ ข้อความ และคะแนนต้องอ้างผลตรวจเดียวกัน |
| CR09-06 | P2 | Logout ล้มเหลวแต่ UI แสดงว่าออกจากระบบแล้ว | UI ต้องแสดงผล logout ตามการยืนยันจาก server |
| CR09-07 | P2 | DNS failure ถูกจัดเป็น SSRF violation | DNS failure ระหว่าง capture เป็น `Availability Issue`; blocked address ยังคงเป็น security failure |

## 4. หลักการร่วม

1. คง single API worker ตามสถาปัตยกรรมปัจจุบัน ไม่เพิ่ม Redis หรือระบบ queue โดยไม่มีความจำเป็นในขอบเขตนี้
2. ไม่ลบฐานข้อมูล ประวัติผลตรวจ snapshots หรือ baselines เพื่อแก้ข้อผิดพลาด
3. ไม่รับ live page เป็น baseline ใหม่อัตโนมัติเพื่อชดเชย baseline ที่อ่านไม่ได้ และคงข้อห้าม demote baseline สุดท้าย
4. คง authentication, CSRF, service-worker blocking และ WebSocket blocking ระหว่าง remediation
5. ไม่เปลี่ยน detector thresholds เพียงเพื่อให้ tests ผ่านหรือปิดบังผลตรวจไม่ครบ
6. Regression tests ใช้ fixtures, mocks, ฐานข้อมูลทดสอบ และปลายทางทดสอบที่ควบคุมได้ ไม่ใช้ข้อมูล production
7. การแก้ให้ capture ทำงานได้และการยืนยัน isolation ต้องมีหลักฐานแยกกัน การ launch สำเร็จอย่างเดียวไม่ได้ยืนยัน sandbox
8. ไม่เปิด sandbox บน Linux ปัจจุบันทันทีโดยยังไม่ทดสอบ และไม่เพิ่ม automatic downgrade เมื่อผู้ดูแลตั้งค่าให้เปิด

## 5. CR09-01 — ปิดช่องว่าง SSRF ใน redirect และ popup

### ตำแหน่งและสาเหตุ

- `backend/app/services/capture/capture.py`: `guard_navigation()`, `route.continue_()`, `page.route()` และการตรวจ redirect count หลัง `page.goto()`
- `backend/app/core/ssrf_guard.py`: URL validation, DNS resolution และ IP policy
- `docker-compose.yml`: network isolation ของ capture runtime

`page.route()` ไม่ intercept คำขอแรกของ popup และ handler ถูกเรียกเฉพาะ URL แรกเมื่อ response เป็น redirect การตรวจ redirect count หลัง navigation เสร็จไม่ป้องกัน request ที่ส่งไปแล้ว นอกจากนี้การ pin IP ปัจจุบันครอบคลุมเฉพาะ hostname เริ่มต้น

### ขั้นตอนดำเนินการ

1. สร้าง regression fixtures สำหรับ redirect และ popup โดยมี request counter ที่ปลายทางต้องห้าม เพื่อยืนยันว่า request ไม่ได้ไปถึงปลายทางจริง
2. ย้ายการควบคุม HTTP requests ไปที่ browser context เพื่อครอบคลุมหน้าใหม่และ popup ตั้งแต่ request แรก และตรวจขอบเขต WebSocket blocking ให้ครอบคลุมหน้าใหม่ด้วย
3. ออกแบบการควบคุม redirect ก่อนเปิด connection ของแต่ละ hop ห้ามถือว่าการย้ายไป `context.route()` เพียงอย่างเดียวแก้ redirect ได้ครบ
4. ประเมินกลไก redirect mediation ที่ไม่ติดตาม redirect อัตโนมัติ หรือ egress proxy ที่ตรวจทุก connection โดยทดสอบผลต่อ cookies, resource loading, scripts และความเที่ยงตรงของภาพก่อนเลือกวิธี
5. ตรวจ scheme และ resolved IP ของทุกปลายทางที่เกี่ยวข้อง คุม DNS rebinding ที่จุด connection สำหรับ hostname อื่นด้วย ไม่อาศัย cache ว่า hostname เคยปลอดภัยอย่างเดียว
6. กำหนด egress policy ของ capture ให้ปฏิเสธ loopback/private/link-local และปลายทางต้องห้ามตาม policy จริงของระบบ ไม่อ้างว่าปิดช่อง SSRF ครบหากมีเพียง application checks ที่ยังข้ามได้
7. คง service-worker blocking และแยกจำนวน redirect ของ main frame ออกจาก navigation ของ iframe

### เกณฑ์รับงาน

- Direct request, HTTP redirect chain, popup และ subresource redirect ไปยังปลายทางต้องห้ามต้องถูกหยุดก่อนปลายทางรับ request
- Redirect limit ถูกบังคับก่อนตาม hop ที่เกินกำหนด
- Redirect ระหว่างปลายทางที่อนุญาตยังจับภาพได้ และ iframe ปกติไม่กิน main-frame redirect quota
- ทดสอบ DNS rebinding ด้วย resolver/proxy จำลองโดยไม่เข้าถึงบริการภายในจริง
- รายงานข้อจำกัดที่ยังเหลือของ protocol และ network paths อย่างชัดเจนก่อนปิดประเด็น

## 6. CR09-02 — กำหนด sandbox policy ให้ชัดเจนโดยรักษาการทำงานบน Linux

### บริบทที่ต้องรักษา

ตาม [บันทึก Docker remediation วันที่ 8 กันยายน](../refinement/8-9-2026/Docker-Deployment-Remediation-and-Stage2-Restart-8-9-2026.md) เคยเกิด `Chromium sandboxing failed!` บน Ubuntu/Docker และเพิ่ม fallback เพื่อให้ capture กลับมาทำงาน บันทึกระบุ root execution และข้อจำกัด seccomp/user namespaces เป็นสาเหตุ แต่ยังต้องตรวจ logs และ runtime ปัจจุบันเพื่อยืนยันรายละเอียด

Compose ใน workspace กำหนด `BROWSER_DISABLE_SANDBOX=true` โดยตรงใน `environment` ซึ่งมีลำดับสูงกว่าค่าจาก `env_file` จึงอาจปิด sandbox ตั้งแต่ launch แรกแม้ `backend/.env` กำหนด `false`

`seccomp:unconfined` เป็นการยกเลิก seccomp filtering ไม่ใช่การเปิด Chromium sandbox ส่วน `ipc: host` มีผลต่อ shared memory/IPC ไม่ใช่หลักฐานว่า sandbox เปิดแล้ว การใช้ configuration เหล่านี้ต้องอธิบายตามผลจริง

### ตำแหน่ง

- `backend/app/services/capture/capture.py`: exception handler ที่ retry ด้วย `chromium_sandbox=False`
- `backend/app/core/config.py`: `BROWSER_DISABLE_SANDBOX`
- `backend/.env.example`, `docker-compose.yml` และเอกสาร deployment
- `backend/tests/test_capture.py`: tests ของ launch configuration

### ขั้นตอนดำเนินการ

1. ตรวจแบบ read-only บน Linux: effective configuration โดยไม่เผย secrets, UID/GID ของ browser, image/package/browser versions, seccomp mode, user-namespace restrictions และ logs ของ launch failure
2. แยกสาเหตุ root execution, namespace/seccomp/AppArmor restriction, dependencies และ resource exhaustion ตามหลักฐาน ห้ามใช้คำว่า `closed` เพียงอย่างเดียวตัดสินว่าเป็น sandbox failure
3. กำหนดพฤติกรรมของแอปตามตารางด้านล่างและยกเลิกการ downgrade อัตโนมัติเมื่อ configuration ต้องการ sandbox
4. ทำให้แหล่ง configuration ชัดเจน เอกสารต้องระบุ Compose precedence และวิธีตรวจค่าที่ container ใช้จริง การแก้ `.env` อย่างเดียวอาจไม่เปลี่ยนค่าที่มี override
5. สำหรับ Linux ที่ยังรองรับ sandbox ไม่ได้ ให้คงการปิดแบบ explicit เป็นโหมดชั่วคราวที่ระบุข้อจำกัดจริง ประเมิน non-root, filesystem permissions, writable mounts และ egress isolation ของโหมดนี้ ห้ามระบุว่าเทียบเท่าการมี browser sandbox
6. เตรียม runtime สำหรับ sandbox แยกจากระบบที่กำลังใช้งาน: ผู้ใช้ที่ไม่ใช่ root, seccomp profile ที่รองรับ syscalls สำหรับ user namespaces และสิทธิ์ data directories ที่จำเป็น
7. เนื่องจาก Compose ปัจจุบันติดตั้ง dependencies ตอน startup ต้องเตรียม dependencies ใน image หรือขั้นตอนที่เหมาะสมก่อนเปลี่ยน runtime user ไม่เปลี่ยน `user` แล้วคาดว่า startup เดิมจะทำงานโดยอัตโนมัติ
8. ไม่ใช้ `SYS_ADMIN` หรือ `seccomp:unconfined` เป็นคำตอบถาวรโดยไม่มีการประเมินสิทธิ์ ทดสอบ runtime ที่จำกัดสิทธิ์และเปิด sandbox ได้จริงก่อนเสนอเปลี่ยน production
9. หลังผ่าน isolated smoke test จึงเสนอ deployment พร้อมผลทดสอบและ rollback ไปยัง configuration ที่บันทึกไว้ โดยไม่ลบข้อมูลหรือ reset baselines

| Configuration | พฤติกรรมเป้าหมาย |
| --- | --- |
| `BROWSER_DISABLE_SANDBOX=False` และ runtime รองรับ | เปิดด้วย `chromium_sandbox=True` |
| `BROWSER_DISABLE_SANDBOX=False` แต่ launch ล้มเหลว | รายงาน failure พร้อมสาเหตุ ไม่ลองใหม่แบบปิด sandbox |
| `BROWSER_DISABLE_SANDBOX=True` | เปิดแบบไม่มี sandbox ตามค่าที่กำหนด พร้อม warning ที่ชัดเจน |

### เกณฑ์รับงาน

- Mock tests ครอบคลุมทั้งสองค่า และ errors ที่มี `sandboxing`, `closed` และ error อื่น ไม่พบ retry แบบปิด sandbox เมื่อกำหนดให้เปิด
- ทดสอบ configuration precedence และบันทึก effective mode โดยไม่เปิดเผยค่าลับ
- Linux smoke test ยืนยันทั้ง launch/capture และหลักฐาน sandbox ของ runtime จริง ไม่อาศัย mock options อย่างเดียว
- ไม่เปลี่ยนโหมด Linux ที่กำลังใช้งานจนกว่าขั้นตอนตรวจสอบและ rollback จะพร้อม
- แยกสถานะงานเป็น “แก้ automatic fallback แล้ว” และ “Linux runtime รองรับ sandbox แล้ว” ห้ามปิดสองงานพร้อมกันจากหลักฐานเพียงอย่างเดียว

## 7. CR09-03 — แยก structural comparison ที่ตรวจไม่ได้ออกจากผลไม่มีการเปลี่ยนแปลง

### ตำแหน่งและสาเหตุ

- `backend/app/services/diff/diff.py`: `compare_html_files()` คืน score ศูนย์เมื่อ path หายหรืออ่านไม่ได้; `summarize_diff()` กลบข้อความ unavailable
- `backend/app/services/checks.py`: การจัดอันดับ baseline และการตัดสิน `OK`

baseline ที่ HTML ใช้งานไม่ได้อาจได้รับคะแนนดีกว่า baseline ที่ตรวจครบและพบ script injection ทำให้เลือก baseline ที่ตรวจไม่ครบเป็นผล `OK`

### ขั้นตอนดำเนินการ

1. กำหนด unavailable/error ให้แยกจาก numeric score ห้ามใช้ `0` แทนการตรวจไม่สำเร็จ
2. แนวทางเริ่มต้นให้ check จบเป็น `Failed` พร้อม `last_error` ที่ระบุ artifact/baseline ที่มีปัญหาเมื่อ structural comparison ของ candidate ที่ต้องตรวจไม่ครบ ไม่เพิ่ม target status ใหม่โดยไม่จำเป็น
3. ไม่ส่ง comparison ที่ไม่ครบเข้า `select_best_baseline()` ในรูป zero score และไม่สรุป `OK` จาก text/visual เพียงสอง detector
4. รักษาความแตกต่างระหว่าง content change กับ detector failure; ถ้าต้องการบันทึก partial findings เพิ่มในอนาคตต้องออกแบบ API/UI ให้ชัดเจนก่อน
5. ตรวจ legacy snapshots ที่ไม่มี HTML แล้วเสนอการกู้คืนจาก backup หรือ baseline ใหม่ที่ผู้ดูแลตรวจและอนุมัติ ห้าม auto-rebaseline
6. ตรวจ cleanup ของ staging และ transaction เมื่อ diff ล้มเหลว โดยไม่ลบ baseline หรือ history

### เกณฑ์รับงาน

- Missing path, missing file และ permission error ไม่ให้ผล `OK` หรือ summary ที่อ้างว่าตรวจโครงสร้างสำเร็จ
- Multi-baseline test ที่ baseline หนึ่งอ่านไม่ได้และอีก baseline ตรวจพบ injection ต้องไม่ให้ baseline ที่อ่านไม่ได้ชนะด้วย score ศูนย์
- รายงาน error ให้ผู้ดูแลแก้ artifact ได้ และตรวจซ้ำสำเร็จเมื่อ artifact กลับมาพร้อม
- กรณี HTML ครบและไม่มีการเปลี่ยนแปลงยังให้ `OK`; structural injection ยังให้ `Changed`

## 8. CR09-04 — ป้องกัน baseline mutation ระหว่างตรวจ

### ตำแหน่ง

- `backend/app/api/routes/targets.py`: `demote_target_baseline()`
- `backend/app/services/review.py`: `approve_baseline()`
- `backend/app/services/concurrency.py`: `is_target_in_flight()`
- Frontend baseline actions และ `BaselineManagerModal.tsx`

### ขั้นตอนดำเนินการ

1. ใช้ guard ร่วมสำหรับ baseline approval และ demotion โดยตรวจทั้ง `STATUS_CHECKING` และ process-local in-flight state รวมถึงงานที่รอ semaphore
2. ตอบ conflict ที่สื่อความหมาย เช่น HTTP 409 เมื่อ baseline mutation ชนงานตรวจ
3. คง last-baseline guard, target ownership validation และ retention cap เดิม
4. ให้ UI แสดงเหตุผลเมื่อแก้ baseline ไม่ได้และจัดการ conflict จาก server; UI disabling อย่างเดียวไม่ใช่ concurrency protection
5. หากมีการเพิ่ม await ระหว่าง guard กับ commit ในอนาคต ต้องใช้ lock/atomic coordination ที่ป้องกัน race ได้จริง คงขอบเขต single worker ของแผนนี้

### เกณฑ์รับงาน

- งานที่รอ semaphore หรือกำลัง diff ปฏิเสธทั้ง approve และ demote
- ทำ regression ตามลำดับที่จำลองได้ในการรีวิว: เริ่ม diff → ขอ demote → ตรวจ conflict → ปล่อย diff และตรวจ baseline references
- เมื่อ check จบแล้ว mutation ทำงานได้ตามปกติ รวมถึงเงื่อนไข baseline สุดท้าย

## 9. CR09-05 — ผูก Target Detail กับคู่ snapshot ของผลตรวจเดียวกัน

### ตำแหน่งและสาเหตุ

- `frontend/src/pages/TargetDetailPage.tsx`: ใช้ `snapshots[0]` และ standalone baseline endpoint แสดงภาพ/ข้อความ ขณะที่คะแนนมาจาก `checks[0]`
- `frontend/src/hooks/useTargetDetail.ts` และ `frontend/src/api/snapshots.ts`

Snapshot ล่าสุดที่จัดเก็บอาจเป็นภาพตอน `Changed` แม้ check ล่าสุดเป็น `OK` เพราะรอบ `OK` ทิ้ง capture และอ้าง baseline เดิม นอกจากนี้ standalone baseline อาจไม่ใช่ baseline ที่ check เลือกจากหลายชุด

### ขั้นตอนดำเนินการ

1. เมื่อมี latest check ให้ใช้ `baseline_snapshot_id` และ `current_snapshot_id` ของ check นั้นสำหรับทั้ง screenshot และ text comparison
2. ดึง snapshot metadata ตาม ID เมื่อจำเป็น ไม่พึ่งว่ารายการ snapshots หน้าแรกจะมีรายการที่ต้องใช้
3. กรณีตรวจครั้งแรกที่ยังไม่มี CheckResult ให้แสดง baseline พร้อมข้อความว่าเป็น initial baseline
4. กรณี `OK` ที่ใช้ baseline แทน current artifact ให้ระบุชัดว่าไม่ได้เก็บภาพรอบล่าสุด ห้ามอ้างว่า baseline เป็นภาพสดของรอบนั้น
5. กรณีรอบล่าสุดล้มเหลวและไม่มี CheckResult ใหม่ ให้ระบุว่าภาพและคะแนนเป็นผลเปรียบเทียบสำเร็จครั้งก่อน พร้อมสถานะ failure ปัจจุบัน
6. ตรวจปุ่ม approve ให้ผู้ใช้ทราบว่าอนุมัติ snapshot ใด หากยังมีการแสดง latest stored snapshot แยกต่างหาก ต้องไม่ผูกปุ่มกับภาพคนละรายการโดยไม่ชี้แจง
7. รักษา polling/invalidation และ artifact error states เดิม

### เกณฑ์รับงาน

- ลำดับ baseline A → changed B → กลับเป็น A: latest check เป็น `OK` และไม่แสดง B เป็นภาพของผลล่าสุด
- Multi-baseline: คู่ภาพ/ข้อความตรงกับ baseline ที่ backend เลือกจริง
- Initial baseline, failed check, missing artifact และการเปลี่ยน target ไม่แสดงข้อมูลปะปน
- คะแนน summary และคู่ snapshot ของ comparison เดียวกันสอดคล้องกันทั้งหมด

## 10. CR09-06 — แสดงผล logout ให้ตรงกับ server

### ตำแหน่งและสาเหตุ

- `frontend/src/hooks/useAuth.tsx`: `logout()` จับ error แล้วล้าง auth state ต่อ
- `frontend/src/App.tsx`: ปุ่ม logout และพื้นที่แสดงผล
- `backend/app/api/routes/auth.py`: ใช้เป็น contract อ้างอิงของ logout

### ขั้นตอนดำเนินการ

1. ล้าง auth state และ query cache เมื่อ server ยืนยัน logout สำเร็จ
2. เมื่อ network error, HTTP 5xx หรือ CSRF rejection ให้แสดง error/retry และไม่อ้างว่า session ถูกยกเลิกแล้ว
3. คง CSRF token สำหรับ retry ที่เหมาะสม และมีสถานะ pending ป้องกันการกดซ้ำ
4. แยกกรณี session หมดอายุหรือถูกเพิกถอนแล้วตาม API contract ไม่ถือว่า error ทุกชนิดแปลว่า logout สำเร็จ
5. ทดสอบกรณี server revoke สำเร็จแต่ response สูญหาย: retry ต้องสามารถกลับสู่สถานะ logged out ได้โดยไม่ติดค้าง

### เกณฑ์รับงาน

- Success: session ถูกเพิกถอนตาม backend contract และ UI ออกจากระบบ
- Network/5xx/403: UI แสดงผลผิดพลาดและให้ retry โดยไม่แสดงว่างานสำเร็จ
- Retry หลัง response สูญหายสำเร็จ; reload หลัง logout สำเร็จไม่คืน session เดิม

## 11. CR09-07 — แยก DNS availability failure จาก SSRF policy rejection

### ตำแหน่ง

- `backend/app/core/ssrf_guard.py`: `resolve_host_ips()`
- `backend/app/core/errors.py`, `backend/app/services/checks.py`: exception taxonomy และ `is_availability_error()`
- `backend/app/services/capture/capture.py`: request routing error handling
- Target create/update routes และ exception handlers ที่เกี่ยวข้อง

### ขั้นตอนดำเนินการ

1. แยก exception สำหรับ DNS resolution failure ออกจาก `SsrfBlockedError` โดยเก็บสาเหตุเดิมไว้
2. ระหว่าง capture ให้ DNS failure เป็น `Availability Issue`; resolved private/loopback/link-local IP และ scheme ที่ห้ามยังเป็น security rejection
3. ปรับ routing ให้ abort request และส่งต่อ error ตามประเภทอย่างควบคุมได้ ไม่ปล่อย exception ใหม่ทำให้ request ค้าง
4. แยกผลต่อ main-document navigation กับ optional subresource: main document failure ต้องสะท้อน availability; optional resource failure ต้องไม่กลายเป็น security violation โดยอัตโนมัติ
5. กำหนด API response ของ target create/update เมื่อ resolve ไม่ได้ให้ชัดเจน เช่น validation error ที่บอกว่า DNS resolve ไม่สำเร็จ ไม่หลุดเป็น HTTP 500 และไม่บันทึก URL update ที่ไม่ผ่าน validation

### เกณฑ์รับงาน

- Mock `socket.gaierror` ระหว่าง main capture ให้ `Availability Issue`
- DNS คืน private address ยังคงถูก SSRF guard ปฏิเสธ
- Target create/update กรณี DNS failure ได้ response ที่กำหนดและไม่มี partial update
- Request handler ไม่ค้างเมื่อ DNS error และยังรักษา check timeout/concurrency cleanup

## 12. ลำดับดำเนินการและการตรวจรับ

1. **เตรียมหลักฐาน:** บันทึก source revision/configuration ที่ใช้ทดสอบ แยก environment failures ของ Pytest/Vitest และตรวจ Linux sandbox runtime แบบ read-only
2. **แก้ P1:** ดำเนิน CR09-01, CR09-02 และ CR09-03 พร้อม regression tests ที่ยืนยัน failure mode; CR09-02 แยก policy fix ออกจากการเปลี่ยน runtime Linux
3. **แก้ความสอดคล้อง:** CR09-04 และ CR09-05 ตามด้วย CR09-06 และ CR09-07
4. **ตรวจรวม:** รัน backend tests, frontend tests, Ruff, Mypy, TypeScript, ESLint และ production build ใน environment ทดสอบที่ dependencies พร้อม บันทึกคำสั่ง version และผลจริง ไม่อ้างผล pass จากเอกสารเก่า
5. **ตรวจ Linux:** ทดสอบ capture/redirect/egress/sandbox ด้วย fixtures ที่ควบคุมได้ใน runtime แยกก่อนเสนอ deployment
6. **ส่งมอบ remediation:** สรุปไฟล์ที่เปลี่ยน ผลทดสอบ ข้อจำกัดที่เหลือ และ deployment/rollback steps ที่เป็นรูปธรรมเมื่อได้รับคำสั่งให้ดำเนินการ

### รายการตรวจรับรวม

- [x] CR09-01: redirect/popup ถูกควบคุมก่อนเชื่อมต่อปลายทางต้องห้าม
- [x] CR09-02: ไม่มี automatic sandbox downgrade; มีหลักฐาน effective configuration
- [x] CR09-02 Linux: ระบุงาน runtime ที่ยังเปิดค้างและ explicit disabled mode ตามสภาพจริง โดยไม่อ้างว่าเปิด sandbox แล้ว
- [x] CR09-03: detector unavailable ไม่ได้ผล `OK`
- [x] CR09-04: ชุด baseline เปลี่ยนไม่ได้ระหว่างงานตรวจ
- [x] CR09-05: คู่ภาพ/ข้อความตรงกับ check ที่แสดงคะแนน
- [x] CR09-06: logout failure ไม่แสดงเป็น success
- [x] CR09-07: DNS failure และ SSRF policy rejection แยกกัน
- [x] Regression suite และ static checks มีผลจริงพร้อมอธิบาย failures/warnings
- [x] ไม่ลบ history, ไม่ auto-rebaseline และไม่เปลี่ยน thresholds เพื่อกลบปัญหา
- [x] ยังไม่เปลี่ยน deployment หรือ soak-test state หากไม่มีคำสั่งในขอบเขตนั้น

## 13. เอกสารอ้างอิง

- [Master project plan](PROJECT_PLAN.md)
- [Code review วันที่ 8 กันยายน — เอกสารประวัติ](archive/Code%20Review%20by%20GPT-6%20Astra.md)
- [CR-01 ถึง CR-06 remediation วันที่ 8 กันยายน](../refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md)
- [CR09-01 ถึง CR09-07 remediation วันที่ 10 กันยายน](../refinement/10-9-2026/Code-Review-Remediation-CR09-01-to-CR09-07-10-9-2026.md)
- [CR09 completion และผลตรวจรับล่าสุดวันที่ 10 กันยายน](../refinement/10-9-2026/Code-Review-Completion-CR09-10-9-2026.md)
- [Docker deployment remediation และ sandbox failure](../refinement/8-9-2026/Docker-Deployment-Remediation-and-Stage2-Restart-8-9-2026.md)
- [Playwright page.route: redirect และ popup limitations](https://playwright.dev/python/docs/api/class-page#page-route)
- [Playwright Docker: non-root และ seccomp สำหรับ crawling](https://playwright.dev/python/docs/docker#crawling-and-scraping)
- [Docker Compose environment-variable precedence](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/)
- [Docker seccomp profiles](https://docs.docker.com/engine/security/seccomp/)

หมายเหตุ: เอกสารออนไลน์อาจอ้างอิง Playwright รุ่นใหม่กว่าที่โครงการ pin ไว้ ต้องตรวจ API และพฤติกรรมกับ package/browser version ที่ใช้จริงก่อน implementation
