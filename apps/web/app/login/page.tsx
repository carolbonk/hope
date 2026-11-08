import { Suspense } from "react";
import { LoginScreen } from "./LoginScreen";

export const metadata = { title: "Sign in · Hope" };

export default function LoginPage() {
  return (
    <Suspense>
      <LoginScreen />
    </Suspense>
  );
}
