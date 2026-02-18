# Data Dictionary + Relationships (สำหรับให้ LLM สร้าง Query ได้)

> โครงนี้มาจากตาราง metadata ที่ให้มา (คอลัมน์: `collection_name, name, raw_title, type, interface` ฯลฯ)
> เป้าหมาย: ให้ LLM รู้ว่า “จะ JOIN/กรอง/สรุปผล” ยังไง โดยดูจาก `belongsTo / hasMany / belongsToMany / belongsToArray`

---

## 1) ภาพรวมโดเมน (Disaster Relief Flow)

**แกนหลักของข้อมูล**
- **B00 (`b000_open_disaster`)** = “ประกาศเขตพื้นที่ภัย (ระดับประกาศ)”
- **B10 (`b100_disaster_area`)** = “พื้นที่ประสบภัย/พื้นที่ประกาศช่วยเหลือ (ระดับพื้นที่: จว/อ/ต/หมู่บ้าน)”
- **EX01 (`b10ex01`)** = “เกษตรกร/ฟาร์ม + จำนวนสัตว์ (ดึงข้อมูล)”
- **B20 (`b20_init_help`)** = “การช่วยเหลือเบื้องต้น (สรุปยอดช่วยเหลือเป็นหัวข้อ)”
  - แตกย่อย: **B21 (อาหารสัตว์), B22 (อพยพสัตว์), B23 (รักษา)**
- **B30 (`b30_init_damage`)** = “ความเสียหายเบื้องต้น”
  - แตกย่อย: **B31 (จำนวนความเสียหายแยกตามประเภทสัตว์)**
- **C10 (`c10_request_for_relief`)** = “คำขอรับการช่วยเหลือ (กษ.01)”
  - แตกย่อย: C11 (ไม่ได้อยู่ในชุดนี้ แต่มี relation), C103 (เอกสาร)
- **C102 (`c102_request_for_relief`)** = “คำขอรับการช่วยเหลือ (กษ.02 หมู่บ้าน)”
- **SPS01/02/03 (`tbl_sps01/02/03`)** = “ตารางสรุป/รายงานตามรอบ (รายพื้นที่)”
  - SPS02 Help Log / SPS03 Damage Log = “ประวัติ log รายวัน/ตามรอบ”
  - SPS02 Round Report / SPS03 Round Report = “ออกรายงานเป็นรอบ”

---

## 2) กติกาอ่านความสัมพันธ์จาก type/interface

ใช้ rules นี้เพื่อให้ LLM สร้าง JOIN ได้แบบไม่หลง:

- `belongsTo` (m2o)  
  => ตารางนี้มี FK ไปอีกตาราง (หลายแถว → 1 แถวปลายทาง)  
  **JOIN**: `this.<xxx_id> = target.id`

- `hasMany` (o2m)  
  => ตารางนี้เป็น parent, ปลายทางมี FK กลับมา  
  **JOIN**: `child.<parent_id> = parent.id`

- `belongsToMany` (attachment)  
  => เป็น many-to-many หรือเป็น resource แนบไฟล์  
  **JOIN**: แล้วแต่ระบบจัด attachment (มักมี junction table)  
  > ในชุดนี้เห็น `request_for_assistance` เป็น attachment

- `belongsToArray` (mbm)  
  => เก็บ array ของ id (เช่น set/json)  
  **Filter/Join**: ใช้ `ANY/IN/contains` แล้วแต่ DB (Postgres: `= ANY()` / `@>`)

---

## 3) Entity / Table Cheat Sheet (What is it + Key fields + Relations)

### 3.1 `b000_open_disaster` (B00) — ประกาศเขตพื้นที่ภัย (หัวประกาศ)
**คีย์หลัก**
- `id` (PK)
- `name` (ชื่อประกาศ)
- `start_at`, `end_at` (ช่วงประกาศ)
- `status_id` (belongsTo: สถานการณ์ปัจจุบัน)
- ไฟล์: `attached_file`

**ความสัมพันธ์สำคัญ**
- hasMany → `open_disaster_b10` (B10)
- hasMany → `c102_request_for_relief` (C102)
- hasMany → `ex02_ids` (EX02 จำนวนสัตว์ - มีชื่อ แต่ตารางไม่อยู่ในชุดนี้)
- hasMany → `sps01_b00`, `sps02_round_b00`, `sps03_round_b00`

**ใช้ทำ Query แนวไหน**
- หา “ประกาศไหน” ครอบช่วงเวลา X
- drill down ไปพื้นที่ (B10), คำขอ (C10/C102), รายงาน (SPS)

---

### 3.2 `b100_disaster_area` (B10) — พื้นที่ประสบภัย/ประกาศเขตช่วยเหลือ
**คีย์หลัก**
- `id` (PK)
- วันที่: `annonced_date` (ประกาศ), `end_annonced` (ปิดภัย)
- ที่ตั้ง: `province_id`, `amphur_id`, `tambon_id`, `village_id`
- อ้างอิงไป B00: มีทั้ง `b10_open_disaster_id`/`open_disaster_ids` (belongsTo)
- สถานะงาน: `sps1_status_id`, `sps2_status_id`, `sps3_status_id`, `eregis_status_id`, `status_id`
- ไฟล์: `attached_file`, `end_attachment`

**ความสัมพันธ์สำคัญ**
- belongsTo → `province`, `amphur`, `tambon`, `village`, `disaster_type`, `open_disaster_ids(B00)`
- hasMany → `c10_request_for_relief` (C10)
- hasMany → `c102_request_for_relief` (C102)
- hasMany → `b10ex01_b10` (EX01 เกษตรกร)
- hasMany → `b40_b10` (B40 quota), `b41_b10` (B41 rate)
- belongsToArray → `m04many` (หมู่บ้านหลายหมู่)

**ใช้ทำ Query แนวไหน**
- แสดงพื้นที่ประสบภัยตามจังหวัด/อำเภอ/ตำบล/หมู่บ้าน
- join ไปคำขอ/เกษตรกร/สรุปช่วยเหลือ-เสียหาย

---

### 3.3 `b10ex01` (EX01) — เกษตรกร/ฟาร์ม + จำนวนสัตว์
**คีย์หลัก**
- `id` (PK)
- อ้างอิงพื้นที่: `b10_id` (FK ไป B10)
- ข้อมูลเกษตรกร: `farmer_pid`, `farmer_name`, `mobile_no`, ที่อยู่ฟาร์ม ฯลฯ
- จำนวนสัตว์รวมตามประเภท: `l_11000000` (โคเนื้อ), `l_12000000` (โคนม), …, `l_19000000` (อื่นๆ), `l_20000000` (นกกระทา)

**ความสัมพันธ์**
- belongsTo → `b10_b10ex01` (B10)

**ใช้ทำ Query แนวไหน**
- รวมจำนวนสัตว์ในพื้นที่/ประกาศ
- หาเกษตรกรในพื้นที่แล้วคำนวณสิทธิ/ผลกระทบ

---

### 3.4 `b20_init_help` (B20) — ช่วยเหลือเบื้องต้น (สรุปรวม)
**คีย์หลัก**
- `id` (PK)
- `farmer_id` (FK ไป EX01/เกษตรกร)
- `disaster_area_id` (FK ไป B10)
- ค่าสรุป: `total_feed_count`, `total_move_animal_count`, `total_healthcare_count`, `total_relief_bags`
- breakdown รวม: `feed_1`, `feed_2`, `health_1`, `health_2`

**ความสัมพันธ์**
- belongsTo → `farmer` (EX01), `disaster_area` (B10), `status_id`
- hasMany → `feed_count` (B21), `move_animal_count` (B22), `healthcare_count` (B23)

**ใช้ทำ Query แนวไหน**
- รวมการช่วยเหลือเบื้องต้นต่อพื้นที่/ต่อช่วงเวลา
- join เด็ก ๆ (B21/22/23) เพื่อแตกประเภท

---

### 3.5 `b21_feed_count` (B21) — รายการอาหารสัตว์ที่ช่วยเหลือ
**คีย์หลัก**
- `id` (PK)
- `b20_init_help_id` (FK → B20)
- `feed_type_id` (FK → M06 ประเภทอาหาร)
- `amount`

**ความสัมพันธ์**
- belongsTo → `b20_init_help`, `feed_type`, `sps02hl_b21` (log)

---

### 3.6 `b22_move_animal` (B22) — รายการอพยพสัตว์
**คีย์หลัก**
- `id` (PK)
- `b20_init_help` (น่าจะ FK → B20 แม้ชื่อคอลัมน์แปลก)
- `animal_type_id`, `migration_point_id`
- `amount`
- `sps02hl_b22_id` (FK → log)

**ความสัมพันธ์**
- belongsTo → `animal_type`, `migration_point`, `sps02hl_b22`

---

### 3.7 `b23_healthcare_count` (B23) — รายการรักษาสัตว์
**คีย์หลัก**
- `id` (PK)
- `b20_init_help_id` (FK → B20)
- `healthcare_type_id`
- `amount`
- `sps02hl_b23_id` (FK → log)

**ความสัมพันธ์**
- belongsTo → `b20_init_help`, `healthcare_type`, `sps02hl_b23`

---

### 3.8 `b30_init_damage` (B30) — ความเสียหายเบื้องต้น (สรุปรวม)
**คีย์หลัก**
- `id` (PK)
- `disaster_area_id` (FK → B10)
- `farmer_id` (FK → EX01)
- `total_damage`, `total_animal`

**ความสัมพันธ์**
- belongsTo → `disaster_area`, `farmer`, `status_id`
- hasMany → `b31_damage_count`

---

### 3.9 `b31_damage_count` (B31) — ความเสียหายแยกตามประเภทสัตว์
**คีย์หลัก**
- `id` (PK)
- `b30_init_damage_id` (FK → B30)
- `animal_type_id`
- `amount`
- มีทั้ง `farmer_id`, `disaster_area_id` (ช่วย filter เร็วขึ้น)

**ความสัมพันธ์**
- belongsTo → `b30_init_damage`, `animal_type`

---

### 3.10 `b40_help_quata_area` (B40) — โควต้า/สิทธิการช่วยเหลือ (ตามระเบียบ)
**คีย์หลัก**
- `id` (PK)
- `b00_b40_id` (FK → B00), `b10_b40_id` (FK → B10), `c10_b40_id` (FK → C10)
- `m05_b40_id` (FK → ประเภทสัตว์)
- `help_quota` (จำนวน/วงเงินโควต้า)

**ความสัมพันธ์**
- belongsTo → `b00_b40`, `b10_b40`, `m05_b40`

---

### 3.11 `b41_assis_rate_area` (B41) — อัตราการช่วยเหลือ (ตามระเบียบ)
**คีย์หลัก**
- `id` (PK)
- `b00_b41_id` (FK → B00), `b10_b41_id` (FK → B10), `b41_c10_id` (FK → C10)
- `m05_b41_id` (ประเภทสัตว์), `m09_b41_id` (ประเภทย่อย)
- `help_rate` (อัตราช่วยเหลือ)

**ความสัมพันธ์**
- belongsTo → `b00_b41`, `b10_b41`, `m05_b41`, `m09_b41`

---

### 3.12 `c10_request_for_relief` (C10) — คำขอรับการช่วยเหลือ (กษ.01)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_open_disaster_id` (→ B00), `b10_disaster_area_id` (→ B10), `farmer_id` (→ EX01)
- ช่วงภัย: `start_date`, `end_date`
- การอนุมัติ: `approved_status`, `approved_by`, `approved_at`
- งบ: `government_budget`, `permanent_secretary_budget`, `organization_assis_amont`, `value_assis_amount`
- `total_request_damage`
- attachments: `request_for_assistance`

**ความสัมพันธ์**
- belongsTo → `farmer`, `b00_open_disaster`, `b10_disaster_area_id`
- hasMany → `c11_request_damage_count`, `b40_c10`, `b41_c10`, `c103_c10`

---

### 3.13 `c101_request_area` — คำขอรับการช่วยเหลือระดับ “พื้นที่”
**คีย์หลัก**
- `id` (PK)
- FK: `b00_open_disaster_id`, `b10_disaster_area_id`
- งบ + `value_assis_amount`
- สถานะ: `status`, `level_area`

**ความสัมพันธ์**
- belongsTo → `b10_disaster_area`, `b00_open_disaster`
- hasMany → `c103_c101`

---

### 3.14 `c102_request_for_relief` (C102) — คำขอรับการช่วยเหลือ (กษ.02 หมู่บ้าน)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_open_disaster_id`, `b10_disaster_area_id`, `farmer_id`
- location: `province_id`, `amphur_id`, `tambon_id`, `village_id`
- linkage: `c10_id` (ชี้ไป C10)
- approval: `approved_status`, `approved_by`, `approved_at`

**ความสัมพันธ์**
- belongsTo → `b00_open_disaster`, `b10_disaster_area`, `farmer`, `province/amphur/tambon/village`

---

### 3.15 `tbl_sps01` — SPS01 (ยืนยันจำนวนสัตว์ รายพื้นที่)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps01_id` (→ B00), `b10_sps01_id` (→ B10), `m01/02/03/04` (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน), `m08` (ประเภทภัย)
- metrics: `total_*` และ `help_*`, `grand_total`, `grand_help_total`, `total_animals`, `total_farmers`
- status: `sps01_status`
- date: `annonced_date` (วันที่เกิดภัย)

**ความสัมพันธ์**
- belongsTo → B00, B10, M01-04, M08

---

### 3.16 `tbl_sps02` — SPS02 (สรุปช่วยเหลือเฉพาะหน้า รายวัน/รายรอบ)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps02_id` (→ B00), `b10_sps02_id` (→ B10), `m01-04`
- รอบรายงาน: `sps02_round_sps02_id` (→ SPS02 round)
- date: `sps02_round_date`
- metrics: `total_*` (สัตว์), `feed_1/2`, `health_1/2`, `total_relief_bags`, `total_farmers`, `total_animals`
- status: `sps02_status`

**ความสัมพันธ์**
- belongsTo → B00, B10, M01-04, `sps02_round_sps02`

---

### 3.17 `tbl_sps02_help_log` — Log การช่วยเหลือ (เชื่อม B21/B22/B23)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps02hl_id` (→ B00), `b10_sps02hl_id` (→ B10)
- FK: `sps02rr_sps02hl_id` (→ SPS02 round report), `sps02_sps02hl_id` (→ SPS02)
- totals: `total_farmers`, `total_relief_bags`

**ความสัมพันธ์**
- belongsTo → B00, B10, SPS02 round, SPS02
- hasMany → `b21_sps02hl`, `b22_sps02hl`, `b23_sps02hl`

---

### 3.18 `tbl_sps02_round_report` — รายงานรอบ SPS02
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps02_round_id` (→ B00)
- `round_date`, `round_date_status`

**ความสัมพันธ์**
- belongsTo → B00
- hasMany → `sps02hl_sps02rr` (help logs), `sps02_sps02_round` (ตารางสรุป)

---

### 3.19 `tbl_sps03` — SPS03 (สรุปความเสียหาย + สะสม)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps03_id` (→ B00), `b10_sps03_id` (→ B10), `m01-04`
- รอบรายงาน: `sps03_round_sps03_id`
- date: `sps03_round_date`
- metrics: `total_*` (ยอดรอบนี้), `collect_*` (ยอดสะสม), `total_farmers`
- status: `sps03_status`

**ความสัมพันธ์**
- belongsTo → B00, B10, M01-04, `sps03_round_sps03`
- hasMany → `sps03dl_sps03` (damage log)

---

### 3.20 `tbl_sps03_damage_log` — Log ความเสียหาย (เชื่อม B31)
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps03dl_id` (→ B00), `b10_sps03dl_id` (→ B10)
- FK: `sps03rr_sps03dl_id` (→ SPS03 round report), `sps03_sps03dl_id` (→ SPS03)
- totals: `total_farmers`

**ความสัมพันธ์**
- belongsTo → B00, B10, SPS03 round, SPS03
- hasMany → `b31_sps03dl` (B31)

---

### 3.21 `tbl_sps03_round_report` — รายงานรอบ SPS03
**คีย์หลัก**
- `id` (PK)
- FK: `b00_sps03_round_id` (→ B00)
- `round_date`, `round_date_status`

**ความสัมพันธ์**
- belongsTo → B00
- hasMany → `sps03_sps03_round`

---

## 4) Join Paths ที่พบบ่อย (Query Patterns)

### A) จาก “ประกาศภัย (B00)” ไป “พื้นที่ (B10)”
- `b100_disaster_area.open_disaster_ids (belongsTo) -> b000_open_disaster.id`
- หรือถ้าใช้ FK อีกชื่อ: `b100_disaster_area.b10_open_disaster_id -> b000_open_disaster.id`

### B) จาก “พื้นที่ (B10)” ไป “เกษตรกร (EX01)”
- `b10ex01.b10_id -> b100_disaster_area.id`

### C) จาก “พื้นที่/เกษตรกร” ไป “ช่วยเหลือเบื้องต้น (B20)”
- `b20_init_help.disaster_area_id -> b100_disaster_area.id`
- `b20_init_help.farmer_id -> b10ex01.id (หรือ id เกษตรกรตามระบบ)`

### D) แตก “รายละเอียดช่วยเหลือ” จาก B20
- `b21_feed_count.b20_init_help_id -> b20_init_help.id`
- `b22_move_animal.(b20_init_help FK) -> b20_init_help.id`
- `b23_healthcare_count.b20_init_help_id -> b20_init_help.id`

### E) จาก “พื้นที่/เกษตรกร” ไป “ความเสียหาย (B30/B31)”
- `b30_init_damage.disaster_area_id -> b100_disaster_area.id`
- `b31_damage_count.b30_init_damage_id -> b30_init_damage.id`

### F) จาก “คำขอ (C10/C102)” ไป “โควต้า/อัตรา (B40/B41)”
- `b40_help_quata_area.c10_b40_id -> c10_request_for_relief.id`
- `b41_assis_rate_area.b41_c10_id -> c10_request_for_relief.id`
- และเชื่อมตามประกาศ/พื้นที่ด้วย `b00_*`, `b10_*`

### G) รายงานสรุป (SPS) เชื่อมกับ B00/B10 + Location
- SPS01/02/03 มี FK ไป `b00_*_id`, `b10_*_id`, `m01-04`
- Logs (SPS02_help_log, SPS03_damage_log) เชื่อมไป round report + ตัวตาราง SPS + B00/B10

---

## 5) ตัวอย่าง “Intent → SQL Sketch” (ให้ LLM ยึดเป็นแพทเทิร์น)

### 5.1 “สรุปจำนวนสัตว์ในพื้นที่ประกาศ (B00) แยกตามจังหวัด”
- Start: `b000_open_disaster` filter by `id` หรือ date range
- Join: B10 → จังหวัด
- Aggregate จาก: `b10ex01.l_*` sum (หรือใช้ SPS01 totals ถ้าต้องการแบบยืนยันแล้ว)

### 5.2 “ยอดช่วยเหลือถุงยังชีพรายวันใน B10”
- Start: `tbl_sps02` filter `b10_sps02_id = :b10Id`
- Use `sps02_round_date` group by date
- Select `total_relief_bags`, `total_farmers`, `total_animals`

### 5.3 “รายละเอียดอาหารสัตว์ที่ช่วยเหลือ (ชนิดอาหาร + จำนวน) ในช่วงวัน X-Y”
- Start: `tbl_sps02_help_log` filter date via join `tbl_sps02` หรือ round report date
- Join: `b21_feed_count` (ผ่าน relation `b21_sps02hl`) + `feed_type`
- Group by `feed_type.name`

> หมายเหตุ: ชื่อ FK ใน log เด็ก ๆ ใช้ pattern `sps02hl_b21_id` ฯลฯ

---

## 6) Mapping คำศัพท์ไทย → Entity (ช่วย LLM เลือก table ได้ไว)

- “ประกาศพื้นที่ภัย” → `b000_open_disaster` (B00)
- “พื้นที่ประสบภัย / เขตช่วยเหลือ” → `b100_disaster_area` (B10)
- “เกษตรกร / ฟาร์ม / จำนวนสัตว์” → `b10ex01` (EX01)
- “ช่วยเหลือเบื้องต้น / ถุงยังชีพ / อพยพ / รักษา / อาหารสัตว์” → `b20_init_help` + `b21/b22/b23`
- “ความเสียหาย” → `b30_init_damage` + `b31_damage_count`
- “คำขอ กษ.01” → `c10_request_for_relief`
- “คำขอ กษ.02 หมู่บ้าน” → `c102_request_for_relief`
- “รายงาน ศปส.1” → `tbl_sps01`
- “รายงาน ศปส.2” → `tbl_sps02` + `tbl_sps02_help_log` + `tbl_sps02_round_report`
- “รายงาน ศปส.3” → `tbl_sps03` + `tbl_sps03_damage_log` + `tbl_sps03_round_report`
- “โควต้า/อัตราช่วยเหลือ (ตามระเบียบ)” → `b40_help_quata_area`, `b41_assis_rate_area`

---
