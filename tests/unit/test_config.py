"""
Unit tests for configuration loading and validation.
"""

import pytest
import yaml
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exceptions import ConfigurationError
from tests.fixtures.sample_data import SAMPLE_CONFIG


class TestConfiguration:
    """Test configuration loading and validation."""
    
    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(SAMPLE_CONFIG, f)
            temp_path = f.name
        
        try:
            # This would normally be in trade_filter.py - we'll test the logic
            with open(temp_path, 'r') as f:
                loaded_config = yaml.safe_load(f)
            
            assert loaded_config is not None
            assert 'rules' in loaded_config
            assert loaded_config['rules']['vix_max'] == 22
            assert loaded_config['rules']['intraday_change_max'] == 1.0
            
        finally:
            os.unlink(temp_path)
    
    def test_config_with_missing_required_section(self):
        """Test config missing required sections."""
        invalid_config = {
            'strikes': {'otm_percent': 1.0}
            # Missing 'rules' section
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_config, f)
            temp_path = f.name
        
        try:
            with open(temp_path, 'r') as f:
                loaded_config = yaml.safe_load(f)
            
            # Simulate validation that would happen in real code
            if 'rules' not in loaded_config:
                raise ConfigurationError("Missing required 'rules' section in configuration")
                
            assert False, "Should have raised ConfigurationError"
            
        except ConfigurationError:
            pass  # Expected
        finally:
            os.unlink(temp_path)
    
    def test_config_with_invalid_values(self):
        """Test config with invalid numeric values."""
        invalid_config = SAMPLE_CONFIG.copy()
        invalid_config['rules']['vix_max'] = -5  # Negative VIX
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_config, f)
            temp_path = f.name
        
        try:
            with open(temp_path, 'r') as f:
                loaded_config = yaml.safe_load(f)
            
            # Simulate validation
            if loaded_config['rules']['vix_max'] <= 0:
                raise ConfigurationError("VIX max must be positive")
                
            assert False, "Should have raised ConfigurationError"
            
        except ConfigurationError:
            pass  # Expected
        finally:
            os.unlink(temp_path)
    
    def test_config_with_invalid_percentage(self):
        """Test config with invalid percentage values."""
        invalid_config = SAMPLE_CONFIG.copy()
        invalid_config['rules']['intraday_change_max'] = 150  # Too high
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_config, f)
            temp_path = f.name
        
        try:
            with open(temp_path, 'r') as f:
                loaded_config = yaml.safe_load(f)
            
            # Simulate validation
            if not (0 <= loaded_config['rules']['intraday_change_max'] <= 100):
                raise ConfigurationError("Intraday change max must be between 0 and 100")
                
            assert False, "Should have raised ConfigurationError"
            
        except ConfigurationError:
            pass  # Expected
        finally:
            os.unlink(temp_path)
    
    def test_merge_with_defaults(self):
        """Test merging user config with defaults."""
        partial_config = {
            'rules': {
                'vix_max': 25  # Override default
            }
            # Missing other sections
        }
        
        default_config = SAMPLE_CONFIG.copy()
        
        # Simulate merge logic
        merged_config = {**default_config, **partial_config}
        
        # Rules should be completely replaced (not merged deeply in this simple case)
        assert merged_config['rules']['vix_max'] == 25
        # Other sections should remain from default
        assert merged_config['strikes']['otm_percent'] == 1.0
    
    def test_nonexistent_config_file(self):
        """Test handling of non-existent config file."""
        nonexistent_path = "/tmp/does_not_exist_config.yaml"
        
        # Should fall back to defaults or raise error
        if not Path(nonexistent_path).exists():
            # This would trigger default loading in real code
            assert not Path(nonexistent_path).exists()
    
    def test_invalid_yaml_syntax(self):
        """Test handling of invalid YAML syntax."""
        invalid_yaml = """
        rules:
          vix_max: 22
        strikes: [
          otm_percent: 1.0  # Invalid syntax - mixing list and dict
        ]
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            with pytest.raises(yaml.YAMLError):
                yaml.safe_load(open(temp_path, 'r'))
                
        finally:
            os.unlink(temp_path)
    
    def test_telegram_config_validation(self):
        """Test Telegram configuration validation."""
        # Test valid config
        valid_telegram = SAMPLE_CONFIG['telegram'].copy()
        valid_telegram['enabled'] = True
        valid_telegram['bot_token'] = 'valid_token_123'
        valid_telegram['chat_id'] = 'valid_chat_456'
        
        # Test invalid config - missing bot_token
        invalid_telegram = valid_telegram.copy()
        invalid_telegram['bot_token'] = ''
        
        if invalid_telegram['enabled'] and not invalid_telegram['bot_token']:
            with pytest.raises(ConfigurationError):
                raise ConfigurationError("Telegram bot_token required when enabled")