#!/usr/bin/env python
"""
Comprehensive test runner for the notification system

This script runs all test cases and provides detailed reporting.
"""
import os
import sys

import django
from django.conf import settings
from django.core.management import execute_from_command_line
from django.test.utils import get_runner


def run_notification_tests():
    """Run all notification system tests"""

    print("🚀 Running Notification System Test Suite")
    print("=" * 60)

    # Test modules to run
    test_modules = [
        "notification.tests",
        "notification.test_services",
        "notification.test_rules_engine",
        "notification.test_utils",
        "notification.test_tasks",
        "notification.test_api_usage",
    ]

    # Test categories
    test_categories = {
        "Models": [
            "NotificationModelTests",
            "NotificationTemplateTests",
            "NotificationRuleTests",
            "UserNotificationPreferenceTests",
            "DeviceTokenTests",
            "NotificationBatchTests",
        ],
        "Services": [
            "FCMServiceTests",
            "APNSServiceTests",
            "EmailNotificationServiceTests",
            "SMSNotificationServiceTests",
            "NotificationServiceFactoryTests",
            "DeliveryStatusTrackerTests",
        ],
        "Rules Engine": [
            "NotificationRulesEngineTests",
            "EventDataBuilderTests",
            "ConvenienceFunctionTests",
        ],
        "Utilities": [
            "NotificationHelperTests",
            "NotificationTemplateBuilderTests",
            "NotificationRuleBuilderTests",
            "DefaultSystemSetupTests",
            "UtilityIntegrationTests",
        ],
        "Tasks": [
            "NotificationTaskTests",
            "NotificationBatchTaskTests",
            "MaintenanceTaskTests",
            "TaskErrorHandlingTests",
            "TaskRetryTests",
        ],
        "API Usage": [
            "NotificationAPIUsageTests",
            "APIErrorHandlingTests",
            "APIPermissionTests",
            "APIRateLimitingTests",
            "APIResponseFormatTests",
            "APIFilteringAndSearchTests",
        ],
    }

    print("📋 Test Categories:")
    for category, tests in test_categories.items():
        print(f"  {category}: {len(tests)} test classes")

    print(f"\n📦 Total Test Modules: {len(test_modules)}")
    print(f"🧪 Total Test Classes: {sum(len(tests) for tests in test_categories.values())}")

    print("\n" + "=" * 60)
    print("🏃 Starting Test Execution...")
    print("=" * 60)

    # Run tests with verbose output
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

    # Test command arguments
    test_args = [
        "manage.py",
        "test",
        "--verbosity=2",
        "--keepdb",  # Keep test database for faster subsequent runs
        "--parallel",  # Run tests in parallel
    ] + test_modules

    try:
        execute_from_command_line(test_args)
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("=" * 60)

    except SystemExit as e:
        if e.code == 0:
            print("\n" + "=" * 60)
            print("✅ All tests passed!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("❌ Some tests failed!")
            print("=" * 60)
            sys.exit(e.code)

    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        sys.exit(1)


def run_specific_test_category(category):
    """Run tests for a specific category"""

    category_mapping = {
        "models": "notification.tests.NotificationModelTests",
        "services": "notification.test_services",
        "rules": "notification.test_rules_engine",
        "utils": "notification.test_utils",
        "tasks": "notification.test_tasks",
        "api": "notification.test_api_usage",
    }

    if category.lower() not in category_mapping:
        print(f"❌ Unknown category: {category}")
        print(f"Available categories: {', '.join(category_mapping.keys())}")
        sys.exit(1)

    test_module = category_mapping[category.lower()]

    print(f"🚀 Running {category.title()} Tests")
    print("=" * 40)

    test_args = ["manage.py", "test", "--verbosity=2", "--keepdb", test_module]

    execute_from_command_line(test_args)


def run_coverage_report():
    """Run tests with coverage reporting"""

    print("📊 Running Tests with Coverage Report")
    print("=" * 50)

    try:
        import coverage
    except ImportError:
        print("❌ Coverage package not installed. Install with: pip install coverage")
        sys.exit(1)

    # Start coverage
    cov = coverage.Coverage(source=["notification"])
    cov.start()

    # Run tests
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

    test_args = [
        "manage.py",
        "test",
        "notification",
        "--verbosity=1",
        "--keepdb",
    ]

    try:
        execute_from_command_line(test_args)
    except SystemExit:
        pass

    # Stop coverage and generate report
    cov.stop()
    cov.save()

    print("\n" + "=" * 50)
    print("📊 Coverage Report")
    print("=" * 50)

    cov.report()

    # Generate HTML report
    cov.html_report(directory="htmlcov")
    print(f"\n📄 HTML coverage report generated in 'htmlcov' directory")


def main():
    """Main function to handle command line arguments"""

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "coverage":
            run_coverage_report()
        elif command in ["models", "services", "rules", "utils", "tasks", "api"]:
            run_specific_test_category(command)
        elif command == "help":
            print_help()
        else:
            print(f"❌ Unknown command: {command}")
            print_help()
            sys.exit(1)
    else:
        run_notification_tests()


def print_help():
    """Print help information"""

    print("🧪 Notification System Test Runner")
    print("=" * 40)
    print("Usage: python run_tests.py [command]")
    print()
    print("Commands:")
    print("  (no command)  Run all tests")
    print("  models        Run model tests only")
    print("  services      Run service tests only")
    print("  rules         Run rules engine tests only")
    print("  utils         Run utility tests only")
    print("  tasks         Run task tests only")
    print("  api           Run API tests only")
    print("  coverage      Run tests with coverage report")
    print("  help          Show this help message")
    print()
    print("Examples:")
    print("  python run_tests.py")
    print("  python run_tests.py services")
    print("  python run_tests.py coverage")


if __name__ == "__main__":
    main()
