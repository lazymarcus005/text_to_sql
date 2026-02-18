````md
# Preparation Module (MySQL) — Data Dictionary + Relationships (ให้ LLM สร้าง SQL ได้)

หมวดนี้คือ “ทรัพยากร/ความพร้อม” ก่อนเกิดเหตุ เช่น คอกสัตว์ จุดอพยพ เสบียง รถ หน่วยสัตวแพทย์ ฯลฯ  
ทุกตารางในหมวดนี้มัก filter ด้วย **ปี (`year_report`) + รอบรายงาน (`round_report`) + จังหวัด/อำเภอ/ตำบล** และ join ชื่อพื้นที่จาก master (`m_province/m_amphur/m_tambon/m_village`)

---

## 0) Rules อ่านความสัมพันธ์ (MySQL)

- `belongsTo (m2o)` = มี FK ไปตารางปลายทาง  
  `LEFT JOIN target ON this.<fk> = target.id`

- `hasMany (o2m)` = เป็น parent, child มี FK กลับมา  
  `LEFT JOIN child ON child.<parent_id> = parent.id`

- `belongsToMany (attachment)` = many-to-many / ไฟล์แนบ  
  ต้องมี junction table (ชื่อจริงขึ้นกับระบบ)  
  แนวคิด query: join ผ่าน `<table>_<field>` หรือ `attachments` mapping (แล้วแต่ implementation)

> NOTE: หลายคอลัมน์ชื่อ `*_name` ในชุดนี้เป็น `belongsTo m2o` แต่ชื่อ field เป็น “ชื่อ”  
> ให้ LLM treat ว่าเป็น “dimension object” (ไว้ join ชื่อจังหวัด/อำเภอ/ชนิดสัตว์) ไม่ใช่ string ธรรมดา

---

## 1) Tables ในหมวด Preparation

## 1.1 `animal_pen` — ข้อมูลคอกสัตว์/แผง + จำนวนประเภทสัตว์ (เชิงสำรวจ/รายงาน)
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `amphur_id` → `m_amphur.id`
- `tambon_id` → `m_tambon.id`
- `report_schedule_items_id` → `bd161_report_schedule_items.id` *(ตาราง BD161 ยังไม่อยู่ในชุดที่ส่ง)*
- `migrated_animal_id` → (น่าจะไป master ประเภทสัตว์/กลุ่มสัตว์ — ยังไม่ชัดจากชุดนี้)
- `animal_pen_id` (อาจเป็นรหัสคอก/แผง)

**Measures**
- `num_panel` จำนวน(แผง)
- `animal_type_amount` จำนวนประเภทสัตว์

**Relations**
- hasMany → `possession_animal_type` (BD101 - สัตว์ในครอบครอง)
- hasMany → `group_animal_type` (BD121 - กลุ่มประเภทสัตว์)

**Operational fields**
- `year_report`, `round_report`, `report_status`

**Query ใช้บ่อย**
- จำนวนคอก/แผงต่อจังหวัด/รอบ/ปี
- นับประเภทสัตว์ที่มีในคอกต่อพื้นที่

---

## 1.2 `centering_command` — คำสั่ง/ประกาศศูนย์ฯ (มีไฟล์แนบ)
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `disaster_type_id` → `m_disaster_type.id`

**Time**
- `start_date`, `end_date`
- `doc_date_expire` วันหมดอายุเอกสาร
- `year`

**Attachments**
- `file_command` (belongsToMany attachment)

**Operational fields**
- `status`, `report_cycle`

**Query ใช้บ่อย**
- คำสั่งที่ยังไม่หมดอายุในจังหวัด X
- คำสั่งตามประเภทภัย + ช่วงเวลา

---

## 1.3 `emergency_kit` — ถุงยังชีพ/ชุดฉุกเฉิน (stock/แผน)
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `report_schedule_items_id` → BD161

**Measures**
- `f_v05zvzumm0m` จำนวน(ถุง) *(field code)*
- `num_bag_1` สัตว์ใหญ่
- `num_bag_2` สัตว์ปีก
- `num_bag_3` สัตว์เลี้ยง

**Fields**
- `receive_location` สถานที่รับ

**Operational**
- `year_report`, `round_report`, `status`

**Query ใช้บ่อย**
- ถุงยังชีพคงเหลือ/แผนต่อจังหวัดแยกประเภทสัตว์

---

## 1.4 `grass_supply` — คลังเสบียง/อาหารสัตว์ (inventory)
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `amphur_id` → `m_amphur.id`
- `tambon_id` → `m_tambon.id`
- `affiliated_id` → (หน่วยงานสังกัด / master ยังไม่อยู่ในชุดนี้)
- `livestock_id` → (เขต/หน่วยปศุสัตว์ / master ยังไม่อยู่ในชุดนี้)

**Measures**
- `quantity` ปริมาณคงคลัง

**Fields**
- `warehouse_name` ชื่อคลัง
- `feed_name` ชื่อเสบียง
- `last_updated_at`

**Operational**
- `year_report`, `round_report`

**Query ใช้บ่อย**
- inventory เสบียงรายจังหวัด/เขต/หน่วยงาน
- list คลังที่อัปเดตล่าสุดในช่วง X

---

## 1.5 `migration_area` — จุด/พื้นที่อพยพสัตว์
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `amphur_id` → `m_amphur.id`
- `tambon_id` → `m_tambon.id`
- `moo_id` → (น่าจะไป `m_village.id` หรือ master “หมู่” แยก — ในชุดนี้มี `moo_name` เป็น belongsTo)
- `migrated_animal_id` → (ประเภทสัตว์/กลุ่มสัตว์ที่อพยพ — ยังไม่ชัด)
- `migration_area_id` (รหัสจุดอพยพ)
- `report_schedule_items_id` → BD161

**Measures**
- `amount` จำนวน(ตัว)
- `area_rai` จำนวนพื้นที่(ไร่)
- `amount_animal_type` จำนวนประเภทสัตว์

**Geo**
- `coordinates_xy` (string)
- `location` (type point)

**Relations**
- hasMany → `possession_animal_type` (BD101)
- hasMany → `log_migration_area_fk` (BD102 log)

**Operational**
- `status_report`, `round_report`, `remark`, `year_report`
- `flg_master` (ค่าเริ่มต้น)

**Query ใช้บ่อย**
- จุดอพยพในจังหวัด X พร้อมพิกัด
- capacity (area_rai / amount) ตามรอบรายงาน

---

## 1.6 `vehicle` — รถสำหรับภารกิจ/อพยพ
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `amphur_id` → `m_amphur.id`
- `livestock_zone_id` → (เขตปศุสัตว์ master ยังไม่อยู่ในชุด)
- `livestock_id` → (หน่วยงาน/สังกัด master ยังไม่อยู่ในชุด)
- `report_schedule_items_id` → BD161
- `agency` (belongsTo m2o) → master หน่วยงาน *(ยังไม่อยู่ในชุด)*
- `livestock_district` (belongsTo m2o) → master เขต *(ยังไม่อยู่ในชุด)*

**Measures**
- `num_car` จำนวน(คัน)
- `weight_capacity_tons` พิกัดน้ำหนัก(ตัน)

**Fields**
- `registration_number`
- `driver_name`, `driver_phone`
- `provin_coordinator_name`, `provin_coordinator_phone`
- `type_car` ประเภทรถ

**Operational**
- `status_report`, `round_report`, `year_report`

**Query ใช้บ่อย**
- รถพร้อมใช้รายจังหวัด/ประเภทรถ/รอบรายงาน
- sum น้ำหนักบรรทุกต่อจังหวัด

---

## 1.7 `veterinary_unit` — หน่วยสัตวแพทย์/กำลังคน
**PK**
- `id`

**FK/Dimensions**
- `province_id` → `m_province.id`
- `amphur_id` → `m_amphur.id`
- `tambon_id` → `m_tambon.id`
- `moo_id` → (น่าจะ `m_village.id` / หรือ master หมู่)
- `report_schedule_id` → (schedule master ยังไม่อยู่ในชุด)
- `report_schedule_items_id` → BD161

**Measures**
- `num_people` จำนวนคน
- `unit_team` จำนวนทีม

**Fields**
- `veterinary_unit_name`
- `danger_level` ระดับภัย

**Relations**
- hasMany → `people_doc` (หมอ)

**Operational**
- `status` (สถานะรายงาน), `round_report`, `year_report`

**Query ใช้บ่อย**
- กำลังสัตวแพทย์ต่อจังหวัด/รอบ
- list หน่วยในพื้นที่ + จำนวนทีม

---

## 2) Join Map กับ Master (ที่ใช้จริงใน MySQL)

> ใช้ master จากชุดก่อนหน้า: `m_province, m_amphur, m_tambon, m_village, m_disaster_type`

**ทุก table ที่มี location id**
- `*.province_id = m_province.id`
- `*.amphur_id   = m_amphur.id`
- `*.tambon_id   = m_tambon.id`

**กรณี `moo_id`**
- ถ้าหมู่คือ “หมู่บ้าน” ให้ลอง:
  - `migration_area.moo_id = m_village.id`
  - `veterinary_unit.moo_id = m_village.id`
- ถ้าไม่ match (เพราะ moo แยก master) ให้ fallback join ผ่าน field `moo_name` ที่เป็น belongsTo (ตามระบบ)

**ภัยพิบัติ**
- `centering_command.disaster_type_id = m_disaster_type.id`

---

## 3) SQL Templates (MySQL) — Ready-to-copy

### 3.1 รวมจำนวน “ถุงยังชีพ” รายจังหวัด แยกประเภทถุง
```sql
SELECT
  p.province_name,
  SUM(e.num_bag_1) AS bag_large,
  SUM(e.num_bag_2) AS bag_poultry,
  SUM(e.num_bag_3) AS bag_pet,
  SUM(e.f_v05zvzumm0m) AS bag_total
FROM emergency_kit e
LEFT JOIN m_province p ON e.province_id = p.id
WHERE e.year_report = :year
  AND e.round_report = :round
GROUP BY p.province_name
ORDER BY bag_total DESC;
````

### 3.2 Inventory เสบียงรายอำเภอ (ล่าสุด)

```sql
SELECT
  p.province_name,
  a.amphur_name,
  g.warehouse_name,
  g.feed_name,
  g.quantity,
  g.last_updated_at
FROM grass_supply g
LEFT JOIN m_province p ON g.province_id = p.id
LEFT JOIN m_amphur  a ON g.amphur_id   = a.id
WHERE g.year_report = :year
  AND g.round_report = :round
ORDER BY g.last_updated_at DESC;
```

### 3.3 จุดอพยพสัตว์ในจังหวัด (พร้อมพิกัด)

```sql
SELECT
  p.province_name,
  a.amphur_name,
  t.tambon_name,
  ma.migration_area_name,
  ma.area_rai,
  ma.amount,
  ma.coordinates_xy,
  ma.status_report,
  ma.round_report
FROM migration_area ma
LEFT JOIN m_province p ON ma.province_id = p.id
LEFT JOIN m_amphur  a ON ma.amphur_id   = a.id
LEFT JOIN m_tambon  t ON ma.tambon_id   = t.id
WHERE ma.province_id = :province_id
  AND ma.year_report = :year;
```

### 3.4 รถพร้อมใช้: จำนวนคัน + น้ำหนักรวม ต่อจังหวัด/ประเภทรถ

```sql
SELECT
  p.province_name,
  v.type_car,
  SUM(v.num_car) AS total_cars,
  SUM(v.num_car * v.weight_capacity_tons) AS total_capacity_tons
FROM vehicle v
LEFT JOIN m_province p ON v.province_id = p.id
WHERE v.year_report = :year
  AND v.round_report = :round
GROUP BY p.province_name, v.type_car
ORDER BY total_cars DESC;
```

### 3.5 หน่วยสัตวแพทย์: จำนวนทีม/คน ต่ออำเภอ

```sql
SELECT
  p.province_name,
  a.amphur_name,
  SUM(u.unit_team) AS total_teams,
  SUM(u.num_people) AS total_people
FROM veterinary_unit u
LEFT JOIN m_province p ON u.province_id = p.id
LEFT JOIN m_amphur  a ON u.amphur_id   = a.id
WHERE u.year_report = :year
  AND u.round_report = :round
GROUP BY p.province_name, a.amphur_name;
```

---

## 4) Heuristics ให้ LLM เลือก table (เร็วมาก)

* “คอก/แผง/จำนวนแผง” → `animal_pen`
* “คำสั่ง/หนังสือ/เอกสารคำสั่ง/หมดอายุเอกสาร” → `centering_command`
* “ถุงยังชีพ/ชุดฉุกเฉิน/สถานที่รับ” → `emergency_kit`
* “คลัง/เสบียง/อาหารสัตว์คงคลัง” → `grass_supply`
* “จุดอพยพ/พื้นที่อพยพ/พิกัด” → `migration_area`
* “รถ/ทะเบียน/พิกัดน้ำหนัก/ประเภทรถ” → `vehicle`
* “หน่วยสัตวแพทย์/ทีม/หมอ/กำลังคน” → `veterinary_unit`

---

## 5) จุดที่ “ยังต้องเดา” (แต่ทำ fallback ให้ LLM ได้)

1. `report_schedule_items_id` → BD161
2. `moo_id` ว่า join `m_village.id` ได้ไหม
3. `migrated_animal_id` ชี้ไปตารางไหน (animal type? group?)

**Fallback logic ที่แนะนำสำหรับ LLM**

* ถ้าจอย `moo_id = m_village.id` ไม่ได้ → ใช้ field object `moo_name` (belongsTo) แทน
* ถ้าอยากได้ชื่อ “ชนิดสัตว์” แต่ `migrated_animal_id` ไม่ชัด → ใช้ `animal_type_name` ที่เป็น belongsTo object แทน (ตาม metadata)

---

```

ถ้าคุณส่ง metadata ของ BD161/BD101/BD121/BD102 เพิ่มมาอีกนิด ผมจะต่อ relationship graph ให้ครบ (รวมเส้นทาง drill-down จาก preparation → log/detail) แล้ว LLM จะ generate query ได้แบบไม่พังเลย.
```
