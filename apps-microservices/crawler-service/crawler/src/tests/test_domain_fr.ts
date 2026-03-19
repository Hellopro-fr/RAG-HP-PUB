import { DetectionLangueClient } from "../class/DetectionLangueClient.js";

const log = (msg: string, success: boolean) => {
    if (success) console.log(`✅ ${msg}`);
    else console.error(`❌ ${msg}`);
};

async function runTests() {
    console.log("=== STARTING DETECTION LANGUE CLIENT TESTS ===");

    // --- PART 1: extractPrimaryMethod (Unit - no API needed) ---
    console.log("\n--- Test 1: extractPrimaryMethod ---");

    const methodCases = [
        // HTML method present → prefer it over URL method
        { input: "langHtml", expected: "langHtml" },
        { input: "langHtml+nlp_confirmed", expected: "langHtml" },
        { input: "direct_match+langHtml+nlp_confirmed", expected: "langHtml" },
        { input: "direct_match+matchMeta+nlp_soft_confirmed", expected: "matchMeta" },
        { input: "pattern_match_path+matchHttpEquiv", expected: "matchHttpEquiv" },
        // No HTML method → fall back to first component
        { input: "matchMeta", expected: "matchMeta" },
        { input: "direct_match+nlp_confirmed", expected: "direct_match" },
        { input: "pattern_match_path+nlp_soft_confirmed", expected: "pattern_match_path" },
        { input: "nlp_confirmed", expected: "nlp_confirmed" },
        { input: "direct_match", expected: "direct_match" },
        // Edge case: empty/undefined method guard
        { input: "", expected: "" },
    ];

    for (const test of methodCases) {
        const result = DetectionLangueClient.extractPrimaryMethod(test.input);
        log(
            `extractPrimaryMethod("${test.input}") Expected: "${test.expected}" | Got: "${result}"`,
            result === test.expected
        );
    }

    // --- PART 1b: requiresNlpValidation (Unit - no API needed) ---
    console.log("\n--- Test 1b: requiresNlpValidation ---");

    const nlpValidationCases = [
        // HTML-based methods (whitelist) → forced_method works, no NLP needed
        { input: "langHtml", expected: false },
        { input: "matchMeta", expected: false },
        { input: "matchHttpEquiv", expected: false },
        // URL-based methods → forced_method useless, needs NLP
        { input: "direct_match", expected: true },
        { input: "pattern_match_path", expected: true },
        { input: "pattern_match_query", expected: true },
        // NLP-only methods → needs NLP
        { input: "nlp_confirmed", expected: true },
        { input: "nlp_soft_confirmed", expected: true },
        { input: "french_lexical_signal", expected: true },
        { input: "alternative_link_validated", expected: true },
        // Edge cases: nlp_override_* and unknown methods also need NLP (whitelist approach)
        { input: "nlp_override_langHtml", expected: true },
        { input: "no_redirect", expected: true },
        { input: "some_future_method", expected: true },
        { input: "", expected: true },
    ];

    for (const test of nlpValidationCases) {
        const result = DetectionLangueClient.requiresNlpValidation(test.input);
        log(
            `requiresNlpValidation("${test.input}") Expected: ${test.expected} | Got: ${result}`,
            result === test.expected
        );
    }

    // --- PART 2: API Integration Tests (require running API) ---
    const apiUrl = process.env.DETECTION_LANGUE_API_URL || "http://api-detection-langue-fr-service:8999";
    const client = new DetectionLangueClient(apiUrl);

    // Check if the API is reachable before running integration tests
    try {
        const healthCheck = await client.checkUrl("https://www.example.fr", false);
        console.log("\n--- Test 2: check-url endpoint ---");

        const testCasesUrl = [
            { url: "https://www.example.fr", name: "TLD .fr", expected: true },
            { url: "https://fr.example.com", name: "Subdomain fr.", expected: true },
            { url: "https://www.example.com/fr/page", name: "Path /fr/", expected: true },
            { url: "https://www.example.com/page?lang=fr", name: "Query lang=fr", expected: true },
            { url: "https://www.example.com", name: "Generic .com", expected: false },
            { url: "https://www.example.com/en/page", name: "English Path", expected: false },
        ];

        for (const test of testCasesUrl) {
            const result = await client.checkUrl(test.url, false);
            log(
                `[${test.name}] (${test.url}) Expected: ${test.expected} | Got: ${result.ok}`,
                result.ok === test.expected
            );
        }

        // --- Test 3: detect endpoint with HTML content ---
        console.log("\n--- Test 3: detect endpoint (with HTML content) ---");

        const testCasesDetect = [
            {
                name: "French HTML lang",
                url: "https://www.example.com",
                content: '<!DOCTYPE html><html lang="fr-FR"><head></head><body><p>Bonjour le monde</p></body></html>',
                expected: true,
            },
            {
                name: "English HTML lang",
                url: "https://www.example.com",
                content: '<!DOCTYPE html><html lang="en-US"><head></head><body><p>Hello world</p></body></html>',
                expected: false,
            },
        ];

        for (const test of testCasesDetect) {
            const result = await client.detect(test.url, test.content, {
                mode: "simple",
                useNlpDetection: false,
            });
            log(
                `[${test.name}] Expected ok=${test.expected} | Got ok=${result.ok} (method: ${result.method})`,
                result.ok === test.expected
            );
        }
    } catch (e: any) {
        console.warn(`\n⚠️  API not reachable at ${apiUrl} — skipping integration tests.`);
        console.warn(`   Error: ${e.message}`);
        console.warn(`   Start the API with: docker compose --profile app up api-detection-langue-fr-service`);
    }

    console.log("\n=== TESTS FINISHED ===");
}

runTests().catch(console.error);
