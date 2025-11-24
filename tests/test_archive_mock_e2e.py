import os
import subprocess
import unittest

# Path to the script we want to test
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../tools/upload_daemon.sh'))
ARCHIVES_DIR = os.path.abspath(os.path.join(os.path.dirname(
    __file__), '../apps-microservices/crawler-service/crawler_archives'))

class TestArchiveMockE2E(unittest.TestCase):
    def setUp(self):
        # Ensure archives dir exists
        os.makedirs(ARCHIVES_DIR, exist_ok=True)
        
        # Create a dummy archive file
        self.test_file = os.path.join(ARCHIVES_DIR, "test_crawl_123.tar.gz")
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("dummy content")
            
    def tearDown(self):
        # Cleanup
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        # We do NOT remove the directory as it is a bind mount and should persist

    def test_daemon_logic(self):
        """
        Verifies that the bash script:
        1. Finds the file.
        2. Calls 'gcloud storage cp'.
        3. Deletes the file on success.
        """
        print(f"\nTesting script at: {SCRIPT_PATH}")
        print(f"Test file created at: {self.test_file}")

        # We will mock 'gcloud' by creating a temporary function in the shell environment
        # that the script will use.
        # The mock gcloud will just print arguments and return 0 (success).
        
        mock_gcloud = """
        gcloud() {
            echo "MOCK_GCLOUD: $*"
            if [[ "$1" == "storage" && "$2" == "cp" ]]; then
                return 0
            fi
            return 1
        }
        export -f gcloud
        """

        # We modify the script execution to include our mock
        # We also modify the script to run ONCE instead of looping, by replacing 'while true' with 'for i in 1'
        # or just by injecting a break. 
        # Actually, simpler: we can just source the script in a subshell that has the mock, 
        # BUT the script has an infinite loop.
        
        # Alternative: Create a modified temporary version of the script that runs once.
        with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
            script_content = f.read()
            
        # Replace infinite loop with single pass
        script_content = script_content.replace(
            "while true; do", "for i in 1; do")
        # We do NOT replace 'done' because the inner loop also uses 'done'
        # Remove sleep
        script_content = script_content.replace("sleep $CHECK_INTERVAL", "# sleep removed")

        tmp_script_path = os.path.join(ARCHIVES_DIR, "tmp_test_daemon.sh")
        with open(tmp_script_path, 'w', encoding='utf-8') as f:
            f.write(mock_gcloud + "\n")
            f.write(script_content)
            
        os.chmod(tmp_script_path, 0o755)

        try:
            # Run the modified script
            # We need to pass the environment variable for the bucket AND the archives dir
            env = os.environ.copy()
            env["GCS_BUCKET_NAME"] = "mock-bucket"
            env["ARCHIVES_DIR"] = ARCHIVES_DIR

            result = subprocess.run(
                ["bash", tmp_script_path],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
                check=False
            )
            
            print("Script Output:\n", result.stdout)
            print("Script Error:\n", result.stderr)

            # Assertions
            self.assertIn("Found archive: test_crawl_123.tar.gz", result.stdout)
            self.assertIn("MOCK_GCLOUD: storage cp", result.stdout)
            self.assertIn("Upload successful", result.stdout)
            
            # Verify file deletion
            self.assertFalse(os.path.exists(self.test_file), "File should have been deleted after success")

        finally:
            if os.path.exists(tmp_script_path):
                os.remove(tmp_script_path)

if __name__ == '__main__':
    unittest.main()
