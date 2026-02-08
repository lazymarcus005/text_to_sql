
# Text-to-SQL Assistant Agent.

**Text-to-SQL and Analytical Assistant Platform**
*(Gemini + LangChain + FastAPI)*

---

## 1. วัตถุประสงค์ของระบบ

Text-to-SQL Assistant Agent. เป็นระบบผู้ช่วยอัจฉริยะที่ออกแบบมาเพื่อ
**ตอบคำถามจากข้อมูลเชิงโครงสร้าง (Structured Data)** โดยอาศัยเทคโนโลยีปัญญาประดิษฐ์เชิงตัวแทน (Agentic AI)

ระบบสามารถ:

* แปลงคำถามภาษาธรรมชาติเป็นคำสั่ง SQL
* ดำเนินการสืบค้นข้อมูลจากฐานข้อมูลอย่างปลอดภัย
* วิเคราะห์ผลลัพธ์ และนำเสนอคำตอบในรูปแบบที่เข้าใจง่าย
* เหมาะสำหรับการใช้งานในบริบท **ภาครัฐ / องค์กร / หน่วยงานขนาดใหญ่**

---

## 2. ขอบเขตการใช้งาน (Scope)

* รองรับการตอบคำถาม **เฉพาะใน domain ที่กำหนดไว้ล่วงหน้า**

  * ตัวอย่าง: ช่วยสรุปการช่วยเหลือในช่วงภัยพิบัติ
* ไม่อนุญาตให้:

  * แก้ไขข้อมูลในฐานข้อมูล
  * ดำเนินการคำสั่งที่อยู่นอกเหนือจาก SELECT
  * ตอบคำถามที่อยู่นอกขอบเขตข้อมูลที่ระบบเข้าถึงได้

---

## 3. คุณสมบัติหลักของระบบ (Key Features)

* **Web-based Chat Interface**

  * รองรับ Markdown, ตาราง, และโค้ด
  * แสดงหลักฐานข้อมูล (SQL / Parameters / Result) แยกจากคำตอบ
* **Streaming Response (Server-Sent Events)**

  * แสดงขั้นตอนการทำงานแบบเรียลไทม์
* **Agent-based Architecture**

  * แยกหน้าที่ชัดเจน ดูแลและขยายระบบได้ง่าย
* **Domain Guard**

  * ป้องกันการใช้งานนอกขอบเขตที่กำหนด
* **Analytical Answering**

  * คำตอบประกอบด้วย:

    * คำตอบสรุป
    * การวิเคราะห์
    * หลักฐานข้อมูล
    * ระดับความมั่นใจ (เป็นเปอร์เซ็นต์)
    * ข้อจำกัดของข้อมูล

---

## 4. สถาปัตยกรรมระบบ (Architecture)

### 4.1 Architecture Diagram (ASCII)

```
+-------------------+
|   Web Browser     |
|  (Chat UI)        |
+---------+---------+
          |
          | HTTP / SSE
          v
+---------+---------+
| FastAPI Backend   |
|  (Orchestration)  |
+---------+---------+
          |
          | Step-based Control Flow
          v
+---------------------------+
|      Domain Guard         |
|  (Keyword / Heuristic)   |
+-------------+-------------+
              |
              v
+---------------------------+
|   TextToSQL Agent         |
|  (Gemini + LangChain)    |
|  - JSON-only output      |
|  - SQL rewrite on error  |
+-------------+-------------+
              |
              v
+---------------------------+
|   SQL Validator           |
|  - Read-only enforcement |
|  - SQL hygiene check     |
+-------------+-------------+
              |
              v
+---------------------------+
|   SQL Execution Layer     |
|  - Timeout control       |
|  - Row limit (sampling)  |
|  - Streaming rows        |
+-------------+-------------+
              |
              v
+---------------------------+
|   Composer Agent          |
|  - Analysis               |
|  - Evidence               |
|  - Confidence (%)         |
+-------------+-------------+
              |
              v
+---------------------------+
|  Response (Markdown)      |
|  + Trace ID               |
+---------------------------+
```

---

## 5. องค์ประกอบของระบบ (System Components)

### 5.1 TextToSQL Agent

* ใช้โมเดล Gemini ผ่าน Google AI Studio
* บังคับรูปแบบผลลัพธ์เป็น JSON
* รองรับการ retry เมื่อ:

  * โครงสร้าง JSON ไม่ถูกต้อง
  * SQL ไม่ผ่านการตรวจสอบ
  * ฐานข้อมูลส่ง error กลับมา (external feedback)
* ห้ามเดา schema ที่ไม่มีอยู่จริง

---

### 5.2 SQL Execution Layer

* รองรับเฉพาะคำสั่ง SELECT
* มีการกำหนด:

  * Statement timeout
  * จำนวนแถวสูงสุด (Row cap)
* ส่งผลลัพธ์กลับแบบ streaming เพื่อรองรับข้อมูลจำนวนมาก

---

### 5.3 Composer Agent

* วิเคราะห์ผลลัพธ์จาก SQL
* จัดทำคำตอบในรูปแบบ Markdown โดยมีโครงสร้างตายตัว
* แสดงระดับความมั่นใจ (%)

  * อิงจากจำนวนข้อมูล
  * การสุ่มตัวอย่าง
  * จำนวนครั้งที่ retry
  * ความครบถ้วนของผลลัพธ์

---

## 6. การติดตั้งและใช้งาน (Deployment)

### 6.1 การติดตั้งในเครื่อง (Local Deployment)

```bash
cp .env.example .env
# กำหนด GOOGLE_API_KEY จาก https://aistudio.google.com/api-keys
docker compose up --build
```

### 6.2 การเข้าใช้งาน

* Web Interface: `http://localhost:8000`

---

## 7. API Interface

### POST `/query/stream`

ใช้สำหรับเรียกแบบ streaming

ตัวอย่าง:

```bash
curl -X POST http://localhost:8000/query/stream \
  -H "Content-Type: application/json" \
  -d '{"user_prompt":"ตอนนี้มีภัยพิบัติอะไรบ้าง"}'
```

---

### POST `/query/stream`

ใช้สำหรับเรียกแบบ streaming (SSE)

Event ที่รองรับ:

* `step`
* `sql`
* `rows`
* `answer`
* `error`
* `done`

---

## 8. ความปลอดภัยและความน่าเชื่อถือ

* จำกัด domain ของคำถาม
* ป้องกัน SQL Injection ด้วย:

  * SQL validation
  * Parameterized query
* Prompt ของ LLM ผ่านการ escape ตัวแปรพิเศษ
* ไม่อนุญาตให้แก้ไขข้อมูลในฐานข้อมูล

---

## 9. หมายเหตุ

ระบบนี้ถูกออกแบบเป็น **โครงสร้างต้นแบบเชิงผลิต (Production-oriented Skeleton)**
เหมาะสำหรับ:

* หน่วยงานภาครัฐ
* องค์กรขนาดใหญ่
* ระบบข้อมูลภายใน (Internal Data Assistant)

สามารถนำไปต่อยอดเพื่อ:

* เชื่อมต่อฐานข้อมูลจริง
* เพิ่มระบบยืนยันตัวตน (Authentication / Authorization)
* บันทึก log และ audit trail
* รองรับหลาย domain พร้อมกัน

---