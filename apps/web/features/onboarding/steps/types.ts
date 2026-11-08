import type { ProfileForm } from "@/lib/api/profile";
import type { Errors } from "../model";

export interface StepProps {
  form: ProfileForm;
  set: (update: (form: ProfileForm) => ProfileForm) => void;
  errors: Errors;
}
