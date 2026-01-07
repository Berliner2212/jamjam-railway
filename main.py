from flask import Flask, request, jsonify
import requests
from woocommerce import API
import os

app = Flask(__name__)

def get_wc_api(site):
    if site == 'jamjam':
        return API(
            url=os.getenv('WORDPRESS_URL', 'https://jamjam.hr'),
            consumer_key=os.getenv('WC_API_KEY'),
            consumer_secret=os.getenv('WC_API_SECRET'),
            version="wc/v3",
            timeout=60
        ), os.getenv('WORDPRESS_URL', 'https://jamjam.hr')
    else:  # berliner
        return API(
            url=os.getenv('BERLINER_WORDPRESS_URL', 'https://berliner.hr'),
            consumer_key=os.getenv('BERLINER_WC_API_KEY'),
            consumer_secret=os.getenv('BERLINER_WC_API_SECRET'),
            version="wc/v3",
            timeout=60
        ), os.getenv('BERLINER_WORDPRESS_URL', 'https://berliner.hr')

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
    wcapi, wordpress_url = get_wc_api(site)
    
    print(f"🚀 {site.upper()} stock update triggered")
    
    # Endpoint paths differ
    if site == 'jamjam':
        endpoint = f"{wordpress_url}/wp-json/jamjam/v1/get-all-stock"
    else:
        endpoint = f"{wordpress_url}/wp-json/thor/v1/get-all-stock"
    
    try:
        response = requests.get(endpoint, timeout=60)
        stock_data = response.json()
        total_products = len(stock_data)
        print(f"📦 Loaded {total_products} products from {site}")
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return jsonify({"error": str(e)}), 500
    
    updated = 0
    errors = 0
    
    for sku, locations in stock_data.items():
        try:
            total = sum(locations.values())
            products = wcapi.get("products", params={"sku": sku}).json()
            
            if not products or len(products) == 0:
                errors += 1
                continue
            
            product_id = products[0]['id']
            
            wcapi.put(f"products/{product_id}", {
                "stock_quantity": total,
                "manage_stock": True,
                "stock_status": "instock" if total > 0 else "outofstock"
            })
            
            updated += 1
            
            if updated % 100 == 0:
                print(f"✅ Updated {updated}/{total_products}")
                
        except Exception as e:
            errors += 1
    
    print(f"🎉 {site.upper()} done: {updated} updated, {errors} errors")
    
    return jsonify({
        "success": True,
        "site": site,
        "updated": updated,
        "errors": errors,
        "total": total_products
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
