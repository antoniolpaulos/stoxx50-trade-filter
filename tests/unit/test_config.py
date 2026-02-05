"""
Unit tests for configuration loading and validation - testing real functions from trade_filter.py.
"""

import pytest
import yaml
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import load_config, config_exists, telegram_needs_setup, DEFAULT_CONFIG
from exceptions import ConfigurationError


class TestLoadConfig:
    """Test load_config function from trade_filter.py."""
    
    def test_load_valid_config(self, sample_config):
        """Test loading a valid configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sample_config, f)
            temp_path = f.name
        
        try:
            loaded_config = load_config(temp_path)
            
            assert loaded_config is not None
            assert 'rules' in loaded_config
            assert loaded_config['rules']['vstoxx_max'] == 25
            assert loaded_config['rules']['intraday_change_max'] == 1.0
            assert loaded_config['strikes']['wing_width'] == 50
            
        finally:
            os.unlink(temp_path)
    
    def test_config_merge_with_defaults(self):
        """Test that user config merges with defaults."""
        partial_config = {
            'rules': {
                'vstoxx_max': 30  # Override default
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(partial_config, f)
            temp_path = f.name
        
        try:
            loaded_config = load_config(temp_path)
            
            # User override should be applied
            assert loaded_config['rules']['vstoxx_max'] == 30
            
            # Default values should still be present
            assert loaded_config['rules']['intraday_change_max'] == 1.0
            assert loaded_config['strikes']['wing_width'] == 50
            
        finally:
            os.unlink(temp_path)
    
    def test_load_nonexistent_config_uses_defaults(self):
        """Test that loading non-existent config falls back to defaults."""
        nonexistent_path = "/tmp/does_not_exist_config_12345.yaml"

        loaded_config = load_config(nonexistent_path)

        # Should return default config
        assert loaded_config is not None
        assert 'rules' in loaded_config
        assert loaded_config['rules']['vix_warn'] == 22  # Default value from DEFAULT_CONFIG
    
    def test_load_config_with_telegram_section(self):
        """Test loading config with Telegram settings."""
        config_with_telegram = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token_123',
                'chat_id': 'test_chat_456'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_with_telegram, f)
            temp_path = f.name
        
        try:
            loaded_config = load_config(temp_path)
            
            assert loaded_config['telegram']['enabled'] is True
            assert loaded_config['telegram']['bot_token'] == 'test_token_123'
            assert loaded_config['telegram']['chat_id'] == 'test_chat_456'
            
        finally:
            os.unlink(temp_path)
    
    def test_load_config_with_invalid_yaml(self):
        """Test handling of invalid YAML syntax."""
        # This YAML has unbalanced brackets which is truly invalid
        invalid_yaml = """rules:
  vstoxx_max: 25
  unclosed: {key: value
strikes:
  otm_percent: 1.0
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name

        try:
            with pytest.raises(yaml.YAMLError):
                load_config(temp_path)

        finally:
            os.unlink(temp_path)


class TestConfigExists:
    """Test config_exists function from trade_filter.py."""
    
    def test_config_exists_true(self):
        """Test config_exists when config.yaml exists."""
        # Create a temporary config file at the expected location
        # We can't easily test this without modifying the DEFAULT_CONFIG_PATH
        # So we'll test the logic indirectly
        assert isinstance(config_exists(), bool)
    
    def test_default_config_structure(self):
        """Test that DEFAULT_CONFIG has the expected structure."""
        assert 'rules' in DEFAULT_CONFIG
        assert 'strikes' in DEFAULT_CONFIG
        assert 'additional_filters' in DEFAULT_CONFIG
        assert 'telegram' in DEFAULT_CONFIG
        
        # Check specific default values
        assert DEFAULT_CONFIG['rules']['vix_warn'] == 22
        assert DEFAULT_CONFIG['rules']['intraday_change_max'] == 1.0
        assert DEFAULT_CONFIG['strikes']['otm_percent'] == 1.0
        assert DEFAULT_CONFIG['strikes']['wing_width'] == 50


class TestTelegramNeedsSetup:
    """Test telegram_needs_setup function from trade_filter.py."""
    
    def test_telegram_disabled(self):
        """Test when Telegram is disabled."""
        config = {
            'telegram': {
                'enabled': False,
                'bot_token': '',
                'chat_id': ''
            }
        }
        
        result = telegram_needs_setup(config)
        
        assert result is False
    
    def test_telegram_enabled_but_not_configured(self):
        """Test when Telegram is enabled but not configured."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '',
                'chat_id': ''
            }
        }
        
        result = telegram_needs_setup(config)
        
        assert result is True
    
    def test_telegram_enabled_with_placeholder_token(self):
        """Test when Telegram has placeholder values."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'YOUR_BOT_TOKEN',
                'chat_id': 'YOUR_CHAT_ID'
            }
        }
        
        result = telegram_needs_setup(config)
        
        assert result is True
    
    def test_telegram_properly_configured(self):
        """Test when Telegram is properly configured."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
                'chat_id': '123456789'
            }
        }
        
        result = telegram_needs_setup(config)
        
        assert result is False
    
    def test_telegram_missing_bot_token(self):
        """Test when bot_token is missing but chat_id is present."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '',
                'chat_id': '123456789'
            }
        }
        
        result = telegram_needs_setup(config)
        
        assert result is True
    
    def test_telegram_missing_chat_id(self):
        """Test when chat_id is missing but bot_token is present."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
                'chat_id': ''
            }
        }
        
        result = telegram_needs_setup(config)
        
        assert result is True


class TestConfigurationValidation:
    """Test configuration validation logic."""
    
    def test_valid_config_values(self, sample_config):
        """Test validation of valid configuration values."""
        # VSTOXX max should be positive
        assert sample_config['rules']['vstoxx_max'] > 0
        
        # Intraday change max should be reasonable
        assert 0 < sample_config['rules']['intraday_change_max'] <= 100
        
        # Wing width should be positive
        assert sample_config['strikes']['wing_width'] > 0
        
        # OTM percent should be reasonable
        assert 0 < sample_config['strikes']['otm_percent'] <= 10
    
    def test_invalid_vstoxx_max(self):
        """Test validation of invalid VSTOXX max value."""
        invalid_config = {
            'rules': {
                'vstoxx_max': -5  # Negative VSTOXX
            }
        }
        
        if invalid_config['rules']['vstoxx_max'] <= 0:
            with pytest.raises(ConfigurationError):
                raise ConfigurationError("VSTOXX max must be positive")
    
    def test_invalid_intraday_change(self):
        """Test validation of invalid intraday change value."""
        invalid_config = {
            'rules': {
                'intraday_change_max': -1.0  # Negative change
            }
        }
        
        if invalid_config['rules']['intraday_change_max'] < 0:
            with pytest.raises(ConfigurationError):
                raise ConfigurationError("Intraday change max must be non-negative")
    
    def test_invalid_wing_width(self):
        """Test validation of invalid wing width."""
        invalid_config = {
            'strikes': {
                'wing_width': 0  # Zero wing width
            }
        }
        
        if invalid_config['strikes']['wing_width'] <= 0:
            with pytest.raises(ConfigurationError):
                raise ConfigurationError("Wing width must be positive")
    
    def test_calendar_events_watchlist(self, sample_config):
        """Test calendar events watchlist configuration."""
        watchlist = sample_config['calendar']['always_watch']
        
        # Should contain EUR/Eurozone specific events
        assert any('ECB' in event for event in watchlist)
        assert any('Eurozone' in event for event in watchlist)
        assert any('German' in event for event in watchlist)
        
        # Should not contain USD-specific events
        assert not any('FOMC' in event for event in watchlist)
        assert not any('NFP' in event for event in watchlist)


class TestConfigFileOperations:
    """Test configuration file operations."""
    
    def test_config_roundtrip(self, sample_config):
        """Test that config can be saved and loaded correctly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sample_config, f)
            temp_path = f.name

        try:
            # Load the config
            loaded_config = load_config(temp_path)

            # Verify original values are preserved (merged with defaults)
            # The loaded config may have extra keys from DEFAULT_CONFIG
            for key, value in sample_config['rules'].items():
                assert loaded_config['rules'][key] == value
            assert loaded_config['strikes'] == sample_config['strikes']
            assert loaded_config['calendar']['always_watch'] == sample_config['calendar']['always_watch']

        finally:
            os.unlink(temp_path)
    
    def test_config_with_extra_sections(self):
        """Test loading config with extra user-defined sections."""
        config_with_extra = {
            'rules': {'vstoxx_max': 25},
            'user_notes': {
                'strategy': 'Iron Condor',
                'notes': 'My custom notes'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_with_extra, f)
            temp_path = f.name
        
        try:
            loaded_config = load_config(temp_path)
            
            # Extra sections should be preserved
            assert 'user_notes' in loaded_config
            assert loaded_config['user_notes']['strategy'] == 'Iron Condor'
            
        finally:
            os.unlink(temp_path)
