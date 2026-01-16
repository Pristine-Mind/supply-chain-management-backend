# Loyalty Program System

This document outlines the Loyalty Program implemented in the supply chain management system.

## Features
- **Tier-based Rewards**: Different tiers (Bronze, Silver, Gold) with increasing point entry requirements.
- **Point Multipliers**: Higher tiers earn more points for the same expenditure (e.g., Bronze 1x, Silver 1.25x, Gold 1.5x).
- **Exclusive Perks**: Each tier has specific perks (e.g., Priority Support, Free Shipping, Exclusive Deals).
- **Automated Earnings**:
  - **Purchases**: Points awarded automatically on successful checkout.
  - **Reviews**: Bonus points awarded for contributing product reviews.
  - **Sign-ups**: Welcome bonus for new users.
- **Points Redemption**: Customers can redeem points for currency value (e.g., for discounts).
- **Automated Notifications**: In-app and Email alerts for:
  - Tier Upgrades (e.g., "Welcome to Silver!")
  - Point Expiry warnings (e.g., "50 points expiring in 7 days").
- **Back-office Tools**: 
  - Automated point expiry tasks.
  - Transaction archiving for performance.
  - Order-to-loyalty synchronization tasks to fix missing points.
  - Detailed analytics reports via CLI.

## Models
1. **LoyaltyTier**: Defines membership levels, multipliers, and point thresholds.
2. **LoyaltyPerk**: Benefits tied to specific tiers (e.g., "Free Shipping").
3. **UserLoyalty**: The central profile for each user tracking current and lifetime points.
4. **LoyaltyTransaction**: A ledger of every point earned, spent, or expired.
5. **LoyaltyTransactionArchive**: Long-term storage for historical transactions.
6. **LoyaltyConfiguration**: Global settings for point values and expiry rules.


## API Endpoints (v1)
- `GET /api/v1/loyalty/user/`: Get current user's profile and tier status.
- `GET /api/v1/loyalty/user/summary/`: Get detailed dashboard data (stats, next tier progress).
- `GET /api/v1/loyalty/user/transactions/`: List user's point history (paginated).
- `POST /api/v1/loyalty/user/redeem/`: Redeem points (`points`, `description` required).
- `GET /api/v1/loyalty/tiers/`: List all available tiers and included perks.

---

# Frontend Integration Requirements

To fully leverage the loyalty system, the following features should be implemented in the frontend:

### 1. User Dashboard / Profile Page
- **Tier Badge**: Display the user's current tier (Bronze/Silver/Gold) prominently.
- **Points Balance**: Show current "Spendable Points" vs "Lifetime Points".
- **Progress Bar**: Visualize progress toward the "Next Tier" (e.g., "You need 250 more points to reach Gold").
- **Perk List**: List active perks the user currently enjoys based on their tier.

### 2. Loyalty History Page
- **Transaction List**: A list of earned/spent points with dates and descriptions.
- **Filtering**: Allow users to filter by "Earned", "Spent", or "Expired".

### 3. Checkout Integration
- **Redemption Toggle**: Allow users to apply points as a discount.
- **Point Projection**: Show how many points the user *will* earn from the current cart (e.g., "Buy this and earn 45 points").
- **Tier Multiplier Indicator**: Remind users of their bonus (e.g., "Silver Member: 1.25x Points Applied").

### 4. Tier Exploration Page
- **Comparison Table**: A "Compare Tiers" view showing what Bronze, Silver, and Gold members get.
- **CTA**: "Shop more to reach Silver" buttons for Bronze users.

### 5. Review Incentives
- **Call to Action**: On "Pending Reviews", show potential points (e.g., "Review this product and earn 5 points!").

### 6. Notifications
- **Toast/Popup**: Real-time tray notifications for "Points Earned" after checkout and "Tier Upgraded" alerts.
