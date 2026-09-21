@echo off
setlocal

set "REVIEW_FILE=%~dp0processed_data\normalized\bank_transactions_full_review.html"

if not exist "%REVIEW_FILE%" (
    echo Bank review HTML was not found:
    echo %REVIEW_FILE%
    echo Run transaction normalization first.
    pause
    exit /b 1
)

start "" "%REVIEW_FILE%"
endlocal
