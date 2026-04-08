"""
Advanced Brand Products Downloader - Extended Features
Includes filtering, export options, and data analysis capabilities.
"""

import json
import os
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


class AdvancedBrandProductDownloader:
    """Advanced downloader with filtering and analysis capabilities."""

    def __init__(self, excel_dir: str, output_dir: str = "brand_downloads", samples_per_brand: int = 3):
        """Initialize the advanced downloader."""
        self.excel_dir = Path(excel_dir)
        self.output_dir = Path(output_dir)
        self.samples_per_brand = samples_per_brand
        self.output_dir.mkdir(exist_ok=True)
        self.brands_data = []

    def load_excel_file(self, filepath: Path) -> Dict[str, Any]:
        """Load and extract data from Excel file."""
        try:
            df = pd.read_excel(filepath)
            brand_name = filepath.stem
            df.columns = df.columns.str.strip().str.lower()

            # Column detection
            product_col = None
            price_col = None
            qty_col = None

            for col in df.columns:
                if any(x in col for x in ["product", "name", "title", "item"]):
                    product_col = col
                if any(x in col for x in ["price", "cost", "rate", "amount"]):
                    price_col = col
                if any(x in col for x in ["qty", "quantity", "stock", "units"]):
                    qty_col = col

            if product_col is None:
                for col in df.columns:
                    if df[col].dtype == "object":
                        product_col = col
                        break

            if price_col is None:
                for col in df.columns:
                    if df[col].dtype in ["float64", "int64"]:
                        price_col = col
                        break

            samples = []
            if product_col and price_col:
                df_clean = df[[product_col, price_col]].dropna()
                df_unique = df_clean.drop_duplicates(subset=[product_col])

                for idx, row in df_unique.head(self.samples_per_brand).iterrows():
                    samples.append(
                        {
                            "product_name": str(row[product_col]).strip(),
                            "price": float(row[price_col]) if pd.notna(row[price_col]) else 0.0,
                        }
                    )

            return {
                "brand_name": brand_name,
                "file": filepath.name,
                "total_products": len(df),
                "samples": samples,
                "sampled_count": len(samples),
            }

        except Exception as e:
            return {
                "brand_name": filepath.stem,
                "file": filepath.name,
                "error": str(e),
                "samples": [],
            }

    def process_all_excel_files(self) -> List[Dict[str, Any]]:
        """Process all Excel files."""
        excel_files = list(self.excel_dir.glob("*.xlsx")) + list(self.excel_dir.glob("*.xls"))

        if not excel_files:
            print(f"No Excel files found in {self.excel_dir}")
            return []

        print(f"Found {len(excel_files)} Excel files. Processing...")

        for filepath in excel_files:
            print(f"  Processing {filepath.name}...", end=" ")
            brand_data = self.load_excel_file(filepath)
            self.brands_data.append(brand_data)
            print(f"({len(brand_data.get('samples', []))} samples)")

        return self.brands_data

    def filter_by_price_range(self, min_price: float = 0, max_price: float = float("inf")) -> List[Dict[str, Any]]:
        """Filter products by price range."""
        filtered_brands = []

        for brand_data in self.brands_data:
            filtered_samples = [s for s in brand_data.get("samples", []) if min_price <= s["price"] <= max_price]

            if filtered_samples:
                filtered_brands.append({**brand_data, "samples": filtered_samples, "sampled_count": len(filtered_samples)})

        return filtered_brands

    def filter_by_brand(self, brand_names: List[str]) -> List[Dict[str, Any]]:
        """Filter by specific brand names."""
        return [b for b in self.brands_data if b["brand_name"].lower() in [name.lower() for name in brand_names]]

    def get_price_statistics(self) -> Dict[str, float]:
        """Calculate price statistics across all products."""
        all_prices = []

        for brand_data in self.brands_data:
            for sample in brand_data.get("samples", []):
                all_prices.append(sample["price"])

        if not all_prices:
            return {}

        return {
            "min_price": min(all_prices),
            "max_price": max(all_prices),
            "average_price": statistics.mean(all_prices),
            "median_price": statistics.median(all_prices),
            "std_dev": statistics.stdev(all_prices) if len(all_prices) > 1 else 0,
            "total_products_sampled": len(all_prices),
        }

    def get_brand_analysis(self) -> Dict[str, Any]:
        """Get detailed analysis per brand."""
        analysis = {}

        for brand_data in self.brands_data:
            samples = brand_data.get("samples", [])
            prices = [s["price"] for s in samples]

            if prices:
                analysis[brand_data["brand_name"]] = {
                    "total_in_excel": brand_data.get("total_products", 0),
                    "samples_extracted": len(samples),
                    "price_range": {
                        "min": min(prices),
                        "max": max(prices),
                        "average": sum(prices) / len(prices),
                    },
                    "products": samples,
                }

        return analysis

    def export_filtered_json(self, filtered_brands: List[Dict], filename: Optional[str] = None) -> str:
        """Export filtered data as JSON."""
        if filename is None:
            filename = f"filtered_brands_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_file = self.output_dir / filename

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "total_brands": len(filtered_brands),
            "brands": filtered_brands,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Filtered JSON saved to: {output_file}")
        return str(output_file)

    def export_with_analysis(self) -> str:
        """Export data with analysis included."""
        output_file = self.output_dir / f"brands_with_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        analysis = self.get_brand_analysis()
        stats = self.get_price_statistics()

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_brands": len(self.brands_data),
                "total_samples": sum(len(b.get("samples", [])) for b in self.brands_data),
                "price_statistics": stats,
            },
            "brand_analysis": analysis,
            "raw_data": self.brands_data,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Analysis JSON saved to: {output_file}")
        return str(output_file)

    def print_analysis_report(self):
        """Print detailed analysis report."""
        print("\n" + "=" * 70)
        print("ADVANCED BRAND PRODUCTS ANALYSIS REPORT")
        print("=" * 70)

        # Overall statistics
        stats = self.get_price_statistics()
        print("\n📊 OVERALL PRICE STATISTICS:")
        print("-" * 70)
        print(f"  Total Brands: {len(self.brands_data)}")
        print(f"  Total Sample Products: {stats.get('total_products_sampled', 0)}")
        print(f"  Price Range: ${stats.get('min_price', 0):.2f} - ${stats.get('max_price', 0):.2f}")
        print(f"  Average Price: ${stats.get('average_price', 0):.2f}")
        print(f"  Median Price: ${stats.get('median_price', 0):.2f}")
        print(f"  Standard Deviation: ${stats.get('std_dev', 0):.2f}")

        # Brand analysis
        print("\n📈 BRAND-WISE ANALYSIS:")
        print("-" * 70)

        analysis = self.get_brand_analysis()
        for brand_name, brand_info in sorted(analysis.items()):
            print(f"\n{brand_name.upper()}")
            print(f"  Total Products in Excel: {brand_info['total_in_excel']}")
            print(f"  Samples Extracted: {brand_info['samples_extracted']}")
            print(f"  Price Range: ${brand_info['price_range']['min']:.2f} - ${brand_info['price_range']['max']:.2f}")
            print(f"  Average Price: ${brand_info['price_range']['average']:.2f}")

            if brand_info["products"]:
                print("  Sample Products:")
                for idx, product in enumerate(brand_info["products"], 1):
                    print(f"    {idx}. {product['product_name']} - ${product['price']:.2f}")

        print("\n" + "=" * 70)


def main():
    """Main function with example usage."""

    # Initialize downloader
    downloader = AdvancedBrandProductDownloader(excel_dir="./producer", samples_per_brand=3)

    # Process all files
    downloader.process_all_excel_files()

    # Export full data with analysis
    downloader.export_with_analysis()

    # Example: Filter by price range
    print("\n" + "=" * 70)
    print("EXAMPLE FILTERS:")
    print("=" * 70)

    # Get products under $50
    budget_brands = downloader.filter_by_price_range(min_price=0, max_price=50)
    print(f"\n📌 Products under $50: {sum(len(b.get('samples', [])) for b in budget_brands)} found")
    if budget_brands:
        downloader.export_filtered_json(budget_brands, "products_under_50.json")

    # Get premium products over $100
    premium_brands = downloader.filter_by_price_range(min_price=100)
    print(f"💎 Premium products over $100: {sum(len(b.get('samples', [])) for b in premium_brands)} found")
    if premium_brands:
        downloader.export_filtered_json(premium_brands, "premium_products_over_100.json")

    # Print analysis report
    downloader.print_analysis_report()


if __name__ == "__main__":
    main()
