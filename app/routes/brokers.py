"""
Broker management routes with secure credential storage
Handles broker connection, credential encryption, and validation
"""
from flask import Blueprint, jsonify, request, current_app, render_template
from flask_login import login_required, current_user
import os
import json
from datetime import datetime
from app import db
from app.models.broker import BrokerProfile, UserBrokerCredential, ImportedTradeSource
from app.utils.credential_manager import encrypt_credentials, decrypt_credentials, mask_sensitive_data
from app.mappers.instrument_mapper import list_available_brokers, get_broker_profile

bp = Blueprint('brokers', __name__, url_prefix='/brokers')

BROKERS_FILE_REL = os.path.join('..', 'data', 'brokers.json')


def _load_brokers_json():
    """Load brokers from JSON file."""
    try:
        brokers_path = os.path.join(
            os.path.dirname(os.path.dirname(current_app.root_path)),
            'data', 'brokers.json'
        )
        if not os.path.exists(brokers_path):
            brokers_path = os.path.join(current_app.root_path, '..', 'data', 'brokers.json')
        
        with open(brokers_path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception as e:
        current_app.logger.error(f"Failed to load brokers.json: {e}")
        return []


@bp.route('', methods=['GET'])
@bp.route('/', methods=['GET'])
@login_required
def broker_settings_page():
    """Broker settings page - select and manage broker connections."""
    brokers = _load_brokers_json()
    
    user_credentials = UserBrokerCredential.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()
    
    connected_broker_ids = {c.broker.broker_id for c in user_credentials if c.broker}
    
    return render_template(
        'brokers/settings.html',
        brokers=brokers,
        connected_broker_ids=connected_broker_ids,
        user_credentials=user_credentials
    )


@bp.route('/api/list', methods=['GET'])
def api_list_brokers():
    """API: List all available brokers."""
    brokers = _load_brokers_json()
    safe_brokers = []
    for b in brokers:
        safe_brokers.append({
            'id': b.get('id'),
            'name': b.get('name'),
            'description': b.get('description'),
            'api_supported': b.get('api_supported', False),
            'import_formats': b.get('import_formats', []),
            'website': b.get('website'),
            'notes': b.get('notes')
        })
    return jsonify({'success': True, 'brokers': safe_brokers})


@bp.route('/api/<broker_id>', methods=['GET'])
def api_get_broker_details(broker_id):
    """API: Get details of a specific broker."""
    brokers = _load_brokers_json()
    broker = next((b for b in brokers if b.get('id') == broker_id), None)
    
    if not broker:
        return jsonify({'success': False, 'error': 'Broker not found'}), 404
    
    safe_broker = {
        'id': broker.get('id'),
        'name': broker.get('name'),
        'description': broker.get('description'),
        'api_supported': broker.get('api_supported', False),
        'api_type': broker.get('api_type'),
        'api_docs_url': broker.get('api_docs_url'),
        'import_formats': broker.get('import_formats', []),
        'account_currency_options': broker.get('account_currency_options', []),
        'website': broker.get('website'),
        'notes': broker.get('notes')
    }
    
    return jsonify({'success': True, 'broker': safe_broker})


@bp.route('/connect/<broker_id>', methods=['GET'])
@login_required
def connect_broker_page(broker_id):
    """Page to connect a broker with API credentials."""
    brokers = _load_brokers_json()
    broker = next((b for b in brokers if b.get('id') == broker_id), None)
    
    if not broker:
        return render_template('errors/404.html'), 404
    
    return render_template(
        'brokers/connect.html',
        broker=broker
    )


@bp.route('/api/connect', methods=['POST'])
@login_required
def api_connect_broker():
    """
    API: Connect to a broker by storing encrypted credentials.
    
    Requires JSON payload:
    {
        'broker_id': 'oanda' or 'binance' or other broker ID,
        'nickname': 'My Trading Account',
        'account_id': '123-456-789',
        'account_currency': 'USD',
        'is_demo': true/false,
        'credentials': {
            'api_key': '...',
            'api_secret': '...'  (if required)
        },
        'consent': true  (required - user must consent to API access)
    }
    """
    payload = request.json or {}
    broker_id = payload.get('broker_id', '').lower()
    nickname = payload.get('nickname', '')
    account_id = payload.get('account_id', '')
    account_currency = payload.get('account_currency', 'USD')
    is_demo = payload.get('is_demo', False)
    credentials = payload.get('credentials', {})
    consent = payload.get('consent', False)
    
    if not broker_id:
        return jsonify({'success': False, 'error': 'broker_id required'}), 400
    
    if not consent:
        return jsonify({
            'success': False, 
            'error': 'You must consent to API access before connecting'
        }), 400
    
    broker_profile = BrokerProfile.query.filter_by(broker_id=broker_id).first()
    if not broker_profile:
        broker_data = next((b for b in _load_brokers_json() if b.get('id') == broker_id), None)
        if not broker_data:
            return jsonify({'success': False, 'error': 'Unknown broker'}), 400
        
        broker_profile = BrokerProfile(
            broker_id=broker_id,
            name=broker_data.get('name', broker_id),
            description=broker_data.get('description'),
            api_supported=broker_data.get('api_supported', False),
            api_type=broker_data.get('api_type'),
            import_formats=broker_data.get('import_formats'),
            website=broker_data.get('website')
        )
        db.session.add(broker_profile)
        db.session.flush()
    
    try:
        encrypted_api_key = None
        encrypted_api_secret = None
        encrypted_access_token = None
        
        if credentials.get('api_key'):
            encrypted_api_key = encrypt_credentials({'key': credentials['api_key']})
        if credentials.get('api_secret'):
            encrypted_api_secret = encrypt_credentials({'secret': credentials['api_secret']})
        if credentials.get('access_token'):
            encrypted_access_token = encrypt_credentials({'token': credentials['access_token']})
        
        user_cred = UserBrokerCredential(
            user_id=current_user.id,
            broker_profile_id=broker_profile.id,
            nickname=nickname or f'{broker_profile.name} Account',
            account_id=account_id,
            account_currency=account_currency,
            is_demo=is_demo,
            encrypted_api_key=encrypted_api_key,
            encrypted_api_secret=encrypted_api_secret,
            encrypted_access_token=encrypted_access_token,
            consent_given_at=datetime.utcnow(),
            consent_ip=request.remote_addr
        )
        db.session.add(user_cred)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Broker connected successfully',
            'credential_id': user_cred.id,
            'broker_id': broker_id
        }), 201
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Broker connection error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/api/my-connections', methods=['GET'])
@login_required
def api_list_user_connections():
    """API: List user's connected brokers."""
    creds = UserBrokerCredential.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()
    
    result = []
    for cred in creds:
        result.append({
            'id': cred.id,
            'broker_id': cred.broker.broker_id if cred.broker else None,
            'broker_name': cred.broker.name if cred.broker else None,
            'nickname': cred.nickname,
            'account_id': cred.account_id,
            'account_currency': cred.account_currency,
            'is_demo': cred.is_demo,
            'last_sync_at': cred.last_sync_at.isoformat() if cred.last_sync_at else None,
            'last_sync_status': cred.last_sync_status,
            'has_api_key': bool(cred.encrypted_api_key),
            'created_at': cred.created_at.isoformat() if cred.created_at else None
        })
    
    return jsonify({'success': True, 'connections': result})


@bp.route('/api/disconnect/<int:credential_id>', methods=['DELETE'])
@login_required
def api_disconnect_broker(credential_id):
    """API: Disconnect and delete stored broker credentials."""
    cred = UserBrokerCredential.query.filter_by(
        id=credential_id,
        user_id=current_user.id
    ).first()
    
    if not cred:
        return jsonify({'success': False, 'error': 'Connection not found'}), 404
    
    cred.is_active = False
    cred.encrypted_api_key = None
    cred.encrypted_api_secret = None
    cred.encrypted_access_token = None
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Broker disconnected',
        'credential_id': credential_id
    })


@bp.route('/api/test-connection/<int:credential_id>', methods=['POST'])
@login_required
def api_test_connection(credential_id):
    """API: Test broker API connection."""
    cred = UserBrokerCredential.query.filter_by(
        id=credential_id,
        user_id=current_user.id
    ).first()
    
    if not cred:
        return jsonify({'success': False, 'error': 'Connection not found'}), 404
    
    if not cred.broker or not cred.broker.api_supported:
        return jsonify({
            'success': False,
            'error': 'This broker does not support API connections'
        }), 400
    
    broker_id = cred.broker.broker_id
    
    try:
        if broker_id == 'oanda':
            from app.importers.oanda import OANDAImporter
            
            api_key = None
            if cred.encrypted_api_key:
                decrypted = decrypt_credentials(cred.encrypted_api_key)
                api_key = decrypted.get('key')
            
            importer = OANDAImporter(
                api_key=api_key,
                account_id=cred.account_id,
                is_practice=cred.is_demo
            )
            result = importer.test_connection()
            
        elif broker_id == 'binance':
            from app.importers.binance import BinanceImporter
            
            api_key = None
            api_secret = None
            if cred.encrypted_api_key:
                decrypted = decrypt_credentials(cred.encrypted_api_key)
                api_key = decrypted.get('key')
            if cred.encrypted_api_secret:
                decrypted = decrypt_credentials(cred.encrypted_api_secret)
                api_secret = decrypted.get('secret')
            
            importer = BinanceImporter(
                api_key=api_key,
                api_secret=api_secret
            )
            result = importer.test_connection()
        else:
            return jsonify({
                'success': False,
                'error': f'API testing not implemented for {broker_id}'
            }), 400
        
        cred.last_sync_at = datetime.utcnow()
        cred.last_sync_status = 'success' if result.get('success') else 'failed'
        cred.last_sync_error = result.get('error') if not result.get('success') else None
        db.session.commit()
        
        return jsonify(result)
        
    except Exception as e:
        cred.last_sync_status = 'error'
        cred.last_sync_error = str(e)
        db.session.commit()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
