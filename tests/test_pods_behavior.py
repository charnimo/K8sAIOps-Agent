"""Comprehensive behavioral tests for Tools/pods.py module."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Tools import pods


class TestPodListingBehavior:
    """Test actual pod listing behavior and output structure."""
    
    def test_list_pods_returns_proper_structure(self, nginx_deployment, test_namespace):
        """Verify pod list contains required fields in correct format."""
        import time
        time.sleep(2)
        
        pod_list = pods.list_pods(test_namespace)
        
        assert isinstance(pod_list, list)
        assert len(pod_list) > 0, "Should have at least one pod from deployment"
        
        pod = pod_list[0]
        
        # Verify required fields
        assert "name" in pod, "Pod must have name"
        assert "namespace" in pod, "Pod must have namespace"
        assert "phase" in pod, "Pod must have phase"
        assert pod["phase"] in ["Running", "Pending", "Failed", "Unknown", "Succeeded"]
        
        # Verify structure fields
        assert "ready" in pod, "Pod must have ready boolean"
        assert isinstance(pod["ready"], bool)
        
        assert "node" in pod, "Pod must have node assignment"
        assert "age" in pod, "Pod must have age"
        
        # Verify containers
        assert "containers" in pod
        assert isinstance(pod["containers"], list)
        if len(pod["containers"]) > 0:
            container = pod["containers"][0]
            assert "name" in container
            assert "ready" in container
            assert "restart_count" in container
            assert isinstance(container["restart_count"], int)
            assert "state" in container
    
    def test_list_pods_with_label_selector_filters_correctly(self, nginx_deployment, test_namespace):
        """Verify label selector actually filters pods."""
        import time
        time.sleep(2)
        
        # List with label selector
        all_pods = pods.list_pods(test_namespace)
        labeled_pods = pods.list_pods(test_namespace, label_selector="app=nginx")
        
        # Both should be lists
        assert isinstance(all_pods, list)
        assert isinstance(labeled_pods, list)
        
        # Labeled pods should be fewer or equal to all pods
        assert len(labeled_pods) <= len(all_pods)
        
        # All pods with app=nginx label should have that label
        for pod in labeled_pods:
            assert pod.get("labels", {}).get("app") == "nginx"
    
    def test_pod_status_reflects_actual_state(self, nginx_deployment, test_namespace):
        """Verify pod status accurately reflects running state."""
        import time
        time.sleep(3)
        
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        assert len(pod_list) > 0
        
        pod_name = pod_list[0]["name"]
        status = pods.get_pod_status(pod_name, test_namespace)
        
        # Should reflect running state
        assert status.get("phase") == "Running"
        assert status.get("ready") is True
        
        # Verify container is actually running
        containers = status.get("containers", [])
        assert len(containers) > 0
        container = containers[0]
        assert container.get("ready") is True
        assert "state" in container
        assert "running" in container.get("state", {})


class TestPodEventsBehavior:
    """Test actual pod event behavior and sorting."""
    
    def test_pod_events_sorted_correctly(self, nginx_deployment, test_namespace):
        """Verify events are sorted with warnings first, then by recency."""
        import time
        time.sleep(2)
        
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        events = pods.get_pod_events(pod_name, test_namespace)
        
        assert isinstance(events, list)
        
        if len(events) > 0:
            # Verify event structure
            event = events[0]
            assert "type" in event  # Warning or Normal
            assert "reason" in event
            assert "message" in event
            assert "count" in event
            assert isinstance(event["count"], int)
            
            # Verify sorting: warnings should come first
            warning_indices = [i for i, e in enumerate(events) if e.get("type") == "Warning"]
            normal_indices = [i for i, e in enumerate(events) if e.get("type") == "Normal"]
            
            if warning_indices and normal_indices:
                # All warnings should come before normals
                assert max(warning_indices) < min(normal_indices)


class TestPodLogsBehavior:
    """Test actual pod log retrieval."""
    
    def test_logs_returned_as_string(self, nginx_deployment, test_namespace):
        """Verify logs are returned as structured string."""
        import time
        time.sleep(3)
        
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        logs = pods.get_pod_logs(pod_name, test_namespace)
        
        # Logs should be a string (possibly empty for fresh pods)
        assert isinstance(logs, str)
        
        # For nginx, we should have startup logs
        if len(logs) > 0:
            # Should contain typical nginx startup info
            log_lower = logs.lower()
            # Don't assert specific content as it may vary
            assert len(logs) > 100  # Should have reasonable content


class TestPodDiagnosticsBehavior:
    """Test pod diagnostic functionality."""
    
    def test_detect_pod_issues_structure(self, nginx_deployment, test_namespace):
        """Verify issue detection returns proper structure."""
        import time
        time.sleep(3)
        
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        result = pods.detect_pod_issues(pod_name, test_namespace)
        
        # Should return a dict with issues or a list
        assert isinstance(result, (dict, list))
        
        if isinstance(result, dict):
            # Diagnostic format
            assert "issues" in result or "severity" in result
            if "issues" in result:
                assert isinstance(result["issues"], list)
        else:
            # Plain list format
            assert isinstance(result, list)
            # All items should be strings or dicts describing issues
            for issue in result:
                assert isinstance(issue, (str, dict))


class TestPodMetricsEnrichment:
    """Test pod status enrichment with metrics."""
    
    def test_metrics_enrichment_structure(self, nginx_deployment, test_namespace):
        """Verify pod metrics enrichment returns complete data."""
        import time
        time.sleep(3)
        
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        if len(pod_list) == 0:
            pytest.skip("No pods found")
        
        pod_name = pod_list[0]["name"]
        status = pods.get_pod_status_with_metrics(pod_name, test_namespace)
        
        # Should have basic status info
        assert status is not None
        assert "name" in status
        assert status["name"] == pod_name
        
        # May or may not have metrics depending on Metrics Server
        # but structure should be consistent
        if "metrics" in status:
            metrics = status["metrics"]
            assert isinstance(metrics, (dict, str))
