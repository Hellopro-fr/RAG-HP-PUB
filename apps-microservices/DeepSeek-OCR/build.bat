@echo off
REM DeepSeek-OCR Docker Build Script for Windows
REM This script builds the Docker container with the new folder structure

echo 🔧 Building DeepSeek-OCR Docker container...

REM Check if models directory exists
if not exist "models" (
    echo ⚠️  Models directory not found. Creating it...
    mkdir models
    echo 💡 Please download the DeepSeek-OCR model to models\deepseek-ai\DeepSeek-OCR\
    echo    Run: huggingface-cli download deepseek-ai/DeepSeek-OCR --local-dir models\deepseek-ai/DeepSeek-OCR
    echo.
)

REM Check if model files exist
if not exist "models\deepseek-ai\DeepSeek-OCR\config.json" (
    echo ❌ Model files not found in models\deepseek-ai\DeepSeek-OCR\
    echo 💡 Please download the model first:
    echo    huggingface-cli download deepseek-ai/DeepSeek-OCR --local-dir models\deepseek-ai\DeepSeek-OCR
    echo.
    pause
    exit /b 1
)

REM Check if DeepSeek-OCR source exists
if not exist "DeepSeek-OCR\DeepSeek-OCR-master" (
    echo ❌ DeepSeek-OCR source not found in DeepSeek-OCR\DeepSeek-OCR-master\
    pause
    exit /b 1
)

REM Build the Docker image
echo 🏗️  Building Docker image with CUDA 12.1...
echo ⏳ This may take 10-20 minutes on first build...
echo.
echo 🧹 Clearing Docker build cache to ensure latest changes...

docker builder prune -f
echo.
docker-compose build

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ Build failed!
    echo 💡 Possible solutions:
    echo    1. Ensure Docker Desktop is running with GPU support
    echo    2. Check that NVIDIA Container Toolkit is installed
    echo    3. Verify you have sufficient disk space (10GB+)
    echo    4. Try running: docker system prune -f
    echo.
    pause
    exit /b 1
)

echo ✅ Build complete!
echo.
echo 🚀 To start the service, run:
echo    docker-compose up -d
echo.
echo 🔍 To check the service, run:
echo    curl http://localhost:8000/health
echo.
echo 📋 To view logs, run:
echo    docker-compose logs -f deepseek-ocr
echo.
echo 🔧 New OCR functionality added:
echo    - Enhanced PDF to OCR processor (pdf_to_ocr_enhanced.py)
echo    - OCR-specific prompt support: '<image>\nFree OCR.'
echo    - Test scripts: test_ocr_prompt.py, quick_test_ocr.py
echo.
echo 🧪 To test OCR functionality:
echo    docker-compose exec deepseek-ocr python quick_test_ocr.py
echo.
pause