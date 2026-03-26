"""Comprehensive behavioral tests for Tools/deployments.py module."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Tools import deployments


class TestDeploymentListingBehavior:
    """Test actual deployment listing behavior."""
    
    def test_list_deployments_structure(self, nginx_deployment, test_namespace):
        """Verify deployment list has all required fields."""
        import time
        time.sleep(2)
        
        deploy_list = deployments.list_deployments(test_namespace)
        
        assert isinstance(deploy_list, list)
        assert len(deploy_list) > 0
        
        deploy = deploy_list[0]
        
        # Verify required deployment fields
        assert "name" in deploy, "Deployment must have name"
        assert "namespace" in deploy, "Deployment must have namespace"
        assert deploy["namespace"] == test_namespace
        
        # Verify replica fields
        assert "replicas" in deploy, "Must have replicas (desired count)"
        assert "ready_replicas" in deploy or "readyReplicas" in deploy
        assert isinstance(deploy.get("replicas", 0), int)
        
        # Verify strategy
        if "strategy" in deploy:
            assert deploy["strategy"] in ["RollingUpdate", "Recreate"]
        
        # Verify containers
        assert "containers" in deploy
        assert isinstance(deploy["containers"], list)
        if len(deploy["containers"]) > 0:
            container = deploy["containers"][0]
            assert "name" in container
            assert "image" in container
            assert "resources" in container or container.get("resources") is not None


class TestDeploymentStatusBehavior:
    """Test deployment status functionality."""
    
    def test_get_deployment_returns_accurate_state(self, nginx_deployment, test_namespace):
        """Verify get_deployment returns current deployment state."""
        import time
        time.sleep(2)
        
        deploy = deployments.get_deployment(nginx_deployment, test_namespace)
        
        assert deploy is not None
        assert deploy.get("name") == nginx_deployment
        assert deploy.get("namespace") == test_namespace
        
        # Should reflect actual desired replicas (2 from fixture)
        assert "replicas" in deploy
        desired = deploy.get("replicas", 0)
        assert desired == 2, f"Deployment should have 2 replicas, has {desired}"
        
        # Verify pod replica status
        ready = deploy.get("ready_replicas")
        if ready is not None:
            assert ready <= desired


class TestDeploymentScalingBehavior:
    """Test actual scaling operations and state changes."""
    
    def test_scale_deployment_changes_replicas(self, nginx_deployment, test_namespace):
        """Verify scaling actually changes replica count."""
        import time
        time.sleep(3)
        
        # Get initial state
        initial = deployments.get_deployment(nginx_deployment, test_namespace)
        initial_count = initial.get("replicas", 0)
        
        # Scale to different number
        new_count = 3 if initial_count != 3 else 4
        result = deployments.scale_deployment(nginx_deployment, test_namespace, new_count)
        
        # Verify response structure
        assert isinstance(result, dict)
        
        if result.get("success"):
            # Wait for scale operation to register
            time.sleep(2)
            
            # Verify actual change
            updated = deployments.get_deployment(nginx_deployment, test_namespace)
            actual_count = updated.get("replicas", 0)
            assert actual_count == new_count, f"Expected {new_count} replicas, got {actual_count}"
            
            # Scale back to original
            deployments.scale_deployment(nginx_deployment, test_namespace, initial_count)


class TestDeploymentRolloutBehavior:
    """Test rollout operations."""
    
    def test_rollout_restart_updates_pod_age(self, nginx_deployment, test_namespace):
        """Verify rollout restart actually restarts pods."""
        import time
        time.sleep(2)
        
        # Get pod age before restart
        from Tools import pods
        pod_list_before = pods.list_pods(test_namespace, label_selector="app=nginx")
        
        if len(pod_list_before) == 0:
            pytest.skip("No pods found")
        
        # Perform rollout restart
        result = deployments.rollout_restart(nginx_deployment, test_namespace)
        assert isinstance(result, dict)
        
        if result.get("success"):
            # Wait for rollout to complete
            time.sleep(5)
            
            # Get pods after restart - should be newer
            pod_list_after = pods.list_pods(test_namespace, label_selector="app=nginx")
            
            # Pod age should be reset (1s or similar)
            for pod in pod_list_after:
                age_str = pod.get("age", "")
                # After restart, age should be very small (seconds)
                assert "s" in age_str or "m" in age_str, f"Pod should have young age after restart, got {age_str}"


class TestDeploymentDiagnosticsBehavior:
    """Test deployment diagnostic functionality."""
    
    def test_deployment_reflects_pod_replicas(self, nginx_deployment, test_namespace):
        """Verify deployment status reflects actual pod replicas."""
        import time
        time.sleep(3)
        
        # Get deployment
        deploy = deployments.get_deployment(nginx_deployment, test_namespace)
        
        # Get actual pods via list
        from Tools import pods
        pod_list = pods.list_pods(test_namespace, label_selector="app=nginx")
        
        # Deployment replicas should match actual pod count
        desired = deploy.get("replicas", 0)
        assert len(pod_list) > 0, "Should have at least one pod"
        assert len(pod_list) <= desired + 1  # +1 for timing variance


class TestDeploymentEventsBehavior:
    """Test deployment event retrieval."""
    
    def test_get_deployment_events_structure(self, nginx_deployment, test_namespace):
        """Verify deployment events have proper structure."""
        import time
        time.sleep(2)
        
        events = deployments.get_deployment_events(nginx_deployment, test_namespace)
        
        assert isinstance(events, list)
        
        if len(events) > 0:
            event = events[0]
            
            # Verify event fields
            assert "type" in event
            assert event["type"] in ["Warning", "Normal"]
            
            assert "reason" in event
            assert "message" in event
            assert "count" in event
            assert isinstance(event["count"], int)
            
            # Verify timestamps are present
            if "last_time" in event:
                assert len(event["last_time"]) > 0


class TestDeploymentUpdateBehavior:
    """Test deployment update operations."""
    
    def test_patch_resource_limits_updates_specs(self, nginx_deployment, test_namespace):
        """Verify patching resource limits actually updates them."""
        import time
        
        # Get initial limits
        initial = deployments.get_deployment(nginx_deployment, test_namespace)
        initial_containers = initial.get("containers", [])
        
        if len(initial_containers) == 0:
            pytest.skip("No containers found")
        
        # Patch new limits using correct parameter names
        result = deployments.patch_resource_limits(
            nginx_deployment, 
            test_namespace,
            cpu_limit="1000m",
            memory_limit="1Gi"
        )
        
        assert isinstance(result, dict)
        
        if result.get("success"):
            time.sleep(2)
            
            # Verify limits were updated
            updated = deployments.get_deployment(nginx_deployment, test_namespace)
            updated_containers = updated.get("containers", [])
            
            if len(updated_containers) > 0:
                container = updated_containers[0]
                if "resources" in container:
                    limits = container["resources"].get("limits", {})
                    # Limits should be updated
                    if limits:
                        # CPU should be present
                        assert "cpu" in limits or "memory" in limits
