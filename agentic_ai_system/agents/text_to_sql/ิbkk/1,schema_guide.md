# Disaster Relief System — Unified Schema Guide (MySQL)

DB Engine: MySQL  
Purpose: ให้ LLM ใช้สร้าง SQL ได้ถูกต้อง สม่ำเสมอ และเลือก join path ไม่ผิด

---

# 1️⃣ SYSTEM OVERVIEW

ระบบแบ่งเป็น 3 โมดูลหลัก:

1) Master (M*)  
2) Transaction (B00/B10/C10/B20/B30/SPS*)  
3) Preparation (vehicle / migration_area / grass_supply / ฯลฯ)

---

# 2️⃣ START TABLE MAP (Intent → Entry Point)

ถ้าผู้ใช้พูดถึง...

| Intent | Start Table |
|--------|-------------|
| ประกาศพื้นที่ภัย | b000_open_disaster |
| พื้นที่ประสบภัย | b100_disaster_area |
| เกษตรกร | b10ex01 |
| คำขอ กษ.01 | c10_request_for_relief |
| คำขอ กษ.02 | c102_request_for_relief |
| ช่วยเหลือเบื้องต้น | b20_init_help |
| ความเสียหาย | b30_init_damage |
| รายงาน ศปส.1 | tbl_sps01 |
| รายงาน ศปส.2 | tbl_sps02 |
| รายงาน ศปส.3 | tbl_sps03 |
| คอกสัตว์ | animal_pen |
| ถุงยังชีพ | emergency_kit |
| เสบียง/คลัง | grass_supply |
| จุดอพยพ | migration_area |
| รถ | vehicle |
| หน่วยสัตวแพทย์ | veterinary_unit |

---

# 3️⃣ CANONICAL JOIN DICTIONARY (ใช้เสมอ)

## Location
province_id = m_province.id  
amphur_id   = m_amphur.id  
tambon_id   = m_tambon.id  
village_id  = m_village.id  

## Disaster
disaster_type_id = m_disaster_type.id  

## Animal
animal_type_id = m_animal_type.id  
m05_* = m_animal_type.id  
m09_* = m_anima_sub_type.id  

## Feed / Healthcare
feed_type_id = m_feed_type.id  
healthcare_type_id = m_healthcare_type.id  

## Status
พยายาม join:
transaction.status_id = m_status.id  

ถ้าไม่ match:
transaction.status_id = m_status.status_id  

---

# 4️⃣ GOLDEN JOIN PATHS (ถูกต้องโดย design)

## B00 → B10 → (C10 / EX01 / B20 / B30)

b000_open_disaster
    ↓
b100_disaster_area
    ↓
    ├─ c10_request_for_relief
    ├─ b10ex01
    ├─ b20_init_help → b21/b22/b23
    └─ b30_init_damage → b31

---

## B20 Help Breakdown
b20_init_help
    ├─ b21_feed_count
    ├─ b22_move_animal
    └─ b23_healthcare_count

---

## B30 Damage Breakdown
b30_init_damage
    └─ b31_damage_count

---

## SPS Reports
ต้องการยอดรายงานอย่างเป็นทางการ:
- SPS01 = tbl_sps01
- SPS02 = tbl_sps02 (+ help_log + round_report)
- SPS03 = tbl_sps03 (+ damage_log + round_report)

---

# 5️⃣ SOURCE OF TRUTH RULES

ต้องการข้อมูลจากการบันทึกจริง → ใช้ Transaction tables (B20/B30/C10)

ต้องการรายงานตามรอบ → ใช้ SPS tables

อย่าผสม B20 กับ SPS02 เว้นแต่ user ระบุชัดว่าต้องการเปรียบเทียบ

---

# 6️⃣ SQL GUARDRAILS

- ใช้ LEFT JOIN กับ master tables
- ถ้ามี GROUP BY ให้ group ทุก dimension ที่ select
- ถ้า filter วันที่ ต้องระบุ field ชัดเจน
- ใช้ alias table เสมอ
- ใช้ SUM() กับ measure columns
- year_report และ round_report ต้อง filter พร้อมกันถ้าเป็น preparation tables

---

# 7️⃣ DATE FIELDS (สำคัญ)

ประกาศภัย → start_at / end_at  
พื้นที่ → annonced_date / end_annonced  
คำขอ → approved_at / start_date / end_date  
SPS02 → sps02_round_date  
SPS03 → sps03_round_date  
Preparation → year_report  

---

# 8️⃣ COMMON FILTER PATTERNS

รายจังหวัด:
WHERE province_id = :province_id

รายปี:
WHERE year_report = :year

รายรอบ:
WHERE round_report = :round

ช่วงเวลา:
WHERE date_field BETWEEN :start AND :end

---

# 9️⃣ FALLBACK LOGIC

ถ้า moo_id join ไม่ได้:
ใช้ moo_name relation object แทน

ถ้า migrated_animal_id ไม่ชัด:
ใช้ animal_type_name relation object แทน

---

# 🔟 ALWAYS PREFER

- Join path ตาม Golden Paths
- Use canonical join keys
- แยก Transaction กับ Report ให้ชัด

---

END OF CORE GUIDE
