USE catms_db;

ALTER TABLE branch
    ADD CONSTRAINT fk_branch_manager_staff
    FOREIGN KEY (manager_staff_id) REFERENCES staff(staff_id);