@echo off
REM Comprehensive K8sAIOps-Agent Test Suite
REM Tests actual behavior and output validation, not just return types

echo.
echo ============================================
echo K8sAIOps-Agent Behavioral Test Suite
echo ============================================
echo.
echo Starting comprehensive behavioral tests...
echo This validates actual functionality, not just types
echo.

cd /d %~dp0

REM Run all behavioral tests with detailed output
python -m pytest tests/test_pods_behavior.py tests/test_deployments_behavior.py tests/test_metrics_behavior.py tests/test_configmaps_behavior.py tests/test_diagnostics_behavior.py tests/test_services_behavior.py -v --tb=short

echo.
echo ============================================
echo Test Summary Report
echo ============================================
echo.

REM Run with minimal output for summary
python -m pytest tests/test_pods_behavior.py tests/test_deployments_behavior.py tests/test_metrics_behavior.py tests/test_configmaps_behavior.py tests/test_diagnostics_behavior.py tests/test_services_behavior.py --tb=no -q

echo.
echo ============================================
echo Test Run Complete
echo ============================================
echo.
pause
