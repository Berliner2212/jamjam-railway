from flask import Flask, request, jsonify
import requests
import time
import logging
import os

app = Flask(__name__)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Konfiguracija
WP_BASE_URL = 'https://berliner.hr/wp-json/thor/v1'
BATCH_SIZE = 50  # Koliko SKU-ova odjednom
DELAY_SECONDS = 1  # Pauza između batch-eva

def send_batch(items, endpoint):
    """Šalje jedan batch na WordPress"""
    try:
        url = f"{WP_BASE_URL}{endpoint}"
        logger.info(f"🔄 Sending {len(items)} items to {url}")
        
        response = requests.post(
            url,
            json=items,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )
        
        logger.info(f"📡 WordPress response: {response.status_code}")
        
        response.raise_for_status()
        
        return {'success': True, 'count': len(items), 'status_code': response.status_code}
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed for {endpoint}: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:200]}")
        return {'success': False, 'count': len(items), 'error': str(e)}
    except Exception as e:
        logger.error(f"❌ Unexpected error for {endpoint}: {str(e)}")
        return {'success': False, 'count': len(items), 'error': str(e)}

def process_location(items, endpoint, location_name):
    """Procesira sve stavke za jednu lokaciju (Split ili Osijek)"""
    if not items:
        logger.info(f"⚠️ No items for {location_name}")
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
        
        logger.info(f"📤 Sending batch {batch_num}/{(len(items)-1)//BATCH_SIZE + 1} for {location_name} ({len(batch)} items)")
        
        result = send_batch(batch, endpoint)
        
        if result['success']:
            results['success'] += result['count']
            logger.info(f"✅ Batch {batch_num} successful: {result['count']} items")
        else:
            results['failed'] += result['count']
            results['errors'].append({
                'batch': batch_num,
                'error': result.get('error', 'Unknown error')
            })
            logger.error(f"❌ Batch {batch_num} failed: {result.get('error')}")
        
        # Pauza između batch-eva (osim zadnjeg)
        if i + BATCH_SIZE < len(items):
            logger.info(f"⏳ Waiting {DELAY_SECONDS}s before next batch...")
            time.sleep(DELAY_SECONDS)
    
    logger.info(f"✅ {location_name} completed: {results['success']}/{results['total']} successful")
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
    """Endpoint za Split zalihe - SINKRONO"""
    try:
        items = request.get_json()
        
        if not isinstance(items, list):
            logger.error("❌ Invalid request: expected array")
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 Received {len(items)} Split items")
        
        # SINKRONO procesiranje - čeka da završi
        results = process_location(items, '/split', 'Split')
        
        logger.info(f"🏁 Split sync completed: {results}")
        
        return jsonify({
            'status': 'completed',
            'message': f'Processed {len(items)} Split items',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error in sync_split: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/sync/osijek', methods=['POST'])
def sync_osijek():
    """Endpoint za Osijek zalihe - SINKRONO"""
    try:
        items = request.get_json()
        
        if not isinstance(items, list):
            logger.error("❌ Invalid request: expected array")
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 Received {len(items)} Osijek items")
        
        # SINKRONO procesiranje - čeka da završi
        results = process_location(items, '/osijek', 'Osijek')
        
        logger.info(f"🏁 Osijek sync completed: {results}")
        
        return jsonify({
            'status': 'completed',
            'message': f'Processed {len(items)} Osijek items',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error in sync_osijek: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/sync/combined', methods=['POST'])
def sync_combined():
    """Endpoint za obje lokacije odjednom - SINKRONO"""
    try:
        data = request.get_json()
        
        split_items = data.get('split', [])
        osijek_items = data.get('osijek', [])
        
        if not isinstance(split_items, list) and not isinstance(osijek_items, list):
            logger.error("❌ Invalid request: expected split and/or osijek arrays")
            return jsonify({'error': 'Expected split and/or osijek arrays'}), 400
        
        total_count = len(split_items) + len(osijek_items)
        logger.info(f"📥 Received {len(split_items)} Split + {len(osijek_items)} Osijek items")
        
        results_combined = {}
        
        # Procesiranje Split
        if split_items:
            logger.info("🔄 Starting Split processing...")
            results_combined['split'] = process_location(split_items, '/split', 'Split')
        
        # Procesiranje Osijek
        if osijek_items:
            logger.info("🔄 Starting Osijek processing...")
            results_combined['osijek'] = process_location(osijek_items, '/osijek', 'Osijek')
        
        logger.info(f"🏁 Combined sync completed: {results_combined}")
        
        return jsonify({
            'status': 'completed',
            'message': f'Processed {len(split_items)} Split and {len(osijek_items)} Osijek items',
            'results': results_combined
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error in sync_combined: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'THOR Stock Sync Railway',
        'version': '1.1 - Synchronous',
        'endpoints': {
            'health': '/health',
            'split': '/sync/split',
            'osijek': '/sync/osijek',
            'combined': '/sync/combined'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🚀 Starting THOR Stock Sync on port {port}")
    logger.info(f"📍 WordPress endpoint: {WP_BASE_URL}")
    logger.info(f"📦 Batch size: {BATCH_SIZE}")
    app.run(host='0.0.0.0', port=port, debug=False)
