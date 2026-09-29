# แผนแก้ไขและตรวจรับ CR09 ให้ครบ — 10 กันยายน 2026

**สถานะ ณ 10 กันยายน 2026: ดำเนินการแก้ source code และตรวจรับบน Windows แล้ว; isolated Linux runtime/sandbox verification ยังเปิดอยู่เพราะ Docker daemon ไม่ทำงาน**  
แผนหลักของชุดรีวิว: [Code Review by GPT6 Astra 9-9-2026](Code%20Review%20by%20GPT6%20Astra%209-9-2026.md)  
Master plan: [PROJECT_PLAN.md](PROJECT_PLAN.md)  
ประวัติที่ตรวจซ้ำ: [Refinement CR09 วันที่ 10 กันยายน](../refinement/10-9-2026/Code-Review-Remediation-CR09-01-to-CR09-07-10-9-2026.md)

## 1. ขอบเขตและผลลัพธ์ที่ต้องได้

แผนนี้ต่อยอดการแก้ไขที่มีอยู่ เพื่อปิดส่วนที่ยังไม่ครบใน CR09-01 และ CR09-05 และเติมหลักฐานตรวจรับของอีก 5 ข้อ ไม่รื้อการแก้ไขที่ถูกต้องแล้วโดยไม่มีข้อบกพร่องรองรับ

ผู้ใช้อนุมัติ implementation ในรอบถัดมาแล้ว งานที่ทำครอบคลุม source code, regression tests และ local verification โดยไม่มี production deployment หรือการเปลี่ยน production runtime

ข้อจำกัดที่ต้องรักษาเมื่อได้รับคำสั่งให้เริ่ม:

- คง single API worker และ concurrency limits ตามสถาปัตยกรรมปัจจุบัน
- ไม่ลบฐานข้อมูล ประวัติ snapshots หรือ baselines; ไม่ auto-rebaseline และไม่เปลี่ยน thresholds เพื่อให้ tests ผ่าน
- คง authentication, CSRF, service-worker blocking และ WebSocket blocking
- ใช้ฐานข้อมูลและ network fixtures สำหรับทดสอบแยกจาก production
- ไม่เปลี่ยนโหมด sandbox ของ Linux ที่ใช้งานอยู่จนกว่าจะมีหลักฐาน runtime และแผน rollback พร้อม
- ไม่เปลี่ยน Stage 2 หรือ reset soak test จากงาน remediation โดยอัตโนมัติ
- แยกสถานะ “แก้โค้ดแล้ว”, “ทดสอบแล้ว” และ “deploy แล้ว” พร้อมหลักฐานของแต่ละสถานะ

## 2. สถานะเริ่มต้นจากการตรวจซ้ำ

| ID | สถานะโค้ดที่ยืนยันจากการอ่าน | งานที่ยังต้องทำ |
| --- | --- | --- |
| CR09-01 | ยังแก้ไม่ครบ | ปิด fetch-error fallback, ผูก IP policy กับ connection จริง, รักษา redirect semantics, จัดการ request ที่ frame ยังไม่พร้อม และพิสูจน์ egress |
| CR09-02 | แก้ automatic sandbox fallback แล้ว | เพิ่ม error/configuration tests และตรวจ Linux runtime แยกจาก policy fix |
| CR09-03 | แก้ structural unavailable ให้ Failed แล้ว | ยืนยัน missing/permission/recovery cases และ cleanup โดยไม่เสีย baseline/history |
| CR09-04 | เพิ่ม Checking/in-flight guards แล้วในขอบเขต single worker | ทดสอบ interleaving ระหว่าง diff และขณะรอ semaphore ทั้ง approve และ demote |
| CR09-05 | ภาพ/ข้อความผูก check IDs แล้ว แต่ยังไม่ครบ | metadata และ approval ต้องอ้าง snapshot เดียวกัน; แสดงผลเก่าเมื่อ check ล่าสุดล้มเหลวให้ชัด |
| CR09-06 | แก้ logout state/error feedback แล้ว | ทดสอบ success, 401, network/5xx/403 และ response-loss retry |
| CR09-07 | แยก DNS exception และ availability classification แล้ว | ทดสอบผ่าน capture routing และ create/update API จริงใน fixture รวมถึง timeout/cleanup |

หลักฐานที่มีจากรอบตรวจซ้ำ ไม่ใช่ผลทดสอบ implementation ตามแผนนี้:

- TypeScript ผ่านทั้ง `tsconfig.app.json` และ `tsconfig.node.json`
- ESLint ไม่มี error มี 1 warning ใน `useAuth.tsx`
- Ruff 0.7.4 ตาม version ที่ pin พบ UP038 ใน `backend/app/services/checks.py` และเมื่อรวม scripts พบ I001 เดิมใน `backend/scripts/create_user.py`
- มี 69 test functions ในห้าไฟล์ที่ refinement ระบุ แต่รอบตรวจซ้ำไม่ได้รัน Pytest/Vitest ทั้งชุด และยังไม่มี Linux runtime evidence
- การจำลอง handler ในหน่วยความจำยืนยันว่า initial fetch error เรียก `continue_()` และ request ที่อ่าน `frame` แล้วเกิด Playwright error หลุดออกจาก handler ก่อน abort/fetch
- DNS rebinding และความเที่ยงตรงของ browser redirect ยังไม่ได้พิสูจน์ด้วย network/browser integration test; ข้อค้นพบส่วนนี้มาจาก source ของแอปและ Playwright 1.48.0 ที่ติดตั้ง

## 3. ลำดับงานและจุดตรวจรับ

| ลำดับ | งาน | สิ่งที่ต้องได้ก่อนผ่านขั้นตอน |
| --- | --- | --- |
| 0 | บันทึกสภาพแวดล้อมและเตรียม fixtures | ระบุ source/configuration ที่ทดสอบ, tool/browser versions และแยกข้อมูลทดสอบได้ |
| 1 | ออกแบบและพิสูจน์ CR09-01 | วิธีที่ปิด network bypass และรักษาพฤติกรรมเว็บได้จริง; หากยังพิสูจน์ไม่ได้ให้คงสถานะเปิด |
| 2 | แก้ CR09-01 และ CR09-05 พร้อม regression tests | เกณฑ์ของหัวข้อ 4 และ 5 ผ่าน |
| 3 | ตรวจรับอีก 5 ข้อและแก้เฉพาะข้อบกพร่องที่พบ | test matrix ในหัวข้อ 6 ผ่าน; แยกสถานะ Linux sandbox |
| 4 | รัน regression suite/static checks/build | ผลจริงพร้อมคำสั่ง version ขอบเขต และ failures/warnings |
| 5 | ทดสอบใน isolated Linux runtime | ยืนยัน capture/redirect/egress และ effective sandbox mode โดยไม่แตะ production |
| 6 | ส่งมอบผลและแผน deploy/rollback | ปิดเฉพาะข้อที่มีหลักฐานครบ; deployment รอคำสั่งแยก |

## 4. CR09-01 — ปิด SSRF และรักษาความเที่ยงตรงของ capture

ไฟล์หลัก: `backend/app/services/capture/capture.py`, `backend/app/core/ssrf_guard.py`, `backend/app/core/errors.py`, `backend/tests/test_capture.py`, `backend/tests/test_ssrf_guard.py`; configuration ของ runtime ทดสอบตามวิธีที่ผ่านการพิสูจน์

### 4.1 แก้เส้นทางผิดพลาดให้ปิด request อย่างควบคุมได้

1. ยกเลิกการ fallback ไป `route.continue_()` เมื่อ fetch/validation/redirect mediation ล้มเหลว
2. ส่งต่อเหตุผลตามประเภท: SSRF policy rejection, DNS failure, timeout หรือ capture failure พร้อม abort/close ที่เหมาะสม ห้ามกลืน error จนได้ false OK
3. แยก main document, popup, iframe และ optional subresource ให้ชัด เพื่อรักษา availability classification และไม่ให้ iframe กิน main-frame redirect quota
4. จัดการกรณี `request.frame` โยน exception โดยไม่ใช้ `hasattr()` เป็นตัวรับประกันความปลอดภัย และไม่อาศัย main-page frame อย่างเดียวสำหรับทุกหน้า
5. ตรวจ scheme ของทุกปลายทางตาม policy จริง ไม่ใส่ production bypass สำหรับ `file://` เพื่อรองรับ tests; local fixtures ให้แยกกลไกทดสอบออกจาก policy ใช้งานจริง ส่วน browser-local data/blob/about ต้องกำหนดขอบเขตอย่างชัดเจน

### 4.2 จุดตัดสินใจด้าน transport ก่อนเลือก implementation

วิธีใหม่ต้องผ่านเงื่อนไขพร้อมกัน: ตรวจ IP ที่จะเชื่อมต่อจริง, ไม่มี direct fallback ที่ข้าม policy, ตรวจแต่ละ redirect ก่อนตาม hop และรักษา URL/origin/method/cookie semantics ของ browser

ให้ประเมินสองแนวทางด้วย isolated fixtures บน Playwright 1.48.0 ก่อนเลือก:

| แนวทาง | สิ่งที่ต้องพิสูจน์ | เงื่อนไขที่ทำให้ใช้ไม่ได้ |
| --- | --- | --- |
| Browser จัดการ redirect โดยมี egress proxy/network isolation บังคับทุก connection | Proxy resolve/validate แล้วเชื่อมต่อ IP เดียวกัน, ปิด direct egress และมีวิธีนับ redirect ต่อ chain ก่อนเกิน limit | Proxy ตรวจเฉพาะ hostname, browser ยังออกทางอื่นได้ หรือควบคุม quota แต่ละ chain ไม่ได้ |
| Request mediation ที่ควบคุม transport และส่ง redirect กลับ browser อย่างถูกต้อง | ทุก hop รวม popup/subresource ถูก intercept จริง, transport เชื่อมต่อ IP ที่ตรวจแล้ว พร้อม Host/TLS SNI/certificate validation ที่ถูกต้อง | ต้องใช้ `route.fetch()` แบบ resolve ใหม่โดยไม่ผูก IP หรือยุบ final response ใส่ origin เดิมจนหน้าเว็บเปลี่ยนพฤติกรรม |

การย้ายไป context routing อย่างเดียวไม่เพียงพอ และ Chromium `--host-resolver-rules` ไม่ใช่หลักฐานว่าคุม connection ของ APIRequestContext ได้ หากต้องเพิ่ม proxy/component/dependency ให้ระบุเหตุผล ขอบเขต configuration และภาระดูแลก่อน integration ไม่เลือกกลไกเพียงเพราะ unit tests ผ่าน

ในขั้นออกแบบต้องบันทึกวิธีเชื่อมโยง redirect chain กับ request/page และวิธีบังคับ limit ก่อนส่ง hop ถัดไปด้วย ห้ามอ้างว่า proxy ทั่วไปแก้ redirect limit ได้เองโดยไม่มีหลักฐาน

### 4.3 Browser/network acceptance tests

สร้างปลายทาง fixture ที่ควบคุมได้และมี request counters ทั้งฝั่ง allowed และ blocked พร้อม resolver จำลอง; ทดสอบในเครือข่ายแยก ไม่ใช้บริการภายในจริงเป็นปลายทางทดสอบ

| กรณี | ผลที่ต้องได้ |
| --- | --- |
| Direct request ไป blocked address | ปลายทางรับ 0 requests |
| Main redirect, popup request แรก, iframe และ subresource redirect ไป blocked address | ปลายทางรับ 0 requests ทุกเส้นทาง |
| DNS เปลี่ยนจาก allowed เป็น blocked ระหว่าง validation กับ connection รวม hostname เริ่มต้น | ไม่เชื่อมต่อ blocked IP; ทดสอบการ reuse connection ตามกลไกที่เลือกด้วย |
| Initial fetch error/connection reset/timeout | ไม่มี continue/direct fallback; จบงานและคืน concurrency slot ได้ |
| Request ก่อน frame พร้อม | ไม่เกิด uncaught handler error หรือ request ค้าง; policy ยังทำงาน |
| Redirect เท่ากับ limit และเกิน limit | เท่ากับ limit สำเร็จ; hop ที่เกิน limit ได้รับ 0 requests |
| หลาย iframe/popup หรือหลาย resource chains | quota แยกถูกต้อง ไม่ปะปนกับ main frame |
| Allowed redirect ข้าม path, host และ HTTP → HTTPS | final URL, origin, relative CSS/image/script, cookies และ DOM ตรงกับ browser behavior ของ fixture |
| 301/302/303/307/308 รวม request ที่มี POST body | method/body และ cookie behavior ตรง contract; ไม่ replay POST โดยผิด semantics |
| Service workers, WebSockets และ network paths อื่นที่ routing ไม่ครอบคลุม | มี policy/egress บังคับจริง หรือระบุข้อจำกัดและคงงานเปิดหากข้ามไป blocked destination ได้ |

ใช้ DOM assertions, final URL, request logs และภาพของ fixture ที่คงที่เทียบกับ browser อ้างอิงในเครือข่ายทดสอบเดียวกัน ไม่เทียบภาพจาก production ที่เปลี่ยนตลอดเวลา ไม่ใช้ bypass policy ในระบบจริงเพื่อให้ test ทำงาน

**เกณฑ์ปิด CR09-01:** acceptance tests ผ่านทั้ง application path และ isolated Linux egress; ไม่มีข้อจำกัดที่ยังทำให้เข้าถึง blocked destination ได้ การ capture สำเร็จหรือ mock options ถูกต้องอย่างเดียวไม่ถือว่าผ่าน

## 5. CR09-05 — ให้ภาพ metadata คะแนน และ approval อ้างรายการเดียวกัน

ไฟล์หลัก: `frontend/src/pages/TargetDetailPage.tsx`, `frontend/src/hooks/useTargetDetail.ts`, `frontend/src/api/snapshots.ts` และ tests ที่เกี่ยวข้อง; ตรวจ endpoint snapshot metadata ตาม ID ที่มีอยู่ก่อนเพิ่ม backend API

1. สร้างข้อมูล comparison จาก CheckResult เดียว โดยใช้ baseline/current IDs เป็นแหล่งอ้างอิงสำหรับภาพ ข้อความ metadata และคะแนน
2. ดึง metadata ตาม snapshot ID โดยตรงเมื่อไม่มีใน cache; ไม่ถือว่า snapshots 50 รายการแรกหรือ active baseline list ครอบคลุมประวัติที่ check อ้างทั้งหมด
3. เอา fallback ที่แสดง metadata ของ baseline คนละ ID และ fallback ของปุ่มอนุมัติไป latest stored snapshot ออก เมื่อ metadata หาไม่พบให้แสดง unavailable/retry และปิด action ที่ยังระบุ snapshot ไม่ได้
4. ปุ่ม Approve ต้องระบุ snapshot ที่กำลังอนุมัติให้ผู้ใช้ทราบ และใช้ ID เดียวกับรายการที่แสดง หากต้องคงการอนุมัติ snapshot เก่า ให้เป็นการเลือกอย่างชัดเจน
5. Initial baseline ให้ตัดสินจากการยังไม่มี CheckResult ไม่ใช้จำนวน snapshots เท่ากับหนึ่งแทนจำนวนครั้งที่ตรวจ เพราะรอบ OK ไม่สร้าง snapshot ใหม่
6. ผล OK ที่ baseline/current ID เดียวกันให้ระบุว่าใช้ภาพ baseline เนื่องจากไม่เก็บ live capture รอบนั้น ไม่เรียกภาพนี้ว่าภาพสด
7. Failed/Availability Issue ที่ไม่สร้าง CheckResult ใหม่ ให้แสดง current failure และเวลาของผลเปรียบเทียบสำเร็จครั้งก่อนอย่างชัดเจน ไม่ติดป้ายผลเก่าว่าเป็นผลรอบที่ล้มเหลว
8. รักษา query invalidation, polling, query keys ตาม target/snapshot IDs และ error/retry states ระหว่างเปลี่ยน target

กรณีตรวจรับ:

- Baseline A → Changed B → กลับ A: ภาพ/ข้อความอ้าง A ทั้งคู่ และไม่มีปุ่มอนุมัติ B โดย fallback
- Baseline ที่ match อยู่เกิน 50 snapshots แรก: โหลด metadata ตาม ID ได้ คะแนน/ภาพ/metadata ตรงกัน
- Multi-baseline ที่ match ไม่ใช่ baseline ใหม่สุด หรือ baseline ถูก demote หลัง check: ยังแสดง historical reference ที่ถูกต้อง
- Initial capture และหลายรอบ OK ที่มี snapshot เดียว: ข้อความ initial/comparison ถูกต้อง
- รอบล่าสุด Failed/Availability Issue หลังผล OK หรือ Changed: แสดงอายุผลเก่าและความผิดพลาดรอบปัจจุบัน
- Missing metadata/artifact, API failure, retry และเปลี่ยน target ระหว่างโหลด: ไม่แสดงข้อมูลคนละ target หรืออนุมัติผิด snapshot
- Approval mutation ส่ง ID ตรงกับ snapshot ที่ผู้ใช้เห็น และจัดการ 409 โดยแสดงเหตุผล

## 6. ตรวจรับอีก 5 ข้อโดยรักษาการแก้ไขที่มีอยู่

| ID | งานและการทดสอบที่ต้องเติม | เกณฑ์ผ่าน |
| --- | --- | --- |
| CR09-02 | Mock ทั้งสองค่า sandbox และ launch errors ที่มี sandboxing, closed และ error อื่น; ตรวจ effective Compose configuration โดยไม่เผย secrets | เปิด/ปิดตรงค่า ไม่มี retry downgrade; configuration precedence ถูกบันทึก |
| CR09-02 Linux | ตรวจ UID/GID, browser/image versions, seccomp, namespace/AppArmor restrictions และ logs; เตรียม non-root/dependencies/writable paths ใน runtime แยกหากต้องทดสอบเปิด sandbox | แยกผล “capture ได้” จาก “sandbox เปิดจริง”; หาก Linux ยัง explicit disabled ให้คงสถานะ runtime งานเปิดและระบุข้อจำกัด ไม่อ้างว่าเปิด sandbox แล้ว |
| CR09-03 | Missing path/file, permission error, baseline เสียร่วมกับ baseline ที่พบ injection, HTML ครบ/no change/injection และตรวจซ้ำหลังคืน artifact | unavailable ไม่ได้ OK; last_error ช่วยระบุ artifact/baseline; staging สะอาดและ history ไม่หาย |
| CR09-04 | ใช้ events/barriers คุมจังหวะเริ่ม diff → ขอ approve/demote → ตรวจ 409 → ปล่อย diff; ทดสอบขณะรอ semaphore และหลังงานจบ | mutation ระหว่าง in-flight ถูกปฏิเสธ baseline references คงเดิม; หลังจบทำงานได้ และยังห้าม demote baseline สุดท้าย |
| CR09-06 | Frontend integration tests สำหรับ success, 401, network error, 500, 403, pending click suppression และ retry หลัง server revoke แล้ว response สูญหาย; ตรวจ reload กับ backend contract | error ไม่ล้าง auth/CSRF โดยผิดเงื่อนไข; success/expired session กลับ logged out และล้าง cache ได้ |
| CR09-07 | DNS failure ตอน initial validation, main request และ redirect hop; optional resource DNS failure; resolved private IP; create/update API failure และ timeout/cancellation | main DNS เป็น Availability Issue, blocked IP เป็น security failure, optional failure ไม่กลายเป็น SSRF เอง; API ไม่ 500/partial update และ handler/concurrency ไม่ค้าง |

ความต้องการเปิด Chromium sandbox บน production เป็นงาน runtime แยกจาก code fix การคง explicit disabled mode พร้อมรายงานข้อจำกัดทำได้ตามแผนเดิม แต่ต้องไม่รายงานว่างานเปิด sandbox สำเร็จ

## 7. การตรวจรวมและหลักฐานส่งมอบ

ก่อนรัน ให้บันทึก OS, Python/Node, Playwright/browser, Ruff/Mypy/TypeScript versions และ dependency/lockfile ที่ใช้ ทดสอบจาก source เดียวกัน หากไม่มี Git revision ให้บันทึก manifest ของไฟล์และ SHA-256 ในพื้นที่ผลทดสอบ เพื่ออ้างกลับได้ ไม่อ้างผลจากเอกสารเก่าแทนผลรอบใหม่

คำสั่งอ้างอิงหลังได้รับคำสั่งเริ่มดำเนินการ โดยใช้ interpreter ของ environment ทดสอบ:

จาก `backend/`:

```text
python -m pytest tests
python -m ruff check --no-cache app tests scripts
python -m mypy app scripts
```

จาก `frontend/`:

```text
npm run test
node node_modules/typescript/lib/tsc.js --project tsconfig.app.json --noEmit
node node_modules/typescript/lib/tsc.js --project tsconfig.node.json --noEmit
npm run lint
npm run build
```

- เริ่มจาก regression ของ failure mode ที่แก้ แล้วจึงรัน suite รวมหลังโค้ดนิ่ง; ไม่รันซ้ำโดยไม่มีการเปลี่ยนแปลงหรือประเด็นค้าง
- แก้ UP038 ใน checks.py และ I001 ใน create_user.py ภายในรอบ implementation โดยไม่เปลี่ยน behavior; ใช้ Ruff version ที่ pin ไม่อัปเกรดเพื่อซ่อนผลตรวจ
- บันทึก ESLint warning ที่มีอยู่และตัดสิน disposition ให้ชัด ไม่รายงานว่าไม่มี warning หากยังมี
- ถ้า Pytest/Vitest ติด environment ให้แยก “เริ่มทดสอบไม่ได้” จาก “tests fail”; เตรียม environment ที่ dependencies ตาม lock พร้อม ไม่ปิด checks หรือเปลี่ยน dependency constraints เพียงเพื่อให้ผลเขียว
- ผล 69 tests เดิมเป็น subset ไม่ใช่ full backend suite; จำนวน test รอบใหม่ต้องนับจาก output จริง
- Unit/static checks ผ่านไม่แทนที่ browser integration, request counters, Linux isolation หรือ sandbox evidence

## 8. ส่งมอบและ deployment

เมื่อ implementation และการทดสอบตามขอบเขตเสร็จ ให้จัดทำ refinement รอบใหม่ ระบุไฟล์ที่เปลี่ยน สาเหตุ ผลทดสอบ ข้อจำกัด และสถานะรายข้อ โดยเชื่อมกลับมาที่แผนนี้ ไม่แก้ประวัติเดิมให้เสมือนเคยผ่านสิ่งที่ไม่ได้ทดสอบ

ก่อนเสนอ production deployment ต้องมี:

1. Source/configuration ที่ผ่าน isolated Linux tests และผล effective mode โดยไม่มี secrets
2. แผนสำรองฐานข้อมูล/artifacts/configuration และการตรวจความพร้อมของ backup โดยไม่ลบต้นฉบับ
3. ขั้นตอนหยุดรับงานใหม่และรอ in-flight jobs จบก่อนเปลี่ยน runtime; ตรวจ permissions/startup dependencies และ single worker
4. Smoke tests หลัง deploy สำหรับ login/logout, capture, baseline references และ status classification
5. Rollback ไป source/configuration/image ที่บันทึกไว้ พร้อมชี้แจงว่าการย้อน transport อาจคืนช่องโหว่เดิม; หาก isolation ใช้ไม่ได้ให้หยุด capture ที่มีความเสี่ยงแทนการ bypass policy
6. การติดตามผลโดยรักษา Stage 2/soak-test history เดิม และระบุผลกระทบหากมี downtime

การ deploy หรือเปลี่ยน production runtime ต้องได้รับคำสั่งจากผู้ใช้แยกจากการอนุมัติแก้โค้ด

## 9. Checklist ปิดงาน

- [x] CR09-01 ปิด fallback/rebinding/redirect/popup gaps และมี blocked-destination counters เท่ากับศูนย์
- [x] Redirect ของ capture navigation ซึ่งเริ่มด้วย GET รักษา final URL, origin และ relative resources; resource/non-GET transport ยังผ่าน browser กับ validating proxy จึงคง HTTP semantics ของ browser
- [x] CR09-05 ภาพ/ข้อความ/metadata/คะแนน/approval ตรงรายการเดียวกัน รวมรายการที่อยู่นอกหน้าแรก
- [x] CR09-02/03/04/06/07 ผ่าน regression matrix; แยกงาน Linux sandbox ที่ยังเปิดอย่างตรงไปตรงมา
- [x] Backend suite, frontend suite, Ruff, Mypy, TypeScript, ESLint และ build มีผลจริงพร้อม versions และ disposition ของ warnings
- [ ] Isolated Linux capture/egress/effective sandbox mode มีหลักฐาน ไม่อ้างผล mock แทน runtime
- [x] ไม่มี history สูญหาย, auto-rebaseline หรือ threshold adjustment เพื่อกลบ failure
- [x] Refinement รอบใหม่และสถานะในแผนตรงกับหลักฐาน; ไม่มีข้อกำหนดที่ยังไม่ผ่านแต่ระบุว่า completed
- [ ] เตรียม deployment/rollback ที่ review ได้; ยังไม่ deploy หากไม่มีคำสั่ง

## 10. สถานะหลังดำเนินการ

แก้ source code และตรวจรับบน Windows แล้วตาม [Code Review Completion CR09 — 10-9-2026](../refinement/10-9-2026/Code-Review-Completion-CR09-10-9-2026.md) ไม่มีการ deploy หรือเปลี่ยน production configuration งานที่ยังเปิดคือ isolated Linux runtime/egress และ effective Chromium sandbox verification ซึ่งต้องใช้ Docker daemon หรือ Linux host ที่ทำงานได้
