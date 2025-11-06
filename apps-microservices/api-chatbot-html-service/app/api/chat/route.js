
import { NextResponse } from 'next/server'

export async function POST(request) {
  const body = await request.json()
  const { prompt, temperature, max_tokens, enable_thinking, options } = body

  try {
    const response = await fetch("https://api.hellopro.eu/chat-service/llm/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prompt,
        temperature,
        max_tokens,
        enable_thinking,
        options,
      }),
    });

    const data = await response.json();

    return NextResponse.json(data);
  } catch (error) {
    console.error("Error calling chat service:", error);
    return NextResponse.json({ error: "Failed to call chat service" }, { status: 500 });
  }
}
