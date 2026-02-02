**VIEW** ชื่อ `vw_c102_request_tambon` เอาข้อมูล “คำขอช่วยเหลือ C102” (`c102_request_for_relief` = crfr) มาสรุป **ระดับพื้นที่ (group ตามหมู่บ้าน)** โดย join ไปหาเหตุภัยพิบัติ + พื้นที่ภัยพิบัติ + ฟอร์ม C10 + รายการความเสียหาย C11 แล้วรวมจำนวนสัตว์/ยอดเงินช่วยเหลือ “แยกตาม *ชนิดย่อยสัตว์* (animal_sub_type)” ตั้งแต่ `mast.id` 1–31

สรุปง่ายๆ:
**1 แถว = 1 หมู่บ้าน (bda.village_id)** แล้วมีคอลัมน์:

* จำนวนสัตว์เสียหายแยก `amount_mast_1..amount_mast_31`
* ยอดเงินช่วยเหลือแยก `total_mast_1..total_mast_31` (help_rate * amount)

---

## Output หลักที่ VIEW คืนมา (หมวดสำคัญ)

### ข้อมูลคำขอ / ฟอร์ม

* `crfr.id`, `approved_status`, `approved_at`, `approved_by`
* `crfr.c10_id`, `crfr2.start_date`, `crfr2.end_date`

### เหตุภัยพิบัติ / พื้นที่

* `bod.name`
* `bda.annonced_title`
* `bda.province_id/amphur_id/tambon_id/village_id` + ชื่อพื้นที่ `mp/ma/mt/mv`

### ผู้ยื่น (เกษตรกร)

* `count(distinct ef.farmer_id) as farmer_ids`
* แต่ก็ยัง select `ef.id/full_name/national_id` มาด้วย (ซึ่งจริงๆมันไม่เข้ากับ group by)

### สัตว์เสียหาย + เงินช่วยเหลือ

* `amount_mast_1..amount_mast_31` = sum(crdc.amount) ตาม `animal_sub_type_id`
* `total_mast_1..total_mast_31` = sum(mast.help_rate * crdc.amount)

---
