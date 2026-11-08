-- H6: funder jargon found on each requirements read (see hope_discovery.glossary).
ALTER TABLE application_requirements ADD COLUMN terms jsonb NOT NULL DEFAULT '[]';
