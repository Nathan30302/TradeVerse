"""
Import routes for uploading files and triggering API imports
Handles CSV, MT4/MT5 statement uploads and broker API imports
"""
from flask import Blueprint, request, jsonify, current_app, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import hashlib
from datetime import datetime

from app import db
from app.models.broker import ImportedTradeSource, UserBrokerCredential
from app.models.trade import Trade
from app.importers.csv_importer import CSVImporter
from app.importers.mt5_parser import MT5Parser
from app.importers.oanda import OANDAImporter
from app.importers.binance import BinanceImporter
from app.utils.credential_manager import decrypt_credentials
from app.services.instrument_catalog import get_instrument

bp = Blueprint('imports', __name__, url_prefix='/imports')

UPLOAD_FOLDER = os.path.join('instance', 'uploads')
ALLOWED_EXTENSIONS = {'csv', 'htm', 'html', 'txt'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_hash(file_content):
    """Generate hash of file content for duplicate detection."""
    return hashlib.sha256(file_content).hexdigest()


@bp.route('', methods=['GET'])
@bp.route('/', methods=['GET'])
@login_required
def import_page():
    """Import landing page - choose broker and import method."""
    from app.mappers.instrument_mapper import list_available_brokers
    
    brokers = list_available_brokers()
    
    user_connections = UserBrokerCredential.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()
    
    recent_imports = ImportedTradeSource.query.filter_by(
        user_id=current_user.id
    ).order_by(ImportedTradeSource.created_at.desc()).limit(10).all()
    
    return render_template(
        'imports/index.html',
        brokers=brokers,
        user_connections=user_connections,
        recent_imports=recent_imports
    )


@bp.route('/new', methods=['GET'])
@login_required
def new_import_page():
    """Start new import - select broker and method."""
    from app.mappers.instrument_mapper import list_available_brokers
    
    broker_id = request.args.get('broker', '')
    method = request.args.get('method', '')
    
    brokers = list_available_brokers()
    
    user_connections = UserBrokerCredential.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).all()
    
    return render_template(
        'imports/new.html',
        brokers=brokers,
        selected_broker=broker_id,
        selected_method=method,
        user_connections=user_connections
    )


@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    """Upload CSV or MT4/MT5 statement file."""
    if request.method == 'GET':
        from app.mappers.instrument_mapper import list_available_brokers
        brokers = list_available_brokers()
        return render_template('imports/upload.html', brokers=brokers)
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'error': 'Invalid file type. Allowed: CSV, HTM, HTML, TXT'
        }), 400
    
    broker_id = request.form.get('broker', 'generic')
    dry_run = request.form.get('dry_run', 'false').lower() in ('true', '1', 'yes')
    
    try:
        file_content = file.read()
        file_hash = get_file_hash(file_content)
        
        existing = ImportedTradeSource.query.filter_by(
            user_id=current_user.id,
            file_hash=file_hash
        ).first()
        
        if existing and not dry_run:
            return jsonify({
                'success': False,
                'error': 'This file has already been imported',
                'existing_import_id': existing.id
            }), 400
        
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if ext == 'csv':
            importer = CSVImporter(broker_id)
        else:
            importer = MT5Parser(broker_id)
        
        importer.dry_run = dry_run
        result = importer.parse(file_content)
        
        if not result.success:
            return jsonify({
                'success': False,
                'error': result.message,
                'errors': result.errors
            }), 400
        
        result.trades = importer.validate(result.trades)
        
        if dry_run:
            return jsonify({
                'success': True,
                'dry_run': True,
                'message': f'Preview: {len(result.trades)} trades parsed',
                'result': result.to_dict()
            })
        
        upload_folder = os.path.join(current_app.root_path, UPLOAD_FOLDER)
        os.makedirs(upload_folder, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        saved_filename = f'{current_user.id}_{timestamp}_{filename}'
        filepath = os.path.join(upload_folder, saved_filename)
        
        with open(filepath, 'wb') as f:
            f.write(file_content)
        
        import_source = ImportedTradeSource(
            user_id=current_user.id,
            source_type='file',
            broker_id=broker_id,
            broker_name=broker_id,
            filename=filename,
            file_hash=file_hash,
            file_size=len(file_content),
            date_range_start=result.date_range_start,
            date_range_end=result.date_range_end,
            status='importing'
        )
        db.session.add(import_source)
        db.session.flush()
        
        imported_count = 0
        skipped_count = 0
        failed_count = 0
        
        for trade_record in result.trades:
            if trade_record.validation_errors:
                failed_count += 1
                continue
            
            existing_trade = Trade.query.filter_by(
                user_id=current_user.id,
                trade_id=trade_record.broker_ticket
            ).first()
            
            if existing_trade:
                skipped_count += 1
                continue
            
            instrument = None
            instrument_id = None
            if trade_record.canonical_symbol:
                instrument = get_instrument(trade_record.canonical_symbol)
                if instrument:
                    from app.models.instrument import Instrument
                    db_instrument = Instrument.query.filter_by(
                        symbol=instrument['symbol']
                    ).first()
                    if db_instrument:
                        instrument_id = db_instrument.id
            
            trade = Trade(
                user_id=current_user.id,
                symbol=trade_record.canonical_symbol or trade_record.broker_symbol,
                instrument_id=instrument_id,
                trade_type=trade_record.direction,
                lot_size=trade_record.lot_size,
                entry_price=trade_record.entry_price,
                exit_price=trade_record.exit_price,
                stop_loss=trade_record.stop_loss,
                take_profit=trade_record.take_profit,
                entry_date=trade_record.entry_date,
                exit_date=trade_record.exit_date,
                profit_loss=trade_record.profit_loss,
                commission=trade_record.commission,
                swap=trade_record.swap,
                status='closed' if trade_record.exit_price else 'open',
                trade_id=trade_record.broker_ticket,
                broker=broker_id,
                imported_source_id=import_source.id
            )
            db.session.add(trade)
            imported_count += 1
        
        import_source.trades_imported = imported_count
        import_source.trades_skipped = skipped_count
        import_source.trades_failed = failed_count
        import_source.status = 'completed'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully imported {imported_count} trades',
            'import_id': import_source.id,
            'trades_imported': imported_count,
            'trades_skipped': skipped_count,
            'trades_failed': failed_count
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Import error: {e}')
        return jsonify({
            'success': False,
            'error': f'Import failed: {str(e)}'
        }), 500


@bp.route('/api-import/<int:credential_id>', methods=['POST'])
@login_required
def api_import(credential_id):
    """Import trades via broker API."""
    cred = UserBrokerCredential.query.filter_by(
        id=credential_id,
        user_id=current_user.id,
        is_active=True
    ).first()
    
    if not cred:
        return jsonify({'success': False, 'error': 'Connection not found'}), 404
    
    if not cred.broker or not cred.broker.api_supported:
        return jsonify({
            'success': False,
            'error': 'This broker does not support API imports'
        }), 400
    
    broker_id = cred.broker.broker_id
    dry_run = request.json.get('dry_run', False) if request.json else False
    
    try:
        if broker_id == 'oanda':
            api_key = None
            if cred.encrypted_api_key:
                decrypted = decrypt_credentials(cred.encrypted_api_key)
                api_key = decrypted.get('key')
            
            importer = OANDAImporter(
                api_key=api_key,
                account_id=cred.account_id,
                is_practice=cred.is_demo
            )
            
        elif broker_id == 'binance':
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
        else:
            return jsonify({
                'success': False,
                'error': f'API import not implemented for {broker_id}'
            }), 400
        
        importer.dry_run = dry_run
        result = importer.parse(None)
        
        if not result.success:
            return jsonify({
                'success': False,
                'error': result.message,
                'errors': result.errors
            }), 400
        
        result.trades = importer.validate(result.trades)
        
        if dry_run:
            return jsonify({
                'success': True,
                'dry_run': True,
                'message': f'Preview: {len(result.trades)} trades found',
                'result': result.to_dict()
            })
        
        import_source = ImportedTradeSource(
            user_id=current_user.id,
            source_type='api',
            broker_id=broker_id,
            broker_name=cred.broker.name,
            date_range_start=result.date_range_start,
            date_range_end=result.date_range_end,
            status='importing'
        )
        db.session.add(import_source)
        db.session.flush()
        
        imported_count = 0
        skipped_count = 0
        
        for trade_record in result.trades:
            if trade_record.validation_errors:
                continue
            
            existing_trade = Trade.query.filter_by(
                user_id=current_user.id,
                trade_id=trade_record.broker_ticket
            ).first()
            
            if existing_trade:
                skipped_count += 1
                continue
            
            trade = Trade(
                user_id=current_user.id,
                symbol=trade_record.canonical_symbol or trade_record.broker_symbol,
                trade_type=trade_record.direction,
                lot_size=trade_record.lot_size,
                entry_price=trade_record.entry_price,
                exit_price=trade_record.exit_price,
                stop_loss=trade_record.stop_loss,
                take_profit=trade_record.take_profit,
                entry_date=trade_record.entry_date,
                exit_date=trade_record.exit_date,
                profit_loss=trade_record.profit_loss,
                commission=trade_record.commission,
                swap=trade_record.swap,
                status='closed' if trade_record.exit_price else 'open',
                trade_id=trade_record.broker_ticket,
                broker=broker_id,
                imported_source_id=import_source.id
            )
            db.session.add(trade)
            imported_count += 1
        
        import_source.trades_imported = imported_count
        import_source.trades_skipped = skipped_count
        import_source.status = 'completed'
        
        cred.last_sync_at = datetime.utcnow()
        cred.last_sync_status = 'success'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully imported {imported_count} trades',
            'import_id': import_source.id,
            'trades_imported': imported_count,
            'trades_skipped': skipped_count
        })
        
    except Exception as e:
        db.session.rollback()
        cred.last_sync_status = 'error'
        cred.last_sync_error = str(e)
        db.session.commit()
        
        current_app.logger.error(f'API import error: {e}')
        return jsonify({
            'success': False,
            'error': f'Import failed: {str(e)}'
        }), 500


@bp.route('/history', methods=['GET'])
@login_required
def import_history():
    """View import history."""
    imports = ImportedTradeSource.query.filter_by(
        user_id=current_user.id
    ).order_by(ImportedTradeSource.created_at.desc()).all()
    
    return render_template('imports/history.html', imports=imports)


@bp.route('/api/history', methods=['GET'])
@login_required
def api_import_history():
    """API: Get import history."""
    imports = ImportedTradeSource.query.filter_by(
        user_id=current_user.id
    ).order_by(ImportedTradeSource.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'imports': [i.to_dict() for i in imports]
    })


@bp.route('/api/<int:import_id>', methods=['GET'])
@login_required
def api_get_import(import_id):
    """API: Get import details."""
    import_source = ImportedTradeSource.query.filter_by(
        id=import_id,
        user_id=current_user.id
    ).first()
    
    if not import_source:
        return jsonify({'success': False, 'error': 'Import not found'}), 404
    
    trades = Trade.query.filter_by(
        imported_source_id=import_id
    ).all()
    
    return jsonify({
        'success': True,
        'import': import_source.to_dict(),
        'trades_count': len(trades)
    })
