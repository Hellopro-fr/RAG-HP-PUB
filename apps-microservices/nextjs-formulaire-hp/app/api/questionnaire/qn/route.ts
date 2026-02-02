import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = process.env.HELLOPRO_API_URL || 'https://dev-api.hellopro.fr';
const URL_API_QUESTION = `${BASE_URL}/v2/index.php`;
const TOKEN            = process.env.NEXT_TOKEN_API_QUESTION || '';

export async function POST(request: NextRequest) {
  try {

    const body = await request.formData();
    const rubriqueId = body.get('rubriqueId');
    const q1Answer = body.get('q1Answer');

    if (!rubriqueId || !q1Answer) {
      return NextResponse.json(
        { error: 'rubrique_id and q1_answer required' },
        { status: 400 }
      );
    }

    const url = new URL(URL_API_QUESTION);
    console.log('Calling Questionnaire Q1 API:', url.toString());

     const payloadQN = {
      etape: "question",
      field: "question2aN",
      action: "get",
      data: { 
        id_categorie: rubriqueId, 
        id_reponse_parent: q1Answer, 
      }
    };

    const response = await fetch(URL_API_QUESTION, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`
        },
      body: JSON.stringify(payloadQN),
    });    

    if (!response.ok) {
      return NextResponse.json(
        { error: `API error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();

    console.log("API QN", data);

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('Questionnaire Qn proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
