# สรุปการปรับปรุงระบบเชื่อมต่อหน้าบ้าน–หลังบ้าน (Frontend–Backend Integration)

เอกสารนี้สรุปรายละเอียดการแก้ไขระบบและอินเตอร์เฟซเพื่อบูรณาการระบบตรวจจับการเปลี่ยนแปลงหน้าเว็บ (Web Defacement Project) ให้ทำงานร่วมกันได้อย่างสมบูรณ์

---

## 📋 สรุปผลการปรับปรุงตามหัวข้อ (To-dos)

| ลำดับงาน | รายการการแก้ไข | ฝั่งระบบ | ผลลัพธ์และการเปลี่ยนแปลง |
| :--- | :--- | :---: | :--- |
| **To-do 1** | Surface `last_error` in UI | Frontend | แสดงข้อความสาเหตุของข้อผิดพลาดหากประมวลผลล้มเหลว (Failed) บนหน้า Dashboard และหน้าละเอียด |
| **To-do 2** | Handle `accepted: false` & errors | Frontend | จัดการการกดเช็คซ้ำซ้อนขณะตรวจอยู่ โดยแสดงผล Notice พร้อมพิมพ์คำแปลข้อผิดพลาดจาก API ที่ชัดเจน |
| **To-do 3** | Expose diff thresholds via API | Both | สร้าง API `/config` ดึงค่า Threshold จริงจากหลังบ้านไปแสดงฝั่งหน้าบ้านแทนการเขียนแบบฮาร์ดโค้ด |
| **To-do 4** | Poll target detail on checking | Frontend | อัปเดตหน้าจออัตโนมัติ (Polling) เฉพาะช่วงประมวลผล และ invalidate query ทันทีเมื่อเปลี่ยนสถานะเสร็จสิ้น |
| **To-do 5** | Format FastAPI 422 errors | Frontend | จัดการแปลงข้อผิดพลาดอาร์เรย์ของการตรวจสอบฟิลด์ส่งค่า (fastapi 422) ให้อ่านรู้เรื่อง |
| **To-do 6** | Document `CHECK_TIMEOUT_SECONDS` | Backend | บันทึกคำอธิบายตัวเลือกเวลาในการตั้งค่าระบบทั้งหมดไว้ใน `.env.example` |

---

## 🛠️ รายละเอียดไฟล์ที่มีการเปลี่ยนแปลง (Files Modified)

### 🖥️ ฝั่งระบบหลังบ้าน (Backend)

* **[NEW] [config.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/schemas/config.py)**: สร้าง Pydantic Schema สำหรับกำหนดรูปแบบข้อมูลการตั้งค่าความต่าง
* **[NEW] [config.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/api/routes/config.py)**: เพิ่ม API Endpoint `GET /config`
* **[MODIFY] [main.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/main.py)**: ลงทะเบียน API Router ชุดใหม่
* **[MODIFY] [test_api_routes.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/tests/test_api_routes.py)**: เพิ่มชุดทดสอบ API `/config`
* **[MODIFY] [.env.example](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/.env.example)**: ระบุค่าเริ่มต้น `CHECK_TIMEOUT_SECONDS=90`

### 🎨 ฝั่งระบบหน้าบ้าน (Frontend)

* **[MODIFY] [target.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/types/target.ts)**: เพิ่มตัวแปร `last_error` ใน Interface
* **[NEW] [config.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/config.ts)**: โมดูล API สำหรับเรียกอ่านข้อมูล `/config`
* **[MODIFY] [client.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/client.ts)**: จัดการรวมข้อความผิดพลาด FastAPI 422 ให้แสดงผลแยกแต่ละฟิลด์อย่างสวยงาม
* **[MODIFY] [client.test.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/client.test.ts)**: เพิ่มการทดสอบการรวมข้อความผิดพลาด 422
* **[MODIFY] [useTargetDetail.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/hooks/useTargetDetail.ts)**: ตั้งค่าการดึงข้อมูลตามระยะเวลาที่กำหนดเฉพาะตอนกำลังประมวลผล (Polling) และสร้าง Hook สำหรับอ่านคอนฟิกหลังบ้าน
* **[MODIFY] [TargetStatusBadge.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/components/TargetStatusBadge.tsx)**: ปรับปรุงให้รับค่า `title` แสดงเป็น Tooltip เมื่อชี้เมาส์เหนือ Badge
* **[MODIFY] [TargetListPage.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetListPage.tsx)**: แสดงรายละเอียดข้อความข้อผิดพลาด, ข้อความแจ้งเตือนปุ่มกดซ้ำซ้อน และส่งค่า `last_error` ให้กับ Badge
* **[MODIFY] [TargetDetailPage.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetDetailPage.tsx)**: เพิ่มการแสดงผลกรอบข้อผิดพลาดสีแดงด้านบนเมื่อประมวลผลเว็บล้มเหลว ดึงข้อมูลและ invalidate ข้อมูลเมื่อการตรวจวิเคราะห์สถานะเสร็จสิ้น
* **[MODIFY] [TargetDetailPage.test.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetDetailPage.test.tsx)** & **[TargetListPage.test.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetListPage.test.tsx)**: แก้ไข Mock ข้อมูลระบบการดึงเกณฑ์วิเคราะห์ และ Mock ข้อมูลปุ่มการตรวจวิเคราะห์สำหรับทำการทดสอบฝั่งหน้าบ้าน

---

## 🧪 ผลการรับรองความถูกต้องของระบบ (Verification Status)

> [!TIP]
> การตรวจสอบโค้ดทั้งหมดผ่านเกณฑ์ความปลอดภัย ความพร้อมใช้งาน และการวิเคราะห์โครงสร้างชนิดข้อมูล 100%

* **ฝั่งระบบหลังบ้าน (Backend)**
  * **pytest**: ผ่านการทดสอบทั้งหมด 46/46 ชุดทดสอบ
  * **ruff check**: ผ่านโดยไม่มีคำเตือนหรือข้อผิดพลาดโครงสร้างโค้ด
  * **mypy**: ผ่านโดยไม่มีข้อผิดพลาดการประกาศชนิดข้อมูลใด ๆ
* **ฝั่งระบบหน้าบ้าน (Frontend)**
  * **vitest**: ผ่านการทดสอบทั้งหมด 20/20 ชุดทดสอบ
  * **eslint**: ผ่านโดยไม่มีปัญหาโครงสร้างโค้ดเหลือค้าง
  * **tsc**: ผ่านการตรวจสอบโครงสร้าง Typescript ทั้งหมดโดยไม่มีข้อบกพร่อง
