type RedirectState = { from?: { pathname: string } } | null | undefined

// Where to send the user after a successful login. RequireAuth stores the
// location it redirected from as { from: location } in the navigation state;
// this reads it back. Falls back to "/" both when there's nothing to return
// to and when the stored path is /login itself - a session that expired
// while already sitting on /login must not bounce right back there.
export function postLoginRedirect(state: unknown): string {
  const from = (state as RedirectState)?.from?.pathname
  if (!from || from === '/login') return '/'
  return from
}
