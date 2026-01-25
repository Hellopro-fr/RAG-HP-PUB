import sys
import os
import asyncio
import logging

# Ensure 'src' is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, '..', 'src')
sys.path.insert(0, src_path)

from domain_fr import DomainFR

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Test")

async def run_tests():
    logger.info("=== STARTING PYTHON DOMAIN_FR TESTS ===")
    
    # --- PART 1: CONTENT DETECTION ---
    logger.info("\n--- Test 1: Content Language Detection ---")
    domain_fr = DomainFR("http://example.com")
    
    test_cases_content = [
        {
            "name": "HTML Lang Attribute (fr-FR)",
            "content": '<!DOCTYPE html><html lang="fr-FR"><head></head><body></body></html>',
            "expected": "fr"
        },
        {
            "name": "HTML Lang Attribute (fr)",
            "content": '<html lang="fr">',
            "expected": "fr"
        },
        {
            "name": "OpenGraph Locale",
            "content": '<meta property="og:locale" content="fr_FR" />',
            "expected": "fr"
        },
        {
            "name": "Meta Language",
            "content": '<meta name="LANGUAGE" content="fr" />',
            "expected": "fr"
        },
        {
            "name": "HTTP-Equiv",
            "content": '<meta http-equiv="content-language" content="fr" />',
            "expected": "fr"
        },
        {
            "name": "English Content",
            "content": '<html lang="en-US">',
            "expected": "en"
        },
        {
            "name": "No Language Info",
            "content": '<html><body>Hello</body></html>',
            "expected": False
        }
    ]

    for test in test_cases_content:
        result = domain_fr.detect_language(test["content"])
        
        val = result["value"] if result else False
        expected = test["expected"]
        
        is_success = val == expected
        icon = "✅" if is_success else "❌"
        logger.info(f"{icon} [{test['name']}] Expected: {expected} | Got: {val}")

    # --- PART 2: URL PATTERN DETECTION ---
    logger.info("\n--- Test 2: URL Pattern Detection ---")
    
    test_cases_url = [
        {"url": "https://www.example.fr", "name": "TLD .fr", "expected": True},
        {"url": "https://fr.example.com", "name": "Subdomain fr.", "expected": True},
        {"url": "https://www.example.com/fr/page", "name": "Path /fr/", "expected": True},
        {"url": "https://www.example.com/page?lang=fr", "name": "Query lang=fr", "expected": True},
        {"url": "https://www.example.com/page?locale=fr-CA", "name": "Query locale=fr-CA", "expected": True},
        {"url": "https://www.example.com", "name": "Generic .com", "expected": False},
        {"url": "https://www.example.com/en/page", "name": "English Path", "expected": False}
    ]

    for test in test_cases_url:
        # Check URL without tracking redirects (unit test logic)
        result = await DomainFR.check_url(test["url"], track_redirect=False)
        is_ok = result.get("ok", False)
        
        is_success = is_ok == test["expected"]
        icon = "✅" if is_success else "❌"
        logger.info(f"{icon} [{test['name']}] ({test['url']}) Expected: {test['expected']} | Got: {is_ok}")

    logger.info("\n=== TESTS FINISHED ===")

if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        pass
