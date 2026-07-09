import { NextResponse } from "next/server"
import { getAuthConfig, SESSION_COOKIE, appOrigin } from "@hellopro/auth"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET() {
  const cfg = await getAuthConfig()
  const loginUrl = new URL("/auth/login", appOrigin()).toString()
  const target = cfg.centralLogout
    ? `${cfg.accountPublicUrl}/logout?post_logout_redirect_uri=${encodeURIComponent(loginUrl)}`
    : loginUrl
  const res = NextResponse.redirect(target)
  res.cookies.delete(SESSION_COOKIE)
  return res
}
