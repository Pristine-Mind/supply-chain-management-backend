"""
Script to download brands and sample products from Excel sheets.
Extracts brand information and a few sample products with pricing from each brand's Excel file.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import openpyxl
import pandas as pd


class BrandProductDownloader:
    """Download and process brand and product data from Excel sheets."""

    def __init__(self, excel_dir: str, output_dir: str = "brand_downloads", samples_per_brand: int = 3):
        """
        Initialize the downloader.

        Args:
            excel_dir: Directory containing Excel files for each brand
            output_dir: Directory to save output files
            samples_per_brand: Number of sample products to extract per brand
        """
        self.excel_dir = Path(excel_dir)
        self.output_dir = Path(output_dir)
        self.samples_per_brand = samples_per_brand
        self.output_dir.mkdir(exist_ok=True)
        self.brands_data = []

    def load_excel_file(self, filepath: Path) -> Dict[str, Any]:
        """
        Load and extract data from Excel file.

        Args:
            filepath: Path to Excel file

        Returns:
            Dictionary containing brand name and product samples
        """
        try:
            # Use pandas to read Excel
            df = pd.read_excel(filepath)

            # Extract brand name from filename
            brand_name = filepath.stem

            # Clean column names
            df.columns = df.columns.str.strip().str.lower()

            # Find product name and price columns (common variations)
            product_col = None
            price_col = None

            for col in df.columns:
                if any(x in col for x in ["product", "name", "title"]):
                    product_col = col
                if any(x in col for x in ["price", "cost", "rate", "amount"]):
                    price_col = col

            # If columns not found by name, try first text column and a numeric column
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

            # Extract sample products
            samples = []
            if product_col and price_col:
                # Remove rows with missing values in key columns
                df_clean = df[[product_col, price_col]].dropna()

                # Get first N samples (non-duplicate)
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
            print(f"Error loading {filepath}: {str(e)}")
            return {
                "brand_name": filepath.stem,
                "file": filepath.name,
                "error": str(e),
                "samples": [],
            }

    def process_all_excel_files(self) -> List[Dict[str, Any]]:
        """
        Process all Excel files in the directory.

        Returns:
            List of brand data dictionaries
        """
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

    def save_json_output(self) -> str:
        """Save brand and product data as JSON."""
        output_file = self.output_dir / f"brands_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "total_brands": len(self.brands_data),
            "brands": self.brands_data,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\n✓ JSON saved to: {output_file}")
        return str(output_file)

    def save_csv_output(self) -> str:
        """Save brand and product data as CSV."""
        output_file = self.output_dir / f"brands_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        rows = []
        for brand_data in self.brands_data:
            brand_name = brand_data.get("brand_name", "Unknown")
            for idx, sample in enumerate(brand_data.get("samples", []), 1):
                rows.append(
                    {
                        "brand": brand_name,
                        "product_name": sample.get("product_name", ""),
                        "price": sample.get("price", 0.0),
                        "sample_number": idx,
                        "total_in_brand": brand_data.get("total_products", 0),
                    }
                )

        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)
        print(f"✓ CSV saved to: {output_file}")
        return str(output_file)

    def save_html_output(self) -> str:
        """Save brand and product data as HTML."""
        output_file = self.output_dir / f"brands_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        html = (
            """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Brands & Products Report</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
                h1 { color: #333; text-align: center; }
                .brand-section { background: white; margin: 20px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                .brand-name { font-size: 1.5em; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }
                .brand-info { color: #666; font-size: 0.9em; margin-bottom: 10px; }
                table { width: 100%; border-collapse: collapse; margin-top: 10px; }
                th { background-color: #3498db; color: white; padding: 10px; text-align: left; }
                td { padding: 8px; border-bottom: 1px solid #ddd; }
                tr:hover { background-color: #f9f9f9; }
                .price { font-weight: bold; color: #27ae60; }
                .footer { text-align: center; color: #999; margin-top: 30px; font-size: 0.9em; }
            </style>
        </head>
        <body>
            <h1>Brands & Product Samples Report</h1>
            <p style="text-align: center; color: #666;">Generated on: """
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + """</p>
        """
        )

        for brand_data in self.brands_data:
            brand_name = brand_data.get("brand_name", "Unknown")
            total_products = brand_data.get("total_products", 0)
            samples = brand_data.get("samples", [])

            html += f"""
            <div class="brand-section">
                <div class="brand-name">{brand_name}</div>
                <div class="brand-info">File: {brand_data.get('file')} | Total Products in Excel: {total_products} | Samples Extracted: {len(samples)}</div>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Product Name</th>
                            <th class="price">Price</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for idx, sample in enumerate(samples, 1):
                product_name = sample.get("product_name", "")
                price = sample.get("price", 0.0)
                html += f"""
                        <tr>
                            <td>{idx}</td>
                            <td>{product_name}</td>
                            <td class="price">${price:.2f}</td>
                        </tr>
                """

            html += """
                    </tbody>
                </table>
            </div>
            """

        html += """
            <div class="footer">
                <p>This report contains sample products extracted from brand Excel files.</p>
            </div>
        </body>
        </html>
        """

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"✓ HTML saved to: {output_file}")
        return str(output_file)

    def print_summary(self):
        """Print summary of downloaded data."""
        print("\n" + "=" * 60)
        print("BRANDS & PRODUCTS SUMMARY")
        print("=" * 60)

        total_samples = sum(len(b.get("samples", [])) for b in self.brands_data)

        print(f"\nTotal Brands: {len(self.brands_data)}")
        print(f"Total Sample Products: {total_samples}")
        print(f"Samples per Brand: {self.samples_per_brand}")

        print("\n" + "-" * 60)
        print("BRAND DETAILS:")
        print("-" * 60)

        for brand_data in self.brands_data:
            brand_name = brand_data.get("brand_name", "Unknown")
            samples = brand_data.get("samples", [])

            if brand_data.get("error"):
                print(f"\n❌ {brand_name}")
                print(f"   Error: {brand_data.get('error')}")
            else:
                print(f"\n✓ {brand_name}")
                print(f"   Total Products in Excel: {brand_data.get('total_products', 0)}")
                print(f"   Samples Extracted: {len(samples)}")

                if samples:
                    print("   Sample Products:")
                    for idx, sample in enumerate(samples, 1):
                        print(f"     {idx}. {sample.get('product_name', '')} - ${sample.get('price', 0.0):.2f}")

        print("\n" + "=" * 60)


def main():
    """Main function to run the brand product downloader."""
    # Configuration
    excel_directory = "./producer"  # Directory containing Excel files
    samples_per_brand = 3  # Number of samples to extract per brand

    # Initialize downloader
    downloader = BrandProductDownloader(excel_dir=excel_directory, samples_per_brand=samples_per_brand)

    # Process all Excel files
    downloader.process_all_excel_files()

    # Save outputs in multiple formats
    downloader.save_json_output()
    downloader.save_csv_output()
    downloader.save_html_output()

    # Print summary
    downloader.print_summary()


if __name__ == "__main__":
    main()
