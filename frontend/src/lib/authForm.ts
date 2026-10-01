// Register-only checks (KAN-79), run before signUp() is ever called. Sign
// in skips them: an older account's password may predate the length rule.
export const MIN_PASSWORD_LENGTH = 6

export type RegistrationCheck =
  | { ok: true }
  | { ok: false; field: 'password' | 'confirmPassword'; error: string }

export function validateRegistration({
  password,
  confirmPassword,
}: {
  password: string
  confirmPassword: string
}): RegistrationCheck {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return { ok: false, field: 'password', error: `Use at least ${MIN_PASSWORD_LENGTH} characters.` }
  }
  if (!confirmPassword) {
    return { ok: false, field: 'confirmPassword', error: 'Type your password again to confirm it.' }
  }
  if (password !== confirmPassword) {
    return { ok: false, field: 'confirmPassword', error: "Passwords don't match." }
  }
  return { ok: true }
}
