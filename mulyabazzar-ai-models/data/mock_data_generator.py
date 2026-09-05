import argparse
import json
import os
import random


class MockGraphDataGenerator:
    """
    A helper class to generate synthetic, scaled mock data for the AI Graph Engine.

    Parameters:
    -----------
    num_users : int
        The total number of business profiles (VStore nodes) to generate in the network.
    products_per_user : int
        The number of products to generate for EACH user.
        (Total products will be num_users * products_per_user).
    num_interactions : int
        The total number of randomized B2B connections (EAction edges) between users.
    num_sales : int
        The total number of randomized e-commerce transactions across the platform.
    """

    def __init__(self, num_users: int, products_per_user: int, num_interactions: int, num_sales: int):
        self.num_users = num_users
        self.products_per_user = products_per_user
        self.num_interactions = num_interactions
        self.num_sales = num_sales
        os.makedirs("data", exist_ok=True)

    def generate(self):
        print(f"--- Generating Dynamic Mock Data ---")
        print(
            f"Users: {self.num_users} | Products per user: {self.products_per_user} | B2B Edges: {self.num_interactions} | Sales: {self.num_sales}"
        )
        roles = ["business_owner", "general user"]
        business_types = ["retailer", "wholesaler", "distributor"]
        users = []

        for i in range(self.num_users):
            users.append(
                {
                    "profile_id": f"USER_{i}",
                    "username": f"user_{i}",
                    "email": f"store{i}@example.com",
                    "role": random.choice(roles),
                    "business_type": random.choice(business_types),
                    "b2b_verified": random.choice([True, False]),
                    "has_access_to_marketplace": True,
                    "associated_producers": [i],
                }
            )

        with open("data/user_profiles.json", "w") as f:
            json.dump(users, f, indent=4)
        categories = ["Steel", "Ceramics", "Hardware", "Cement", "Paint", "Electrical"]
        products = []
        product_id_counter = 0

        for u in range(self.num_users):
            for p in range(self.products_per_user):
                products.append(
                    {
                        "id": product_id_counter,
                        "seller_id": u,
                        "name": f"Product_{product_id_counter}",
                        "category": random.choice(categories),
                        "price": round(random.uniform(100, 15000), 2),
                        "stock": random.randint(10, 1000),
                    }
                )
                product_id_counter += 1

        with open("data/products_cache.json", "w") as f:
            json.dump(products, f, indent=4)
        interactions = []
        for i in range(self.num_interactions):
            initiator = random.randint(0, self.num_users - 1)
            target = random.randint(0, self.num_users - 1)
            while initiator == target:
                target = random.randint(0, self.num_users - 1)

            interactions.append(
                {
                    "id": i,
                    "initiator": initiator,
                    "target_business": target,
                    "interaction_type": random.choice(["view", "connect", "order"]),
                    "weight": random.choice([1.0, 3.0, 5.0]),
                }
            )

        with open("data/b2b_interactions_cache.json", "w") as f:
            json.dump(interactions, f, indent=4)
        eco_sales = []
        if products:
            for i in range(self.num_sales):
                buyer = random.randint(0, self.num_users - 1)
                product = random.choice(products)
                while buyer == product["seller_id"]:
                    buyer = random.randint(0, self.num_users - 1)

                eco_sales.append(
                    {
                        "id": i,
                        "buyer": buyer,
                        "seller": product["seller_id"],
                        "product": product["id"],
                        "quantity": random.randint(1, 50),
                        "payment_status": "online",
                        "shipping_cost": round(random.uniform(50, 500), 2),
                    }
                )

        with open("data/ecommerce_sales_cache.json", "w") as f:
            json.dump(eco_sales, f, indent=4)

        print(f" Success! Generated {self.num_users} users and {len(products)} total products.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Mock Graph Data via CLI")

    parser.add_argument("--users", type=int, default=10, help="Number of users to generate")
    parser.add_argument("--products", type=int, default=5, help="Number of products PER user")
    parser.add_argument("--interactions", type=int, default=20, help="Number of B2B edge connections")
    parser.add_argument("--sales", type=int, default=50, help="Number of E-commerce transactions")

    args = parser.parse_args()
    generator = MockGraphDataGenerator(
        num_users=args.users, products_per_user=args.products, num_interactions=args.interactions, num_sales=args.sales
    )
    generator.generate()
