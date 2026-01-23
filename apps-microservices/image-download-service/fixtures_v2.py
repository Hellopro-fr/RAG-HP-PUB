import pika
import json
import random
import os
import uuid

# Configuration RabbitMQ
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
EXCHANGE_NAME = "data_exchange_produits"
ROUTING_KEY = "new_data.product"

DOMAINS = [f"shop-{i}.com" for i in range(1, 11)] # 10 domains
Ref_Id_Start = 50000

def generate_image_url(format_type):
    # placehold.co supports extensions
    # 800x800 for main images
    base = "https://placehold.co/800x800"
    color = f"{random.randint(0, 255):02x}{random.randint(0, 255):02x}{random.randint(0, 255):02x}"
    text_color = "ffffff"
    text = f"Image-{format_type}"
    return f"{base}/{color}/{text_color}.{format_type}?text={text}"

def main():
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
        
        print(f"🚀 Injecting fixtures to {EXCHANGE_NAME}...")
        
        count = 0
        formats = ["png", "jpg", "gif", "webp"]
        
        for domain in DOMAINS:
            print(f"Processing domain: {domain}")
            for i in range(20): # 20 products per domain
                product_id = Ref_Id_Start + count
                normalized_name = f"produit-test-{product_id}"
                
                # 10 images per product, mixed formats
                image_urls = []
                for _ in range(10):
                    fmt = random.choice(formats)
                    image_urls.append(generate_image_url(fmt))
                
                payload = {
                    "source": "test_web", # Changed to test_web as requested
                    "domaine": domain,
                    "id_produit": str(product_id),
                    "nom": f"Produit Test {product_id}",
                    "url_images": image_urls,
                    "url_produit": f"http://{domain}/item/{product_id}"
                }
                
                channel.basic_publish(
                    exchange=EXCHANGE_NAME,
                    routing_key=ROUTING_KEY,
                    body=json.dumps(payload),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Persistent
                    )
                )
                count += 1
                
        print(f"✅ Successfully injected {count} products with 10 images each.")
        connection.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
