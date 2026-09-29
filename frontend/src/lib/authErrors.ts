type SupabaseAuthError = { message: string }

// Supabase's own error messages are already reasonable defaults, but a few of
// them are worth rephrasing for this UI's tone; anything unrecognized (or
// empty, e.g. a network failure with no message) falls back accordingly.
export function describeAuthError(error: SupabaseAuthError): string {
  switch (error.message) {
    case 'Invalid login credentials':
      return 'Incorrect email or password.'
    case 'User already registered':
      return 'An account with this email already exists.'
    default:
      return error.message || 'Something went wrong. Please try again.'
  }
}
