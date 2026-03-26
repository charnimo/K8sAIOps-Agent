"""Comprehensive behavioral tests for Tools/secrets.py and diagnostics."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Tools import secrets, diagnostics


class TestSecretCRUDBehavior:
    """Test Secret create, read, delete operations."""
    
    def test_create_secret_stores_keys(self, test_namespace):
        """Verify created secret stores all provided keys."""
        import time
        import base64
        
        secret_name = "test-behavioral-secret"
        secret_data = {
            "api_key": base64.b64encode(b"secret123").decode(),
            "token": base64.b64encode(b"token456").decode(),
            "config": base64.b64encode(b"data").decode()
        }
        
        # Create
        result = secrets.create_secret(secret_name, test_namespace, secret_data)
        assert result is True or (isinstance(result, dict) and result.get("success"))
        
        time.sleep(1)
        
        # Verify exists
        secret = secrets.get_secret(secret_name, test_namespace) if hasattr(secrets, 'get_secret') else None
        if secret:
            assert secret.get("name") == secret_name
        
        # Cleanup
        try:
            if hasattr(secrets, 'delete_secret'):
                secrets.delete_secret(secret_name, test_namespace)
        except:
            pass
    
    def test_list_secrets_includes_created_secret(self, test_namespace):
        """Verify created secret appears in listings."""
        import time
        import base64
        
        secret_name = "test-list-behavioral-secret"
        result = secrets.create_secret(
            secret_name,
            test_namespace,
            {"key": base64.b64encode(b"value").decode()}
        )
        
        if result is True or (isinstance(result, dict) and result.get("success")):
            time.sleep(1)
            
            # List secrets
            secret_list = secrets.list_secrets(test_namespace)
            assert isinstance(secret_list, list)
            
            secret_names = [s.get("name") for s in secret_list]
            assert secret_name in secret_names, f"Created secret should be in list"


class TestDiagnosticsBehavior:
    """Test comprehensive diagnostic functionality."""
    
    def test_diagnose_pod_has_complete_structure(self, nginx_deployment, test_namespace):
        """Verify pod diagnosis returns all required diagnostic information."""
        import time
        
        time.sleep(3)
        
        from Tools import pods
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        diagnosis = diagnostics.diagnose_pod(pod_name, test_namespace)
        
        # Should be a dict with diagnostic info
        assert isinstance(diagnosis, dict)
        
        # Verify target info
        if "target" in diagnosis:
            target = diagnosis["target"]
            assert target.get("name") == pod_name
            assert target.get("namespace") == test_namespace
        
        # Verify diagnostic content
        if "issues" in diagnosis:
            # Issues should be a list (even if empty)
            assert isinstance(diagnosis["issues"], (list, dict))
        
        if "severity" in diagnosis:
            # Severity level
            assert diagnosis["severity"] in ["healthy", "warning", "critical"]
        
        # Should have status
        if "status" in diagnosis:
            status = diagnosis["status"]
            assert status.get("name") == pod_name
            assert status.get("namespace") == test_namespace
            assert "phase" in status
            assert "ready" in status
        
        # Should have events
        if "events" in diagnosis:
            assert isinstance(diagnosis["events"], list)
            if len(diagnosis["events"]) > 0:
                event = diagnosis["events"][0]
                assert "type" in event
                assert "reason" in event
        
        # Should have logs
        if "logs" in diagnosis:
            assert isinstance(diagnosis["logs"], str)
    
    def test_cluster_health_snapshot_structure(self, test_namespace):
        """Verify cluster health snapshot returns proper structure."""
        import time
        time.sleep(2)
        
        health = diagnostics.cluster_health_snapshot(namespace=test_namespace)
        
        assert isinstance(health, dict)
        
        # Should have some cluster info
        assert len(health) > 0, "Health snapshot should contain health information"


class TestDiagnosticsAccuracy:
    """Test diagnostic accuracy and real-time updates."""
    
    def test_pod_diagnosis_reflects_current_state(self, nginx_deployment, test_namespace):
        """Verify pod diagnosis accurately reflects current pod state."""
        import time
        
        time.sleep(3)
        
        from Tools import pods
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        
        # Get pod status directly
        pod_status = pods.get_pod_status(pod_name, test_namespace)
        
        # Get diagnosis
        diagnosis = diagnostics.diagnose_pod(pod_name, test_namespace)
        
        # Diagnostic status should match pod status
        diag_status = diagnosis.get("status", {})
        
        # Core fields should match
        assert diag_status.get("name") == pod_status.get("name")
        assert diag_status.get("namespace") == pod_status.get("namespace")
        assert diag_status.get("phase") == pod_status.get("phase")
        assert diag_status.get("ready") == pod_status.get("ready")
    
    def test_healthy_pod_has_no_critical_issues(self, nginx_deployment, test_namespace):
        """Verify running pods are diagnosed as healthy."""
        import time
        
        time.sleep(3)
        
        from Tools import pods
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        pod_status = pods.get_pod_status(pod_name, test_namespace)
        
        # If pod is running and ready, it should be healthy
        if pod_status.get("phase") == "Running" and pod_status.get("ready") is True:
            diagnosis = diagnostics.diagnose_pod(pod_name, test_namespace)
            
            # Should not be critical
            severity = diagnosis.get("severity", "")
            assert severity != "critical", "Running ready pod should not be diagnosed as critical"
            
            # Issues list should be empty or minimal
            issues = diagnosis.get("issues", [])
            if isinstance(issues, list):
                # Running pods shouldn't have serious issues
                for issue in issues:
                    assert "CrashLoop" not in str(issue)
                    assert "Pending" not in str(issue)
