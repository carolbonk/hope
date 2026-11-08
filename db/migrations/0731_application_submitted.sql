-- Recording the funder portal's receipt on a bid moves the application to 'submitted' (terminal).
ALTER TABLE applications DROP CONSTRAINT applications_stage_check;
ALTER TABLE applications ADD CONSTRAINT applications_stage_check CHECK (stage IN
  ('saved','eligibility','approval','drafting','ready','submitted'));
