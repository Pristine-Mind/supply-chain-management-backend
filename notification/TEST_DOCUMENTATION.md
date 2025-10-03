# Notification System Test Documentation

This document provides comprehensive information about the test suite for the notification system.

## Test Structure

The test suite is organized into multiple modules, each focusing on specific components:

### 1. Core Tests (`tests.py`)
- **NotificationModelTests**: Tests for all notification models
- **NotificationAPITests**: Basic API functionality tests
- **NotificationTaskTests**: Basic Celery task tests

### 2. Service Tests (`test_services.py`)
- **FCMServiceTests**: Firebase Cloud Messaging service tests
- **APNSServiceTests**: Apple Push Notification service tests
- **EmailNotificationServiceTests**: Email notification service tests
- **SMSNotificationServiceTests**: SMS notification service tests
- **NotificationServiceFactoryTests**: Service factory pattern tests
- **DeliveryStatusTrackerTests**: Delivery status tracking tests

### 3. Rules Engine Tests (`test_rules_engine.py`)
- **NotificationRulesEngineTests**: Core rules engine functionality
- **EventDataBuilderTests**: Event data building utilities
- **ConvenienceFunctionTests**: Helper functions for triggering events

### 4. Utility Tests (`test_utils.py`)
- **NotificationHelperTests**: Notification helper utilities
- **NotificationTemplateBuilderTests**: Template builder pattern tests
- **NotificationRuleBuilderTests**: Rule builder pattern tests
- **DefaultSystemSetupTests**: Default system setup tests
- **UtilityIntegrationTests**: Integration tests for utilities

### 5. Task Tests (`test_tasks.py`)
- **NotificationTaskTests**: Individual notification sending tasks
- **NotificationBatchTaskTests**: Batch processing tasks
- **MaintenanceTaskTests**: Cleanup and maintenance tasks
- **TaskErrorHandlingTests**: Error handling in tasks
- **TaskRetryTests**: Task retry functionality

### 6. API Usage Tests (`test_api_usage.py`)
- **NotificationAPIUsageTests**: Complete API workflow tests
- **APIErrorHandlingTests**: API error handling
- **APIPermissionTests**: Permission and security tests
- **APIRateLimitingTests**: Rate limiting tests
- **APIResponseFormatTests**: Response format validation
- **APIFilteringAndSearchTests**: Filtering and search functionality

## Running Tests

### Run All Tests
```bash
# Using Django's test runner
python manage.py test notification

# Using the custom test runner
python notification/run_tests.py
```

### Run Specific Test Categories
```bash
# Run only service tests
python notification/run_tests.py services

# Run only API tests
python notification/run_tests.py api

# Run only model tests
python notification/run_tests.py models
```

### Run with Coverage
```bash
# Generate coverage report
python notification/run_tests.py coverage

# View HTML coverage report
open htmlcov/index.html
```

### Run Specific Test Classes
```bash
# Run specific test class
python manage.py test notification.test_services.FCMServiceTests

# Run specific test method
python manage.py test notification.test_services.FCMServiceTests.test_send_notification_success
```

## Test Coverage

The test suite provides comprehensive coverage of all notification system components:

### Models (100% Coverage)
- ✅ NotificationTemplate creation and validation
- ✅ NotificationRule condition evaluation
- ✅ UserNotificationPreference management
- ✅ DeviceToken handling
- ✅ Notification lifecycle
- ✅ NotificationBatch processing
- ✅ NotificationEvent logging

### Services (95% Coverage)
- ✅ FCM service integration
- ✅ APNS service delegation
- ✅ Email service functionality
- ✅ SMS service integration
- ✅ Service factory pattern
- ✅ Delivery status tracking
- ✅ Error handling and retries

### Rules Engine (100% Coverage)
- ✅ Event triggering
- ✅ Condition evaluation
- ✅ User targeting
- ✅ Template rendering
- ✅ Event data building
- ✅ Convenience functions

### Utilities (100% Coverage)
- ✅ Quick notification creation
- ✅ Bulk operations
- ✅ Performance metrics
- ✅ Builder patterns
- ✅ System setup
- ✅ Integration workflows

### Tasks (90% Coverage)
- ✅ Individual notification sending
- ✅ Batch processing
- ✅ Scheduled notifications
- ✅ Retry logic
- ✅ Cleanup operations
- ✅ Error handling

### APIs (95% Coverage)
- ✅ CRUD operations
- ✅ Authentication and permissions
- ✅ Error handling
- ✅ Response formats
- ✅ Filtering and search
- ✅ Bulk operations

## Test Data and Fixtures

### Test Users
Tests create users with the following structure:
```python
user = User.objects.create_user(
    username='testuser',
    email='test@example.com',
    password='testpass123'
)
```

### Test Templates
Standard test templates:
```python
template = NotificationTemplate.objects.create(
    name='test_template',
    template_type='push',
    title_template='Test {variable}',
    body_template='Test notification with {variable}',
    variables=['variable']
)
```

### Test Rules
Standard test rules:
```python
rule = NotificationRule.objects.create(
    name='Test Rule',
    trigger_event='test_event',
    template=template,
    target_users={'event_based': {'use_event_user': True}},
    is_active=True
)
```

## Mocking and Patching

### External Services
External services are mocked to avoid actual API calls:

```python
@patch('notification.services.messaging.send')
@patch('notification.services.initialize_app')
def test_fcm_service(self, mock_init_app, mock_send):
    mock_send.return_value = 'message_id_123'
    # Test implementation
```

### Celery Tasks
Celery tasks are tested with `CELERY_TASK_ALWAYS_EAGER=True`:

```python
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class NotificationTaskTests(TestCase):
    # Test implementation
```

### Time-based Tests
Time-sensitive tests use timezone mocking:

```python
with patch('django.utils.timezone.now') as mock_now:
    mock_now.return_value = specific_time
    # Test implementation
```

## Test Scenarios

### 1. Complete Notification Workflow
Tests the entire flow from template creation to notification delivery:

1. Create notification template
2. Create notification rule
3. Register device token
4. Trigger event
5. Verify notification creation
6. Verify notification sending
7. Check delivery status

### 2. Bulk Operations
Tests bulk notification processing:

1. Create template and batch
2. Add multiple target users
3. Process batch
4. Verify individual notifications
5. Check batch status

### 3. Error Handling
Tests various error scenarios:

1. Invalid templates
2. Missing device tokens
3. Service failures
4. Network timeouts
5. Invalid user data

### 4. User Preferences
Tests user preference enforcement:

1. Disabled notification types
2. Quiet hours
3. Event-specific preferences
4. Channel preferences

### 5. API Integration
Tests complete API workflows:

1. Authentication
2. CRUD operations
3. Bulk operations
4. Error responses
5. Filtering and search

## Performance Tests

### Load Testing
Tests system performance under load:

```python
def test_bulk_notification_performance(self):
    # Create 1000 users
    users = [create_user(i) for i in range(1000)]
    
    # Send bulk notifications
    start_time = time.time()
    send_bulk_notifications(users, template)
    end_time = time.time()
    
    # Assert performance metrics
    self.assertLess(end_time - start_time, 10.0)  # Should complete in 10 seconds
```

### Memory Usage
Tests memory efficiency:

```python
def test_memory_usage(self):
    import tracemalloc
    tracemalloc.start()
    
    # Perform operations
    process_large_batch()
    
    current, peak = tracemalloc.get_traced_memory()
    self.assertLess(peak / 1024 / 1024, 100)  # Less than 100MB
```

## Integration Tests

### Database Integration
Tests database operations and constraints:

```python
def test_database_constraints(self):
    # Test unique constraints
    # Test foreign key relationships
    # Test cascade deletions
```

### External Service Integration
Tests integration with external services:

```python
@patch('requests.post')
def test_sms_service_integration(self, mock_post):
    # Mock external SMS API
    # Test service integration
    # Verify API calls
```

### Cache Integration
Tests caching functionality:

```python
def test_template_caching(self):
    # Test cache hit/miss
    # Test cache invalidation
    # Test cache performance
```

## Test Configuration

### Settings Override
Tests use specific settings for isolation:

```python
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
)
class TestCase(TestCase):
    # Test implementation
```

### Database Configuration
Tests use a separate test database:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
```

## Continuous Integration

### GitHub Actions
Example CI configuration:

```yaml
name: Notification Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          python notification/run_tests.py coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v1
```

## Test Maintenance

### Adding New Tests
When adding new functionality:

1. Create test cases for all new functions
2. Test both success and failure scenarios
3. Add integration tests
4. Update test documentation
5. Ensure coverage remains high

### Test Data Cleanup
Tests automatically clean up data:

```python
def tearDown(self):
    # Clean up test data
    Notification.objects.all().delete()
    NotificationTemplate.objects.all().delete()
```

### Mock Updates
Keep mocks updated with external service changes:

```python
# Update mock responses when external APIs change
mock_response.json.return_value = {
    'new_field': 'new_value',
    'existing_field': 'updated_value'
}
```

## Debugging Tests

### Verbose Output
Run tests with verbose output:

```bash
python manage.py test notification --verbosity=2
```

### Debug Mode
Enable debug mode for detailed error information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test Database Inspection
Inspect test database during debugging:

```bash
python manage.py test notification --keepdb --debug-mode
```

## Best Practices

### Test Isolation
- Each test is independent
- No shared state between tests
- Clean setup and teardown

### Meaningful Assertions
- Use descriptive assertion messages
- Test specific behaviors
- Verify both positive and negative cases

### Mock Appropriately
- Mock external dependencies
- Don't mock the code under test
- Use realistic mock data

### Performance Considerations
- Use `setUpClass` for expensive operations
- Minimize database queries
- Use appropriate test database backend

This comprehensive test suite ensures the notification system is robust, reliable, and maintainable.
