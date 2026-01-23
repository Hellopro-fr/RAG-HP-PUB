import sys
import os
import asyncio
import logging

# Ensure 'src' is in python path to import the module
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, '..', 'src')
sys.path.insert(0, src_path)

from redirect_tracker import RedirectTracker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Test")

async def run_tests():
    logger.info("=== STARTING PYTHON REDIRECT TRACKER TESTS ===")
    tracker = RedirectTracker()
    test_url = "http://github.com" # Should redirect to https://github.com

    # 1. Test Local Redirection (httpx)
    logger.info("\n--- Test 1: Local HTTP Redirection ---")
    try:
        result = await tracker.get_url_redirection(test_url)
        
        if result['success'] and len(result['redirects']) > 0:
            logger.info("✅ Success: Detected redirects locally.")
            logger.info(f"Redirect Chain: {result['redirect_chain']}")
            logger.info(f"Final URL: {result['final_url']}")
        else:
            logger.info("❌ Failed: No redirects detected or request failed.")
            logger.info(result)
            
    except Exception as e:
        logger.error(f"❌ Error during local test: {e}")

    # 2. Test Pemavor API Fallback
    logger.info("\n--- Test 2: Pemavor API Redirection ---")
    try:
        urls_to_check = [test_url]
        # Call the static method
        result = await RedirectTracker.get_url_redirection_pemavor(urls_to_check)

        if result['success'] and 'data' in result:
            logger.info("✅ Success: Received response from Pemavor API.")
            
            # Basic validation of response structure
            api_data = result['data']
            if 'Data' in api_data and test_url in api_data['Data']:
                chain = api_data['Data'][test_url]
                final_hop = chain[-1]
                logger.info(f"Final Hop from API: {final_hop}")
            else:
                logger.info(f"⚠️ API Response format unexpected: {api_data.keys()}")
        else:
            logger.info(f"❌ Failed: API request unsuccessful. Status: {result.get('status_code')}")
            if 'error' in result:
                logger.error(f"Error details: {result['error']}")

    except Exception as e:
        logger.error(f"❌ Error during Pemavor test: {e}")
        
    logger.info("\n=== TESTS FINISHED ===")

if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        pass
