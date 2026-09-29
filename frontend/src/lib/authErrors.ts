type SupabaseAuthError = { message: string }

// Also used directly by useAuth.tsx's signUp(): with "Confirm email" on,
// Supabase doesn't return this as an error for a duplicate registration (see
// that file for why) - the message still needs to match what a user would
// see if the same situation happened with "Confirm email" off, where
// Supabase does return it as the 'User already registered' error below.
export const ACCOUNT_ALREADY_EXISTS_MESSAGE = 'An account with this email already exists.'

// Supabase's own error messages are already reasonable defaults, but a few of
// them are worth rephrasing for this UI's tone; anything unrecognized (or
// empty, e.g. a network failure with no message) falls back accordingly.
export function describeAuthError(error: SupabaseAuthError): string {
  switch (error.message) {
    case 'Invalid login credentials':
      return 'Incorrect email or password.'
    case 'User already registered':
      return ACCOUNT_ALREADY_EXISTS_MESSAGE
    default:
      return error.message || 'Something went wrong. Please try again.'
  }
}
