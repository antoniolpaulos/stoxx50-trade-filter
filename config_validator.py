"""
Configuration validation for STOXX50 Trade Filter.
Validates configuration on startup with helpful error messages and suggestions.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
from pathlib import Path
import re

from logger import get_logger


@dataclass
class ValidationError:
    """Represents a single validation error."""
    field: str
    message: str
    severity: str = "error"  # error, warning, info
    suggestion: Optional[str] = None
    current_value: Any = None
    expected_type: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    def get_all_issues(self) -> List[ValidationError]:
        return self.errors + self.warnings


class ConfigValidator:
    """Validates trade filter configuration."""
    
    # Valid ranges for numeric values
    VALID_RANGES = {
        'vix_warn': (5.0, 50.0),
        'intraday_change_max': (0.1, 10.0),
        'otm_percent': (0.1, 5.0),
        'wing_width': (10, 200),
        'ma_deviation_max': (0.5, 10.0),
        'prev_day_range_max': (0.5, 5.0),
        'credit': (0.5, 10.0),
    }
    
    # Required sections
    REQUIRED_SECTIONS = ['rules', 'strikes']
    
    # Optional sections with defaults
    OPTIONAL_SECTIONS = {
        'additional_filters': {},
        'calendar': {'always_watch': [], 'use_backup_api': True},
        'telegram': {'enabled': False, 'bot_token': '', 'chat_id': ''},
        'portfolio': {'enabled': False, 'file': 'portfolio.json', 'credit': 2.50},
        'logging': {'enabled': True, 'level': 'INFO', 'log_dir': 'logs'}
    }
    
    def __init__(self):
        self.logger = get_logger()
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    def validate(self, config: Dict[str, Any], config_path: Optional[Path] = None) -> ValidationResult:
        """
        Validate entire configuration.
        
        Args:
            config: Configuration dictionary
            config_path: Path to config file (for context)
            
        Returns:
            ValidationResult with errors and warnings
        """
        self.errors = []
        self.warnings = []
        
        self.logger.debug("Starting configuration validation")
        
        # Check required sections
        self._validate_required_sections(config)
        
        # Validate rules section
        if 'rules' in config:
            self._validate_rules(config['rules'])
        
        # Validate strikes section
        if 'strikes' in config:
            self._validate_strikes(config['strikes'])
        
        # Validate additional filters
        if 'additional_filters' in config:
            self._validate_additional_filters(config['additional_filters'])
        
        # Validate calendar settings
        if 'calendar' in config:
            self._validate_calendar(config['calendar'])
        
        # Validate Telegram settings
        if 'telegram' in config:
            self._validate_telegram(config['telegram'])
        
        # Validate portfolio settings
        if 'portfolio' in config:
            self._validate_portfolio(config['portfolio'])
        
        # Validate logging settings
        if 'logging' in config:
            self._validate_logging(config['logging'])
        
        # Check for unknown sections
        self._validate_unknown_sections(config)
        
        # Cross-field validations
        self._validate_cross_fields(config)
        
        is_valid = len(self.errors) == 0
        
        if is_valid:
            self.logger.info("Configuration validation passed")
        else:
            self.logger.error(f"Configuration validation failed with {len(self.errors)} errors")
        
        return ValidationResult(
            is_valid=is_valid,
            errors=self.errors,
            warnings=self.warnings
        )
    
    def _validate_required_sections(self, config: Dict[str, Any]):
        """Check that all required sections are present."""
        for section in self.REQUIRED_SECTIONS:
            if section not in config:
                self.errors.append(ValidationError(
                    field=f"config.{section}",
                    message=f"Required section '{section}' is missing",
                    severity="error",
                    suggestion=f"Add the '{section}' section to your config.yaml"
                ))
    
    def _validate_rules(self, rules: Dict[str, Any]):
        """Validate rules section."""
        # vix_warn
        if 'vix_warn' in rules:
            self._validate_numeric(
                'rules.vix_warn',
                rules['vix_warn'],
                self.VALID_RANGES['vix_warn'],
                int,
                "VIX warning threshold"
            )
        else:
            self.warnings.append(ValidationError(
                field="rules.vix_warn",
                message="vix_warn not specified, using default (22)",
                severity="warning",
                suggestion="Add 'vix_warn: 22' to customize the threshold"
            ))
        
        # intraday_change_max
        if 'intraday_change_max' in rules:
            self._validate_numeric(
                'rules.intraday_change_max',
                rules['intraday_change_max'],
                self.VALID_RANGES['intraday_change_max'],
                (int, float),
                "Maximum intraday change percentage"
            )
        else:
            self.errors.append(ValidationError(
                field="rules.intraday_change_max",
                message="intraday_change_max is required",
                severity="error",
                suggestion="Add 'intraday_change_max: 1.0' for 1% maximum change"
            ))
    
    def _validate_strikes(self, strikes: Dict[str, Any]):
        """Validate strikes section."""
        # otm_percent
        if 'otm_percent' in strikes:
            self._validate_numeric(
                'strikes.otm_percent',
                strikes['otm_percent'],
                self.VALID_RANGES['otm_percent'],
                (int, float),
                "OTM percentage for strike calculation"
            )
        else:
            self.warnings.append(ValidationError(
                field="strikes.otm_percent",
                message="otm_percent not specified, using default (1.0)",
                severity="warning"
            ))
        
        # wing_width
        if 'wing_width' in strikes:
            self._validate_numeric(
                'strikes.wing_width',
                strikes['wing_width'],
                self.VALID_RANGES['wing_width'],
                int,
                "Wing width in points"
            )
        else:
            self.warnings.append(ValidationError(
                field="strikes.wing_width",
                message="wing_width not specified, using default (50)",
                severity="warning"
            ))
    
    def _validate_additional_filters(self, filters: Dict[str, Any]):
        """Validate additional_filters section."""
        # ma_deviation_max
        if 'ma_deviation_max' in filters:
            self._validate_numeric(
                'additional_filters.ma_deviation_max',
                filters['ma_deviation_max'],
                self.VALID_RANGES['ma_deviation_max'],
                (int, float),
                "Maximum MA deviation percentage"
            )
        
        # prev_day_range_max
        if 'prev_day_range_max' in filters:
            self._validate_numeric(
                'additional_filters.prev_day_range_max',
                filters['prev_day_range_max'],
                self.VALID_RANGES['prev_day_range_max'],
                (int, float),
                "Maximum previous day range percentage"
            )
        
        # check_vstoxx_term_structure
        if 'check_vstoxx_term_structure' in filters:
            if not isinstance(filters['check_vstoxx_term_structure'], bool):
                self.errors.append(ValidationError(
                    field="additional_filters.check_vstoxx_term_structure",
                    message="Must be a boolean (true/false)",
                    severity="error",
                    current_value=filters['check_vstoxx_term_structure'],
                    expected_type="boolean"
                ))
            elif filters['check_vstoxx_term_structure']:
                self.warnings.append(ValidationError(
                    field="additional_filters.check_vstoxx_term_structure",
                    message="VSTOXX term structure data is limited on yfinance",
                    severity="warning",
                    suggestion="Consider disabling this filter or using VIX as proxy"
                ))
    
    def _validate_calendar(self, calendar: Dict[str, Any]):
        """Validate calendar section."""
        # always_watch
        if 'always_watch' in calendar:
            if not isinstance(calendar['always_watch'], list):
                self.errors.append(ValidationError(
                    field="calendar.always_watch",
                    message="Must be a list of event names",
                    severity="error",
                    current_value=calendar['always_watch'],
                    expected_type="list"
                ))
            else:
                # Validate each item is a string
                for i, item in enumerate(calendar['always_watch']):
                    if not isinstance(item, str):
                        self.errors.append(ValidationError(
                            field=f"calendar.always_watch[{i}]",
                            message="Each watchlist item must be a string",
                            severity="error",
                            current_value=item,
                            expected_type="string"
                        ))
        
        # use_backup_api
        if 'use_backup_api' in calendar:
            if not isinstance(calendar['use_backup_api'], bool):
                self.errors.append(ValidationError(
                    field="calendar.use_backup_api",
                    message="Must be a boolean (true/false)",
                    severity="error",
                    current_value=calendar['use_backup_api'],
                    expected_type="boolean"
                ))
    
    def _validate_telegram(self, telegram: Dict[str, Any]):
        """Validate Telegram section."""
        if not isinstance(telegram.get('enabled'), bool):
            self.errors.append(ValidationError(
                field="telegram.enabled",
                message="Must be a boolean (true/false)",
                severity="error"
            ))
            return
        
        if telegram.get('enabled'):
            # Validate bot_token format
            token = telegram.get('bot_token', '')
            if not token or token == 'YOUR_BOT_TOKEN':
                self.errors.append(ValidationError(
                    field="telegram.bot_token",
                    message="Valid bot token required when Telegram is enabled",
                    severity="error",
                    suggestion="Get a token from @BotFather on Telegram"
                ))
            elif not re.match(r'^\d+:[A-Za-z0-9_-]+$', token):
                self.warnings.append(ValidationError(
                    field="telegram.bot_token",
                    message="Bot token format looks unusual",
                    severity="warning",
                    suggestion="Token should be in format: 123456:ABC-DEF..."
                ))
            
            # Validate chat_id
            chat_id = telegram.get('chat_id', '')
            if not chat_id or chat_id == 'YOUR_CHAT_ID':
                self.errors.append(ValidationError(
                    field="telegram.chat_id",
                    message="Valid chat ID required when Telegram is enabled",
                    severity="error",
                    suggestion="Send a message to your bot and check the API response"
                ))
    
    def _validate_portfolio(self, portfolio: Dict[str, Any]):
        """Validate portfolio section."""
        if 'credit' in portfolio:
            self._validate_numeric(
                'portfolio.credit',
                portfolio['credit'],
                self.VALID_RANGES['credit'],
                (int, float),
                "Credit per spread"
            )
        
        if 'file' in portfolio:
            if not isinstance(portfolio['file'], str):
                self.errors.append(ValidationError(
                    field="portfolio.file",
                    message="Portfolio file must be a string",
                    severity="error"
                ))
            elif not portfolio['file'].endswith('.json'):
                self.warnings.append(ValidationError(
                    field="portfolio.file",
                    message="Portfolio file should have .json extension",
                    severity="warning",
                    suggestion="Use 'portfolio.json' instead"
                ))
        
        if 'include_in_telegram' in portfolio:
            if not isinstance(portfolio['include_in_telegram'], bool):
                self.errors.append(ValidationError(
                    field="portfolio.include_in_telegram",
                    message="Must be a boolean (true/false)",
                    severity="error"
                ))
    
    def _validate_logging(self, logging_config: Dict[str, Any]):
        """Validate logging section."""
        if 'level' in logging_config:
            valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
            if logging_config['level'] not in valid_levels:
                self.errors.append(ValidationError(
                    field="logging.level",
                    message=f"Invalid log level: {logging_config['level']}",
                    severity="error",
                    current_value=logging_config['level'],
                    suggestion=f"Use one of: {', '.join(valid_levels)}"
                ))
        
        if 'log_dir' in logging_config:
            if not isinstance(logging_config['log_dir'], str):
                self.errors.append(ValidationError(
                    field="logging.log_dir",
                    message="Log directory must be a string",
                    severity="error"
                ))
    
    def _validate_unknown_sections(self, config: Dict[str, Any]):
        """Check for unknown sections in config."""
        known_sections = set(self.REQUIRED_SECTIONS) | set(self.OPTIONAL_SECTIONS.keys())
        
        for section in config.keys():
            if section not in known_sections:
                self.warnings.append(ValidationError(
                    field=f"config.{section}",
                    message=f"Unknown section '{section}' will be ignored",
                    severity="warning",
                    suggestion=f"Remove '{section}' or check for typos"
                ))
    
    def _validate_cross_fields(self, config: Dict[str, Any]):
        """Validate relationships between fields."""
        # Check that MA deviation makes sense with change threshold
        if 'additional_filters' in config and 'rules' in config:
            ma_max = config['additional_filters'].get('ma_deviation_max', 3.0)
            change_max = config['rules'].get('intraday_change_max', 1.0)
            
            if ma_max <= change_max:
                self.warnings.append(ValidationError(
                    field="additional_filters.ma_deviation_max",
                    message="MA deviation threshold should be larger than intraday change threshold",
                    severity="warning",
                    current_value=f"MA: {ma_max}%, Change: {change_max}%",
                    suggestion=f"Consider setting ma_deviation_max to at least {change_max * 2}%"
                ))
        
        # Check portfolio credit vs wing width
        if 'portfolio' in config and 'strikes' in config:
            credit = config['portfolio'].get('credit', 2.50)
            wing_width = config['strikes'].get('wing_width', 50)
            
            max_loss = wing_width - credit
            if max_loss < credit * 2:
                self.warnings.append(ValidationError(
                    field="portfolio.credit",
                    message="Credit seems high relative to wing width (limited risk/reward)",
                    severity="warning",
                    current_value=f"Credit: {credit}, Wing: {wing_width}, Max Loss: {max_loss}",
                    suggestion="Consider wider wings or lower credit for better R/R"
                ))
    
    def _validate_numeric(self, field: str, value: Any, valid_range: Tuple[float, float], 
                         valid_types: Union[type, Tuple[type, ...]], description: str):
        """Helper to validate numeric fields."""
        if not isinstance(value, valid_types):
            type_names = valid_types if isinstance(valid_types, type) else ', '.join(t.__name__ for t in valid_types)
            self.errors.append(ValidationError(
                field=field,
                message=f"{description} must be a number",
                severity="error",
                current_value=value,
                expected_type=type_names
            ))
            return
        
        min_val, max_val = valid_range
        if value < min_val or value > max_val:
            self.errors.append(ValidationError(
                field=field,
                message=f"{description} must be between {min_val} and {max_val}",
                severity="error",
                current_value=value,
                suggestion=f"Use a value between {min_val} and {max_val}"
            ))
    
    def format_report(self, result: ValidationResult) -> str:
        """Format validation result as human-readable report."""
        lines = []
        lines.append("\n" + "=" * 60)
        lines.append("CONFIGURATION VALIDATION REPORT")
        lines.append("=" * 60)
        
        if result.is_valid and not result.has_warnings:
            lines.append("✅ Configuration is valid!")
        elif result.is_valid:
            lines.append("✅ Configuration is valid (with warnings)")
        else:
            lines.append("❌ Configuration has errors!")
        
        if result.errors:
            lines.append(f"\nErrors ({len(result.errors)}):")
            for error in result.errors:
                lines.append(f"  ❌ {error.field}")
                lines.append(f"     {error.message}")
                if error.suggestion:
                    lines.append(f"     💡 {error.suggestion}")
                if error.current_value is not None:
                    lines.append(f"     Current: {error.current_value}")
        
        if result.warnings:
            lines.append(f"\nWarnings ({len(result.warnings)}):")
            for warning in result.warnings:
                lines.append(f"  ⚠️  {warning.field}")
                lines.append(f"     {warning.message}")
                if warning.suggestion:
                    lines.append(f"     💡 {warning.suggestion}")
        
        lines.append("=" * 60 + "\n")
        
        return "\n".join(lines)


def validate_config(config: Dict[str, Any], config_path: Optional[Path] = None, 
                   strict: bool = False) -> bool:
    """
    Validate configuration and optionally raise on errors.
    
    Args:
        config: Configuration dictionary
        config_path: Path to config file
        strict: If True, raise exception on validation errors
        
    Returns:
        True if valid, False otherwise
    """
    validator = ConfigValidator()
    result = validator.validate(config, config_path)
    
    # Print report
    report = validator.format_report(result)
    print(report)
    
    if not result.is_valid and strict:
        from exceptions import ConfigurationError
        raise ConfigurationError(f"Configuration validation failed with {len(result.errors)} errors")
    
    return result.is_valid


# Convenience function for use in trade_filter.py
def check_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Quick config check returning (is_valid, list_of_issues).
    
    Returns:
        Tuple of (is_valid, list of issue messages)
    """
    validator = ConfigValidator()
    result = validator.validate(config)
    
    issues = []
    for error in result.errors:
        issues.append(f"ERROR: {error.field} - {error.message}")
    for warning in result.warnings:
        issues.append(f"WARNING: {warning.field} - {warning.message}")
    
    return result.is_valid, issues
