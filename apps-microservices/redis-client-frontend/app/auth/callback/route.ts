import { NextResponse, type NextRequest } from "next/server"
import { completeCallback, SESSION_COOKIE, appOrigin } from "@hellopro/auth"

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
    const res = NextResponse.redirect(new URL("/", appOrigin()))
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
    const url = new URL("/auth/denied", appOrigin())
    url.searchParams.set("email", result.email)
    return clearPkce(NextResponse.redirect(url))
  }

  const url = new URL("/auth/login", appOrigin())
  url.searchParams.set("error", result.reason)
  return clearPkce(NextResponse.redirect(url))
}
