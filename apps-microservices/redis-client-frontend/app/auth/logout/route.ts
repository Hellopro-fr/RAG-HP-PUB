import { NextResponse, type NextRequest } from "next/server"
import { getAuthConfig, SESSION_COOKIE } from "@hellopro/auth"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const cfg = getAuthConfig()
  const loginUrl = new URL("/auth/login", request.url).toString()
  const target = cfg.centralLogout
    ? `${cfg.accountPublicUrl}/logout?post_logout_redirect_uri=${encodeURIComponent(loginUrl)}`
    : loginUrl
  const res = NextResponse.redirect(target)
  res.cookies.delete(SESSION_COOKIE)
  return res
}
