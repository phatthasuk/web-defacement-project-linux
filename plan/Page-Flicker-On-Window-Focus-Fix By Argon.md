# Remediation Plan: Page Flicker on Window Focus / Tab Switch

**Date**: October 16, 2026  
**Author**: Argon  
**Document**: `plan/Page-Flicker-On-Window-Focus-Fix By Argon.md`  
**Status**: Proposed Plan (Pending Implementation)

---

## 1. สรุปปัญหา (Problem Summary)

เมื่อผู้ใช้งานสลับไปหน้าต่างอื่น แท็บอื่น หรือคลิกออกไปนอกพื้นที่เว็บเพจ (เช่น Address Bar, DevTools, หรือโปรแกรมอื่น) แล้วคลิกกลับเข้ามาที่หน้าเว็บ จะเกิดอาการ **หน้าเพจกระพริบ (Page Flicker / Flash)** ไปเป็นหน้าจอดำพร้อมไอคอนหมุนโหลดชั่วขณะ ก่อนจะกลับมาแสดงหน้าเพจเดิม

นอกจากอาการกระพริบทางสายตาแล้ว การที่หน้าเพจถูกถอดออก (Unmount) และสร้างใหม่ (Remount) ทุกครั้งที่เกิด Window Focus ยังทำให้ **Local UI State ของหน้าเพจถูกรีเซ็ตทั้งหมด** เช่น:
- Modal ที่เปิดค้างไว้ถูกปิดลงเอง (เช่น Edit Target Modal, Baseline Manager Modal, Screenshot Preview Modal)
- ข้อความที่กำลังพิมพ์ค้างไว้ในฟอร์มหรือช่องค้นหาหายไป
- ตำแหน่งการเลื่อนหน้าจอ (Scroll Position) กระตุกหรือรีเซ็ต

---

## 2. การวิเคราะห์สาเหตุเชิงลึก (Root Cause Analysis)

### 2.1 ตัวจุดชนวน: `window.addEventListener('focus', ...)` ใน `frontend/src/hooks/useAuth.tsx`

ใน [`AuthProvider`](../frontend/src/hooks/useAuth.tsx) มีการผูก Event Listener กับ `window` `'focus'`:

```tsx
useEffect(() => {
  const onFocus = () => {
    setReloadKey((key) => key + 1);
    void queryClient.invalidateQueries();
  };
  ...
  window.addEventListener('focus', onFocus);
```

ทุกครั้งที่ผู้ใช้คลิกกลับมาที่หน้าเว็บ เบราว์เซอร์จะยิง Event `focus` ทันที ทำให้:
1. `reloadKey` เพิ่มค่าขึ้น `1` และไปกระตุ้น `useEffect` ที่รัน `checkAuth()`
2. `queryClient.invalidateQueries()` สั่ง Invalidate ทุก Query ในระบบพร้อมกัน

### 2.2 ต้นเหตุหลักของการกระพริบ: การตั้ง `setIsLoading(true)` ซ้ำใน Background Revalidation

ใน `useEffect` สำหรับตรวจสอบสิทธิ์ (`checkAuth` ใน [`frontend/src/hooks/useAuth.tsx`](../frontend/src/hooks/useAuth.tsx)):

```tsx
useEffect(() => {
  let cancelled = false;

  async function checkAuth() {
    setIsLoading(true); // <-- ต้นเหตุหลัก! ถูกเรียกซ้ำแม้ว่าจะมี user ล็อกอินอยู่แล้ว
    try {
      const auth = await apiFetch<AuthResponse>('/auth/me');
      if (cancelled) return;
      applyAuth(auth);
    } catch (error) {
      if (cancelled) return;
      setUser(null);
      setCsrfToken(null);
      setAuthError(!(error instanceof ApiError && error.status === 401));
    } finally {
      if (!cancelled) setIsLoading(false);
    }
  }

  checkAuth();
  return () => {
    cancelled = true;
  };
}, [applyAuth, reloadKey]);
```

เมื่อ `setIsLoading(true)` ถูกเรียกในจังหวะที่มี `user` อยู่แล้ว คอมโพเนนต์ [`ProtectedRoute`](../frontend/src/App.tsx) ใน `frontend/src/App.tsx` จะเข้าเงื่อนไข `if (isLoading)` ทันที:

```tsx
if (isLoading) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
    </div>
  );
}
```

**ผลที่เกิดขึ้น:**
1. `<ProtectedRoute>` ถอด `children` (หน้าเพจทั้งหมด) ออกจาก DOM Tree และแสดงหน้า Loading สีดำแทน
2. เมื่อ `GET /api/auth/me` ตอบกลับ (ภายในไม่กี่มิลลิวินาที) `setIsLoading(false)` จะทำงาน
3. `<ProtectedRoute>` นำ `children` กลับมา Mount ใหม่ตั้งแต่ต้น จึงเกิดภาพกระพริบและล้าง State ของคอมโพเนนต์ลูกทั้งหมด

### 2.3 ความเปราะบางเมื่อเกิด Network Error ชั่วคราวระหว่าง Background Check

ในโค้ดปัจจุบัน หากผู้ใช้ล็อกอินอยู่แล้ว แต่จังหวะที่คลิกกลับมาที่หน้าต่างเกิด Network สะดุดชั่วคราว (หรือ Server ตอบ `502`/`503` ชั่วขณะ) บล็อก `catch` ของ `checkAuth()` จะสั่ง `setUser(null)` และ `setAuthError(true)` ทันที ทำให้หน้าเพจที่ผู้ใช้กำลังเปิดทำงานอยู่ถูกแทนที่ด้วยหน้า Error เต็มจอ ทั้งที่เป็นเพียงการเช็คซ้ำเบื้องหลัง

### 2.4 การยิง API ถี่เกินความจำเป็นเมื่อคลิกสลับหน้าต่างไปมา

- Event `window` `'focus'` ทำงานบ่อยมาก (เช่น คลิกสลับระหว่าง 2 จอ, คลิกเปิด/ปิด DevTools, คลิกที่ Address Bar แล้วคลิกกลับเข้าหน้าเว็บ)
- ใน `frontend/src/App.tsx` ตั้งค่า `refetchOnWindowFocus: false` ใน `QueryClient` เอาไว้ แต่ `onFocus` ใน `useAuth.tsx` กลับเรียก `queryClient.invalidateQueries()` ทุกครั้งโดยไม่มี Cooldown ทำให้เกิดการยิง `/auth/me` และรีเฟรช Query ทั้งหมดซ้ำๆ แม้จะเพิ่งเช็คไปเมื่อ 1 วินาทีก่อนหน้า

---

## 3. แนวทางการแก้ไขที่แนะนำ (Recommended Solution)

ใช้แนวทาง **Silent Background Revalidation + Cooldown Throttling** เพื่อให้ได้ทั้ง UX ที่ลื่นไหล (ไม่มีการกระพริบ 100%) และยังคงความปลอดภัยในการตรวจสอบสถานะ Session/Role ของผู้ใช้เมื่อสลับหน้ากลับมา

### Step 1: แยก Initial Auth Load ออกจาก Silent Background Check ใน `useAuth.tsx`

1. **ไม่ตั้ง `isLoading = true` เมื่อมี `user` อยู่แล้ว:**
   - ให้ `isLoading` เป็น `true` เฉพาะตอนเปิดแอปครั้งแรกที่ยังไม่มีข้อมูล `user` (Initial Load) หรือเมื่อผู้ใช้กดปุ่ม `Retry` จากหน้า `authError` เท่านั้น
   - เมื่อเป็นการตรวจสอบซ้ำเบื้องหลัง (Background Revalidation ตอน Focus/Visibility เปลี่ยน) ให้เรียก `GET /api/auth/me` แบบเงียบๆ โดยไม่เปลี่ยน `isLoading` เป็น `true`
2. **การจัดการผลลัพธ์ของ Silent Background Check:**
   - **กรณีสำเร็จ (`200 OK`):** เรียก `applyAuth(auth)` ตามปกติ
     - หากยังคงเป็นผู้ใช้คนเดิมและสิทธิ์เดิม หน้าเพจจะไม่กระพริบและไม่ถูก Unmount
     - หาก Admin เปลี่ยน `role`, บังคับ `must_change_password`, หรือเปลี่ยน User ในอีกแท็บหนึ่ง React จะอัปเดต UI/Redirect ตามสิทธิ์ใหม่ทันที
   - **กรณี `401 Unauthorized`:** ล้าง `user = null`, `setCsrfToken(null)`, `setAuthError(false)`, และ `queryClient.clear()` เพื่อส่งผู้ใช้กลับไปหน้า `/login` ทันทีตามปกติ
   - **กรณี Network / 5xx Error ชั่วคราว:**
     - หากเป็น **Initial Load** (ยังไม่มี `user`): ตั้งค่า `setAuthError(true)` เพื่อแสดงหน้า Retry ตามเดิม
     - หากเป็น **Background Check** (มี `user` อยู่แล้ว): **ไม่ล้าง `user` ทิ้ง และไม่ตั้ง `authError = true`** เพื่อไม่ให้หน้างานที่ผู้ใช้กำลังเปิดดูอยู่พังลงเพราะเน็ตกระตุกชั่วคราว (ปล่อยให้การเรียก API จริงหรือรอบถัดไปจัดการแทน)

### Step 2: เพิ่ม Cooldown ให้การเช็คตอน Focus / Visibility Change

1. กำหนดระยะเวลา Cooldown สั้นๆ (เช่น `FOCUS_REVALIDATE_COOLDOWN_MS = 15_000` หรือ 15 วินาที) โดยเก็บ Timestamp ของการเช็ค `/auth/me` ที่สำเร็จล่าสุด (`lastCheckedAtRef`)
2. เมื่อเกิด Event `focus` บน `window` หรือ `visibilitychange` (เมื่อ `document.visibilityState === 'visible'`):
   - ตรวจสอบว่าเวลาปัจจุบันห่างจาก `lastCheckedAtRef.current` เกินกว่า Cooldown หรือยัง
   - หากยังไม่เกิน Cooldown ให้ข้ามการยิง `/auth/me` และ `invalidateQueries()` เพื่อป้องกันการยิง API รัวๆ เวลาผู้ใช้คลิกเมาส์สลับหน้าต่างไปมาในระยะเวลาสั้นๆ
   - หากเกิน Cooldown แล้ว ให้สั่ง Revalidate `/auth/me` แบบเงียบๆ และ `invalidateQueries()` ตามปกติ

---

## 4. รายละเอียดไฟล์ที่จะแก้ไข (Files to Modify)

1. **`frontend/src/hooks/useAuth.tsx`**
   - ปรับปรุง `checkAuth` เพื่อแยกพฤติกรรมระหว่าง Initial Load / Explicit Retry กับ Silent Background Revalidation (โดยใช้ `useRef` เก็บสถานะว่ามี `user` อยู่แล้วหรือไม่ หรือแยกโหมดการทำงาน)
   - ป้องกันการล้าง `user` และแสดงหน้า Error ทับหน้าเดิมเมื่อเกิด Transient Network/5xx Error ระหว่าง Background Check
   - เพิ่ม Cooldown (`15_000 ms`) สำหรับ `focus` / `visibilitychange` listener เพื่อลดการยิง API ซ้ำซ้อน

2. **`frontend/src/hooks/useAuth.test.tsx`**
   - เพิ่ม Unit Tests ครอบคลุมกรณีต่อไปนี้:
     1. **No Flicker on Window Focus:** เมื่อล็อกอินสำเร็จแล้ว และเกิด Event `window` `'focus'` ต้องเรียก `/auth/me` เบื้องหลังโดยที่ `isLoading` ไม่กลับไปเป็น `true` (คอมโพเนนต์ลูกไม่ถูก Unmount เป็น `loading`)
     2. **Session Expiry on Focus (`401`):** เมื่อเกิด `window` `'focus'` แล้ว `/auth/me` ตอบ `401` ต้องล้างสถานะผู้ใช้และเปลี่ยนเป็น `logged-out`
     3. **Transient Error Resilience on Background Focus:** เมื่อล็อกอินอยู่แล้ว เกิด `window` `'focus'` แล้ว `/auth/me` ตอบ `500` หรือ Network Error ชั่วคราว ต้องยังคงรักษาสถานะ `user` เดิมไว้และไม่ขึ้นหน้า `authError`
     4. **Focus Cooldown Throttling:** หากเกิด `focus` ซ้ำติดๆ กันภายในช่วง Cooldown จะไม่ยิง `/auth/me` ซ้ำซ้อน

---

## 5. แผนการตรวจสอบ (Verification Plan)

1. รันชุดทดสอบ Unit Test ของ Frontend:
   ```bash
   cd frontend && npx vitest run src/hooks/useAuth.test.tsx
   ```
2. รันชุดทดสอบทั้งหมดของ Frontend เพื่อยืนยันว่าไม่มีผลกระทบต่อส่วนอื่น:
   ```bash
   cd frontend && npx vitest run
   ```
3. ทดสอบใช้งานจริงบนเบราว์เซอร์:
   - เปิดหน้า Website List หรือ Target Detail (ลองเปิด Modal หรือพิมพ์ในช่องค้นหาค้างไว้)
   - สลับไปแท็บอื่นหรือโปรแกรมอื่น แล้วคลิกกลับมาที่หน้าเว็บ
   - ยืนยันว่าหน้าเพจไม่กระพริบ ไม่มีวงกลมโหลดคั่น และ Modal/ข้อความในช่องค้นหายังอยู่ครบ
