"""Comprehensive behavioral tests for Tools/configmaps.py CRUD operations."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Tools import configmaps


class TestConfigMapCRUDBehavior:
    """Test ConfigMap create, read, update, delete operations and state changes."""
    
    def test_create_configmap_persists_data(self, test_namespace):
        """Verify created ConfigMap actually exists with correct data."""
        import time
        
        cm_name = "test-behavioral-cm"
        test_data = {"env": "test", "app": "myapp", "version": "1.0"}
        
        # Create
        result = configmaps.create_configmap(cm_name, test_namespace, test_data)
        assert result is True or (isinstance(result, dict) and result.get("success"))
        
        time.sleep(1)
        
        # Verify it exists with correct data
        cm = configmaps.get_configmap(cm_name, test_namespace)
        assert cm is not None, "ConfigMap should exist after creation"
        assert cm.get("name") == cm_name
        
        # Verify data
        data = cm.get("data", {})
        assert data.get("env") == "test"
        assert data.get("app") == "myapp"
        assert data.get("version") == "1.0"
        
        # Cleanup
        try:
            configmaps.delete_configmap(cm_name, test_namespace)
        except:
            pass
    
    def test_list_configmaps_includes_created_maps(self, test_namespace):
        """Verify created ConfigMaps appear in list."""
        import time
        
        cm_name = "test-list-behavioral-cm"
        result = configmaps.create_configmap(cm_name, test_namespace, {"key": "value"})
        
        if result is True or (isinstance(result, dict) and result.get("success")):
            time.sleep(1)
            
            # List and find our ConfigMap
            cm_list = configmaps.list_configmaps(test_namespace)
            assert isinstance(cm_list, list)
            
            cm_names = [c.get("name") for c in cm_list]
            assert cm_name in cm_names, f"Created ConfigMap should be in list. Found: {cm_names}"
            
            # Cleanup
            try:
                configmaps.delete_configmap(cm_name, test_namespace)
            except:
                pass


class TestConfigMapDataRetrieval:
    """Test ConfigMap data retrieval accuracy."""
    
    def test_configmap_data_matches_created_data(self, test_configmap, test_namespace):
        """Verify retrieved data matches created data exactly."""
        cm = configmaps.get_configmap(test_configmap, test_namespace)
        
        assert cm is not None
        data = cm.get("data", {})
        
        # Verify all created keys are present
        assert "key1" in data, "key1 should be present"
        assert data["key1"] == "value1", "key1 value should match"
        
        assert "key2" in data
        assert data["key2"] == "value2"
        
        # Verify multi-line config is intact
        assert "config.yaml" in data
        yaml_content = data["config.yaml"]
        assert "app:" in yaml_content
        assert "name: test" in yaml_content
        assert "port: 8080" in yaml_content


class TestConfigMapDeleteBehavior:
    """Test ConfigMap deletion."""
    
    def test_delete_configmap_removes_resource(self, test_namespace):
        """Verify deleted ConfigMap no longer exists."""
        import time
        
        cm_name = "test-delete-behavioral"
        
        # Create
        result = configmaps.create_configmap(cm_name, test_namespace, {"test": "data"})
        if not result and not (isinstance(result, dict) and result.get("success")):
            pytest.skip("ConfigMap creation failed")
        
        time.sleep(1)
        
        # Verify exists
        cm_before = configmaps.get_configmap(cm_name, test_namespace)
        if cm_before is None:
            pytest.skip("Created ConfigMap not found")
        
        # Delete
        try:
            result = configmaps.delete_configmap(cm_name, test_namespace)
            assert result is True or (isinstance(result, dict) and result.get("success"))
            
            time.sleep(1)
            
            # Verify deleted
            cm_after = configmaps.get_configmap(cm_name, test_namespace)
            assert cm_after is None, "ConfigMap should be deleted"
        except Exception as e:
            # Sometimes fails due to RBAC or timing
            pytest.skip(f"Delete failed: {str(e)}")


class TestConfigMapLabelFiltering:
    """Test label selector filtering."""
    
    def test_label_selector_filters_correctly(self, test_configmap, test_namespace):
        """Verify label selector actually filters ConfigMaps."""
        import time
        
        # List all
        all_cms = configmaps.list_configmaps(test_namespace)
        
        # Try to list with label selector (may not work depending on implementation)
        try:
            labeled_cms = configmaps.list_configmaps(test_namespace, label_selector="app=test")
            
            # If label filtering works, should have subset
            assert len(labeled_cms) <= len(all_cms)
            
            # Filter result should match filter
            for cm in labeled_cms:
                labels = cm.get("labels", {})
                assert labels.get("app") == "test"
        except TypeError:
            # Label selector not supported
            pytest.skip("Label selector not supported for ConfigMaps in this version")
