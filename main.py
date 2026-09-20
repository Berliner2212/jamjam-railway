from flask import Flask, request, jsonify
import requests
import time
import logging
import os
from threading import Thread

app = Flask(__name__)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Konfiguracija
WP_JAMJAM_URL = 'https://jamjam.hr/wp-json/jamjam/v1'
WP_BERLINER_URL = 'https://berliner.hr/wp-json/thor/v1'

BATCH_SIZE = 25
DELAY_SECONDS = 2

# JamJam lokacije
JAMJAM_LOCATIONS = ['p001', 'p0001', 'p14', 'p18', 'p28', 'p20']

def send_batch(items, endpoint, base_url):
    """Šalje jedan batch na WordPress"""
    try:
        url = f"{base_url}{endpoint}"
        logger.info(f"🔄 Sending {len(items)} items to {url}")

        response = requests.post(
            url,
            json=items,
            timeout=90,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 BerlinerStockSync/1.0',
            }
        )

        logger.info(f"📡 WordPress response: {response.status_code}")
        logger.info(f"📡 Final URL: {response.url}")
        logger.info(f"📡 Body: {response.text[:300]}")
        response.raise_for_status()

        # Provjera da je odgovor stvarno od WordPress plugina, a ne HTML / challenge stranica
        try:
            data = response.json()
        except ValueError:
            logger.error(f"❌ Non-JSON response for {endpoint} — request did not reach WordPress plugin")
            return {'success': False, 'count': len(items), 'error': 'Non-JSON response: ' + response.text[:200]}

        if not isinstance(data, dict) or 'status' not in data:
            logger.error(f"❌ Unexpected response for {endpoint}: {data}")
            return {'success': False, 'count': len(items), 'error': f'Unexpected response: {data}'}

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

def process_location(items, endpoint, location_name, base_url):
    """Procesira sve stavke za jednu lokaciju"""
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
    
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        
        logger.info(f"📤 Sending batch {batch_num} for {location_name} ({len(batch)} items)")
        
        result = send_batch(batch, endpoint, base_url)
        
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
        
        if i + BATCH_SIZE < len(items):
            logger.info(f"⏳ Waiting {DELAY_SECONDS}s before next batch...")
            time.sleep(DELAY_SECONDS)
    
    logger.info(f"✅ {location_name} completed: {results['success']}/{results['total']} successful")
    return results

def process_in_background(items, endpoint, location_name, base_url):
    """Procesira u pozadini"""
    logger.info(f"🔄 Background processing started for {location_name}")
    results = process_location(items, endpoint, location_name, base_url)
    logger.info(f"✅ Background processing completed for {location_name}: {results}")

# ============================================
# BERLINER ENDPOINTS (Split, Osijek)
# ============================================

@app.route('/berliner/split', methods=['POST'])
def berliner_split():
    """Berliner Split endpoint"""
    try:
        items = request.get_json()
        if not isinstance(items, list):
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 [BERLINER] Received {len(items)} Split items")
        
        # Pokreni u pozadini
        thread = Thread(
            target=process_in_background,
            args=(items, '/split', 'Berliner Split', WP_BERLINER_URL)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'accepted',
            'message': f'Processing {len(items)} items in background',
            'site': 'berliner',
            'location': 'split'
        }), 202
    except Exception as e:
        logger.error(f"❌ [BERLINER] Error in split: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/berliner/osijek', methods=['POST'])
def berliner_osijek():
    """Berliner Osijek endpoint"""
    try:
        items = request.get_json()
        if not isinstance(items, list):
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 [BERLINER] Received {len(items)} Osijek items")
        
        # Pokreni u pozadini
        thread = Thread(
            target=process_in_background,
            args=(items, '/osijek', 'Berliner Osijek', WP_BERLINER_URL)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'accepted',
            'message': f'Processing {len(items)} items in background',
            'site': 'berliner',
            'location': 'osijek'
        }), 202
    except Exception as e:
        logger.error(f"❌ [BERLINER] Error in osijek: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================
# JAMJAM ENDPOINTS (P001, P0001, P14, P18, P28, P20)
# ============================================

@app.route('/jamjam/<location>', methods=['POST'])
def jamjam_location(location):
    """JamJam dynamic location endpoint"""
    try:
        if location not in JAMJAM_LOCATIONS:
            return jsonify({'error': f'Invalid location. Valid: {JAMJAM_LOCATIONS}'}), 400
        
        items = request.get_json()
        if not isinstance(items, list):
            return jsonify({'error': 'Expected array of items'}), 400
        
        logger.info(f"📥 [JAMJAM] Received {len(items)} items for {location.upper()}")
        
        # Pokreni u pozadini
        thread = Thread(
            target=process_in_background,
            args=(items, f'/{location}', f'JamJam {location.upper()}', WP_JAMJAM_URL)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'accepted',
            'message': f'Processing {len(items)} items in background',
            'site': 'jamjam',
            'location': location
        }), 202
    except Exception as e:
        logger.error(f"❌ [JAMJAM] Error in {location}: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================
# UTILITY ENDPOINTS
# ============================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'Multi-Site Stock Sync',
        'sites': {
            'berliner': ['split', 'osijek'],
            'jamjam': JAMJAM_LOCATIONS
        },
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'Multi-Site Stock Sync Railway',
        'version': '2.1',
        'sites': {
            'berliner': {
                'url': 'https://berliner.hr',
                'endpoints': ['/berliner/split', '/berliner/osijek']
            },
            'jamjam': {
                'url': 'https://jamjam.hr',
                'endpoints': [f'/jamjam/{loc}' for loc in JAMJAM_LOCATIONS]
            }
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🚀 Starting Multi-Site Stock Sync on port {port}")
    logger.info(f"📍 Berliner endpoint: {WP_BERLINER_URL}")
    logger.info(f"📍 JamJam endpoint: {WP_JAMJAM_URL}")
    logger.info(f"📦 Batch size: {BATCH_SIZE}")
    app.run(host='0.0.0.0', port=port, debug=False)
