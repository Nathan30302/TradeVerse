"""
Broker-related database models.

Includes:
- BrokerProfile: Cached broker configuration
- UserBrokerCredential: Encrypted API credentials
- ImportedTradeSource: Record of imported trade batches
"""
from datetime import datetime
from app import db


class BrokerProfile(db.Model):
    """
    Broker profile configuration.
    Can be seeded from brokers.json or created by admin.
    """
    __tablename__ = 'broker_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    broker_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    symbol_patterns = db.Column(db.JSON)
    symbol_mappings = db.Column(db.JSON)
    lot_size_rule = db.Column(db.JSON)
    pip_rules = db.Column(db.JSON)
    tick_rules = db.Column(db.JSON)
    
    account_currency_options = db.Column(db.JSON)
    
    api_supported = db.Column(db.Boolean, default=False)
    api_type = db.Column(db.String(50))
    api_auth_method = db.Column(db.String(50))
    api_base_url = db.Column(db.String(255))
    api_docs_url = db.Column(db.String(255))
    
    import_formats = db.Column(db.JSON)
    csv_format = db.Column(db.JSON)
    
    notes = db.Column(db.Text)
    website = db.Column(db.String(255))
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    credentials = db.relationship('UserBrokerCredential', backref='broker', lazy='dynamic')
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'broker_id': self.broker_id,
            'name': self.name,
            'description': self.description,
            'api_supported': self.api_supported,
            'api_type': self.api_type,
            'api_docs_url': self.api_docs_url,
            'import_formats': self.import_formats or [],
            'account_currency_options': self.account_currency_options or [],
            'website': self.website,
            'notes': self.notes
        }
    
    def __repr__(self):
        return f'<BrokerProfile {self.broker_id}>'


class UserBrokerCredential(db.Model):
    """
    Encrypted broker API credentials for a user.
    Credentials are encrypted using Fernet symmetric encryption.
    """
    __tablename__ = 'user_broker_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    broker_profile_id = db.Column(db.Integer, db.ForeignKey('broker_profiles.id'), nullable=False)
    
    nickname = db.Column(db.String(100))
    account_id = db.Column(db.String(100))
    account_currency = db.Column(db.String(10), default='USD')
    
    encrypted_api_key = db.Column(db.Text)
    encrypted_api_secret = db.Column(db.Text)
    encrypted_access_token = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True)
    is_demo = db.Column(db.Boolean, default=False)
    
    last_sync_at = db.Column(db.DateTime)
    last_sync_status = db.Column(db.String(50))
    last_sync_error = db.Column(db.Text)
    
    consent_given_at = db.Column(db.DateTime)
    consent_ip = db.Column(db.String(50))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('broker_credentials', lazy='dynamic'))
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        data = {
            'id': self.id,
            'broker_id': self.broker.broker_id if self.broker else None,
            'broker_name': self.broker.name if self.broker else None,
            'nickname': self.nickname,
            'account_id': self.account_id,
            'account_currency': self.account_currency,
            'is_active': self.is_active,
            'is_demo': self.is_demo,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'last_sync_status': self.last_sync_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        
        if include_sensitive:
            data['has_api_key'] = bool(self.encrypted_api_key)
            data['has_api_secret'] = bool(self.encrypted_api_secret)
            data['has_access_token'] = bool(self.encrypted_access_token)
        
        return data
    
    def __repr__(self):
        return f'<UserBrokerCredential {self.id} user={self.user_id}>'


class ImportedTradeSource(db.Model):
    """
    Record of an imported trade batch.
    Tracks the source file/API and import metadata.
    """
    __tablename__ = 'imported_trade_sources'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    source_type = db.Column(db.String(20), nullable=False)
    broker_id = db.Column(db.String(50))
    broker_name = db.Column(db.String(100))
    
    filename = db.Column(db.String(255))
    file_hash = db.Column(db.String(64))
    file_size = db.Column(db.Integer)
    
    import_date = db.Column(db.DateTime, default=datetime.utcnow)
    date_range_start = db.Column(db.DateTime)
    date_range_end = db.Column(db.DateTime)
    
    trades_imported = db.Column(db.Integer, default=0)
    trades_skipped = db.Column(db.Integer, default=0)
    trades_failed = db.Column(db.Integer, default=0)
    
    mapping_stats = db.Column(db.JSON)
    errors = db.Column(db.JSON)
    
    status = db.Column(db.String(20), default='pending')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('import_sources', lazy='dynamic'))
    trades = db.relationship('Trade', backref='import_source', lazy='dynamic')
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'source_type': self.source_type,
            'broker_id': self.broker_id,
            'broker_name': self.broker_name,
            'filename': self.filename,
            'import_date': self.import_date.isoformat() if self.import_date else None,
            'date_range_start': self.date_range_start.isoformat() if self.date_range_start else None,
            'date_range_end': self.date_range_end.isoformat() if self.date_range_end else None,
            'trades_imported': self.trades_imported,
            'trades_skipped': self.trades_skipped,
            'trades_failed': self.trades_failed,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<ImportedTradeSource {self.id} {self.source_type}>'
