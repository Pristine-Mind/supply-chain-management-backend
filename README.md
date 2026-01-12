# Supply Chain Management & E-Commerce Backend

A comprehensive backend platform for supply chain management, B2B marketplaces, and modern shoppable content discovery.

## Key Features

- **B2B Supply Chain**: Management of Producers, Customers, Orders, and Logistics.
- **Marketplace**: Scalable product listing, bidding, and purchase workflows.
- **Shoppable Content**: TikTok-style short video and graphics platform with carousel support.
- **Recommendation Engine**: Personalized content feed based on user engagement and interests.
- **External Delivery Integration**: Integrated delivery management for various logistics providers.
- **Notifications & Communication**: Real-time alerts and internal messaging system.

## Core Modules

- `market/`: Core marketplace and shoppable content logic.
- `producer/`: Creator profiles, producer management, and inventory.
- `transport/`: Logistics and fleet management.
- `external_delivery/`: Third-party delivery service integrations.
- `notification/`: Rules-based notification engine.

## Documentation

- [Shoppable Videos & Graphics API](SHOPPABLE_VIDEOS_API.md)
- [Marketplace Product API](MARKETPLACE_PRODUCT_API.md)
- [Mobile Authentication Guide](MOBILE_AUTH_DOCUMENTATION.md)
- [B2B Pricing System](B2B_PRICING_SYSTEM_DOCUMENTATION.md)
- [Delivery API Guide](DELIVERY_API_PLATFORM_GUIDE.md)

## Getting Started

1. Install dependencies: `pip install -r requirements.txt` (or via `pyproject.toml`)
2. Run migrations: `python manage.py migrate`
3. Load initial data: `python manage.py load_video_categories`
4. Start development server: `python manage.py runserver`
