# Capture Improvements Plan

แผนดึง logic จาก prototype `python_project_website_checker/visual-checker` (เอนจินจับภาพ+เทียบ diff ตัวจริงที่ผ่านการใช้งานกับเว็บโรงพยาบาลหลายแห่ง) มาปรับใช้กับโปรเจกต์ปัจจุบัน

**หลักการ:** port เป็น *algorithm/logic* เข้า service ที่มีอยู่ ไม่ใช่ merge โค้ดหรือยกสถาปัตยกรรม (event-bus JSONL, log-tail, filesystem `state/`, Flet UI) มาด้วย เพราะโปรเจกต์ปัจจุบันใช้ DB + REST + scheduling แทนแล้ว

**ปัญหาที่แก้:** capture ปัจจุบัน ([backend/app/services/capture/capture.py](../backend/app/services/capture/capture.py)) แค่ `goto(wait_until="networkidle")` แล้ว screenshot ทันที ไม่มีการทำภาพให้นิ่ง → animation / carousel / lazy image / cookie banner ทำให้ pixel diff เด้งเป็น **false positive** (แจ้งเตือนว่าโดน deface ทั้งที่ไม่ได้โดน)

> หมายเหตุ: ส่วน auto-rebaseline + decision state machine (เดิมคือข้อ 4) แยกไปเป็นแผนอนาคตเพราะ security-sensitive ดู [plan/future/auto-rebaseline.md](future/auto-rebaseline.md)

---

## 1. ⭐ Page-stabilization pipeline (รวม cookie/overlay dismiss)

**ที่มา:** `page_ready.py` (`wait_page_ready`) + `accept_cookie.py` + CSS/init-script ใน `runner.py`
**ปลายทาง:** ยัดเข้า [capture.py](../backend/app/services/capture/capture.py) ก่อนบรรทัด `page.screenshot()`

### เฟสรอหน้าให้พร้อม (แทน `networkidle` เดี่ยวๆ)
- **รอเป็นเฟส** — DOMContentLoaded → network-quiet แบบ adaptive → body attached → patch CSS → กดปิด cookie → รอ content มองเห็น → readyState complete → รอ layout นิ่ง → extra wait
- **Adaptive network-quiet** — นับ request in-flight เอง รอจน "เงียบต่อเนื่อง" 1,200ms (cap 15,000ms) แทนเชื่อ `networkidle` ที่พลาดกับเว็บยิง XHR ตลอด

### ทำภาพให้นิ่ง (กัน false positive)
- **Freeze animation/transition ทั้งหน้า** — `*,*::before,*::after{animation:none!important;transition:none!important}`
- **หยุด carousel/slider/วิดีโอ** — `slick('slickPause')`, `carousel.pause()`, `video.pause()` + `autoplay=false` (slick/owl/bootstrap)
- **ซ่อน preloader/spinner** + unhide element ที่ถูก `visibility:hidden` ตอนโหลด
- **บังคับ lazy image โหลดจริง** — `loading:lazy→eager`, `img.decode()`, prefetch `background-image` (`fetch cache:'force-cache'`)
- **รอทุกภาพที่มองเห็น `complete && naturalWidth>0`** ก่อนถ่าย (timeout 7s)
- **รอ layout นิ่งจริง** — poll `getBoundingClientRect()` ของ `main` จนไม่ขยับต่อเนื่อง 400ms
- **Neutralize scroll** — override `window.scrollTo/scrollBy` กัน JS เลื่อนหน้าเองระหว่างถ่าย
- **`emulate_media(reduced_motion="reduce")`** + viewport ตายตัว → deterministic ทุกรอบ

### Cookie/overlay dismiss (ย้ายมาจากเดิมข้อ 4a)
- **กด "ยอมรับ cookie" อัตโนมัติก่อนถ่าย** — 2 ชั้น: (ก) `get_by_role("button", name=/ยอมรับ|accept|agree|.../)` รองรับไทย+อังกฤษ, (ข) selector เจ้าดัง (CookieYes `.cky-btn-accept`, OneTrust `#onetrust-accept-btn-handler`, Cookiebot)
- **ค้นทั้ง main page + ทุก iframe** (banner หลายเจ้าอยู่ใน iframe)
- **fallback ซ่อนด้วย CSS** (`HIDE_CSS`) ถ้ากดไม่สำเร็จ
- **รอ banner หายจริง** (`offsetParent === null`) ก่อนไปเฟสถ่าย
- **ผลิต flag `cookie_dismissed`/`promo_closed` ไว้เฉยๆ** — ข้อ 1 แค่ทำภาพให้สะอาด + คืน flag; การเอา flag ไปตัดสิน alert เก็บไว้แผนอนาคต

### เสริม / ข้อควรระวัง
- **PhaseRecorder** — เก็บเวลาแต่ละเฟส (ms) ไว้ debug ว่าเว็บไหนช้าตรงไหน (option)
- ⚠️ **ต้องเข้ากับ SSRF guard เดิม** — capture.py ดัก `page.route("**/*")` อยู่; `add_style_tag` ปลอดภัย แต่ `fetch()` prefetch จะวิ่งผ่าน route → guard ต้องอนุญาต same-origin

---

## 2. ⭐ Multi-baseline matching

**ที่มา:** `image_diff.py` (`find_best_baseline`) + `baseline_store.py`
**ปลายทาง:** [services/diff/diff.py](../backend/app/services/diff/diff.py) + model `Snapshot`/`Target`

- **เก็บ baseline ได้หลายรูปต่อ target** (ไม่ใช่ 1 รูปเดียว) — เว็บที่มีแบนเนอร์/โปรหมุนตามปกติมีหน้าตา "ถูกต้อง" ได้หลายแบบ
- **เทียบ current กับทุก baseline แล้วเลือก diff ต่ำสุด** — ตัดสิน alert จาก `best_ratio = min(...)` ไม่ใช่ baseline เดียว → ลด false positive เว็บ dynamic
- **จำกัดจำนวน baseline** (`_prune_old_baselines`, `MAX_BASELINES_PER_SITE=50`) — ลบเก่าสุดเมื่อเกิน กัน storage บวม
- **ตั้งชื่อ baseline ด้วย timestamp** (`_ts_png` เช่น `2026-09-02T14-30-00.png`) — เรียงลำดับได้
- **ทนไฟล์ภาพเสีย** — `LOAD_TRUNCATED_IMAGES=True` + `try/except (OSError, ValueError)` ข้าม baseline ที่ corrupt ไม่ crash ทั้งรอบ
- **บันทึกว่าแมตช์ baseline ตัวไหน** (`matched_baseline`/`closest_baseline`) — เก็บลง CheckResult ให้ผู้ใช้เห็นว่าตัดสินจากฐานอันไหน
- **โครงสร้าง:** ขยาย `is_baseline` (boolean เดี่ยว) → รองรับหลาย snapshot เป็น baseline ต่อ target

---

## 3. Diff heatmap preview (3 ช่อง)

**ที่มา:** `image_diff.py` (`_diff_score_and_preview`)
**ปลายทาง:** [services/diff/diff.py](../backend/app/services/diff/diff.py) + [ScreenshotCompare.tsx](../frontend/src/components/ScreenshotCompare.tsx)

- **diff แบบ pixel + mask** — `ImageChops.difference` → grayscale → boost brightness×2 + contrast×2 → threshold (`MASK_LEVEL=16`) เป็น mask → กัน noise การบีบอัด/anti-alias เด้ง
- **ratio = พิกเซลเปลี่ยน / พิกเซลทั้งหมด** (0..1) เทียบ threshold — วิธี mask นี้แม่นกว่า diff ดิบ
- **ภาพ preview 3 ช่องต่อกัน** `[baseline | current | highlighted]` — ช่อง 3 ทาบจุดต่างสีแดง (`composite` + `blend 0.6`) → เห็นทันทีว่าต่างตรงไหน
- **จัดการภาพคนละขนาด** (`_ensure_same_size`) — resize current ให้เท่า baseline (BILINEAR) ก่อนเทียบ
- **early-exit** — `getbbox() is None` (เหมือนเป๊ะ) คืน 0.0 ทันที
- **ปิด file handle ด้วย context manager** — กัน handle leak ตอน monitor ยาว
- **UI:** เพิ่มโหมด "diff overlay" (แดง) ใน `ScreenshotCompare` ที่ตอนนี้โชว์แค่ baseline/current

---

## ลำดับแนะนำ

| ข้อ | ทำเมื่อไหร่ | เหตุผล |
|---|---|---|
| 1. Page-stabilization + cookie dismiss | เฟสนี้ | อุดจุดอ่อนหลัก (false positive) เสี่ยงต่ำ |
| 2. Multi-baseline matching | เฟสนี้/ถัดไป | ต้องแก้ schema แต่ตรงประเด็น |
| 3. Diff heatmap preview | เฟสนี้/ถัดไป | UX ชัดขึ้น เสี่ยงต่ำ |
| 4. Auto-rebaseline (แยกไฟล์) | อนาคต | security-sensitive — ดู future/auto-rebaseline.md |

## สิ่งที่ไม่ยกมา
- Loop/runner, event-bus JSONL, log-tail, filesystem `state/` → DB + REST + scheduling ของโปรเจกต์ปัจจุบันแทนแล้ว
- Flet UI ทุกตัว
