from flask import Flask, request, jsonify
import requests
import os
import base64

app = Flask(__name__)

def get_wc_auth(site):
    if site == 'jamjam':
        key = os.getenv('ck_3ee27ef20acd559b210ea2f4577a9439e0a2cb9f')
        secret = os.getenv('cs_3beba8b6babdef7c911d90a43a9f2be926292791')
        url = os.getenv('WORDPRESS_URL', 'https://jamjam.hr')
    else:
        key = os.getenv('ck_5958eee3fff61c098712265a905dd9463fb74795')
        secret = os.getenv('cs_5793896b0048eb854e1592a8def97c2534ce42b9')
        url = os.getenv('BERLINER_WORDPRESS_URL', 'https://berliner.hr')
    
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return url, auth

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/update-stock-jamjam', methods=['POST'])
def update_stock_jamjam():
    return update_stock('jamjam')

@app.route('/update-stock-berliner', methods=['POST'])
def update_stock_berliner():
    return update_stock('berliner')

def update_stock(site):
    wordpress_url, auth = get_wc_auth(site)
    
    print(f"🚀 {site.upper()} stock update triggered")
    
    # Dohvati listu SKU-ova iz request body
    request_data = request.get_json()
    sku_list = request_data.get('skus', [])
    
    if not sku_list or len(sku_list) == 0:
        return jsonify({"error": "No SKUs provided"}), 400
    
    print(f"📦 Received {len(sku_list)} SKUs to update")
    
    # Dohvati stock podatke iz WordPress-a
    if site == 'jamjam':
        stock_endpoint = f"{wordpress_url}/wp-json/jamjam/v1/get-all-stock"
    else:
        stock_endpoint = f"{wordpress_url}/wp-json/thor/v1/get-all-stock"
    
    try:
        response = requests.get(stock_endpoint, timeout=120)
        all_stock_data = response.json()
    except Exception as e:
        print(f"❌ Error fetching stock data: {e}")
        return jsonify({"error": str(e)}), 500
    
    # Filtriraj samo SKU-ove iz liste
    stock_data = {sku: all_stock_data[sku] for sku in sku_list if sku in all_stock_data}
    
    print(f"✅ Found stock data for {len(stock_data)} products")
    
    updated = 0
    errors = 0
    not_found = 0
    
    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/json'
    }
    
    for sku, locations in stock_data.items():
        try:
            total = sum(locations.values())
            
            # Traži proizvod po SKU-u
            search_url = f"{wordpress_url}/wp-json/wc/v3/products?sku={sku}"
            search_resp = requests.get(search_url, headers=headers, timeout=30)
            
            if search_resp.status_code != 200:
                not_found += 1
                continue
            
            products = search_resp.json()
            
            if not products or len(products) == 0:
                not_found += 1
                continue
            
            product_id = products[0]['id']
            
            # Updateiraj stock
            update_url = f"{wordpress_url}/wp-json/wc/v3/products/{product_id}"
            update_data = {
                'stock_quantity': total,
                'manage_stock': True,
                'stock_status': 'instock' if total > 0 else 'outofstock'
            }
            
            update_resp = requests.put(update_url, headers=headers, json=update_data, timeout=30)
            
            if update_resp.status_code == 200:
                updated += 1
                if updated % 50 == 0:
                    print(f"✅ Updated {updated}/{len(stock_data)}")
            else:
                errors += 1
                
        except Exception as e:
            errors += 1
    
    print(f"🎉 {site.upper()} done: {updated} updated, {errors} errors, {not_found} not found")
    
    return jsonify({
        "success": True,
        "site": site,
        "updated": updated,
        "errors": errors,
        "not_found": not_found,
        "total_skus": len(sku_list)
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
