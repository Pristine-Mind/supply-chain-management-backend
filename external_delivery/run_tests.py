#!/usr/bin/env python
"""
Comprehensive test runner for external delivery system
"""
import os
import subprocess
import sys
from pathlib import Path

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")
django.setup()


def run_tests():
    """Run all external delivery tests"""

    print("🚀 Running External Delivery System Tests")
    print("=" * 60)

    # Test modules to run
    test_modules = [
        "external_delivery.tests",
        "external_delivery.test_webhooks",
        "external_delivery.test_middleware",
    ]

    # Test categories
    test_categories = {
        "Models & Core Logic": [
            "external_delivery.tests.ExternalBusinessModelTest",
            "external_delivery.tests.ExternalDeliveryModelTest",
        ],
        "Authentication System": [
            "external_delivery.tests.ExternalBusinessAuthenticationTest",
            "external_delivery.tests.APIKeyAuthenticationTest",
            "external_delivery.tests.MixedAuthenticationTest",
        ],
        "API Endpoints": [
            "external_delivery.tests.ExternalBusinessAPITest",
            "external_delivery.tests.ExternalDeliveryAPITest",
        ],
        "Webhook System": [
            "external_delivery.test_webhooks.WebhookUtilsTest",
            "external_delivery.test_webhooks.WebhookLoggingTest",
            "external_delivery.test_webhooks.WebhookAPITest",
            "external_delivery.test_webhooks.WebhookSecurityTest",
            "external_delivery.test_webhooks.WebhookIntegrationTest",
        ],
        "Middleware & Permissions": [
            "external_delivery.test_middleware.ExternalAPIAuthenticationTest",
            "external_delivery.test_middleware.ExternalAPIMiddlewareTest",
            "external_delivery.test_middleware.RateLimitMiddlewareTest",
            "external_delivery.test_middleware.ExternalBusinessOwnerPermissionTest",
            "external_delivery.test_middleware.InternalStaffPermissionTest",
            "external_delivery.test_middleware.PermissionIntegrationTest",
        ],
        "Business Logic & Validation": [
            "external_delivery.tests.ExternalDeliveryValidationTest",
        ],
    }

    # Run all tests
    print("\n📋 Running All Tests...")
    result = subprocess.run(["python", "manage.py", "test"] + test_modules, capture_output=True, text=True)

    if result.returncode == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
        print(result.stdout)
        print(result.stderr)

    # Run tests by category for detailed reporting
    print("\n📊 Detailed Test Results by Category:")
    print("-" * 60)

    overall_success = True

    for category, tests in test_categories.items():
        print(f"\n🧪 {category}")
        print("-" * 40)

        category_success = True

        for test in tests:
            result = subprocess.run(["python", "manage.py", "test", test, "-v", "2"], capture_output=True, text=True)

            if result.returncode == 0:
                print(f"   ✅ {test.split('.')[-1]}")
            else:
                print(f"   ❌ {test.split('.')[-1]}")
                print(f"      Error: {result.stderr.strip()}")
                category_success = False
                overall_success = False

        if category_success:
            print(f"   🎉 All {category} tests passed!")
        else:
            print(f"   ⚠️  Some {category} tests failed!")

    # Coverage report
    print("\n📈 Generating Coverage Report...")
    coverage_result = subprocess.run(
        ["coverage", "run", "--source=external_delivery", "manage.py", "test"] + test_modules, capture_output=True, text=True
    )

    if coverage_result.returncode == 0:
        # Generate coverage report
        coverage_report = subprocess.run(
            ["coverage", "report", "--include=external_delivery/*"], capture_output=True, text=True
        )

        print(coverage_report.stdout)

        # Generate HTML coverage report
        subprocess.run(["coverage", "html", "--include=external_delivery/*"], capture_output=True, text=True)

        print("📄 HTML coverage report generated in htmlcov/")

    # Test summary
    print("\n" + "=" * 60)
    if overall_success:
        print("🎊 ALL TESTS PASSED! External Delivery System is ready!")
    else:
        print("🚨 SOME TESTS FAILED! Please review the errors above.")
    print("=" * 60)

    return overall_success


def run_specific_tests():
    """Run specific test categories"""

    categories = {
        "1": (
            "Authentication Tests",
            [
                "external_delivery.tests.ExternalBusinessAuthenticationTest",
                "external_delivery.tests.APIKeyAuthenticationTest",
                "external_delivery.tests.MixedAuthenticationTest",
            ],
        ),
        "2": (
            "Webhook Tests",
            [
                "external_delivery.test_webhooks.WebhookUtilsTest",
                "external_delivery.test_webhooks.WebhookLoggingTest",
                "external_delivery.test_webhooks.WebhookAPITest",
                "external_delivery.test_webhooks.WebhookSecurityTest",
            ],
        ),
        "3": (
            "Middleware Tests",
            [
                "external_delivery.test_middleware.ExternalAPIAuthenticationTest",
                "external_delivery.test_middleware.ExternalAPIMiddlewareTest",
                "external_delivery.test_middleware.RateLimitMiddlewareTest",
            ],
        ),
        "4": (
            "API Tests",
            [
                "external_delivery.tests.ExternalBusinessAPITest",
                "external_delivery.tests.ExternalDeliveryAPITest",
            ],
        ),
        "5": (
            "Model Tests",
            [
                "external_delivery.tests.ExternalBusinessModelTest",
                "external_delivery.tests.ExternalDeliveryModelTest",
            ],
        ),
    }

    print("🧪 Select Test Category to Run:")
    for key, (name, _) in categories.items():
        print(f"  {key}. {name}")
    print("  0. Run All Tests")

    choice = input("\nEnter your choice (0-5): ").strip()

    if choice == "0":
        return run_tests()
    elif choice in categories:
        name, tests = categories[choice]
        print(f"\n🚀 Running {name}...")

        result = subprocess.run(["python", "manage.py", "test", "-v", "2"] + tests, capture_output=True, text=True)

        print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode == 0:
            print(f"✅ All {name} passed!")
            return True
        else:
            print(f"❌ Some {name} failed!")
            return False
    else:
        print("❌ Invalid choice!")
        return False


def check_test_dependencies():
    """Check if all test dependencies are installed"""

    dependencies = [
        "coverage",
        "django",
        "djangorestframework",
        "djangorestframework-simplejwt",
    ]

    print("🔍 Checking test dependencies...")

    missing = []
    for dep in dependencies:
        try:
            __import__(dep.replace("-", "_"))
        except ImportError:
            missing.append(dep)

    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("📦 Install with: pip install " + " ".join(missing))
        return False
    else:
        print("✅ All test dependencies are installed!")
        return True


def main():
    """Main test runner function"""

    print("🏗️  External Delivery System Test Runner")
    print("=" * 50)

    # Check dependencies
    if not check_test_dependencies():
        return

    # Check if we're in the right directory
    if not Path("external_delivery").exists():
        print("❌ Run this script from the project root directory!")
        return

    # Interactive mode
    if len(sys.argv) > 1:
        # Command line mode
        if sys.argv[1] == "all":
            run_tests()
        elif sys.argv[1] == "auth":
            subprocess.run(
                [
                    "python",
                    "manage.py",
                    "test",
                    "external_delivery.tests.ExternalBusinessAuthenticationTest",
                    "external_delivery.tests.APIKeyAuthenticationTest",
                    "external_delivery.tests.MixedAuthenticationTest",
                    "-v",
                    "2",
                ]
            )
        elif sys.argv[1] == "webhooks":
            subprocess.run(["python", "manage.py", "test", "external_delivery.test_webhooks", "-v", "2"])
        elif sys.argv[1] == "middleware":
            subprocess.run(["python", "manage.py", "test", "external_delivery.test_middleware", "-v", "2"])
        else:
            print("Usage: python run_tests.py [all|auth|webhooks|middleware]")
    else:
        # Interactive mode
        run_specific_tests()


if __name__ == "__main__":
    main()
