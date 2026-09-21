@echo off
setlocal

set "ORDER_REVIEW=%~dp0processed_data\normalized\orders_full_review.html"
set "TAOBAO_REVIEW=%~dp0processed_data\normalized\payment_transactions_full_review.html"
set "MISSING=0"

if exist "%ORDER_REVIEW%" (
    start "" "%ORDER_REVIEW%"
) else (
    echo Order review HTML was not found:
    echo %ORDER_REVIEW%
    set "MISSING=1"
)

if exist "%TAOBAO_REVIEW%" (
    start "" "%TAOBAO_REVIEW%"
) else (
    echo Taobao payment review HTML was not found:
    echo %TAOBAO_REVIEW%
    set "MISSING=1"
)

if "%MISSING%"=="1" (
    echo Run transaction normalization first.
    pause
    exit /b 1
)

endlocal
