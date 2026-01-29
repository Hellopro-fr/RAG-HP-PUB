import { DomainFR } from "../class/DomainFR.js";

const log = (msg: string, success: boolean) => {
    if (success) console.log(`✅ ${msg}`);
    else console.error(`❌ ${msg}`);
};

async function runTests() {
    console.log("=== STARTING NODE.JS DOMAIN_FR TESTS ===");
    
    // --- PART 1: CONTENT DETECTION (Regex) ---
    console.log("\n--- Test 1: Content Language Detection ---");
    const domainFR = new DomainFR("http://example.com");
    
    const testCasesContent = [
        {
            name: "HTML Lang Attribute (fr-FR)",
            content: '<!DOCTYPE html><html lang="fr-FR"><head></head><body></body></html>',
            expected: "fr"
        },
        {
            name: "HTML Lang Attribute (fr)",
            content: '<html lang="fr">',
            expected: "fr"
        },
        {
            name: "OpenGraph Locale",
            content: '<meta property="og:locale" content="fr_FR" />',
            expected: "fr"
        },
        {
            name: "Meta Language",
            content: '<meta name="LANGUAGE" content="fr" />',
            expected: "fr"
        },
        {
            name: "HTTP-Equiv",
            content: '<meta http-equiv="content-language" content="fr" />',
            expected: "fr"
        },
        {
            name: "English Content",
            content: '<html lang="en-US">',
            expected: "en"
        },
        {
            name: "No Language Info",
            content: '<html><body>Hello</body></html>',
            expected: undefined // or false
        }
    ];

    for (const test of testCasesContent) {
        // Accessing private method for testing
        const result = (domainFR as any).detectLanguage(test.content);
        const val = result ? result.value : undefined;
        
        log(
            `[${test.name}] Expected: ${test.expected} | Got: ${val}`, 
            val === test.expected || (test.expected === undefined && result === false)
        );
    }

    // --- PART 2: URL PATTERN DETECTION ---
    console.log("\n--- Test 2: URL Pattern Detection ---");
    
    const testCasesUrl = [
        { url: "https://www.example.fr", name: "TLD .fr", expected: true },
        { url: "https://fr.example.com", name: "Subdomain fr.", expected: true },
        { url: "https://www.example.com/fr/page", name: "Path /fr/", expected: true },
        { url: "https://www.example.com/page?lang=fr", name: "Query lang=fr", expected: true },
        { url: "https://www.example.com/page?locale=fr-CA", name: "Query locale=fr-CA", expected: true },
        { url: "https://www.example.com", name: "Generic .com", expected: false },
        { url: "https://www.example.com/en/page", name: "English Path", expected: false }
    ];

    for (const test of testCasesUrl) {
        // We set trackRedirect=false to avoid network calls (mocking unit test)
        const result = await DomainFR.checkUrl(test.url, false);
        log(
            `[${test.name}] (${test.url}) Expected: ${test.expected} | Got: ${result.ok}`, 
            result.ok === test.expected
        );
    }

    console.log("\n=== TESTS FINISHED ===");
}

runTests().catch(console.error);
