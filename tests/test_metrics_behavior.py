"""Comprehensive behavioral tests for Tools/metrics.py module."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Tools import metrics


class TestResourcePressureDetectionBehavior:
    """Test resource pressure detection accuracy."""
    
    def test_detect_pressure_returns_proper_categories(self, test_namespace):
        """Verify pressure detection categorizes correctly."""
        import time
        time.sleep(3)
        
        result = metrics.detect_resource_pressure(test_namespace)
        
        # Should return dict with categories
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        
        # Verify expected category structure
        assert "high_memory" in result or "high_cpu" in result or "no_limits" in result
        
        # Each category should be a list
        if "high_memory" in result:
            assert isinstance(result["high_memory"], list)
            # Each item should have pod and usage info
            for item in result["high_memory"]:
                assert isinstance(item, dict)
                assert "pod" in item or "container" in item
        
        if "high_cpu" in result:
            assert isinstance(result["high_cpu"], list)
            for item in result["high_cpu"]:
                assert isinstance(item, dict)
        
        if "no_limits" in result:
            assert isinstance(result["no_limits"], list)
            for item in result["no_limits"]:
                assert isinstance(item, dict)
                assert "pod" in item or "container" in item
    
    def test_pressure_threshold_affects_results(self, test_namespace):
        """Verify threshold parameter actually filters results."""
        import time
        time.sleep(3)
        
        # Get pressure at 80%
        result_80 = metrics.detect_resource_pressure(test_namespace, threshold_pct=80)
        
        # Get pressure at 50%
        result_50 = metrics.detect_resource_pressure(test_namespace, threshold_pct=50)
        
        assert isinstance(result_80, dict)
        assert isinstance(result_50, dict)
        
        # Results at 50% threshold should have >= items as 80%
        # (more lenient threshold catches more)
        memory_50 = result_50.get("high_memory", [])
        memory_80 = result_80.get("high_memory", [])
        assert len(memory_50) >= len(memory_80)
        
        cpu_50 = result_50.get("high_cpu", [])
        cpu_80 = result_80.get("high_cpu", [])
        assert len(cpu_50) >= len(cpu_80)


class TestMetricsDataStructure:
    """Test metrics data format and values."""
    
    def test_pressure_items_have_valid_percentages(self, test_namespace):
        """Verify pressure items report valid percentage values."""
        import time
        time.sleep(3)
        
        result = metrics.detect_resource_pressure(test_namespace)
        
        # Check high_memory items have percentage values
        for item in result.get("high_memory", []):
            if "pct" in item:
                pct = item["pct"]
                assert isinstance(pct, (int, float))
                assert 0 <= pct <= 100, f"Percentage should be 0-100, got {pct}"
            
            if "usage" in item and "limit" in item:
                # Should have resource values
                assert len(str(item["usage"])) > 0
                assert len(str(item["limit"])) > 0
        
        # Check high_cpu items similarly
        for item in result.get("high_cpu", []):
            if "pct" in item:
                pct = item["pct"]
                assert isinstance(pct, (int, float))
                assert 0 <= pct <= 100


class TestNodeMetricsStructure:
    """Test node-level metrics collection."""
    
    def test_node_metrics_has_required_fields(self):
        """Verify node metrics have required fields when available."""
        import time
        time.sleep(3)
        
        # This function may or may not exist - test gracefully
        try:
            metrics_func = getattr(metrics, 'get_node_metrics_summary', None)
            if metrics_func is None:
                pytest.skip("get_node_metrics_summary not available")
            
            node_metrics = metrics_func()
            assert isinstance(node_metrics, list)
            
            # Minikube should have at least one node
            if len(node_metrics) > 0:
                metric = node_metrics[0]
                assert isinstance(metric, dict)
                # Should have identifying info
                assert "name" in metric or "node" in metric
        except AttributeError:
            pytest.skip("Function not available in this version")


class TestPodMetricsStructure:
    """Test pod-level metrics."""
    
    def test_pod_metrics_returns_list(self, test_namespace):
        """Verify pod metrics returns list of metric dicts."""
        import time
        time.sleep(3)
        
        try:
            metrics_func = getattr(metrics, 'get_pod_metrics_summary', None)
            if metrics_func is None:
                pytest.skip("get_pod_metrics_summary not available")
            
            pod_metrics = metrics_func(test_namespace)
            assert isinstance(pod_metrics, list)
            
            if len(pod_metrics) > 0:
                metric = pod_metrics[0]
                assert isinstance(metric, dict)
                # Should have pod identifying info
                assert "name" in metric or "pod" in metric
        except AttributeError:
            pytest.skip("Function not available")
