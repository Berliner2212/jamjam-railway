from flask import Flask, request, jsonify
import requests
import time
import logging
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfiguracija
WP_BASE_URL = 'https://berliner.hr/wp-json/thor/v1'
BATCH_SIZE = 50  # Koliko SKU-ova odjednom
DELAY_SECONDS = 1  # Pauza između batch-eva
MAX_WORKERS = 2  # Paralelno procesiranje Split i Osijek

def send_batch(items, endpoint):
    """Šalje jedan batch na WordPress"""
    try:
        url = f"{WP_BASE_URL}{endpoint}"
        response = requests.post(
            url,
            json=items,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        return {'success': True, 'count': len(items)}
    except Exception as e:
        logger.error(f"Batch failed for {endpoint}: {str(e)}")
        return {'success': False, 'count': len(items), 'error': str(e)}

def process_location(items, endpoint, location_name):
    """Procesira sve stavke za jednu lokaciju (Split ili Osijek)"""
    if not items:
        logger.info(f"No items for {location_name}")
        return {'total': 0, 'success': 0, 'failed': 0}
    
    results = {
        'total': len(items),
        'success': 0,
        'failed': 0,
        'errors': []
    }
    
    logger.info(f"📦 Processing {len(items)} items for {location_name}")
    
    # Podijeli u batch-eve
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        
        logger.info(f"Sending batch {batch_num} for {location_name} ({len(batch)} items)")
        
        result = send_batch(batch, endpoint)
        
        if result['success']:
            results['success'] += result['count']
            logger.info(f"✓ Batch {batch_num} successful: {result['count']} items")
        else:
            results['failed'] += result['count']
            results['errors'].append({
                'batch': batch_num,
                'error': result.get('error', 'Unknown error')
            })
            logger.error(f"✗ Batch {batch_num} failed: {result.get('error')}")
        
        # Pauza između batch-eva (osim zadnjeg)
        if i + BATCH_SIZE < len(items):
            time.sleep(DELAY_SECONDS)
    
    logger.info(f"✓ {location_name} completed: {results['success']}/{results['total']} successful")
    return results

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'THOR Stock Sync',
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/sync/split', methods=['POST'])
def sync_split():
    """Endpoint za Split zalihe"""
    try:
        items = request.get_json()
        
        if not isinstance(items, list):
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 Received {len(items)} Split items")
        
        # Odmah vrati odgovor
        response = jsonify({
            'status': 'processing',
            'message': f'Processing {len(items)} Split items in batches of {BATCH_SIZE}',
            'total': len(items)
        })
        
        # Pokreni procesiranje u pozadini
        def async_process():
            results = process_location(items, '/split', 'Split')
            logger.info(f"Split sync completed: {results}")
        
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(async_process)
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error in sync_split: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/sync/osijek', methods=['POST'])
def sync_osijek():
    """Endpoint za Osijek zalihe"""
    try:
        items = request.get_json()
        
        if not isinstance(items, list):
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 Received {len(items)} Osijek items")
        
        # Odmah vrati odgovor
        response = jsonify({
            'status': 'processing',
            'message': f'Processing {len(items)} Osijek items in batches of {BATCH_SIZE}',
            'total': len(items)
        })
        
        # Pokreni procesiranje u pozadini
        def async_process():
            results = process_location(items, '/osijek', 'Osijek')
            logger.info(f"Osijek sync completed: {results}")
        
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(async_process)
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error in sync_osijek: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/sync/combined', methods=['POST'])
def sync_combined():
    """Endpoint za obje lokacije odjednom"""
    try:
        data = request.get_json()
        
        split_items = data.get('split', [])
        osijek_items = data.get('osijek', [])
        
        if not isinstance(split_items, list) and not isinstance(osijek_items, list):
            return jsonify({'error': 'Expected split and/or osijek arrays'}), 400
        
        total_count = len(split_items) + len(osijek_items)
        logger.info(f"📥 Received {len(split_items)} Split + {len(osijek_items)} Osijek items")
        
        # Odmah vrati odgovor
        response = jsonify({
            'status': 'processing',
            'message': f'Processing {len(split_items)} Split and {len(osijek_items)} Osijek items',
            'total': total_count
        })
        
        # Procesiranje u pozadini (paralelno)
        def async_process():
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                
                if split_items:
                    futures.append(executor.submit(process_location, split_items, '/split', 'Split'))
                
                if osijek_items:
                    futures.append(executor.submit(process_location, osijek_items, '/osijek', 'Osijek'))
                
                # Čekaj da sve završi
                results = [f.result() for f in futures]
                logger.info(f"Combined sync completed: {results}")
        
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(async_process)
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Error in sync_combined: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'THOR Stock Sync Railway',
        'version': '1.0',
        'endpoints': {
            'health': '/health',
            'split': '/sync/split',
            'osijek': '/sync/osijek',
            'combined': '/sync/combined'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
