// C3: Authentication middleware — protects all routes including server actions
// Requires ADMIN_TOKEN env var. Validates via cookie or Authorization header.
import { NextResponse, type NextRequest } from "next/server"

export function middleware(request: NextRequest) {
  const adminToken = process.env.ADMIN_TOKEN

  // If no ADMIN_TOKEN is configured, skip auth (development mode)
  if (!adminToken) {
    return NextResponse.next()
  }

  // Check token from cookie or Authorization header
  const cookieToken = request.cookies.get("admin_token")?.value
  const headerToken = request.headers.get("authorization")?.replace("Bearer ", "")

  if (cookieToken === adminToken || headerToken === adminToken) {
    return NextResponse.next()
  }

  // For server actions (POST to same origin), return 401
  if (request.method === "POST") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  // For page requests, redirect to a simple login page
  const loginUrl = new URL("/login", request.url)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  // Protect all routes except static files and the login page
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon-.*|apple-icon|login).*)"],
}
