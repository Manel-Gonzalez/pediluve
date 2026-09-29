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

// The home page's row links here: a read-only view of a past session's full
// transcript (KAN-26).
export function sessionPath(id: string): string {
  return `/sessions/${id}`
}

// Distinct from sessionPath: the live recording view (KAN-38) joins the
// session over the WebSocket rather than just reading it, so it gets its own
// route instead of overloading the read-only one.
export function liveSessionPath(id: string): string {
  return `/sessions/${id}/live`
}
