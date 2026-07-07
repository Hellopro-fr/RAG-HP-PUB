import { NextResponse } from "next/server"
import { startLogin } from "@/lib/auth/flow"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET() {
  const { authorizeUrl, verifier, state, secureCookie } = await startLogin()
  const res = NextResponse.redirect(authorizeUrl)
  const opts = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: secureCookie,
    path: "/",
    maxAge: 600,
  }
  res.cookies.set("oauth_verifier", verifier, opts)
  res.cookies.set("oauth_state", state, opts)
  return res
}
