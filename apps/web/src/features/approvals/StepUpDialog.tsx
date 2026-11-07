"use client";

import { useState } from "react";
import { Button, Modal, TextField } from "@/components/ui";

interface Props {
  open: boolean;
  actionLabel: string;
  onCancel: () => void;
  onVerified: (token: string) => void;
}

/** Placeholder for the IdP step-up MFA flow required on HITL-2/3/5 (blueprint 8.4). */
export function StepUpDialog({ open, actionLabel, onCancel, onVerified }: Props) {
  const [code, setCode] = useState("");
  const valid = /^\d{6}$/.test(code);
  return (
    <Modal
      open={open}
      title="Step-up verification required"
      description="This gate needs a fresh second factor before your decision is recorded."
      onClose={onCancel}
      footer={
        <>
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant="primary" disabled={!valid} onClick={() => onVerified(`mfa-placeholder:${code}`)}>
            Verify and {actionLabel.toLowerCase()}
          </Button>
        </>
      }
    >
      <TextField
        label="6-digit authenticator code"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
        hint="Placeholder: any 6 digits are accepted until the identity-provider step-up flow is connected."
      />
    </Modal>
  );
}
