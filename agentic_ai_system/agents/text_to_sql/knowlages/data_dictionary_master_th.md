````md
# Master Tables (MySQL) + วิธี Join กับ Transaction Tables (ให้ LLM สร้าง SQL ได้)

> DB: **MySQL**
> โฟกัส: ตาราง Master (M*) ที่ใช้เป็น dimension สำหรับ JOIN/Filter/Group ใน Transaction (B00/B10/EX01/B20/B30/C10/C102/SPS*)

---

## 1) Master Tables ที่มีในชุดนี้ (Dimension)

### 1.1 `m_province` (จังหวัด)
**PK**
- `id`

**Fields สำคัญ**
- `province_name` (ชื่อจังหวัด)
- `province_id` (เหมือนไอดีภายนอก/ไอดีซ้ำซ้อน — ใช้ตามที่ transaction อ้าง)
- `l440_m01` (belongsTo → เขตปศุสัตว์)

**ใช้ทำอะไร**
- Group/Filter รายจังหวัด
- Join จาก B10/C102/SPS01-03 ผ่าน `province_id`

---

### 1.2 `m_amphur` (อำเภอ)
**PK**
- `id`

**FK**
- `province_id` → `m_province.id` (ผ่าน relation `province`)

**Fields**
- `amphur_name`

**Relations**
- `province` (belongsTo)

**ใช้ทำอะไร**
- Group/Filter รายอำเภอ (ในจังหวัด)

---

### 1.3 `m_tambon` (ตำบล)
**PK**
- `id`

**FK**
- `amphur_id` → `m_amphur.id` (ผ่าน relation `amphur`)

**Fields**
- `tambon_name`

---

### 1.4 `m_village` (หมู่บ้าน)
**PK**
- `id`

**FK**
- `tambon_id` → `m_tambon.id` (ผ่าน relation `tambon`)

**Fields**
- `village_name`
- `moo` (เลขหมู่)

---

### 1.5 `m_disaster_type` (ประเภทภัยพิบัติ)
**PK**
- `id`

**Fields**
- `disaster_type`
- `status`

**Relations**
- hasMany → B10 (`b10_id`)

---

### 1.6 `m_animal_type` (ประเภทสัตว์ / M05)
**PK**
- `id`

**Fields**
- `animal_type`
- `help_quota` (M05 โควต้าตามระเบียบ)
- `unit` (หน่วย)
- `animal_pen_fk` (belongsTo คอกสัตว์)

**Relations**
- hasMany → `m_anima_sub_type` (ประเภทย่อย / M09)
- hasMany → EX02 (จำนวนสัตว์จาก E-Regis) *(ตาราง EX02 ไม่อยู่ในชุดนี้)*

**ใช้ทำอะไร**
- แปล `animal_type_id` ใน B31/B22 ฯลฯ เป็นชื่อ
- ใช้คุมโควต้า/สิทธิ (B40 จะชี้มาที่ `m05_*` ซึ่งก็คือตารางนี้)

---

### 1.7 `m_anima_sub_type` (ประเภทย่อยสัตว์ / M09)
**PK**
- `id`

**FK**
- `animal_type_id` → `m_animal_type.id`

**Fields**
- `animal_sub_type`
- `age_range`
- `help_rate` (M09 อัตราช่วยเหลือตามระเบียบ)

**ใช้ทำอะไร**
- แยก “ย่อย” ตอนคำนวณอัตราช่วยเหลือ (B41 มี `m09_b41_id`)

---

### 1.8 `m_feed_type` (ประเภทอาหารสัตว์ / M06)
**PK**
- `id`

**Fields**
- `feed_type`

**ใช้ทำอะไร**
- แปล `feed_type_id` ใน `b21_feed_count`

---

### 1.9 `m_healthcare_type` (ประเภทรักษาสัตว์)
**PK**
- `id`

**Fields**
- `healthcare_type`

**ใช้ทำอะไร**
- แปล `healthcare_type_id` ใน `b23_healthcare_count`

---

### 1.10 `m_status` (สถานะกลาง)
**PK**
- `id` (ไอดีแท้)

**Fields**
- `status_id` (ไอดีเทียม)
- `status_name`
- `status_color`
- `status_group`

**ใช้ทำอะไร**
- แปล/จัดกลุ่มสถานะของหลาย transaction table ที่มี `status_id`

---

## 2) Join Map: Transaction → Master (ของจริงที่ LLM ควรใช้)

### 2.1 พื้นที่ประสบภัย `b100_disaster_area` (B10)
> ใน metadata เดิม: `province_id, amphur_id, tambon_id, village_id, disaster_type_id`

**JOIN**
- `b100_disaster_area.province_id = m_province.id`
- `b100_disaster_area.amphur_id   = m_amphur.id`
- `b100_disaster_area.tambon_id   = m_tambon.id`
- `b100_disaster_area.village_id  = m_village.id`
- `b100_disaster_area.disaster_type_id = m_disaster_type.id`

**Path drill-down ที่ชัวร์**
- จังหวัด → อำเภอ → ตำบล → หมู่บ้าน
  - `m_amphur.province_id = m_province.id`
  - `m_tambon.amphur_id   = m_amphur.id`
  - `m_village.tambon_id  = m_tambon.id`

---

### 2.2 คำขอ กษ.02 `c102_request_for_relief`
> มี location id ครบ: `province_id, amphur_id, tambon_id, village_id`

**JOIN**
- `c102_request_for_relief.province_id = m_province.id`
- `c102_request_for_relief.amphur_id   = m_amphur.id`
- `c102_request_for_relief.tambon_id   = m_tambon.id`
- `c102_request_for_relief.village_id  = m_village.id`

---

### 2.3 ความเสียหายแยกสัตว์ `b31_damage_count`
> มี `animal_type_id`

**JOIN**
- `b31_damage_count.animal_type_id = m_animal_type.id`

---

### 2.4 อพยพสัตว์ `b22_move_animal`
> มี `animal_type_id`

**JOIN**
- `b22_move_animal.animal_type_id = m_animal_type.id`

---

### 2.5 อาหารสัตว์ `b21_feed_count`
> มี `feed_type_id`

**JOIN**
- `b21_feed_count.feed_type_id = m_feed_type.id`

---

### 2.6 รักษาสัตว์ `b23_healthcare_count`
> มี `healthcare_type_id`

**JOIN**
- `b23_healthcare_count.healthcare_type_id = m_healthcare_type.id`

---

### 2.7 โควต้า/อัตรา (B40/B41)
**B40**
- `b40_help_quata_area.m05_b40_id = m_animal_type.id`

**B41**
- `b41_assis_rate_area.m05_b41_id = m_animal_type.id`
- `b41_assis_rate_area.m09_b41_id = m_anima_sub_type.id`

---

### 2.8 สถานะ (หลายตาราง)
ถ้า table ใดมี `status_id` แล้วเป็น belongsTo ไป status:
- `transaction.status_id = m_status.id`
> (บางที่อาจใช้ `status_id` เทียม — ถ้า join ไม่ติด ให้ลอง `transaction.status_id = m_status.status_id`)

---

## 3) SQL Templates (MySQL) ให้ LLM หยิบไปใช้ได้ทันที

### 3.1 รายงาน “พื้นที่ประสบภัย” พร้อมชื่อจังหวัด/อำเภอ/ตำบล/หมู่บ้าน
```sql
SELECT
  b10.id,
  p.province_name,
  a.amphur_name,
  t.tambon_name,
  v.village_name,
  v.moo,
  dt.disaster_type,
  b10.annonced_date,
  b10.end_annonced
FROM b100_disaster_area b10
LEFT JOIN m_province p      ON b10.province_id = p.id
LEFT JOIN m_amphur a        ON b10.amphur_id   = a.id
LEFT JOIN m_tambon t        ON b10.tambon_id   = t.id
LEFT JOIN m_village v       ON b10.village_id  = v.id
LEFT JOIN m_disaster_type dt ON b10.disaster_type_id = dt.id
WHERE b10.flg_remove = 0;
````

### 3.2 รวม “ความเสียหาย” แยกประเภทสัตว์ในพื้นที่ (B10)

```sql
SELECT
  b10.id AS disaster_area_id,
  p.province_name,
  at.animal_type,
  SUM(b31.amount) AS damaged_count
FROM b31_damage_count b31
JOIN b100_disaster_area b10 ON b31.disaster_area_id = b10.id
LEFT JOIN m_province p      ON b10.province_id = p.id
LEFT JOIN m_animal_type at  ON b31.animal_type_id = at.id
WHERE b10.id = :b10_id
GROUP BY b10.id, p.province_name, at.animal_type
ORDER BY damaged_count DESC;
```

### 3.3 สรุป “อาหารสัตว์ที่ช่วยเหลือ” แยกตามประเภทอาหาร (ต่อ B20 หรือ ต่อพื้นที่)

```sql
SELECT
  ft.feed_type,
  SUM(b21.amount) AS total_amount
FROM b21_feed_count b21
LEFT JOIN m_feed_type ft ON b21.feed_type_id = ft.id
JOIN b20_init_help b20   ON b21.b20_init_help_id = b20.id
WHERE b20.disaster_area_id = :b10_id
GROUP BY ft.feed_type
ORDER BY total_amount DESC;
```

### 3.4 สรุป “การรักษา” แยกตามประเภทรักษา

```sql
SELECT
  ht.healthcare_type,
  SUM(b23.amount) AS total_amount
FROM b23_healthcare_count b23
LEFT JOIN m_healthcare_type ht ON b23.healthcare_type_id = ht.id
JOIN b20_init_help b20         ON b23.b20_init_help_id = b20.id
WHERE b20.disaster_area_id = :b10_id
GROUP BY ht.healthcare_type;
```

---

## 4) Heuristics ให้ LLM ตัดสินใจเลือก Dimension (เร็ว ๆ)

* ถ้า user พูด “จังหวัด/อำเภอ/ตำบล/หมู่บ้าน” → join `m_province/m_amphur/m_tambon/m_village`
* ถ้าพูด “ประเภทภัย” → join `m_disaster_type`
* ถ้าพูด “ประเภทสัตว์/โควต้า” → join `m_animal_type`
* ถ้าพูด “ประเภทย่อย/อัตรา” → join `m_anima_sub_type`
* ถ้าพูด “อาหารสัตว์” → join `m_feed_type`
* ถ้าพูด “รักษา” → join `m_healthcare_type`
* ถ้าพูด “สถานะ” → join `m_status` (ลอง `id` ก่อน ถ้าไม่ติดค่อย fallback `status_id`)

---
