import { type NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    // Validate request body
    if (!body.raw_html && !body.json_data) {
      return NextResponse.json({ error: 'Request body must contain either "raw_html" or "json_data"' }, { status: 400 })
    }

    // This URL points to the backend service within the Docker network.
    const backendUrl = "http://extractor-testing-service:8000/test-extractors";
    
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