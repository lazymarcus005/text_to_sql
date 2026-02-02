**VIEW** ชื่อ `vw_c12_summary_assis` เอาข้อมูล “สรุปการช่วยเหลือระดับจังหวัด (level_area = province)” มารวมกัน โดยอิงพื้นที่คำขอ (`c101_request_area` = cra) แล้ว join ไปหา

* ข้อมูลสรุป C12 (`c12_summary_assis` = csa)
* ข้อมูลภัยพิบัติ (`b000_open_disaster` = bod)
* รายการคำขอช่วยเหลือ C102 (`c102_request_for_relief` = crfr)
* ฟอร์มคำขอ C10 (`c10_request_for_relief` = crfr2)
* สรุปความเสียหาย/ยอดอนุมัติจาก C11 (`c11_request_damage_count`) แยกตามชนิดสัตว์ 1–14 ผ่านซับคิวรี `tcrdc`
* ชื่อพื้นที่ (จังหวัด/อำเภอ/ตำบล/หมู่บ้าน) และประเภทภัยพิบัติ

สุดท้าย `GROUP BY cra.b10_disaster_area_id` แล้วนับจำนวนเกษตรกรแบบ distinct

## Output หลักที่ VIEW คืนมา (ไฮไลต์ที่สำคัญ)

* ตัวตนพื้นที่/เหตุการณ์: `cra.b10_disaster_area_id`, `cra.b00_open_disaster_id`, `bod.name`, `start_at`, `end_at`
* สรุปงบ/ยอดช่วยเหลือจาก `cra`: `value_assis_amount`, `organization_assis_amont`, `government_budget`, `permanent_secretary_budget`, `approved_at`
* สถานะ summary: `csa.status`, `created_at/updated_at`, `created_by_id/updated_by_id`
* พิกัดพื้นที่: `province/amphur/tambon/village` ids + names
* จำนวนเกษตรกร: `count(distinct ef.farmer_id)` เป็น `farmer_ids`
* ประเภทภัยพิบัติ: `bda.disaster_type_id`, `mdt.disaster_type`
* ยอดอนุมัติจาก `tcrdc`: `approved_total_aid`, `approved_amount`
* แตกยอดตาม animal_type 1–14: `amount_mat_1 .. amount_mat_14`
