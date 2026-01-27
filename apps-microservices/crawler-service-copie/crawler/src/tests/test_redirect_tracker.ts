import { RedirectTracker } from "../class/RedirectTracker.js";

// simple mock for console to verify output
const log = (msg: string, data?: any) => {
    console.log(`[TEST] ${msg}`);
    if (data) console.dir(data, { depth: null, colors: true });
};

async function runTests() {
    console.log("=== STARTING NODE.JS REDIRECT TRACKER TESTS ===");
    const tracker = new RedirectTracker();
    const testUrl = "http://github.com"; // Should redirect to https://github.com

    // 1. Test Local Redirection (got-scraping)
    console.log("\n--- Test 1: Local HTTP Redirection ---");
    try {
        const result = await tracker.getUrlRedirection(testUrl);
        
        if (result.success && result.redirects.length > 0) {
            log("✅ Success: Detected redirects locally.", result.redirects);
            log("Final URL:", result.final_url);
        } else {
            log("❌ Failed: No redirects detected or request failed.", result);
        }
    } catch (error) {
        log("❌ Error during local test:", error);
    }

    // 2. Test Pemavor API Fallback
    console.log("\n--- Test 2: Pemavor API Redirection ---");
    try {
        const urlsToCheck = [testUrl];
        const result = await RedirectTracker.getUrlRedirectionPemavor(urlsToCheck);

        if (result.success && result.data) {
            log("✅ Success: Received response from Pemavor API.", result.data);
            
            // Check specific structure if needed
            const data = result.data["Data"];
            if (data && data[testUrl]) {
                const chain = data[testUrl];
                const finalStatus = chain[chain.length - 1];
                log(`Final Status for ${testUrl}:`, finalStatus);
            }
        } else {
            log("❌ Failed: API request unsuccessful.", result);
        }
    } catch (error) {
        log("❌ Error during Pemavor test:", error);
    }
    console.log("\n=== TESTS FINISHED ===");
}

runTests().catch(console.error);
