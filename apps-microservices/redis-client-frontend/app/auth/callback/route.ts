import { NextResponse, type NextRequest } from "next/server"
import { completeCallback } from "@/lib/auth/flow"
import { SESSION_COOKIE } from "@/lib/auth/session"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

function clearPkce(res: NextResponse): NextResponse {
  res.cookies.delete("oauth_verifier")
  res.cookies.delete("oauth_state")
  return res
}

export async function GET(request: NextRequest) {
  const result = await completeCallback({
    code: request.nextUrl.searchParams.get("code"),
    state: request.nextUrl.searchParams.get("state"),
    stateCookie: request.cookies.get("oauth_state")?.value,
    verifierCookie: request.cookies.get("oauth_verifier")?.value,
  })

  if (result.status === "ok") {
    const res = NextResponse.redirect(new URL("/", request.url))
    res.cookies.set(SESSION_COOKIE, result.sessionToken, {
      httpOnly: true,
      sameSite: "lax",
      secure: result.secureCookie,
      path: "/",
      maxAge: result.ttlSeconds,
    })
    return clearPkce(res)
  }

  if (result.status === "denied") {
    const url = new URL("/auth/denied", request.url)
    url.searchParams.set("email", result.email)
    return clearPkce(NextResponse.redirect(url))
  }

  const url = new URL("/auth/login", request.url)
  url.searchParams.set("error", result.reason)
  return clearPkce(NextResponse.redirect(url))
}
