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
            timeout=120
        ), os.getenv('WORDPRESS_URL', 'https://jamjam.hr')
    else:  # berliner
        return API(
            url=os.getenv('BERLINER_WORDPRESS_URL', 'https://berliner.hr'),
            consumer_key=os.getenv('BERLINER_WC_API_KEY'),
            consumer_secret=os.getenv('BERLINER_WC_API_SECRET'),
            version="wc/v3",
            timeout=120
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
    
    if site == 'jamjam':
        endpoint = f"{wordpress_url}/wp-json/jamjam/v1/get-all-stock"
    else:
        endpoint = f"{wordpress_url}/wp-json/thor/v1/get-all-stock"
    
    try:
        response = requests.get(endpoint, timeout=120)
        stock_data = response.json()
        total_products = len(stock_data)
        print(f"📦 Loaded {total_products} products from {site}")
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return jsonify({"error": str(e)}), 500
    
    # Batch update - 50 proizvoda odjednom
    updated = 0
    errors = 0
    skipped = 0
    batch_data = {'update': []}
    
    # Prvo kreiraj lookup dictionary (SKU -> product_id)
    print("🔍 Building SKU lookup...")
    sku_to_id = {}
    page = 1
    per_page = 100
    
    while True:
        try:
            products = wcapi.get("products", params={"per_page": per_page, "page": page}).json()
            if not products or len(products) == 0:
                break
            
            for product in products:
                if 'sku' in product and product['sku']:
                    sku_to_id[product['sku']] = product['id']
            
            page += 1
            
            if page % 10 == 0:
                print(f"📋 Loaded {len(sku_to_id)} products so far...")
                
        except Exception as e:
            print(f"⚠️ Error loading products page {page}: {e}")
            break
    
    print(f"✅ SKU lookup complete: {len(sku_to_id)} products")
    
    # Sad updateiraj stock
    for sku, locations in stock_data.items():
        try:
            total = sum(locations.values())
            
            # Provjeri da li proizvod postoji
            if sku not in sku_to_id:
                skipped += 1
                continue
            
            product_id = sku_to_id[sku]
            
            # Dodaj u batch
            batch_data['update'].append({
                'id': product_id,
                'stock_quantity': total,
                'manage_stock': True,
                'stock_status': 'instock' if total > 0 else 'outofstock'
            })
            
            # Kad stigneš do 50, pošalji batch
            if len(batch_data['update']) >= 50:
                try:
                    result = wcapi.post("products/batch", batch_data)
                    if result.status_code == 200:
                        updated += len(batch_data['update'])
                        print(f"✅ Updated {updated}/{total_products}")
                    else:
                        errors += len(batch_data['update'])
                        print(f"❌ Batch failed: {result.status_code}")
                    batch_data = {'update': []}
                except Exception as e:
                    errors += len(batch_data['update'])
                    print(f"❌ Batch error: {e}")
                    batch_data = {'update': []}
                
        except Exception as e:
            errors += 1
            print(f"❌ Error processing {sku}: {e}")
    
    # Pošalji zadnji batch
    if len(batch_data['update']) > 0:
        try:
            result = wcapi.post("products/batch", batch_data)
            if result.status_code == 200:
                updated += len(batch_data['update'])
            else:
                errors += len(batch_data['update'])
        except Exception as e:
            errors += len(batch_data['update'])
    
    print(f"🎉 {site.upper()} done: {updated} updated, {errors} errors, {skipped} skipped")
    
    return jsonify({
        "success": True,
        "site": site,
        "updated": updated,
        "errors": errors,
        "skipped": skipped,
        "total": total_products
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
