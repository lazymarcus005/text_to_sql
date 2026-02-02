ได้เลย นี่คือสรุปว่า query นี้ทำอะไร + “มีตารางอะไรบ้าง” แบบชัดๆ

## Query นี้คืออะไร (ภาพรวม)

มันคือการสร้าง **VIEW** ชื่อ `vw_disaster_animal_count` เพื่อสรุปข้อมูล “พื้นที่ภัยพิบัติ” แล้วดึงข้อมูลประกาศภัยพิบัติ + ที่อยู่ (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน) + ประเภทภัย + สถานะ
พร้อมกับ “สรุปรวมจำนวนเกษตรกร/จำนวนสัตว์/ยอดเงินช่วยเหลือ” และแตกเป็นราย **animal_type_id 1–14** ทั้งจำนวน (`total_1..total_14`) และเงินช่วย (`help_amount_1..help_amount_14`)

กรองเฉพาะ:

* `bda.b10_eregis_status_id = 5`
* ในซับคิวรีนับสัตว์กรอง `eaa.m100_status_id = 3`

และสุดท้าย `GROUP BY` ตาม:

* `bod.id`, `bda.disaster_type_id`, `bda.province_id`, `bda.amphur_id`, `bda.tambon_id`, `bda.village_id`

---

## ตาราง/วิว ที่ถูกใช้ทั้งหมด (พร้อม alias)

### ตารางหลัก (FROM)

1. `b100_disaster_area` `bda`  ✅ (ตารางหลัก)

### JOIN ภายนอก (ระดับนอก)

2. `b000_open_disaster` `bod`
3. `m_village` `mv`
4. `m_tambon` `mt`
5. `m_amphur` `ma`
6. `m_province` `mp`
7. `m_disaster_type` `mdt`
8. `m_status` `ms`

### ซับคิวรีรวมยอดสัตว์ (derived table)

ซับคิวรีนี้ถูกตั้งชื่อว่า `teaa` และสร้างจากตาราง:
9. `ex_animal_amount` `eaa`
10. `ex_farmer` `ef`
11. `m_anima_sub_type` `mast`
12. `m_animal_type` `matype`

**สรุป:** ใช้ทั้งหมด **12 ตาราง/วิว** (8 ตัวด้านนอก + 4 ตัวในซับคิวรี)

---

## ฟิลด์ที่ VIEW นี้คืนค่า (แบ่งหมวดให้อ่านง่าย)

### ข้อมูลภัยพิบัติ/ประกาศ

* `bda.id`, `bod.id`, `bod.name`, `bda.annonced_title`
* `bda.disaster_type_id`, `mdt.disaster_type`
* `bda.annonced_date`, `bda.end_annonced`

### สถานะ

* `bda.b10_sps1_status_id`, `ms.status_name`, `ms.status_color`

### พิกัดที่อยู่

* `mv.village_name`, `mt.tambon_name`, `ma.amphur_name`, `mp.province_name`

### สรุปรวมจากซับคิวรี `teaa`

* `teaa.total_farmers`
* `teaa.grand_total_animals`
* `teaa.grand_total_help_amount`
* `teaa.total_1..total_14`
* `teaa.help_amount_1..help_amount_14`

---
