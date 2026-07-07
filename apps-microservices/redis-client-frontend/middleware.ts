// Auth middleware — gates all routes on the signed rcf_session cookie (account-service SSO).
import { NextResponse, type NextRequest } from "next/server"
import { readSession, SESSION_COOKIE } from "@/lib/auth/session"

export async function middleware(request: NextRequest) {
  const session = await readSession(request.cookies.get(SESSION_COOKIE)?.value)
  if (session) {
    return NextResponse.next()
  }

  // Server actions (POST to same origin) get a 401 instead of a redirect.
  if (request.method === "POST") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const loginUrl = new URL("/auth/login", request.url)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  // Protect everything except static assets and the /auth/* routes (login, callback, logout, denied).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon-.*|apple-icon|auth).*)"],
}
