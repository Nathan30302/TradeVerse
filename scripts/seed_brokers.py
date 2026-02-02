#!/usr/bin/env python3
"""
Seed broker profiles from brokers.json into database.
Run with: flask shell < scripts/seed_brokers.py
Or: python scripts/seed_brokers.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models.broker import BrokerProfile


def seed_brokers():
    """Load broker profiles from JSON and insert into database."""
    brokers_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'data', 'brokers.json'
    )
    
    if not os.path.exists(brokers_path):
        print(f"Error: {brokers_path} not found")
        return
    
    with open(brokers_path, 'r', encoding='utf-8') as f:
        brokers = json.load(f)
    
    print(f"Found {len(brokers)} broker profiles to seed...")
    
    created = 0
    updated = 0
    
    for broker_data in brokers:
        broker_id = broker_data.get('id')
        if not broker_id:
            continue
        
        existing = BrokerProfile.query.filter_by(broker_id=broker_id).first()
        
        if existing:
            existing.name = broker_data.get('name', broker_id)
            existing.description = broker_data.get('description')
            existing.symbol_patterns = broker_data.get('symbol_patterns')
            existing.symbol_mappings = broker_data.get('symbol_mappings')
            existing.lot_size_rule = broker_data.get('lot_size_rule')
            existing.pip_rules = broker_data.get('pip_rules')
            existing.tick_rules = broker_data.get('tick_rules')
            existing.account_currency_options = broker_data.get('account_currency_options')
            existing.api_supported = broker_data.get('api_supported', False)
            existing.api_type = broker_data.get('api_type')
            existing.api_auth_method = broker_data.get('api_auth_method')
            existing.api_base_url = broker_data.get('api_base_url')
            existing.api_docs_url = broker_data.get('api_docs_url')
            existing.import_formats = broker_data.get('import_formats')
            existing.csv_format = broker_data.get('csv_format')
            existing.notes = broker_data.get('notes')
            existing.website = broker_data.get('website')
            updated += 1
        else:
            broker = BrokerProfile(
                broker_id=broker_id,
                name=broker_data.get('name', broker_id),
                description=broker_data.get('description'),
                symbol_patterns=broker_data.get('symbol_patterns'),
                symbol_mappings=broker_data.get('symbol_mappings'),
                lot_size_rule=broker_data.get('lot_size_rule'),
                pip_rules=broker_data.get('pip_rules'),
                tick_rules=broker_data.get('tick_rules'),
                account_currency_options=broker_data.get('account_currency_options'),
                api_supported=broker_data.get('api_supported', False),
                api_type=broker_data.get('api_type'),
                api_auth_method=broker_data.get('api_auth_method'),
                api_base_url=broker_data.get('api_base_url'),
                api_docs_url=broker_data.get('api_docs_url'),
                import_formats=broker_data.get('import_formats'),
                csv_format=broker_data.get('csv_format'),
                notes=broker_data.get('notes'),
                website=broker_data.get('website')
            )
            db.session.add(broker)
            created += 1
    
    db.session.commit()
    print(f"Seeding complete: {created} created, {updated} updated")


if __name__ == '__main__':
    app = create_app('development')
    with app.app_context():
        seed_brokers()
