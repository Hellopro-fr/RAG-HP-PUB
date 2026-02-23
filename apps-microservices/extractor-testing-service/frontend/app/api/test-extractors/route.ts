import { type NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    // Validate request body structure for the boilerplate test
    if (!body.main_html || !body.reference_htmls || !Array.isArray(body.reference_htmls)) {
      return NextResponse.json({ error: 'Request body must contain main_html and an array of reference_htmls' }, { status: 400 })
    }

    // Points to the backend service within the Docker network.
    const backendUrl = "http://backend-extractor-testing-service:8034/test-boilerplate";
    
    const backendResponse = await fetch(backendUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    if (!backendResponse.ok) {
        const errorText = await backendResponse.text();
        console.error("Backend Error Response:", errorText);
        throw new Error(`Backend error: ${backendResponse.status} ${backendResponse.statusText} - ${errorText}`);
    }

    const results = await backendResponse.json()
    return NextResponse.json(results)
  } catch (error) {
    console.error("API proxy error:", error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error occurred" },
      { status: 500 },
    )
  }
}