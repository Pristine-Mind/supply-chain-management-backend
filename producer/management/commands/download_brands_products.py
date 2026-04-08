"""
Django management command to download brands and sample products from Excel sheets.
Usage: python manage.py download_brands_products --samples 5 --format json
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Download brands and sample products from Excel files with pricing information"

    def add_arguments(self, parser):
        parser.add_argument(
            "--samples", type=int, default=3, help="Number of sample products to extract per brand (default: 3)"
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["json", "csv", "html", "all"],
            default="all",
            help="Output format: json, csv, html, or all (default: all)",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="brand_downloads",
            help="Output directory for downloaded files (default: brand_downloads)",
        )

    def handle(self, *args, **options):
        samples_per_brand = options["samples"]
        output_format = options["format"]
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(exist_ok=True)

        # Get the producer app directory
        producer_app_dir = Path(__file__).parent.parent.parent
        excel_dir = producer_app_dir

        excel_files = list(excel_dir.glob("*.xlsx")) + list(excel_dir.glob("*.xls"))

        if not excel_files:
            self.stdout.write(self.style.ERROR(f"No Excel files found in {excel_dir}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(excel_files)} Excel files. Processing..."))

        brands_data = []

        for filepath in excel_files:
            self.stdout.write(f"  Processing {filepath.name}...", ending=" ")
            try:
                df = pd.read_excel(filepath)
                brand_name = filepath.stem

                # Clean column names
                df.columns = df.columns.str.strip().str.lower()

                # Find product name and price columns
                product_col = None
                price_col = None

                for col in df.columns:
                    if any(x in col for x in ["product", "name", "title"]):
                        product_col = col
                    if any(x in col for x in ["price", "cost", "rate", "amount"]):
                        price_col = col

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

                    for idx, row in df_unique.head(samples_per_brand).iterrows():
                        samples.append(
                            {
                                "product_name": str(row[product_col]).strip(),
                                "price": float(row[price_col]) if pd.notna(row[price_col]) else 0.0,
                            }
                        )

                brand_data = {
                    "brand_name": brand_name,
                    "file": filepath.name,
                    "total_products": len(df),
                    "samples": samples,
                    "sampled_count": len(samples),
                }
                brands_data.append(brand_data)
                self.stdout.write(self.style.SUCCESS(f"✓ ({len(samples)} samples)"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ Error: {str(e)}"))

        # Save outputs
        if output_format in ["json", "all"]:
            self._save_json(brands_data, output_dir)

        if output_format in ["csv", "all"]:
            self._save_csv(brands_data, output_dir)

        if output_format in ["html", "all"]:
            self._save_html(brands_data, output_dir)

        # Print summary
        self._print_summary(brands_data)

    def _save_json(self, brands_data, output_dir):
        """Save as JSON"""
        output_file = output_dir / f"brands_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "total_brands": len(brands_data),
            "brands": brands_data,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(f"✓ JSON saved to: {output_file}"))

    def _save_csv(self, brands_data, output_dir):
        """Save as CSV"""
        output_file = output_dir / f"brands_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        rows = []
        for brand_data in brands_data:
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
        self.stdout.write(self.style.SUCCESS(f"✓ CSV saved to: {output_file}"))

    def _save_html(self, brands_data, output_dir):
        """Save as HTML"""
        output_file = output_dir / f"brands_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Brands & Products Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                h1 {{ color: #333; text-align: center; }}
                .brand-section {{ background: white; margin: 20px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .brand-name {{ font-size: 1.5em; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
                .brand-info {{ color: #666; font-size: 0.9em; margin-bottom: 10px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th {{ background-color: #3498db; color: white; padding: 10px; text-align: left; }}
                td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background-color: #f9f9f9; }}
                .price {{ font-weight: bold; color: #27ae60; }}
                .footer {{ text-align: center; color: #999; margin-top: 30px; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <h1>Brands & Product Samples Report</h1>
            <p style="text-align: center; color: #666;">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """

        for brand_data in brands_data:
            brand_name = brand_data.get("brand_name", "Unknown")
            total_products = brand_data.get("total_products", 0)
            samples = brand_data.get("samples", [])

            html += f"""
            <div class="brand-section">
                <div class="brand-name">{brand_name}</div>
                <div class="brand-info">File: {brand_data.get('file')} | Total Products: {total_products} | Samples: {len(samples)}</div>
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

        self.stdout.write(self.style.SUCCESS(f"✓ HTML saved to: {output_file}"))

    def _print_summary(self, brands_data):
        """Print summary of downloaded data"""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("BRANDS & PRODUCTS SUMMARY"))
        self.stdout.write("=" * 60)

        total_samples = sum(len(b.get("samples", [])) for b in brands_data)

        self.stdout.write(f"\nTotal Brands: {len(brands_data)}")
        self.stdout.write(f"Total Sample Products: {total_samples}")

        self.stdout.write("\n" + "-" * 60)

        for brand_data in brands_data:
            brand_name = brand_data.get("brand_name", "Unknown")
            samples = brand_data.get("samples", [])

            self.stdout.write(f"\n{brand_name}")
            self.stdout.write(f"  Total Products: {brand_data.get('total_products', 0)}")
            self.stdout.write(f"  Samples: {len(samples)}")

            if samples:
                for idx, sample in enumerate(samples, 1):
                    self.stdout.write(f"    {idx}. {sample.get('product_name', '')} - ${sample.get('price', 0.0):.2f}")

        self.stdout.write("\n" + "=" * 60)
