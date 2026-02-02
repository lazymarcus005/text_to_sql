**VIEW** ชื่อ `vw_disaster_animal_count` เพื่อสรุปข้อมูล “พื้นที่ภัยพิบัติ” แล้วดึงข้อมูลประกาศภัยพิบัติ + ที่อยู่ (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน) + ประเภทภัย + สถานะ
พร้อมกับ “สรุปรวมจำนวนเกษตรกร/จำนวนสัตว์/ยอดเงินช่วยเหลือ” และแตกเป็นราย **animal_type_id 1–14** ทั้งจำนวน (`total_1..total_14`) และเงินช่วย (`help_amount_1..help_amount_14`)

กรองเฉพาะ:

* `bda.b10_eregis_status_id = 5`
* ในซับคิวรีนับสัตว์กรอง `eaa.m100_status_id = 3`

และสุดท้าย `GROUP BY` ตาม:

* `bod.id`, `bda.disaster_type_id`, `bda.province_id`, `bda.amphur_id`, `bda.tambon_id`, `bda.village_id`

---

## ฟิลด์ที่ VIEW นี้คืนค่า

### ข้อมูลภัยพิบัติ/ประกาศ

* `bda.id`, `bod.id`, `bod.name`, `bda.annonced_title`
* `bda.disaster_type_id`, `mdt.disaster_type`
* `bda.annonced_date`, `bda.end_annonced`

### สถานะ

* `bda.b10_sps1_status_id`, `ms.status_name`, `ms.status_color`

### พิกัดที่อยู่

* `mv.village_name`, `mt.tambon_name`, `ma.amphur_name`, `mp.province_name`

### สรุปรวม

* `teaa.total_farmers`
* `teaa.grand_total_animals`
* `teaa.grand_total_help_amount`
* `teaa.total_1..total_14`
* `teaa.help_amount_1..help_amount_14`

---
