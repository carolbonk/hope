import type { Locale } from "@/lib/locale";

const en = {
  promise: "Find grants that fit, and get a plain-English plan to apply.",
  headingSignin: "Sign in to Hope",
  email: "Email",
  password: "Password",
  show: "Show",
  hide: "Hide",
  submitSignin: "Sign in",
  noAccount: "Need an account? Ask your Hope admin to create one for you.",
  signingIn: "Signing in…",
  checking: "Checking your session…",
  demoHint: "Demo: demo@hope.org / hope-demo",
  useDemo: "Use the demo account",
  free: "Free for nonprofits.",
  errorTitle: "Couldn't continue",
  emptyEmail: "Enter your email address.",
  badEmail: "Enter an email like name@example.org.",
  emptyPassword: "Enter your password.",
  invalidCredentials: "That email or password isn't right.",
  rateLimited: "Too many attempts. Wait a minute and try again.",
  network: "We couldn't reach Hope. Check your connection and try again.",
  signedOut: "You're signed out.",
  offline: "You're offline. Connect to sign in.",
};

export type LoginCopy = typeof en;

const es: LoginCopy = {
  promise: "Encuentra subvenciones que encajan y un plan claro para solicitarlas.",
  headingSignin: "Inicia sesión en Hope",
  email: "Correo electrónico",
  password: "Contraseña",
  show: "Mostrar",
  hide: "Ocultar",
  submitSignin: "Iniciar sesión",
  noAccount: "¿Necesitas una cuenta? Pide a tu administrador de Hope que te la cree.",
  signingIn: "Iniciando sesión…",
  checking: "Comprobando tu sesión…",
  demoHint: "Demo: demo@hope.org / hope-demo",
  useDemo: "Usar la cuenta demo",
  free: "Gratis para organizaciones sin fines de lucro.",
  errorTitle: "No se pudo continuar",
  emptyEmail: "Escribe tu correo electrónico.",
  badEmail: "Escribe un correo como nombre@ejemplo.org.",
  emptyPassword: "Escribe tu contraseña.",
  invalidCredentials: "El correo o la contraseña no son correctos.",
  rateLimited: "Demasiados intentos. Espera un minuto e inténtalo de nuevo.",
  network: "No pudimos conectar con Hope. Revisa tu conexión e inténtalo de nuevo.",
  signedOut: "Cerraste sesión.",
  offline: "Estás sin conexión. Conéctate para iniciar sesión.",
};

export const LOGIN_COPY: Record<Locale, LoginCopy> = { en, es };
