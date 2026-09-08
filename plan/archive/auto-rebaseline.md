# Future Plan: Auto-rebaseline + Decision State Machine

**สถานะ:** แผนอนาคต — ยังไม่เริ่ม ต้องตัดสินนโยบายด้านความปลอดภัยก่อน
**ที่มา:** prototype `python_project_website_checker/visual-checker` — `monitor.py` (`monitor_once`) + `monitor_helper/baseline_logic.py`
**เกี่ยวข้องกับ:** [plan/capture-improvements.md](../capture-improvements.md) (ต้องทำข้อ 1 และ 2 ก่อน)

---

## ทำไมแยกออกมาเป็นแผนอนาคต

เดิมส่วนนี้เป็น "ข้อ 4" ในลิสต์รวม แต่แยกออกเพราะ **security-sensitive** ต่างจากข้อ 1–3 ที่เป็น capture/diff เสี่ยงต่ำ:

- ⚠️ **auto-rebaseline เป็นดาบสองคม** — ถ้า attacker deface หน้าเว็บ แล้วระบบบันทึกหน้าที่โดน deface เป็น baseline ใหม่อัตโนมัติ = ระบบกลบร่องรอยการโจมตีเอง
- ⚠️ **ขัดกับ human-approve flow เดิม** — โปรเจกต์ปัจจุบันออกแบบให้คนเป็นคนตัดสิน (`review.py`, `acknowledge`, `approve baseline`) การ rebaseline อัตโนมัติขัดหลักนี้
- ⚠️ **พึ่งพา multi-baseline (ข้อ 2)** — ต้องมี baseline history/schema รองรับก่อน
- ⚠️ **ต้องตัดสินนโยบายก่อนเริ่ม** — จะให้ auto-rebaseline ได้แค่ไหน? ต้องมีคน approve ไหม? เก็บ log/audit อย่างไร?

---

## Scope ที่ prototype ทำไว้ (อ้างอิง)

### Decision state machine ตัดสิน 3 ทาง (`monitor_once`)
- `ratio ≤ threshold` → **match** (บันทึก `matched_baseline` เฉยๆ ไม่เตือน)
- `ratio > threshold` **และ** เพิ่งปิด overlay (`cookie_dismissed`/`promo_closed`) → **rebaseline** (ไม่เตือน)
- `ratio > threshold` ล้วนๆ → **alert** + append baseline ใหม่ (`_alert_and_append`)

### แยกแยะ "เปลี่ยนเพราะ overlay" ออกจาก "โดน deface"
- ใช้ flag `cookie_dismissed`/`promo_closed` ที่ผลิตจาก capture-improvements ข้อ 1 มาตัดสิน
- ควบคุมด้วย env flag: `REBASELINE_ON_COOKIE`, `REBASELINE_ON_OVERLAY` (เปิด/ปิดได้)

### Auto-rebaseline แบบมีเงื่อนไข (`_rebaseline`)
- บันทึก current เป็น baseline ใหม่ + prune ตัวเก่า + log เหตุผล + `closest_baseline`
- ส่ง notification แจ้งว่า rebaseline เพราะอะไร

### แนบภาพ diff ไปกับ notification (`_alert_and_append`)
- ส่ง preview 3 ช่อง (จาก capture-improvements ข้อ 3) แนบ Slack/notifier ตอน alert

---

## เงื่อนไข/คำถามที่ต้องตอบก่อนเริ่ม (Decision checklist)

- [ ] auto-rebaseline อนุญาตเฉพาะกรณี **overlay-triggered เท่านั้น** ใช่ไหม? (ห้ามใช้กับ diff ทั่วไปเด็ดขาด)
- [ ] ต้องมี **human approve** ก่อน rebaseline หรือให้อัตโนมัติได้?
- [ ] เก็บ **audit log** ทุกครั้งที่ rebaseline (ใคร/เมื่อไหร่/เหตุผล/ภาพก่อน-หลัง) อย่างไร?
- [ ] จะ integrate กับ review workflow เดิม (`review.py`) หรือทำ flow แยก?
- [ ] threshold และ policy ต่างกันตาม target ได้ไหม (เว็บสำคัญ = เข้มกว่า)?
- [ ] rollback ได้ไหม ถ้า rebaseline ผิดพลาด?

---

## หลักการความปลอดภัยที่ต้องยึด

1. **auto-rebaseline ต้องจำกัดวงแคบที่สุด** — เฉพาะ overlay-triggered ตามที่ prototype ทำ ห้ามขยายไป diff ทั่วไป
2. **ทุกการ rebaseline ต้องมี audit trail** ที่ลบ/แก้ไม่ได้
3. **ค่า default ควรเป็น human-in-the-loop** — auto เป็น opt-in ต่อ target ไม่ใช่ค่าตั้งต้น
