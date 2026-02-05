"""
Unit tests for configuration validation.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_validator import (
    ConfigValidator, ValidationError, ValidationResult,
    validate_config, check_config
)


class TestConfigValidator:
    """Test the ConfigValidator class."""

    def test_valid_minimal_config(self):
        """Test validation of minimal valid config."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is True

    def test_missing_required_section(self):
        """Test validation with missing required section."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            }
            # Missing 'strikes' section
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False
        assert any('strikes' in e.field for e in result.errors)

    def test_invalid_vix_warn(self):
        """Test validation of invalid vix_warn value."""
        config = {
            'rules': {
                'vix_warn': 100,  # Too high
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False
        assert any('vix_warn' in e.field for e in result.errors)

    def test_invalid_intraday_change_type(self):
        """Test validation with wrong type for intraday_change_max."""
        config = {
            'rules': {
                'intraday_change_max': 'invalid'  # Should be number
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_invalid_otm_percent_range(self):
        """Test validation of OTM percentage out of range."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 10.0,  # Too high
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False
        assert any('otm_percent' in e.field for e in result.errors)

    def test_invalid_wing_width(self):
        """Test validation of wing width."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 5  # Too low
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_telegram_enabled_missing_token(self):
        """Test validation with Telegram enabled but no token."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'telegram': {
                'enabled': True,
                'bot_token': '',
                'chat_id': ''
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False
        assert any('bot_token' in e.field for e in result.errors)

    def test_telegram_disabled_no_validation(self):
        """Test that Telegram validation is skipped when disabled."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'telegram': {
                'enabled': False,
                'bot_token': '',
                'chat_id': ''
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is True

    def test_invalid_calendar_always_watch(self):
        """Test validation of calendar always_watch."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'calendar': {
                'always_watch': 'not a list'  # Should be list
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_invalid_logging_level(self):
        """Test validation of invalid log level."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'logging': {
                'level': 'INVALID'
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_unknown_section_warning(self):
        """Test warning for unknown sections."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'unknown_section': {}  # Unknown
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is True
        assert result.has_warnings
        assert any('unknown_section' in w.field for w in result.warnings)

    def test_cross_field_validation(self):
        """Test cross-field validation."""
        config = {
            'rules': {
                'intraday_change_max': 3.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'additional_filters': {
                'ma_deviation_max': 2.0  # Less than intraday change
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is True
        assert result.has_warnings
        assert any('ma_deviation_max' in w.field for w in result.warnings)

    def test_portfolio_credit_validation(self):
        """Test portfolio credit validation."""
        config = {
            'rules': {
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'portfolio': {
                'credit': 0.3  # Too low
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_complete_valid_config(self):
        """Test complete valid configuration."""
        config = {
            'rules': {
                'vix_warn': 22,
                'intraday_change_max': 1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            },
            'additional_filters': {
                'ma_deviation_max': 3.0,
                'prev_day_range_max': 2.0,
                'check_vstoxx_term_structure': False
            },
            'calendar': {
                'always_watch': ['ECB', 'Eurozone CPI'],
                'use_backup_api': True
            },
            'telegram': {
                'enabled': False,
                'bot_token': '',
                'chat_id': ''
            },
            'portfolio': {
                'enabled': False,
                'file': 'portfolio.json',
                'credit': 2.50
            },
            'logging': {
                'enabled': True,
                'level': 'INFO',
                'log_dir': 'logs'
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is True
        assert not result.has_errors


class TestValidationResult:
    """Test ValidationResult class."""

    def test_result_properties(self):
        """Test ValidationResult properties."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[ValidationError(field="test", message="warning")]
        )

        assert result.has_errors is False
        assert result.has_warnings is True

    def test_get_all_issues(self):
        """Test getting all issues."""
        error = ValidationError(field="error_field", message="error")
        warning = ValidationError(field="warning_field", message="warning")

        result = ValidationResult(
            is_valid=False,
            errors=[error],
            warnings=[warning]
        )

        all_issues = result.get_all_issues()
        assert len(all_issues) == 2


class TestFormatReport:
    """Test report formatting."""

    def test_format_valid_config(self):
        """Test formatting valid config report."""
        config = {
            'rules': {'intraday_change_max': 1.0},
            'strikes': {'otm_percent': 1.0, 'wing_width': 50}
        }

        validator = ConfigValidator()
        result = validator.validate(config)
        report = validator.format_report(result)

        assert "CONFIGURATION VALIDATION REPORT" in report
        assert "valid" in report.lower()

    def test_format_with_errors(self):
        """Test formatting report with errors."""
        config = {
            'rules': {'intraday_change_max': 'invalid'},
            'strikes': {'otm_percent': 1.0, 'wing_width': 50}
        }

        validator = ConfigValidator()
        result = validator.validate(config)
        report = validator.format_report(result)

        assert "errors" in report.lower()
        assert "intraday_change_max" in report


class TestValidateConfig:
    """Test validate_config convenience function."""

    def test_validate_config_returns_bool(self):
        """Test that validate_config returns boolean."""
        config = {
            'rules': {'intraday_change_max': 1.0},
            'strikes': {'otm_percent': 1.0, 'wing_width': 50}
        }

        result = validate_config(config)
        assert isinstance(result, bool)
        assert result is True

    def test_validate_config_with_errors(self):
        """Test validate_config with invalid config."""
        config = {
            'rules': {'intraday_change_max': 'invalid'},
            'strikes': {'otm_percent': 1.0, 'wing_width': 50}
        }

        result = validate_config(config)
        assert result is False


class TestCheckConfig:
    """Test check_config convenience function."""

    def test_check_config_valid(self):
        """Test check_config with valid config."""
        config = {
            'rules': {'vix_warn': 22, 'intraday_change_max': 1.0},
            'strikes': {'otm_percent': 1.0, 'wing_width': 50}
        }

        is_valid, issues = check_config(config)
        assert is_valid is True
        # Config may have warnings but no errors
        assert not any('ERROR' in issue for issue in issues)

    def test_check_config_invalid(self):
        """Test check_config with invalid config."""
        config = {
            'rules': {'intraday_change_max': 'invalid'},
            'strikes': {'otm_percent': 1.0, 'wing_width': 50}
        }

        is_valid, issues = check_config(config)
        assert is_valid is False
        assert len(issues) > 0
        # Check that there is at least one ERROR in the issues
        assert any('ERROR' in issue for issue in issues)


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_config(self):
        """Test validation of empty config."""
        config = {}

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False
        assert len(result.errors) >= 2  # Missing rules and strikes

    def test_none_values(self):
        """Test validation with None values."""
        config = {
            'rules': {
                'intraday_change_max': None
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_negative_values(self):
        """Test validation with negative values."""
        config = {
            'rules': {
                'intraday_change_max': -1.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False

    def test_zero_values(self):
        """Test validation with zero values."""
        config = {
            'rules': {
                'intraday_change_max': 0.0
            },
            'strikes': {
                'otm_percent': 1.0,
                'wing_width': 50
            }
        }

        validator = ConfigValidator()
        result = validator.validate(config)

        assert result.is_valid is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
